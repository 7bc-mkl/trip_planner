"""FastAPI application factory.

The whole API lives under `/api/v1` (spec A13): a URL version prefix, additive-only
within a version, so a status or error code can change later without the
expand/contract dance `BACKWARD_COMPATIBILITY.md` otherwise demands.
"""

from fastapi import FastAPI

from trip_planner.api import health

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(title="Smart Trip Planner", version="0.1.0", docs_url=None, redoc_url=None)
    app.include_router(health.router, prefix=API_PREFIX)
    return app


app = create_app()
