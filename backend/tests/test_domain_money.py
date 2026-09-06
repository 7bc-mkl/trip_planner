"""`domain/money.py` — paired amount/currency validation for a reservation cost."""

from __future__ import annotations

from decimal import Decimal

from trip_planner.domain.money import (
    MAX_COST_AMOUNT,
    MAX_COST_DECIMAL_PLACES,
    MAX_COST_DIGITS,
    CostRejection,
    validate_cost,
)


class TestValidateCost:
    def test_both_absent_is_valid(self) -> None:
        """Clearing a cost — or never having set one — is legitimate."""
        assert validate_cost(cost_amount=None, cost_currency=None) is None

    def test_a_normal_amount_and_currency_is_valid(self) -> None:
        assert validate_cost(cost_amount=Decimal("1250.00"), cost_currency="PLN") is None

    def test_zero_is_a_valid_amount(self) -> None:
        """A free museum day is a real, arranged item with a real cost of zero —
        not the same state as "no cost recorded yet". A naive `if not amount`
        truthiness check treats `Decimal("0")` as falsy and gets this wrong."""
        assert validate_cost(cost_amount=Decimal("0"), cost_currency="PLN") is None

    def test_three_decimal_places_is_refused(self) -> None:
        """A `NUMERIC(12,2)` column cannot hold a third decimal digit."""
        result = validate_cost(cost_amount=Decimal("10.123"), cost_currency="PLN")

        assert result is CostRejection.INVALID_COST

    def test_the_bound_is_the_columns_own_precision(self) -> None:
        """`NUMERIC(12,2)` holds at most `9999999999.99`, written once as data."""
        assert (MAX_COST_DIGITS, MAX_COST_DECIMAL_PLACES) == (12, 2)
        assert Decimal("9999999999.99") == MAX_COST_AMOUNT

    def test_the_largest_storable_amount_is_valid(self) -> None:
        """The bound is inclusive; the test below it is the first refusal."""
        assert validate_cost(cost_amount=MAX_COST_AMOUNT, cost_currency="PLN") is None

    def test_an_amount_past_the_columns_precision_is_refused(self) -> None:
        """Without this the driver raises `numeric field overflow` — a `500`, and
        a poisoned session — where the spec promises `422 invalid_cost`."""
        result = validate_cost(cost_amount=Decimal("12345678901.00"), cost_currency="PLN")

        assert result is CostRejection.INVALID_COST

    def test_one_cent_past_the_bound_is_refused(self) -> None:
        result = validate_cost(
            cost_amount=MAX_COST_AMOUNT + Decimal("0.01"), cost_currency="PLN"
        )

        assert result is CostRejection.INVALID_COST

    def test_a_negative_amount_is_refused(self) -> None:
        result = validate_cost(cost_amount=Decimal("-1.00"), cost_currency="PLN")

        assert result is CostRejection.INVALID_COST

    def test_an_amount_with_no_currency_is_refused(self) -> None:
        result = validate_cost(cost_amount=Decimal("10.00"), cost_currency=None)

        assert result is CostRejection.INVALID_COST

    def test_a_currency_with_no_amount_is_refused(self) -> None:
        result = validate_cost(cost_amount=None, cost_currency="PLN")

        assert result is CostRejection.INVALID_COST

    def test_a_lowercase_currency_code_is_refused(self) -> None:
        """The shape is upper-case; silently upper-casing would mean the API
        accepts something the database `CHECK` does not."""
        result = validate_cost(cost_amount=Decimal("10.00"), cost_currency="pln")

        assert result is CostRejection.INVALID_COST
