"""`domain/items.py` — span validation and the day's ordering rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

import pytest

from trip_planner.domain.items import sorted_items, validate_span
from trip_planner.errors import ApiError, ErrorCode

DAY = date(2026, 10, 10)
TRIP_END = date(2026, 10, 24)


def check(**overrides: object) -> None:
    kwargs: dict[str, object] = {
        "start_date": DAY,
        "start_time": None,
        "end_time": None,
        "end_date": None,
        "trip_end": TRIP_END,
    }
    kwargs.update(overrides)
    validate_span(**kwargs)  # type: ignore[arg-type]


class TestValidateSpan:
    def test_an_item_with_no_times_is_valid(self) -> None:
        """"Sometime that day" — the commonest state early in planning."""
        check()

    def test_a_same_day_item_ending_after_it_starts_is_valid(self) -> None:
        check(start_time=time(9, 0), end_time=time(11, 30))

    def test_a_same_day_item_ending_before_it_starts_is_refused(self) -> None:
        with pytest.raises(ApiError) as raised:
            check(start_time=time(11, 30), end_time=time(9, 0))

        assert raised.value.code is ErrorCode.INVALID_TIME_SPAN
        assert raised.value.status_code == 422
        assert raised.value.field == "end_time"

    def test_the_overnight_flight_is_valid(self) -> None:
        """23:50 → 14:00 the next day. The case the span columns exist for.

        Comparing the two clock times here would reject it, which is why the
        `end_time >= start_time` rule is skipped once `end_date` is set.
        """
        check(start_time=time(23, 50), end_time=time(14, 0), end_date=date(2026, 10, 11))

    def test_an_item_ending_on_its_own_start_day_is_valid(self) -> None:
        """An explicit `end_date` equal to the start day means the same as null."""
        check(end_date=DAY)

    def test_an_end_date_before_the_start_day_is_refused(self) -> None:
        with pytest.raises(ApiError) as raised:
            check(end_date=date(2026, 10, 9))

        assert raised.value.code is ErrorCode.INVALID_TIME_SPAN
        assert raised.value.field == "end_date"

    def test_an_end_date_past_the_trip_is_refused(self) -> None:
        """There is no trip_day out there for the marker to point at."""
        with pytest.raises(ApiError) as raised:
            check(end_date=date(2026, 10, 25))

        assert raised.value.code is ErrorCode.INVALID_TIME_SPAN
        assert raised.value.field == "end_date"

    def test_an_end_date_on_the_trip_s_last_day_is_valid(self) -> None:
        """The boundary is inside the trip: three nights ending on the last day."""
        check(end_date=TRIP_END)

    def test_a_backwards_clock_time_on_a_multi_day_item_is_not_refused(self) -> None:
        """Explicitly asserting the rule that is *not* applied.

        Any overnight item has an end time earlier than its start time; treating
        that as an error would refuse every one of them.
        """
        check(start_time=time(22, 0), end_time=time(6, 0), end_date=date(2026, 10, 12))

    def test_an_end_time_without_a_start_time_is_tolerated(self) -> None:
        """Half-filled input, not an error: the dialog may be mid-edit, and there
        is nothing to compare it against."""
        check(end_time=time(11, 0))


@dataclass
class Entry:
    position: int
    start_time: time | None
    title: str


class TestOrdering:
    def test_timed_items_come_in_clock_order(self) -> None:
        breakfast = Entry(2, time(8, 0), "breakfast")
        museum = Entry(0, time(10, 30), "museum")
        dinner = Entry(1, time(19, 0), "dinner")

        assert [item.title for item in sorted_items([dinner, museum, breakfast])] == [
            "breakfast",
            "museum",
            "dinner",
        ]

    def test_untimed_items_sort_after_every_timed_one(self) -> None:
        """"Sometime that day" is not "before breakfast".

        Sorting an untimed item at midnight would claim the owner planned it first
        thing, which is a statement the plan does not make.
        """
        untimed = Entry(0, None, "buy a SIM card")
        early = Entry(1, time(7, 0), "airport transfer")

        assert [item.title for item in sorted_items([untimed, early])] == [
            "airport transfer",
            "buy a SIM card",
        ]

    def test_untimed_items_are_ordered_among_themselves_by_position(self) -> None:
        """`position` is assigned in creation order, so this is the order they
        were typed in — the only ordering the owner has expressed."""
        second = Entry(1, None, "second")
        first = Entry(0, None, "first")

        assert [item.title for item in sorted_items([second, first])] == ["first", "second"]

    def test_position_breaks_a_tie_between_items_at_the_same_minute(self) -> None:
        later = Entry(1, time(9, 0), "later")
        earlier = Entry(0, time(9, 0), "earlier")

        assert [item.title for item in sorted_items([later, earlier])] == ["earlier", "later"]

    def test_an_empty_day_sorts_to_an_empty_list(self) -> None:
        assert sorted_items([]) == []

    def test_midnight_is_a_time_not_an_absence(self) -> None:
        """00:00 is a real plan (the flight leaves at midnight) and must not be
        treated as untimed, which `if not start_time` would do."""
        midnight = Entry(1, time(0, 0), "midnight departure")
        untimed = Entry(0, None, "sometime")

        assert [item.title for item in sorted_items([untimed, midnight])] == [
            "midnight departure",
            "sometime",
        ]
