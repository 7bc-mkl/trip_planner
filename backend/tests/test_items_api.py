"""The day detail, item CRUD, and the readiness counter on the trip payloads.

These are the endpoints the day-detail screen drives, and the counter they feed
is the number the product exists to show — so the readiness assertions compare
the *served* figure against `domain.readiness` rather than against a hard-coded
number, which is the only way to catch the two drifting apart.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.test_trips_api import TRIPS, create, error_code
from trip_planner.domain.readiness import readiness

DAY = "2026-10-11"


@pytest.fixture
def trip(signed_in_client: TestClient) -> dict:
    """The Malaysia trip: 10 to 24 October, three stages."""
    return create(signed_in_client)


def day_url(trip: dict, day: str = DAY) -> str:
    return f"{TRIPS}/{trip['id']}/days/{day}"


def add_item(client: TestClient, trip: dict, day: str = DAY, **fields: object) -> dict:
    body: dict[str, object] = {"kind": "activity", "title": "Batu Caves"}
    body.update(fields)
    response = client.post(f"{day_url(trip, day)}/items", json=body)
    assert response.status_code == 201, response.text
    return response.json()


class TestDayDetail:
    def test_it_returns_the_day_with_its_derived_stages(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = signed_in_client.get(day_url(trip)).json()

        assert body["date"] == DAY
        assert [stage["place"] for stage in body["stages"]] == ["Kuala Lumpur"]

    def test_a_travel_day_lists_both_stages_in_position_order(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = signed_in_client.get(day_url(trip, "2026-10-15")).json()

        assert [stage["place"] for stage in body["stages"]] == ["Kuala Lumpur", "Penang"]

    def test_a_day_in_no_stage_lists_none(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = signed_in_client.get(day_url(trip, "2026-10-10")).json()

        assert body["stages"] == []

    def test_the_first_day_has_no_previous(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The navigator disables rather than guesses at the boundary."""
        body = signed_in_client.get(day_url(trip, "2026-10-10")).json()

        assert body["previous_date"] is None
        assert body["next_date"] == "2026-10-11"

    def test_the_last_day_has_no_next(self, signed_in_client: TestClient, trip: dict) -> None:
        body = signed_in_client.get(day_url(trip, "2026-10-24")).json()

        assert body["previous_date"] == "2026-10-23"
        assert body["next_date"] is None

    def test_a_middle_day_has_both_neighbours(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = signed_in_client.get(day_url(trip, "2026-10-15")).json()

        assert body["previous_date"] == "2026-10-14"
        assert body["next_date"] == "2026-10-16"

    def test_a_date_outside_the_trip_answers_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Not an empty day: "this day is empty" and "this day is not part of the
        trip" must stay distinguishable."""
        response = signed_in_client.get(day_url(trip, "2026-11-01"))

        assert response.status_code == 404
        assert error_code(response) == "not_found"

    def test_another_owners_trip_answers_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.get(f"{TRIPS}/{uuid.uuid4()}/days/{DAY}")

        assert response.status_code == 404


class TestCreateItem:
    def test_it_creates_the_item(self, signed_in_client: TestClient, trip: dict) -> None:
        item = add_item(signed_in_client, trip, title="Batu Caves")

        assert item["title"] == "Batu Caves"
        assert item["kind"] == "activity"

    def test_the_status_defaults_to_to_plan(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        assert add_item(signed_in_client, trip)["status"] == "to_plan"

    def test_the_position_is_assigned_server_side(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The client never sends it: two tabs must not disagree about an order
        neither of them owns."""
        first = add_item(signed_in_client, trip, title="first")
        second = add_item(signed_in_client, trip, title="second")

        assert [first["position"], second["position"]] == [0, 1]

    def test_position_is_rejected_if_the_client_sends_it(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{day_url(trip)}/items", json={"kind": "activity", "title": "x", "position": 5}
        )

        assert response.status_code == 422
        assert error_code(response) == "validation_error"

    def test_positions_restart_within_each_day(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        add_item(signed_in_client, trip, day="2026-10-11")
        other = add_item(signed_in_client, trip, day="2026-10-12")

        assert other["position"] == 0

    def test_the_item_appears_on_the_day(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        add_item(signed_in_client, trip, title="Batu Caves")

        body = signed_in_client.get(day_url(trip)).json()

        assert [item["title"] for item in body["items"]] == ["Batu Caves"]

    def test_untimed_items_sort_after_timed_ones(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """"Sometime that day" is not "before breakfast"."""
        add_item(signed_in_client, trip, title="sometime")
        add_item(signed_in_client, trip, title="at seven", start_time="07:00")

        body = signed_in_client.get(day_url(trip)).json()

        assert [item["title"] for item in body["items"]] == ["at seven", "sometime"]

    def test_the_overnight_flight_is_accepted(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The case the span columns exist for — one item, not two halves."""
        item = add_item(
            signed_in_client,
            trip,
            day="2026-10-10",
            kind="transport",
            title="LOT LO79 WAW → KUL",
            start_time="23:50",
            end_time="14:00",
            end_date="2026-10-11",
        )

        assert item["end_date"] == "2026-10-11"

    def test_an_end_time_before_the_start_time_on_one_day_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{day_url(trip)}/items",
            json={"kind": "meal", "title": "dinner", "start_time": "20:00", "end_time": "18:00"},
        )

        assert response.status_code == 422
        assert error_code(response) == "invalid_time_span"

    def test_an_end_date_past_the_trip_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{day_url(trip)}/items",
            json={"kind": "accommodation", "title": "hotel", "end_date": "2026-10-30"},
        )

        assert response.status_code == 422
        assert error_code(response) == "invalid_time_span"

    def test_an_unknown_kind_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{day_url(trip)}/items", json={"kind": "submarine", "title": "x"}
        )

        assert response.status_code == 422

    def test_an_unknown_status_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{day_url(trip)}/items", json={"kind": "other", "title": "x", "status": "maybe"}
        )

        assert response.status_code == 422

    def test_adding_to_a_day_outside_the_trip_answers_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{day_url(trip, '2026-11-01')}/items", json={"kind": "other", "title": "x"}
        )

        assert response.status_code == 404


class TestUpdateItem:
    def test_it_updates_a_field(self, signed_in_client: TestClient, trip: dict) -> None:
        item = add_item(signed_in_client, trip)

        response = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"title": "Batu Caves at dawn"}
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Batu Caves at dawn"

    def test_it_moves_an_item_to_another_status(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The action the counter reacts to — the point of the day-detail screen."""
        item = add_item(signed_in_client, trip)

        response = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"status": "done"}
        )

        assert response.json()["status"] == "done"

    def test_an_omitted_field_is_left_alone(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip, start_time="09:00", notes="bring water")

        body = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"status": "done"}
        ).json()

        assert body["start_time"] == "09:00:00"
        assert body["notes"] == "bring water"

    def test_an_explicit_null_clears_the_field(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The distinction a plain `None` default would collapse: without it, an
        item could never lose a time it was given by mistake."""
        item = add_item(signed_in_client, trip, start_time="09:00")

        body = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"start_time": None}
        ).json()

        assert body["start_time"] is None

    def test_it_moves_an_item_to_another_day(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip, day="2026-10-11")

        signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"date": "2026-10-12"}
        )

        assert signed_in_client.get(day_url(trip, "2026-10-11")).json()["items"] == []
        assert len(signed_in_client.get(day_url(trip, "2026-10-12")).json()["items"]) == 1

    def test_a_moved_item_is_renumbered_into_its_new_day(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """It must not keep a position from a day it has left."""
        add_item(signed_in_client, trip, day="2026-10-12", title="already there")
        moved = add_item(signed_in_client, trip, day="2026-10-11", title="moving")

        body = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{moved['id']}", json={"date": "2026-10-12"}
        ).json()

        assert body["position"] == 1

    def test_moving_to_a_date_outside_the_trip_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip)

        response = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"date": "2026-11-01"}
        )

        assert response.status_code == 422
        assert error_code(response) == "date_outside_trip"

    def test_a_move_that_would_push_the_span_past_the_trip_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The span is re-validated against the *resulting* day, not the current one."""
        item = add_item(
            signed_in_client, trip, day="2026-10-11", end_date="2026-10-24", kind="accommodation"
        )

        response = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"date": "2026-10-12"}
        )

        assert response.status_code == 200, (
            "moving the start later does not move the end, so this one is still valid"
        )

        pushed = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"end_date": "2026-10-25"}
        )

        assert pushed.status_code == 422
        assert error_code(pushed) == "invalid_time_span"

    def test_an_unknown_item_answers_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{uuid.uuid4()}", json={"status": "done"}
        )

        assert response.status_code == 404

    def test_an_item_of_another_trip_answers_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """A cross-trip move is unreachable by construction: the trip id is in the
        path, so the item simply is not found."""
        other = create(signed_in_client, title="Portugalia", stages=[{"place": "Lizbona"}])
        item = add_item(signed_in_client, trip)

        response = signed_in_client.patch(
            f"{TRIPS}/{other['id']}/items/{item['id']}", json={"status": "done"}
        )

        assert response.status_code == 404


class TestDeleteItem:
    def test_it_removes_the_item(self, signed_in_client: TestClient, trip: dict) -> None:
        item = add_item(signed_in_client, trip)

        response = signed_in_client.delete(f"{TRIPS}/{trip['id']}/items/{item['id']}")

        assert response.status_code == 204
        assert signed_in_client.get(day_url(trip)).json()["items"] == []

    def test_it_leaves_the_other_items_alone(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        keep = add_item(signed_in_client, trip, title="keep")
        drop = add_item(signed_in_client, trip, title="drop")

        signed_in_client.delete(f"{TRIPS}/{trip['id']}/items/{drop['id']}")

        remaining = signed_in_client.get(day_url(trip)).json()["items"]
        assert [item["id"] for item in remaining] == [keep["id"]]

    def test_deleting_an_unknown_item_answers_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.delete(f"{TRIPS}/{trip['id']}/items/{uuid.uuid4()}")

        assert response.status_code == 404


class TestReadinessOnThePayloads:
    """R02's counter, on both the list row and the timeline."""

    def statuses(self, client: TestClient, trip: dict, *statuses: str) -> None:
        for index, status_value in enumerate(statuses):
            add_item(client, trip, title=f"item {index}", status=status_value)

    def test_a_trip_with_no_items_is_zero_of_zero(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()

        assert body["readiness"] == {"arranged": 0, "tracked": 0}

    def test_items_all_still_to_plan_are_zero_of_zero(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The case that proves the field is `tracked` and not `total`."""
        self.statuses(signed_in_client, trip, "to_plan", "to_plan", "to_plan")

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()

        assert body["readiness"] == {"arranged": 0, "tracked": 0}

    def test_the_served_figure_matches_the_domain_function(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The assertion that catches the two implementations drifting apart."""
        self.statuses(signed_in_client, trip, "done", "done", "to_book", "to_plan")

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()
        served = body["readiness"]

        every_item = [item for day in body["days"] for item in day["items"]]
        arranged, tracked = readiness(_WithStatus(item["status"]) for item in every_item)

        assert served == {"arranged": arranged, "tracked": tracked} == {
            "arranged": 2,
            "tracked": 3,
        }

    def test_the_list_row_carries_the_same_counter(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        self.statuses(signed_in_client, trip, "done", "to_book")

        row = next(
            candidate
            for candidate in signed_in_client.get(TRIPS).json()
            if candidate["id"] == trip["id"]
        )

        assert row["readiness"] == {"arranged": 1, "tracked": 2}

    def test_a_spanning_item_is_counted_once(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Rendered on its start day only, and counted there only."""
        add_item(
            signed_in_client,
            trip,
            day="2026-10-11",
            kind="accommodation",
            title="three nights",
            end_date="2026-10-14",
            status="done",
        )

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()

        assert body["readiness"] == {"arranged": 1, "tracked": 1}
        assert sum(len(day["items"]) for day in body["days"]) == 1

    def test_the_counter_reflects_a_status_change(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The whole loop: arrange one item in the day detail, read the counter."""
        item = add_item(signed_in_client, trip, status="to_book")

        signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"status": "done"}
        )

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()
        assert body["readiness"] == {"arranged": 1, "tracked": 1}


class _WithStatus:
    """Minimal stand-in so the domain function can be run over the JSON payload."""

    def __init__(self, status: str) -> None:
        self.status = status
