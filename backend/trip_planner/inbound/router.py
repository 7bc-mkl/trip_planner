"""Pointing a stored message at a trip — where the deterministic half meets the model.

The order here is the whole design, and every step of it exists to make the
model's involvement as small as it can be:

1. **The candidates are computed first, in code.** `domain/routing.py` extracts
   travel dates and narrows the owner's trips. This costs nothing and needs
   nobody's permission.
2. **Zero candidates never reaches a provider.** No dates, or dates no trip
   covers, is an *answer* — the message goes to the unrouted queue with a reason
   naming the dates it found. Not sending is both free and the smallest possible
   disclosure.
3. **The budget is checked before anything leaves.**
4. **The egress row is committed, and only then is the call made.** A timeout, a
   crash or a provider that never answers cannot erase the record that the
   owner's text may have left. This is the one ordering in this module that is
   not negotiable.
5. **The answer is fenced.** A trip id outside the candidate set was refused by
   `integrations/model.py` before this module sees it.

**Nothing here writes to a plan.** Routing sets `inbound_message.trip_id` and
nothing else — the same single column hand placement sets. D21 still governs
every write into a trip, and `tests/test_inbox_boundary.py` asserts that no
module under `inbound/` so much as names `Item`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.config import ModelSettings
from trip_planner.db.models import (
    InboundMessage,
    InboundModelEgress,
    ModelBillingMonth,
    Owner,
    Trip,
)
from trip_planner.domain.routing import (
    CandidateTrip,
    TripWindow,
    extract_travel_dates,
    select_candidates,
)
from trip_planner.integrations.model import (
    ModelBudget,
    ModelCallFailed,
    ModelClient,
    ModelRefused,
    RoutingRequest,
    Usage,
)

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_ROUTING_ATTEMPTS",
    "RoutingOutcome",
    "month_spend",
    "route_message",
    "trip_windows_for",
]

#: How many transient model failures one message is given before it queues.
#:
#: Three, not the five ingestion gets. A failing provider is slower and costlier
#: to retry than a failing S3 read, and the fallback is better: an unrouted
#: message is a complete, readable message the owner places in two clicks, where
#: an un-ingested one has no body at all.
MAX_ROUTING_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class RoutingOutcome:
    """What routing decided, for the worker's log and for tests to assert on."""

    state: str
    reason: str | None = None
    reason_args: dict[str, str] | None = None
    trip_id: str | None = None
    #: Whether a provider was contacted at all. The tests that matter most in
    #: this module assert this is `False`.
    called_model: bool = False


def trip_windows_for(db: OrmSession, owner: Owner) -> list[TripWindow]:
    """The owner's trips, reduced to what routing may know about them.

    Reduced **here**, at the database boundary, rather than passed as ORM
    objects and narrowed later: `TripWindow` is the exact shape that may be
    shown to a provider (D24), so building it is the moment to decide what
    leaves, and a later refactor adding a column to `Trip` cannot widen it.
    """
    trips = db.execute(
        sa.select(Trip).where(Trip.owner_id == owner.id).order_by(Trip.start_date)
    ).scalars()

    return [
        TripWindow(
            id=str(trip.id),
            title=trip.title,
            start_date=trip.start_date,
            end_date=trip.end_date,
            # Departure and return are the destination names the spec permits.
            # Items, notes, confirmation numbers and costs are not here, and the
            # type has nowhere to put them.
            destinations=tuple(
                place for place in (trip.departure_place, trip.return_place) if place
            ),
        )
        for trip in trips
    ]


def month_spend(db: OrmSession, *, now: datetime) -> Decimal | None:
    """Already-priced spend, or unknown when an outbound call is unresolved."""
    month = now.astimezone(UTC).date().replace(day=1)
    ledger = db.get(ModelBillingMonth, month, populate_existing=True)
    if ledger is None:
        return Decimal(0)
    return None if ledger.unresolved_calls else ledger.spent


def route_message(
    db: OrmSession,
    message: InboundMessage,
    *,
    owner: Owner,
    model_settings: ModelSettings,
    client: ModelClient,
    budget: ModelBudget,
    now: datetime | None = None,
) -> RoutingOutcome:
    """Decide which trip a received message belongs to.

    Commits the audit and unknown-cost reservation before dispatch, and known
    usage before proposal validation. The caller commits the final placement.
    """
    moment = now or datetime.now(UTC)
    # Refresh under a row lock before dispatch; manual placement/deletion wins.
    current = db.scalar(
        sa.select(InboundMessage)
        .where(
            InboundMessage.id == message.id,
            InboundMessage.owner_id == owner.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None or current.state != "received" or current.trip_id is not None:
        return RoutingOutcome(state=current.state if current is not None else "discarded")

    dates = extract_travel_dates(message.text_body)
    candidates = select_candidates(dates, trip_windows_for(db, owner))

    if not candidates:
        # No provider is contacted. Zero candidates is an answer, and the reason
        # names what was found so the owner can see *why* rather than just that.
        reason, args = _no_candidate_reason(dates)
        return _queue(message, reason, args, called_model=False)

    if not budget.permits_a_call():
        # Stopped **before** the row is written and before anything leaves, so
        # no egress is recorded: nothing was attempted.
        logger.warning("inbox: routing skipped, the model budget does not permit a call")
        reason = (
            "routing_budget_exhausted"
            if budget.is_priced and budget.spent_this_month is not None
            else "routing_budget_unavailable"
        )
        return _defer(message, reason)

    # The point of no return. Committed first, so a crash in the next line still
    # leaves the owner able to see that his text may have gone to this provider.
    egress = InboundModelEgress(
        inbound_message_id=message.id,
        kind="text",
        provider=model_settings.provider,
        model=model_settings.model,
        attempted_at=moment,
    )
    month = moment.astimezone(UTC).date().replace(day=1)
    ledger = db.get(ModelBillingMonth, month)
    if ledger is None:
        ledger = ModelBillingMonth(month=month, spent=Decimal(0), unresolved_calls=0)
        db.add(ledger)
    ledger.unresolved_calls += 1
    db.add(egress)
    message.text_sent_at = message.text_sent_at or moment
    db.commit()

    request = RoutingRequest(
        text=message.text_body,
        from_address=message.from_address,
        subject=message.subject,
        sent_at=message.received_at.isoformat(),
        candidates=tuple(one.trip for one in candidates),
    )

    egress_id = egress.id
    message_id = message.id

    def record_usage(usage: Usage) -> None:
        # Commit accounting even if parsing the proposal fails, or the owner
        # deletes/places the message while the provider is answering.
        cost = budget.cost_of(usage)
        if cost is not None:
            ledger.spent += cost
            ledger.unresolved_calls -= 1
        audit = db.get(InboundModelEgress, egress_id, populate_existing=True)
        if audit is not None and usage.is_known:
            audit.input_tokens = usage.input_tokens
            audit.output_tokens = usage.output_tokens
        db.commit()

    failure: str | None = None
    proposal = None
    try:
        # The worker owns retries so every HTTP attempt has its own durable
        # audit and fresh budget check. Unknown usage stops the next dispatch.
        proposal, _ = replace(client, max_attempts=1).route(
            request,
            budget=budget,
            on_usage=record_usage,
        )
    except ModelRefused:
        failure = "routing_refused"
    except ModelCallFailed:
        failure = "routing_failed"

    current = db.scalar(
        sa.select(InboundMessage)
        .where(
            InboundMessage.id == message_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None or current.state != "received" or current.trip_id is not None:
        return RoutingOutcome(
            state=current.state if current is not None else "discarded", called_model=True
        )
    if failure == "routing_refused":
        return _queue(current, failure, None, called_model=True)
    if failure is not None:
        return _after_transient_failure(current)
    if proposal is None or proposal.trip_id is None:
        return _queue(current, "model_found_no_trip", None, called_model=True)
    return _route_to(current, proposal.trip_id, candidates)


def _route_to(
    message: InboundMessage, trip_id: str, candidates: tuple[CandidateTrip, ...]
) -> RoutingOutcome:
    """Set the one column routing is allowed to set."""
    chosen = next((one for one in candidates if one.trip.id == trip_id), None)
    if chosen is None:  # pragma: no cover - the client fences this already
        return _queue(message, "routing_refused", None, called_model=True)

    message.trip_id = uuid.UUID(trip_id)
    message.state = "routed"
    message.routing_reason = "routed_by_model"
    message.routing_reason_args = {"trip": chosen.trip.title}
    message.last_error = None
    return RoutingOutcome(
        state="routed",
        reason="routed_by_model",
        reason_args=message.routing_reason_args,
        trip_id=trip_id,
        called_model=True,
    )


def _no_candidate_reason(dates: tuple[date, ...]) -> tuple[str, dict[str, str] | None]:
    """Why nothing matched, specifically enough to act on.

    *"No trip covers 4–11 October"* tells the owner to check his dates; *"no
    dates found"* tells him the confirmation is one the extractor cannot read.
    They are different problems with different fixes, so they are different
    reasons.
    """
    if not dates:
        return "no_dates_found", None
    return "no_trip_covers_dates", {
        "from": min(dates).isoformat(),
        "to": max(dates).isoformat(),
    }


def _queue(
    message: InboundMessage,
    reason: str,
    args: dict[str, str] | None,
    *,
    called_model: bool,
) -> RoutingOutcome:
    """To the unrouted queue, with a reason the owner reads. Never a lost message.

    `called_model` is passed rather than assumed because the queue is reached
    both ways — before any provider is contacted (no candidates) and after one
    answered unusably. The tests that assert nothing left the deployment read
    this flag, so defaulting it either way would make it a comment rather than a
    fact.
    """
    message.state = "unrouted"
    message.routing_reason = reason
    message.routing_reason_args = args
    return RoutingOutcome(
        state="unrouted", reason=reason, reason_args=args, called_model=called_model
    )


def _defer(message: InboundMessage, reason: str) -> RoutingOutcome:
    """Left `received` and retried later. **Not** queued, and not a failure.

    A budget that will reset next month, or a configuration someone is still
    finishing, is a *not yet* — and a message parked in the unrouted queue over
    it would ask the owner to do by hand what the system is about to do for him.
    """
    message.last_error = reason
    message.routing_reason = reason
    message.routing_reason_args = None
    return RoutingOutcome(state="received", reason=reason, called_model=False)


def _after_transient_failure(message: InboundMessage) -> RoutingOutcome:
    """Count it, and queue it once the cap is reached.

    The message keeps its body and its documents throughout: a provider outage
    degrades to a queue the owner clears in two clicks per message, never to a
    broken page and never to lost mail.
    """
    message.attempts += 1
    message.last_error = "routing_failed"

    if message.attempts >= MAX_ROUTING_ATTEMPTS:
        return _queue(message, "routing_failed", None, called_model=True)

    return RoutingOutcome(state="received", reason="routing_failed", called_model=True)
