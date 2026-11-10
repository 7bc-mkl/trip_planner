"""What a model may claim a confirmation says, and what survives of the claim.

Phase 3 widens the routing answer with a sparse `fields` object (spec, Adapter
contract): `title`, `kind`, `confirmation_number`, `start_date`, `end_date`,
`start_time`, `end_time`, `cost_amount` and `cost_currency`. An absent field is
no claim. This module owns the two halves of turning that into something a
proposal may carry:

1. **`ExtractedFields` is the rejecting reader.** Pydantic with
   `extra="forbid"`: a key the contract does not name is a refusal, not a value
   that gets stored. The provider cannot choose an item, issue a tool call or
   supply user-visible prose — there is nowhere in this shape to put any of it.
2. **`coerce` keeps only what the item table could hold.** Every value goes
   through the rule the shipped write path already applies — `domain/money.py`
   for the cost, `domain/items.validate_span` for the span, the item column
   bounds for the text — and **anything that fails is dropped from the
   proposal rather than offered** (spec, Edge Cases: "a cost with no currency,
   or three decimals … is never proposed"). A proposal the owner could approve
   only to be told `422` would be worse than a smaller proposal.

Pure, like everything under `domain/`: no database and no clock. The allowed
item kinds are passed in rather than imported from `db.models`, because the
dependency runs `db` → `domain` and never the other way.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from datetime import date, time
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr

from trip_planner.domain.items import validate_span
from trip_planner.domain.money import validate_cost
from trip_planner.errors import ApiError

__all__ = [
    "APPROVABLE_FIELDS",
    "CONFIRMATION_NUMBER_MAX",
    "TITLE_MAX",
    "ExtractedFields",
    "ProposalValues",
    "coerce",
    "normalise_title",
]

#: The item columns' own bounds, restated as the rule a proposal must meet. The
#: API's `ItemCreate` and the `ck_item_confirmation_number` CHECK say the same.
TITLE_MAX = 200
CONFIRMATION_NUMBER_MAX = 500

#: What an approval may name in its `fields` allow-list.
#:
#: `cost` is one field, not two: an amount and its currency are one fact
#: (`ck_item_cost_paired`), and an approval that could tick one half would be
#: an approval that could write half a fact. `start_date` is not here — it
#: chooses the day a new item lands on and is used to find an existing one, but
#: moving an existing item between days stays with the ordinary edit screen.
APPROVABLE_FIELDS = (
    "title",
    "kind",
    "confirmation_number",
    "cost",
    "start_time",
    "end_time",
    "end_date",
)

_WHITESPACE = re.compile(r"\s+")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


class ExtractedFields(BaseModel):
    """The model's sparse claim about a confirmation. Every field optional.

    Strict string types, so a provider that answers `{"title": ["a", "b"]}` is
    refused here rather than stringified into something plausible. The cost
    amount alone may also be a JSON number, because that is how most providers
    will write `1234.5` — it is converted through `str`, never through binary
    float arithmetic.
    """

    model_config = ConfigDict(extra="forbid")

    title: StrictStr | None = None
    kind: StrictStr | None = None
    confirmation_number: StrictStr | None = None
    start_date: StrictStr | None = None
    end_date: StrictStr | None = None
    start_time: StrictStr | None = None
    end_time: StrictStr | None = None
    cost_amount: StrictStr | StrictInt | StrictFloat | None = None
    cost_currency: StrictStr | None = None


class ProposalValues(BaseModel):
    """Typed item values, as a proposal stores them — and as an item's snapshot.

    The same shape on both sides of the comparison the review sheet draws:
    what the message says, and what the item said when the proposal was made.
    `None` is "no claim" on the proposed side and "empty" on the current side.

    `extra="forbid"` because this is also the reader for the stored JSONB: a
    proposal written by later code with a field this code does not know fails
    loudly at this boundary rather than being half-applied.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    kind: str | None = None
    confirmation_number: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    cost_amount: Decimal | None = None
    cost_currency: str | None = None

    def is_empty(self) -> bool:
        return all(value is None for value in self.model_dump().values())


def normalise_title(value: str) -> str:
    """Collapsed whitespace, trimmed. The form a title is compared and stored in."""
    return _WHITESPACE.sub(" ", value).strip()


def coerce(
    raw: ExtractedFields,
    *,
    trip_start: date,
    trip_end: date,
    kinds: Collection[str],
) -> ProposalValues:
    """Keep what the item table could hold; drop the rest, field by field.

    Dropping is per fact, never per proposal: a confirmation whose cost is
    unreadable still proposes its confirmation number, and one whose return
    date is impossible still proposes its departure.
    """
    title = _title(raw.title)
    kind = raw.kind.strip().lower() if raw.kind is not None else None
    if kind not in kinds:
        kind = None

    start_date = _date(raw.start_date)
    if start_date is not None and not trip_start <= start_date <= trip_end:
        # A date outside the trip has no day to land on. The end date is
        # dropped with it: a span is measured from a start this proposal no
        # longer claims.
        start_date = None
    end_date = _date(raw.end_date) if start_date is not None else None
    if end_date == start_date:
        # "Ends on its start day" has one representation on an item: NULL.
        end_date = None

    start_time = _time(raw.start_time)
    end_time = _time(raw.end_time)
    try:
        validate_span(
            start_date=start_date or trip_start,
            start_time=start_time,
            end_time=end_time,
            end_date=end_date,
            trip_end=trip_end,
        )
    except ApiError:
        # The span is impossible as a whole — it ends before it starts, or past
        # the trip. Which half is wrong is not knowable from here, so neither
        # end is proposed; the start stands on its own.
        end_date = None
        end_time = None

    amount, currency = _cost(raw.cost_amount, raw.cost_currency)

    return ProposalValues(
        title=title,
        kind=kind,
        confirmation_number=_confirmation_number(raw.confirmation_number),
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        cost_amount=amount,
        cost_currency=currency,
    )


def _title(value: str | None) -> str | None:
    if value is None:
        return None
    title = normalise_title(value)
    if not title:
        return None
    # Truncated rather than dropped: a long title is still the right title, and
    # the owner sees it beside the source text before approving.
    return title[:TITLE_MAX].rstrip()


def _confirmation_number(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    reference = value.strip()
    # Dropped rather than truncated: half a booking reference is a wrong one.
    if len(reference) > CONFIRMATION_NUMBER_MAX:
        return None
    return reference


def _date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _time(value: str | None) -> time | None:
    if value is None:
        return None
    match = _TIME.fullmatch(value.strip())
    if match is None:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    # Seconds are accepted on the way in and not kept: an item's times are to
    # the minute everywhere else in the product.
    return time(hour, minute)


def _cost(
    amount: str | int | float | None, currency: str | None
) -> tuple[Decimal | None, str | None]:
    """The pair, or neither. Decided by the shipped rule, not restated here.

    The currency is upper-cased and trimmed on the way in. That is a coercion
    of *model output*, which is not the API's contract: the item endpoints still
    refuse `"pln"` from a client (`domain/money.py` says why), and the value
    this produces meets that same rule.
    """
    if amount is None or currency is None:
        return None, None
    try:
        value = Decimal(str(amount).strip())
    except InvalidOperation:
        return None, None
    code = currency.strip().upper()
    if validate_cost(cost_amount=value, cost_currency=code) is not None:
        return None, None
    return value, code
