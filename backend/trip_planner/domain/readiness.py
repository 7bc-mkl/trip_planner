"""The readiness counter (R02) — the arithmetic, in one place.

This is the number the whole product exists to show, so it is computed here and
nowhere else: the trip list row, the timeline tile and any later export all call
this function, and `tests/test_trips_api.py` asserts the served figure equals it.
A second implementation "just for the list" is how the two come to disagree.

    arranged = count(status = 'done')
    tracked  = count(status IN ('to_book', 'done'))

Items still `to_plan` are outside **both** halves. That is what the brief means by
"items still *do zaplanowania* stay out of the arithmetic", and it is why the
counter cannot be read as "done out of everything".

**The field is called `tracked`, not `total`.** Every consumer would read `total`
as *the number of items*, which it is not — a trip with ten items all still
`to_plan` has `tracked = 0`. `BACKWARD_COMPATIBILITY.md` names "changing what it
means while keeping its name" as the worst class of break, and a field that
starts out misnamed has already made it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple, Protocol

__all__ = ["Readiness", "readiness"]


class HasStatus(Protocol):
    """Anything with a status — the model, or a plain object in a unit test."""

    status: str


class Readiness(NamedTuple):
    """The counter's two halves. Serialised as `{"arranged": n, "tracked": m}`."""

    arranged: int
    tracked: int


def readiness(items: Iterable[HasStatus]) -> Readiness:
    """Count how much of the plan is arranged, and how much is being tracked at all.

    A spanning item is counted **once**: it is one row, on its start day, whatever
    its `end_date` says. Nothing here looks at dates, which is what guarantees it.
    """
    arranged = 0
    tracked = 0

    for item in items:
        if item.status == "done":
            arranged += 1
            tracked += 1
        elif item.status == "to_book":
            tracked += 1

    return Readiness(arranged=arranged, tracked=tracked)
