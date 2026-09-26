"""FastAPI application factory.

The whole API lives under `/api/v1` (spec A13): a URL version prefix, additive-only
within a version, so a status or error code can change later without the
expand/contract dance `BACKWARD_COMPATIBILITY.md` otherwise demands.

**Authentication is applied by default, not opted into.** Routers other than the
public allow-list are included with `get_current_session` as a router-level
dependency, so a new endpoint is authenticated the moment it is written. The
failure mode of the opposite arrangement is an endpoint that silently ships
unauthenticated, which is exactly what R08 forbids.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from trip_planner.api import attachments, auth, health, inbox, items, stages, trips
from trip_planner.api.deps import get_current_session
from trip_planner.config import Settings, require_settings
from trip_planner.errors import ApiError, ErrorCode, error_body
from trip_planner.spa import mount_spa, static_dir

API_PREFIX = "/api/v1"

#: The dependency list every authenticated router is included with. Using one
#: shared list means a router cannot be added with a *weaker* set by accident.
AUTHENTICATED = [Depends(get_current_session)]

#: Paths reachable without a session. Everything else requires one.
#: The route-enumeration test in tests/test_route_protection.py reads this list,
#: so adding a route here is a deliberate, reviewable act.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        f"{API_PREFIX}/health",
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/auth/logout",
        # The one inbound path R10 permits. AWS SNS cannot hold a session or a
        # CSRF token, so this route proves its origin with a signature instead —
        # see `api/inbox.py`. It records that mail arrived and can do nothing
        # else: no MIME fetch, no attachment, no plan write.
        f"{API_PREFIX}/inbox/receipts/sns",
    }
)


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.field),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Answer validation failures in the project's error shape.

        FastAPI's default body is a list of Pydantic error dicts, which is a
        different contract from every other error this API returns and leaks the
        internal field paths.
        """
        field: str | None = None
        errors = exc.errors()
        if errors:
            location = [part for part in errors[0].get("loc", ()) if isinstance(part, str)]
            # loc starts with the source ("body", "query"); the field is what follows.
            field = location[-1] if len(location) > 1 else None

        return JSONResponse(
            status_code=422,
            content=error_body(ErrorCode.VALIDATION_ERROR, field),
        )

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)

        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.VALIDATION_ERROR
        return JSONResponse(status_code=exc.status_code, content=error_body(code))

    @app.exception_handler(OperationalError)
    def handle_database_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
        """A dead database is a 503, never an empty payload.

        An empty timeline is indistinguishable from a real empty trip and would be
        a lie about the plan.
        """
        return JSONResponse(status_code=503, content=error_body(ErrorCode.SERVICE_UNAVAILABLE))


def _inbox_lifespan(settings: Settings):
    """Run the inbox ingestion loop for the life of the application.

    **Only the deployed entry point installs this.** A lifespan that started a
    thread would otherwise run in every test that constructs an app, against
    whichever database the environment happened to name — so the worker is
    opt-in at construction and `tests/test_scheduler.py` drives `run_once`
    directly instead, which is the part with behaviour worth asserting.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from trip_planner.scheduler import start_inbox_worker

        worker = start_inbox_worker(settings)
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    return lifespan


def create_app(
    *, check_configuration: bool = True, settings: Settings | None = None
) -> FastAPI:
    """Build the application.

    `check_configuration` exists only for tests that construct an app while
    injecting settings; the deployed entry point always validates, and a missing
    variable raises `MissingConfiguration` naming it rather than failing later
    with a confusing connection error.

    `settings`, when given, additionally installs the inbox worker's lifespan —
    so a deployment with the inbox configured runs the loop and one without it
    runs nothing at all, with no thread and no AWS client.
    """
    if check_configuration:
        require_settings()

    app = FastAPI(
        title="Smart Trip Planner",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=_inbox_lifespan(settings) if settings is not None else None,
    )

    _install_exception_handlers(app)

    # Public routers: no session dependency.
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    # The SNS receipt endpoint, deliberately public. Its path is on
    # PUBLIC_PATHS above and tests/test_route_protection.py fails if that list
    # grows by anything else.
    app.include_router(inbox.public_router, prefix=API_PREFIX)

    # Every later router is included with AUTHENTICATED, which applies the session
    # and CSRF checks to all of its routes at once. A router added without it is
    # caught by the route enumeration in tests/test_route_protection.py.
    app.include_router(trips.router, prefix=API_PREFIX, dependencies=AUTHENTICATED)
    app.include_router(items.router, prefix=API_PREFIX, dependencies=AUTHENTICATED)
    app.include_router(stages.router, prefix=API_PREFIX, dependencies=AUTHENTICATED)
    app.include_router(attachments.router, prefix=API_PREFIX, dependencies=AUTHENTICATED)

    # The built SPA, when present. Absent in development and in the test suite,
    # where the Vite dev server serves it instead.
    bundle = static_dir()
    if bundle is not None:
        mount_spa(app, API_PREFIX, bundle)

    return app


def create_production_app() -> FastAPI:
    """The deployed entry point. Validates configuration before serving anything."""
    settings = require_settings()
    return create_app(check_configuration=False, settings=settings)
