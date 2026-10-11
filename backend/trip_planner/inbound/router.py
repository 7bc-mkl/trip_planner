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
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.config import ModelSettings
from trip_planner.db.models import InboundMessage, InboundModelEgress, Owner, Trip
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
                place
                for place in (trip.departure_place, trip.return_place)
                if place
            ),
        )
        for trip in trips
    ]


def month_spend(db: OrmSession, *, now: datetime) -> Decimal:
    """What this billing month's model calls have cost so far.

    Summed from `inbound_model_egress`, which is the same table that records
    *what may have left* — so the budget and the audit trail cannot disagree
    about how many calls were made.

    A call whose usage the provider never reported contributes nothing here,
    which is exactly why an unreported-usage deployment stops making calls:
    `ModelBudget` refuses when the price schedule or the usage is missing, so
    the gap cannot quietly read as free.
    """
    from trip_planner.config import get_settings

    settings = get_settings()
    model = settings.model
    if model is None or not model.priced:
        return Decimal(0)

    assert model.input_price_per_mtok is not None
    assert model.output_price_per_mtok is not None

    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        sa.select(InboundModelEgress.input_tokens, InboundModelEgress.output_tokens).where(
            InboundModelEgress.attempted_at >= start_of_month
        )
    ).all()

    million = Decimal(1_000_000)
    total = Decimal(0)
    for input_tokens, output_tokens in rows:
        if input_tokens is None or output_tokens is None:
            continue
        total += Decimal(input_tokens) * model.input_price_per_mtok / million
        total += Decimal(output_tokens) * model.output_price_per_mtok / million
    return total


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

    **Commits once, deliberately**, to persist the egress row before the call —
    see step 4 of the module docstring. Everything else is left for the caller's
    transaction, so a message and its routing land together.
    """
    moment = now or datetime.now(UTC)

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
        return _defer(message, "routing_budget_exhausted")

    # The point of no return. Committed first, so a crash in the next line still
    # leaves the owner able to see that his text may have gone to this provider.
    egress = InboundModelEgress(
        inbound_message_id=message.id,
        kind="text",
        provider=model_settings.provider,
        model=model_settings.model,
        attempted_at=moment,
    )
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

    try:
        proposal, usage = client.route(request, budget=budget)
    except ModelRefused:
        # The answer arrived and is unusable. Retrying would send the mail again
        # for the same result, so this is decided.
        logger.warning("inbox: the model's routing answer was refused")
        return _queue(message, "routing_refused", None, called_model=True)
    except ModelCallFailed:
        return _after_transient_failure(message)

    _record_usage(db, egress, usage)

    if proposal.trip_id is None:
        return _queue(message, "model_found_no_trip", None, called_model=True)

    return _route_to(message, proposal.trip_id, candidates)


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


def _record_usage(db: OrmSession, egress: InboundModelEgress, usage: Usage) -> None:
    """Stamp what the provider said it charged for, onto the row already written.

    Separate from the insert because the insert happens *before* the call and
    the usage only exists after it. A row with null tokens is therefore a real
    and meaningful state: the call was attempted and the provider reported no
    usage, which is what makes the next budget check refuse rather than guess.
    """
    egress.input_tokens = usage.input_tokens
    egress.output_tokens = usage.output_tokens
    db.flush()
