"""`domain/days.py` — generating a trip's timeline from its range.

Pure functions, no database: the arithmetic that decides how many rows the create
endpoint writes is worth testing on its own, because a fencepost error here is
invisible in an API test that only asserts "some days were created".
"""

from __future__ import annotations

from datetime import date

import pytest

from trip_planner.domain.days import MAX_TRIP_DAYS, generate_days, night_count
from trip_planner.errors import ApiError, ErrorCode


class TestGenerateDays:
    def test_a_one_day_trip_has_exactly_that_day(self) -> None:
        """The degenerate case, and the one a half-open range would return empty."""
        assert generate_days(date(2026, 10, 10), date(2026, 10, 10)) == [date(2026, 10, 10)]

    def test_both_ends_are_included(self) -> None:
        """A trip from the 10th to the 24th visibly has both of those days in it.

        The last day is usually the flight home, so dropping it is not a rounding
        detail — it loses the day most likely to carry a transport item.
        """
        days = generate_days(date(2026, 10, 10), date(2026, 10, 24))

        assert len(days) == 15
        assert days[0] == date(2026, 10, 10)
        assert days[-1] == date(2026, 10, 24)

    def test_the_days_are_consecutive_and_in_order(self) -> None:
        days = generate_days(date(2026, 12, 29), date(2027, 1, 3))

        assert days == [
            date(2026, 12, 29),
            date(2026, 12, 30),
            date(2026, 12, 31),
            date(2027, 1, 1),
            date(2027, 1, 2),
            date(2027, 1, 3),
        ]

    def test_a_leap_day_span_includes_29_february(self) -> None:
        """2028 is a leap year; a range across it must not skip the 29th."""
        days = generate_days(date(2028, 2, 27), date(2028, 3, 2))

        assert date(2028, 2, 29) in days
        assert len(days) == 5

    def test_a_full_leap_year_is_inside_the_bound(self) -> None:
        """366 rather than 365 exists precisely so this real plan is not refused."""
        days = generate_days(date(2028, 1, 1), date(2028, 12, 31))

        assert len(days) == MAX_TRIP_DAYS == 366

    def test_exactly_the_bound_is_allowed(self) -> None:
        """366 is inclusive — the boundary is a permitted plan, not a refused one."""
        assert len(generate_days(date(2026, 1, 1), date(2027, 1, 1))) == 366

    def test_one_day_past_the_bound_is_refused(self) -> None:
        with pytest.raises(ApiError) as raised:
            generate_days(date(2026, 1, 1), date(2027, 1, 2))  # 367 days

        assert raised.value.code is ErrorCode.TRIP_TOO_LONG
        assert raised.value.status_code == 422
        assert raised.value.field == "end_date"

    def test_a_mistyped_year_cannot_ask_for_unbounded_rows(self) -> None:
        """The failure the bound exists for: 2026 typed as 2126."""
        with pytest.raises(ApiError) as raised:
            generate_days(date(2026, 10, 10), date(2126, 10, 24))

        assert raised.value.code is ErrorCode.TRIP_TOO_LONG

    def test_an_inverted_range_is_refused(self) -> None:
        with pytest.raises(ApiError) as raised:
            generate_days(date(2026, 10, 24), date(2026, 10, 10))

        assert raised.value.code is ErrorCode.INVALID_DATE_RANGE
        assert raised.value.field == "end_date"


class TestNightCount:
    def test_it_is_one_fewer_than_the_days(self) -> None:
        """The creator's live summary reads "15 dni / 14 n."."""
        assert night_count(date(2026, 10, 10), date(2026, 10, 24)) == 14

    def test_a_single_day_trip_has_no_nights(self) -> None:
        """A real state — a day trip — not an error."""
        assert night_count(date(2026, 10, 10), date(2026, 10, 10)) == 0

    def test_it_never_goes_negative(self) -> None:
        """An inverted range is refused elsewhere; the summary must not show "-3 n."."""
        assert night_count(date(2026, 10, 24), date(2026, 10, 21)) == 0
