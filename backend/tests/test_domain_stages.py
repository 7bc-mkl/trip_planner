"""`domain/stages.py` — the day-to-stage relation the schema deliberately does not store.

These are the cases the spec's Edge Cases table names for stage coverage: a travel
day shared by two stages, three stages sharing a date, a stage with no dates, and a
day in no stage at all. Each is a state the timeline has to render, so each has a
test rather than a comment.

The stages here are unsaved model instances — no database is needed to exercise a
pure function, and keeping these tests out of the transaction fixture makes them
fast enough to be run on every save.
"""

from __future__ import annotations

from datetime import date

import pytest

from trip_planner.db.models import TripStage
from trip_planner.domain.stages import stage_label, stages_for_day


def stage(place: str, position: int, start: date | None = None, end: date | None = None):
    return TripStage(position=position, place=place, start_date=start, end_date=end)


DELHI = stage("Delhi", 0, date(2026, 11, 10), date(2026, 11, 13))
AGRA = stage("Agra & Jaipur", 1, date(2026, 11, 13), date(2026, 11, 17))
UNDATED = stage("Langkawi", 2)


class TestStagesForDay:
    def test_a_day_inside_one_stage_resolves_to_that_stage(self) -> None:
        assert stages_for_day([DELHI, AGRA], date(2026, 11, 11)) == [DELHI]

    def test_a_travel_day_resolves_to_both_stages_that_share_it(self) -> None:
        """The design export's own example: the 13th is in Delhi *and* in Agra.

        This is why there is no non-overlap constraint on `trip_stage`.
        """
        assert stages_for_day([DELHI, AGRA], date(2026, 11, 13)) == [DELHI, AGRA]

    def test_three_stages_sharing_a_date_all_resolve(self) -> None:
        """Nothing caps the count — only the *label* truncates."""
        a = stage("A", 0, date(2026, 11, 13), date(2026, 11, 13))
        b = stage("B", 1, date(2026, 11, 13), date(2026, 11, 14))
        c = stage("C", 2, date(2026, 11, 12), date(2026, 11, 13))

        assert stages_for_day([a, b, c], date(2026, 11, 13)) == [a, b, c]

    def test_the_result_is_ordered_by_position_not_by_date(self) -> None:
        """`position` is the itinerary's own sequence — the order the creator showed.

        Handed the stages in the wrong order, the function must still answer in
        position order, so a caller cannot make the label read backwards.
        """
        assert stages_for_day([AGRA, DELHI], date(2026, 11, 13)) == [DELHI, AGRA]

    def test_a_stage_with_no_dates_covers_nothing(self) -> None:
        """An undated base is one whose days are not yet decided.

        Treating it as covering the whole trip would label every day with a place
        the owner never assigned to it.
        """
        assert stages_for_day([UNDATED], date(2026, 11, 11)) == []

    @pytest.mark.parametrize(
        ("start", "end"),
        [(date(2026, 11, 10), None), (None, date(2026, 11, 17))],
        ids=["start only", "end only"],
    )
    def test_a_half_dated_stage_covers_nothing(self, start: date | None, end: date | None) -> None:
        """An end without a start is not a range yet, so it cannot contain a day."""
        assert stages_for_day([stage("Penang", 0, start, end)], date(2026, 11, 12)) == []

    def test_a_day_in_no_stage_resolves_to_nothing(self) -> None:
        """A day in transit. Allowed, and rendered without a stage label."""
        assert stages_for_day([DELHI, AGRA], date(2026, 11, 20)) == []

    @pytest.mark.parametrize(
        "day",
        [date(2026, 11, 10), date(2026, 11, 13)],
        ids=["first day of the stage", "last day of the stage"],
    )
    def test_the_stage_range_is_inclusive_at_both_ends(self, day: date) -> None:
        assert DELHI in stages_for_day([DELHI], day)

    def test_no_stages_at_all_is_not_an_error(self) -> None:
        assert stages_for_day([], date(2026, 11, 11)) == []


class TestStageLabel:
    def test_one_stage_is_its_place(self) -> None:
        assert stage_label([DELHI]) == "Delhi"

    def test_two_stages_are_joined_with_an_arrow(self) -> None:
        """An arrow, not a comma: the label describes movement, not a set."""
        assert stage_label([DELHI, AGRA]) == "Delhi → Agra & Jaipur"

    def test_three_stages_truncate_after_two_with_a_count(self) -> None:
        assert stage_label([DELHI, AGRA, UNDATED]) == "Delhi → Agra & Jaipur +1"

    def test_the_count_is_the_number_hidden_not_the_total(self) -> None:
        """"+3" on a five-stage day means three are hidden, not that there are three."""
        stages = [stage(letter, index) for index, letter in enumerate("ABCDE")]

        assert stage_label(stages) == "A → B +3"

    def test_no_stages_gives_an_empty_string(self) -> None:
        """Not "—": a day in no stage renders without a label, and a dash here would
        be an untranslated string on the screen."""
        assert stage_label([]) == ""
