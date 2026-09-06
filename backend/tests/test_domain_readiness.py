"""`domain/readiness.py` — the number the product exists to show.

Plain stand-in objects rather than models: the arithmetic is over statuses, and
involving the database would test the fixture rather than the rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from trip_planner.domain.readiness import readiness


@dataclass
class Entry:
    status: str


def entries(*statuses: str) -> list[Entry]:
    return [Entry(status) for status in statuses]


class TestReadiness:
    def test_an_empty_trip_is_zero_of_zero(self) -> None:
        """Not an error and not a division — the copy for this case has no fraction."""
        assert readiness([]) == (0, 0)

    def test_items_all_still_to_plan_are_zero_of_zero(self) -> None:
        """The case that proves `tracked` is not `total`.

        Ten items, nothing decided: the counter reads "nothing arranged yet", not
        "0 of 10", because the owner has not committed to tracking any of them.
        """
        assert readiness(entries(*["to_plan"] * 10)) == (0, 0)

    def test_to_book_is_tracked_but_not_arranged(self) -> None:
        """Decided to do it, not yet booked: in the denominator, not the numerator."""
        assert readiness(entries("to_book")) == (0, 1)

    def test_done_is_both_arranged_and_tracked(self) -> None:
        assert readiness(entries("done")) == (1, 1)

    def test_the_mixed_case(self) -> None:
        """Two done, three to book, four still to plan → "2 of 5 arranged"."""
        assert readiness(
            entries("done", "done", "to_book", "to_book", "to_book", *["to_plan"] * 4)
        ) == (2, 5)

    def test_to_plan_is_outside_both_halves(self) -> None:
        """Adding an unplanned item must not move either number.

        If `to_plan` counted in the denominator, adding a vague idea to a trip
        would make the plan look *less* ready, which is the opposite of true.
        """
        before = readiness(entries("done", "to_book"))
        after = readiness(entries("done", "to_book", "to_plan", "to_plan"))

        assert before == after == (1, 2)

    def test_arranged_never_exceeds_tracked(self) -> None:
        """The fraction is only renderable if this holds for every input."""
        arranged, tracked = readiness(entries("done", "done", "to_book", "to_plan"))

        assert arranged <= tracked

    def test_a_spanning_item_is_counted_once(self) -> None:
        """It is one row, on its start day, whatever its end_date says.

        The function never looks at dates, which is what guarantees it — this test
        pins that guarantee so a future "count it on every day it covers" change
        has to break a test rather than a number nobody checks.
        """
        overnight_flight = Entry("done")

        assert readiness([overnight_flight]) == (1, 1)

    def test_it_accepts_any_iterable_not_only_a_list(self) -> None:
        """Callers pass a generator over a day's items; a list-only signature would
        force a materialisation at every call site."""
        assert readiness(entry for entry in entries("done", "to_book")) == (1, 2)

    @pytest.mark.parametrize("field", ["arranged", "tracked"])
    def test_the_result_is_addressable_by_name(self, field: str) -> None:
        """It is serialised as `{"arranged": n, "tracked": m}`; positional access
        in the API layer would make a field swap silent."""
        assert hasattr(readiness(entries("done")), field)
