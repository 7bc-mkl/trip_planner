"""Item span validation and the day's ordering rule.

The span rules cannot be a `CHECK` constraint: `end_date` has to be compared
against the *trip's* `end_date`, which lives two tables away. So this module is
the single validation path, called by both `POST` and `PATCH` — one path rather
than two is what stops the two verbs from disagreeing about what a valid item is.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time

from trip_planner.errors import ApiError, ErrorCode

__all__ = ["sort_key", "sorted_items", "validate_span"]


def validate_span(
    *,
    start_date: date,
    start_time: time | None,
    end_time: time | None,
    end_date: date | None,
    trip_end: date,
) -> None:
    """Refuse a span that cannot describe a real stretch of time.

    Three rules, all answering `422 invalid_time_span`:

    - `end_date`, when present, is not before the item's own start day. An item
      that ends before it begins is not a plan.
    - `end_date` does not run past the trip's last day. There is no `trip_day` row
      out there for it to reach, so the timeline could not render the marker.
    - when there is **no** `end_date` and both times are present, `end_time` is not
      before `start_time`. This check is deliberately skipped once `end_date` is
      set: 23:50 → 14:00 is the overnight flight, and comparing the two clock
      times would reject exactly the case the span columns were added for.
    """
    if end_date is not None:
        if end_date < start_date:
            raise ApiError(ErrorCode.INVALID_TIME_SPAN, field="end_date")
        if end_date > trip_end:
            raise ApiError(ErrorCode.INVALID_TIME_SPAN, field="end_date")
        return

    if start_time is not None and end_time is not None and end_time < start_time:
        raise ApiError(ErrorCode.INVALID_TIME_SPAN, field="end_time")


def sort_key(item: object) -> tuple[int, time, int]:
    """The day's ordering: timed items first by time, then untimed by `position`.

    An item with no time is "sometime that day", so it sorts **after** everything
    with a clock time rather than at midnight — putting it first would claim the
    owner planned it before breakfast. `position` breaks the tie among untimed
    items, and among timed ones that share a minute.
    """
    start_time = getattr(item, "start_time", None)
    position = getattr(item, "position", 0)

    if start_time is None:
        return (1, time.min, position)
    return (0, start_time, position)


def sorted_items(items: Iterable[object]) -> list[object]:
    """`items` in the order the day detail and the timeline both render them."""
    return sorted(items, key=sort_key)
