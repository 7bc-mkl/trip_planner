"""The worker function's ASGI app: drain the inbox once per event.

On the Lambda target the in-process thread cannot run — Lambda freezes the
environment between requests — so the same image runs a second function whose
only job is draining the inbox. The Lambda Web Adapter forwards every non-HTTP
event (the web function's asynchronous "kick", or the EventBridge schedule) as a
`POST` to its pass-through path, `/events`. Any event means "drain"; the body is
not read.

**A separate app, not a route on the web app.** The web function's Function URL
is public, so a drain endpoint there would be a new unauthenticated route. Here
the app has no public API at all — only `/events` and the health route the
adapter's readiness check polls — and the function serving it has no URL.

**A time budget, not one batch.** One event loops `InboxWorker.run_once()` until
a pass processes nothing or the budget is spent, so a single kick drains a
backlog larger than `BATCH_SIZE`. The budget is also checked between messages
inside a pass, so ten slow model calls cannot run past Lambda's five-minute
timeout. A single tick of the thread loop is exactly one `run_once()` — the
cleanup pass runs inside it — so each pass here does everything a tick does.

Run as `uvicorn trip_planner.worker_app:create_worker_app --factory`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import timedelta

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from trip_planner.api import health
from trip_planner.app import API_PREFIX, _install_exception_handlers
from trip_planner.config import Settings, require_settings
from trip_planner.inbound.ses import S3Fetcher
from trip_planner.integrations.model import ModelClient
from trip_planner.scheduler import InboxWorker

logger = logging.getLogger(__name__)

__all__ = ["EVENTS_PATH", "WORKER_BUDGET", "DrainSummary", "create_worker_app", "drain"]

#: The Lambda Web Adapter's default pass-through path for non-HTTP events.
EVENTS_PATH = "/events"

#: How long one event may spend draining. A minute under the function's
#: five-minute timeout, which leaves room for the message in flight when the
#: budget runs out and for the cleanup that ends every pass.
WORKER_BUDGET = timedelta(minutes=4)


class DrainSummary(BaseModel):
    processed: int
    budget_exhausted: bool


def drain(
    worker: InboxWorker,
    *,
    clock: Callable[[], float] = time.monotonic,
    budget: timedelta = WORKER_BUDGET,
) -> DrainSummary:
    """Run passes until one processes nothing or the budget is spent."""
    deadline = clock() + budget.total_seconds()

    def within_budget() -> bool:
        return clock() < deadline

    processed = 0
    while within_budget():
        count = worker.run_once(should_continue=within_budget)
        processed += count
        if count == 0:
            break

    return DrainSummary(processed=processed, budget_exhausted=not within_budget())


def create_worker_app(
    *,
    settings: Settings | None = None,
    session_factory: Callable[[], OrmSession] | None = None,
    fetcher: S3Fetcher | None = None,
    model_client: ModelClient | None = None,
    clock: Callable[[], float] = time.monotonic,
    budget: timedelta = WORKER_BUDGET,
) -> FastAPI:
    """Build the worker app. Called with no arguments by `uvicorn --factory`.

    Configuration is validated here, before serving anything, exactly as the web
    app's entry point does. The keyword arguments exist for the tests.
    """
    if settings is None:
        settings = require_settings()

    worker: InboxWorker | None = None
    if settings.inbox is not None:
        if session_factory is None:
            from trip_planner.db.session import get_sessionmaker

            session_factory = get_sessionmaker()
        worker = InboxWorker(
            settings, session_factory, fetcher=fetcher, model_client=model_client
        )

    app = FastAPI(
        title="Smart Trip Planner worker",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    _install_exception_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)

    @app.post(EVENTS_PATH)
    def handle_event() -> DrainSummary:
        if worker is None:
            # No inbox on this deployment: nothing to drain, and not an error.
            return DrainSummary(processed=0, budget_exhausted=False)
        summary = drain(worker, clock=clock, budget=budget)
        logger.info(
            "inbox: worker event processed %d message(s)%s",
            summary.processed,
            "; budget spent" if summary.budget_exhausted else "",
        )
        return summary

    return app
