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

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from trip_planner.api import auth, health
from trip_planner.api.deps import get_current_session
from trip_planner.errors import ApiError, ErrorCode, error_body

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


def create_app() -> FastAPI:
    app = FastAPI(title="Smart Trip Planner", version="0.1.0", docs_url=None, redoc_url=None)

    _install_exception_handlers(app)

    # Public routers: no session dependency.
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)

    # Every later router is included with AUTHENTICATED, which applies the session
    # and CSRF checks to all of its routes at once:
    #
    #   app.include_router(trips.router, prefix=API_PREFIX, dependencies=AUTHENTICATED)
    #
    # Phase 2 adds the first one.

    return app


app = create_app()
