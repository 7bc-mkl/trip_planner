"""`domain/extraction.py` — what survives of a model's claim about a confirmation."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trip_planner.domain.extraction import (
    CONFIRMATION_NUMBER_MAX,
    TITLE_MAX,
    ExtractedFields,
    ProposalValues,
    coerce,
)

KINDS = ("accommodation", "transport", "activity", "meal", "other")
TRIP = {"trip_start": date(2026, 10, 15), "trip_end": date(2026, 10, 30), "kinds": KINDS}


def run(**fields: object) -> ProposalValues:
    return coerce(ExtractedFields.model_validate(fields), **TRIP)  # type: ignore[arg-type]


def test_a_complete_extraction_keeps_every_field() -> None:
    proposal = run(
        title="  Turkish   Airlines TK1234 ",
        kind="Transport",
        confirmation_number=" SX-9912L ",
        start_date="2026-10-17",
        end_date="2026-10-18",
        start_time="23:50",
        end_time="14:00",
        cost_amount="4321.50",
        cost_currency="PLN",
    )

    assert proposal == ProposalValues(
        title="Turkish Airlines TK1234",
        kind="transport",
        confirmation_number="SX-9912L",
        start_date=date(2026, 10, 17),
        end_date=date(2026, 10, 18),
        start_time=time(23, 50),
        end_time=time(14, 0),
        cost_amount=Decimal("4321.50"),
        cost_currency="PLN",
    )


def test_an_absent_field_is_no_claim() -> None:
    assert run().is_empty()


def test_an_unknown_field_is_refused_at_the_boundary() -> None:
    with pytest.raises(ValidationError):
        ExtractedFields.model_validate({"title": "x", "item_id": "anything"})


def test_a_non_string_title_is_refused_rather_than_stringified() -> None:
    with pytest.raises(ValidationError):
        ExtractedFields.model_validate({"title": ["a", "b"]})


def test_an_amount_without_a_currency_is_dropped_whole() -> None:
    proposal = run(cost_amount="120.00", confirmation_number="ABC")

    assert (proposal.cost_amount, proposal.cost_currency) == (None, None)
    assert proposal.confirmation_number == "ABC"


def test_a_currency_without_an_amount_is_dropped_whole() -> None:
    proposal = run(cost_currency="EUR")

    assert (proposal.cost_amount, proposal.cost_currency) == (None, None)


def test_three_decimals_are_never_proposed() -> None:
    proposal = run(cost_amount="10.101", cost_currency="EUR")

    assert (proposal.cost_amount, proposal.cost_currency) == (None, None)


def test_a_lower_case_code_is_coerced_to_the_shape_the_api_accepts() -> None:
    proposal = run(cost_amount="99.90", cost_currency=" eur ")

    assert (proposal.cost_amount, proposal.cost_currency) == (Decimal("99.90"), "EUR")


def test_a_numeric_amount_does_not_pass_through_binary_float() -> None:
    proposal = run(cost_amount=10.1, cost_currency="EUR")

    assert proposal.cost_amount == Decimal("10.1")


@pytest.mark.parametrize("amount", ["abc", "-5", "12345678901.00"])
def test_an_amount_the_column_cannot_hold_is_dropped(amount: str) -> None:
    proposal = run(cost_amount=amount, cost_currency="EUR")

    assert proposal.cost_amount is None


def test_an_impossible_date_span_drops_the_end_and_keeps_the_start() -> None:
    proposal = run(start_date="2026-10-20", end_date="2026-10-18", start_time="10:00")

    assert proposal.start_date == date(2026, 10, 20)
    assert proposal.start_time == time(10, 0)
    assert (proposal.end_date, proposal.end_time) == (None, None)


def test_a_span_past_the_trip_drops_the_end() -> None:
    proposal = run(start_date="2026-10-29", end_date="2026-11-02")

    assert proposal.end_date is None


def test_a_same_day_span_whose_end_precedes_its_start_drops_the_end_time() -> None:
    proposal = run(start_date="2026-10-20", start_time="18:00", end_time="09:00")

    assert proposal.start_time == time(18, 0)
    assert proposal.end_time is None


def test_a_start_date_outside_the_trip_is_dropped_with_its_end() -> None:
    proposal = run(start_date="2026-06-15", end_date="2026-10-20", title="TK")

    assert (proposal.start_date, proposal.end_date) == (None, None)
    assert proposal.title == "TK"


def test_an_end_on_the_start_day_is_stored_as_no_end_date() -> None:
    assert run(start_date="2026-10-20", end_date="2026-10-20").end_date is None


@pytest.mark.parametrize("value", ["17 Oct", "2026/10/17", ""])
def test_a_date_that_is_not_iso_is_dropped(value: str) -> None:
    assert run(start_date=value).start_date is None


@pytest.mark.parametrize("value", ["25:00", "7pm", "12:60"])
def test_a_time_that_is_not_a_time_is_dropped(value: str) -> None:
    assert run(start_time=value).start_time is None


def test_seconds_are_accepted_and_not_kept() -> None:
    assert run(start_time="08:15:30").start_time == time(8, 15)


def test_a_confirmation_number_over_500_characters_is_dropped() -> None:
    proposal = run(confirmation_number="X" * (CONFIRMATION_NUMBER_MAX + 1))

    assert proposal.confirmation_number is None


def test_a_blank_confirmation_number_is_no_claim() -> None:
    assert run(confirmation_number="   ").confirmation_number is None


def test_an_unknown_kind_is_dropped() -> None:
    assert run(kind="spaceship").kind is None


def test_a_long_title_is_truncated_to_the_column_bound() -> None:
    title = run(title="A" * (TITLE_MAX + 50)).title

    assert title is not None and len(title) == TITLE_MAX


def test_a_stored_proposal_with_an_unknown_field_fails_loudly() -> None:
    with pytest.raises(ValidationError):
        ProposalValues.model_validate({"title": "x", "notes": "smuggled"})
