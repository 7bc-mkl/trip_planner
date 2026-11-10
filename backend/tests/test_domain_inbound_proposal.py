"""The proposal diff and the item-target rule — `domain/inbound.py`, Phase 3.

A6 says nothing the owner typed is overwritten by a default. These tests are
that rule, case by case, without a database: the sheet's ticks and the
approval's re-diff are both computed from these functions.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest

from trip_planner.domain.extraction import ProposalValues
from trip_planner.domain.inbound import (
    DayCandidate,
    ItemCandidate,
    choose_target,
    diff_proposal,
    diff_status,
    fallback_title,
    is_no_op,
    normalise_reference,
)

PROPOSED = ProposalValues(
    title="Hotel Majestic",
    confirmation_number="BK-1234",
    start_time=time(15, 0),
    cost_amount=Decimal("480.00"),
    cost_currency="MYR",
)


def rows(proposed: ProposalValues, current: ProposalValues | None) -> dict[str, tuple[bool, bool]]:
    return {
        row.name: (row.changed, row.default_ticked) for row in diff_proposal(proposed, current)
    }


def test_every_empty_current_value_defaults_to_ticked() -> None:
    assert rows(PROPOSED, ProposalValues()) == {
        "title": (True, True),
        "confirmation_number": (True, True),
        "cost": (True, True),
        "start_time": (True, True),
    }


def test_a_new_item_ticks_every_claimed_field() -> None:
    assert all(ticked for _, ticked in rows(PROPOSED, None).values())


def test_every_non_empty_current_value_defaults_to_unticked() -> None:
    current = ProposalValues(
        title="My hotel",
        confirmation_number="TYPED-BY-HAND",
        start_time=time(14, 0),
        cost_amount=Decimal("400.00"),
        cost_currency="MYR",
    )

    assert rows(PROPOSED, current) == {
        "title": (True, False),
        "confirmation_number": (True, False),
        "cost": (True, False),
        "start_time": (True, False),
    }


def test_a_field_the_proposal_does_not_claim_is_not_a_row() -> None:
    names = {row.name for row in diff_proposal(ProposalValues(title="x"), ProposalValues())}

    assert names == {"title"}


def test_cost_is_one_row_compared_as_a_pair() -> None:
    current = ProposalValues(cost_amount=Decimal("480.00"), cost_currency="EUR")
    (row,) = [one for one in diff_proposal(PROPOSED, current) if one.name == "cost"]

    assert row.current == (Decimal("480.00"), "EUR")
    assert row.proposed == (Decimal("480.00"), "MYR")
    assert (row.changed, row.default_ticked) == (True, False)


def test_a_proposal_identical_to_the_item_is_an_all_unticked_no_op() -> None:
    fields = diff_proposal(PROPOSED, PROPOSED)
    status = diff_status("done", "done")

    assert fields and all(not row.changed and not row.default_ticked for row in fields)
    assert status is not None and not status.default_ticked
    assert is_no_op(fields, status)


@pytest.mark.parametrize(
    ("current", "ticked"),
    [(None, True), ("to_plan", True), ("to_book", True), ("done", False)],
)
def test_a_forward_status_move_is_ticked(current: str | None, ticked: bool) -> None:
    status = diff_status("done", current)

    assert status is not None and status.default_ticked is ticked


def test_a_backwards_status_move_is_never_ticked() -> None:
    status = diff_status("to_book", "done")

    assert status is not None
    assert status.changed and not status.default_ticked


def test_no_claimed_status_is_no_status_row() -> None:
    assert diff_status(None, "to_plan") is None


# --------------------------------------------------------------------------- #
# Targeting
# --------------------------------------------------------------------------- #

DAY_17 = DayCandidate(id="d17", date=date(2026, 10, 17))
DAY_18 = DayCandidate(id="d18", date=date(2026, 10, 18))
DAYS = [DAY_17, DAY_18]


def item(id: str, **overrides: object) -> ItemCandidate:
    values: dict[str, object] = {
        "id": id,
        "day_id": "d17",
        "date": date(2026, 10, 17),
        "end_date": None,
        "title": "Flight to Kuala Lumpur",
        "confirmation_number": None,
    }
    values.update(overrides)
    return ItemCandidate(**values)  # type: ignore[arg-type]


def test_one_normalised_confirmation_number_match_is_an_update() -> None:
    proposed = ProposalValues(confirmation_number="sx 9912-l", start_date=date(2026, 10, 18))
    target = choose_target(
        proposed, items=[item("a", confirmation_number="SX-9912L"), item("b")], days=DAYS
    )

    assert (target.kind, target.item_id, target.reason) == (
        "update_item",
        "a",
        "matched_confirmation_number",
    )


def test_a_unique_title_and_start_day_match_is_an_update_when_no_reference_matches() -> None:
    proposed = ProposalValues(
        title="  flight TO kuala   lumpur ",
        confirmation_number="NOPE",
        start_date=date(2026, 10, 17),
    )
    target = choose_target(proposed, items=[item("a"), item("b", title="Hotel")], days=DAYS)

    assert (target.kind, target.item_id, target.reason) == (
        "update_item",
        "a",
        "matched_title_and_day",
    )


def test_the_title_match_respects_a_claimed_end_day() -> None:
    proposed = ProposalValues(
        title="Flight to Kuala Lumpur",
        start_date=date(2026, 10, 17),
        end_date=date(2026, 10, 18),
    )
    target = choose_target(proposed, items=[item("a")], days=DAYS)

    assert target.kind == "create_item"


def test_zero_matches_create_an_item_on_the_extracted_day() -> None:
    proposed = ProposalValues(title="Ferry", start_date=date(2026, 10, 18))
    target = choose_target(proposed, items=[item("a")], days=DAYS)

    assert (target.kind, target.day_id, target.reason) == ("create_item", "d18", "new_item_on_day")


@pytest.mark.parametrize(
    "proposed",
    [
        ProposalValues(confirmation_number="DUP"),
        ProposalValues(title="Flight to Kuala Lumpur", start_date=date(2026, 10, 17)),
    ],
)
def test_several_matches_wait_for_the_owner(proposed: ProposalValues) -> None:
    items = [item("a", confirmation_number="DUP"), item("b", confirmation_number="DUP")]
    target = choose_target(proposed, items=items, days=DAYS)

    assert (target.kind, target.item_id, target.reason) == (
        "update_item",
        None,
        "several_items_match",
    )


def test_no_usable_day_waits_for_the_owner() -> None:
    target = choose_target(ProposalValues(title="Ferry"), items=[], days=DAYS)

    assert (target.kind, target.day_id, target.reason) == ("create_item", None, "no_usable_day")


def test_a_blank_reference_never_matches_an_item_without_one() -> None:
    assert normalise_reference("  - ") == ""
    target = choose_target(
        ProposalValues(confirmation_number=" - ", start_date=date(2026, 10, 17)),
        items=[item("a")],
        days=DAYS,
    )

    assert target.kind == "create_item"


def test_the_fallback_title_prefers_the_claim_then_the_subject() -> None:
    assert fallback_title(ProposalValues(title="X"), subject="S", from_address="f") == "X"
    assert fallback_title(ProposalValues(), subject=" Re:  booking ", from_address="f") == (
        "Re: booking"
    )
    assert fallback_title(ProposalValues(), subject="", from_address="a@b.c") == "a@b.c"
