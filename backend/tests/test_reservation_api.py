"""Reservation data over the existing item `PATCH`.

There is no reservation endpoint and there is deliberately none: the confirmation
number and the cost are fields of the item, written by the request that writes its
title. These tests are therefore about three things the shipped `PATCH` did not
have to answer before — what clears a field, what "together" means for the two
halves of a cost, and what an omitted key does — plus the one guarantee R04 turns
into a contract: **nothing here is ever required.**

The item suite in `tests/test_items_api.py` is untouched by this file, which is
the point: adding optional request fields is non-breaking, so its assertions must
keep passing exactly as written.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_items_api import DAY, add_item, day_url
from tests.test_trips_api import TRIPS, create, error_code


@pytest.fixture
def trip(signed_in_client: TestClient) -> dict:
    return create(signed_in_client)


def item_url(trip: dict, item: dict) -> str:
    return f"{TRIPS}/{trip['id']}/items/{item['id']}"


def patch(client: TestClient, trip: dict, item: dict, **fields: object):
    return client.patch(item_url(trip, item), json=fields)


def booked(client: TestClient, trip: dict) -> dict:
    """An item carrying a full reservation, which most of these tests then edit."""
    item = add_item(client, trip, kind="accommodation", title="Memmo Alfama")
    response = patch(
        client,
        trip,
        item,
        confirmation_number="SX-9912L",
        cost_amount="249.00",
        cost_currency="PLN",
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestWritingReservationData:
    def test_a_patch_stores_all_three_fields(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = booked(signed_in_client, trip)

        assert body["confirmation_number"] == "SX-9912L"
        assert body["cost_currency"] == "PLN"
        # A string on the wire, not a JSON number: a number would be parsed back
        # as a binary float by every client, undoing the NUMERIC(12,2) column.
        assert body["cost_amount"] == "249.00"

    def test_the_item_creates_with_no_reservation_data_and_no_complaint(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """R04 in the contract: none of the three is required, ever."""
        body = add_item(signed_in_client, trip)

        assert body["confirmation_number"] is None
        assert body["cost_amount"] is None
        assert body["cost_currency"] is None

    def test_a_cost_of_exactly_zero_is_accepted(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """A free museum day is an arranged item with an arranged cost of zero."""
        item = add_item(signed_in_client, trip, title="Muzeum Narodowe")

        response = patch(signed_in_client, trip, item, cost_amount="0", cost_currency="PLN")

        assert response.status_code == 200, response.text
        assert response.json()["cost_amount"] == "0.00"

    def test_the_reservation_survives_a_move_to_another_day(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """It is a field of the item, so it follows the item like its title does."""
        item = booked(signed_in_client, trip)

        body = patch(signed_in_client, trip, item, date="2026-10-12").json()

        assert body["confirmation_number"] == "SX-9912L"
        assert body["cost_amount"] == "249.00"

    def test_the_day_detail_and_the_timeline_show_the_same_item_shape(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """One object, one shape — the reason the fields are on both serialisers."""
        booked(signed_in_client, trip)
        reservation = ("confirmation_number", "cost_amount", "cost_currency")

        day = signed_in_client.get(day_url(trip)).json()["items"][0]
        timeline_day = next(
            one
            for one in signed_in_client.get(f"{TRIPS}/{trip['id']}").json()["days"]
            if one["date"] == DAY
        )
        timeline = timeline_day["items"][0]

        assert {field: day[field] for field in reservation} == {
            field: timeline[field] for field in reservation
        }
        assert timeline["cost_amount"] == "249.00"


class TestOmittingAndClearing:
    def test_omitting_a_reservation_field_leaves_it_unchanged(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """An absent key is not the same request as `null` — the whole point of
        routing these through `model_fields_set` rather than a sentinel."""
        item = booked(signed_in_client, trip)

        body = patch(signed_in_client, trip, item, title="Memmo Alfama (potwierdzony)").json()

        assert body["confirmation_number"] == "SX-9912L"
        assert body["cost_amount"] == "249.00"
        assert body["cost_currency"] == "PLN"

    def test_an_explicit_null_clears_the_confirmation_number(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = booked(signed_in_client, trip)

        body = patch(signed_in_client, trip, item, confirmation_number=None).json()

        assert body["confirmation_number"] is None
        # The cost is a different field and a different intention.
        assert body["cost_amount"] == "249.00"

    def test_an_empty_string_clears_the_confirmation_number(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """What the user's emptied text input actually sends.

        The `ck_item_confirmation_number` CHECK refuses `''`, so this has to
        become `NULL` rather than a `422` for clearing a clearable field.
        """
        item = booked(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, confirmation_number="")

        assert response.status_code == 200, response.text
        assert response.json()["confirmation_number"] is None

    def test_clearing_a_cost_requires_clearing_both_halves(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = booked(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, cost_amount=None, cost_currency=None)

        assert response.status_code == 200, response.text
        assert response.json()["cost_amount"] is None
        assert response.json()["cost_currency"] is None

    def test_clearing_only_the_amount_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = booked(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, cost_amount=None)

        assert response.status_code == 422
        assert error_code(response) == "invalid_cost"

    def test_clearing_only_the_currency_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = booked(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, cost_currency=None)

        assert response.status_code == 422
        assert error_code(response) == "invalid_cost"

    def test_a_refused_patch_stores_nothing(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The rejected request must not have half-applied its other fields."""
        item = booked(signed_in_client, trip)

        patch(signed_in_client, trip, item, title="Zmieniony", cost_currency=None)

        body = signed_in_client.get(day_url(trip)).json()["items"][0]
        assert body["title"] == "Memmo Alfama"
        assert body["cost_currency"] == "PLN"


class TestRefusedValues:
    def test_an_amount_without_a_currency_is_invalid_cost(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, cost_amount="249.00")

        assert response.status_code == 422
        assert error_code(response) == "invalid_cost"

    def test_a_currency_without_an_amount_is_invalid_cost(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, cost_currency="PLN")

        assert response.status_code == 422
        assert error_code(response) == "invalid_cost"

    @pytest.mark.parametrize(
        ("amount", "currency"),
        [
            ("-1.00", "PLN"),  # a negative price
            ("10.101", "PLN"),  # a third decimal the column cannot hold
            # A magnitude the column cannot hold: `NUMERIC(12,2)` stops just
            # below 10^10. Unbounded, this was a driver-level `DataError` —
            # an unhandled 500, not this 422.
            ("12345678901.00", "PLN"),
            ("10000000000.00", "PLN"),  # one cent past the largest storable amount
            ("249.00", "pln"),  # lower case: refused, never upper-cased
            ("249.00", "ZLOTY"),  # not ISO 4217's shape
        ],
    )
    def test_a_cost_the_column_could_not_hold_is_invalid_cost(
        self, signed_in_client: TestClient, trip: dict, amount: str, currency: str
    ) -> None:
        """Every one of these is `domain/money.py`'s verdict, not a second copy of it."""
        item = add_item(signed_in_client, trip)

        response = patch(
            signed_in_client, trip, item, cost_amount=amount, cost_currency=currency
        )

        assert response.status_code == 422
        assert error_code(response) == "invalid_cost"

    def test_a_501_character_confirmation_number_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, confirmation_number="A" * 501)

        assert response.status_code == 422
        assert error_code(response) == "invalid_reservation_field"

    def test_a_500_character_confirmation_number_is_stored(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The bound is inclusive; the test above it is the first refusal."""
        item = add_item(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, confirmation_number="B" * 500)

        assert response.status_code == 200, response.text
        assert response.json()["confirmation_number"] == "B" * 500

    def test_correcting_only_the_amount_keeps_the_stored_currency(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The pairing rule is about the resulting row, which is what the CHECK asks.

        A price correction on an item that already has a currency is a legitimate
        request, and the row it produces has both halves.
        """
        item = booked(signed_in_client, trip)

        response = patch(signed_in_client, trip, item, cost_amount="199.50")

        assert response.status_code == 200, response.text
        assert response.json()["cost_amount"] == "199.50"
        assert response.json()["cost_currency"] == "PLN"
