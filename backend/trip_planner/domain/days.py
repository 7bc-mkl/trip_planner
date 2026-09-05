"""Generating a trip's days from its date range.

Creating these dates *is* the "create an empty timeline" action the creator's
primary button performs, so it is a pure function with its own tests rather than
a loop inside the endpoint: the endpoint's job is the transaction, not the
arithmetic.

Like `security/csrf.py`, this module raises `ApiError` directly instead of a
parallel domain exception taxonomy. One set of error codes is what makes the
locale-parity test in `tests/test_errors.py` meaningful — a second, untranslated
hierarchy would defeat it.
"""

from __future__ import annotations

from datetime import date, timedelta

from trip_planner.errors import ApiError, ErrorCode

__all__ = ["MAX_TRIP_DAYS", "generate_days", "night_count"]

#: The longest trip the planner will generate days for.
#:
#: A bound exists so a single mistyped year cannot ask the database for four
#: hundred thousand rows. 366 rather than 365 so that a full leap year — the
#: longest genuine "one year" trip — is inside the limit rather than one day over
#: it, which would be an arbitrary refusal of a real plan.
MAX_TRIP_DAYS = 366


def generate_days(start: date, end: date) -> list[date]:
    """Every date from `start` to `end`, inclusive.

    Inclusive at both ends because a trip from the 10th to the 24th visibly has
    both of those days in it; a half-open range would silently drop the last day
    of every trip, and that day is usually the flight home.

    Raises `422 invalid_date_range` when the range runs backwards and
    `422 trip_too_long` when it exceeds `MAX_TRIP_DAYS`.
    """
    if end < start:
        raise ApiError(ErrorCode.INVALID_DATE_RANGE, field="end_date")

    span = (end - start).days + 1
    if span > MAX_TRIP_DAYS:
        raise ApiError(ErrorCode.TRIP_TOO_LONG, field="end_date")

    return [start + timedelta(days=offset) for offset in range(span)]


def night_count(start: date, end: date) -> int:
    """Nights between two inclusive dates — the creator's "15 dni / 14 n." summary.

    One fewer than the day count, and never negative: a single-day trip has no
    nights, which is a real state and not an error.
    """
    return max((end - start).days, 0)
