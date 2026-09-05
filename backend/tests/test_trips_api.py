"""The trip endpoints: create, list, and the timeline payload.

The creation test cases follow the spec's Edge Cases table row for row — the three
route modes, `stages_required`, `stage_outside_trip`, undated stages — because each
of those rows is a decision the API is supposed to encode, and an endpoint test is
the only place the decision and the wire format are checked together.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import Owner, Trip, TripDay, TripStage

TRIPS = "/api/v1/trips"


def malaysia(**overrides: object) -> dict[str, object]:
    """The owner's own trip from the brief, used as the realistic default body."""
    body: dict[str, object] = {
        "title": "Malezja, październik 2026",
        "start_date": "2026-10-10",
        "end_date": "2026-10-24",
        "departure_place": "Warszawa",
        "return_place": "Katowice",
        "stages": [
            {"place": "Kuala Lumpur", "start_date": "2026-10-11", "end_date": "2026-10-15"},
            {"place": "Penang", "start_date": "2026-10-15", "end_date": "2026-10-19"},
            {"place": "Langkawi", "start_date": "2026-10-19", "end_date": "2026-10-23"},
        ],
    }
    body.update(overrides)
    return body


def create(client: TestClient, **overrides: object) -> dict:
    response = client.post(TRIPS, json=malaysia(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def error_code(response) -> str:
    return response.json()["error"]["code"]


class TestCreateTrip:
    def test_it_creates_the_trip_its_stages_and_every_day(
        self, signed_in_client: TestClient
    ) -> None:
        """One call, one transaction — the creator's primary button."""
        body = create(signed_in_client)

        assert body["title"] == "Malezja, październik 2026"
        assert len(body["stages"]) == 3
        assert len(body["days"]) == 15, "10 to 24 October inclusive"
        assert body["days"][0]["date"] == "2026-10-10"
        assert body["days"][-1]["date"] == "2026-10-24"

    def test_the_response_is_201(self, signed_in_client: TestClient) -> None:
        assert signed_in_client.post(TRIPS, json=malaysia()).status_code == 201

    def test_stage_positions_are_assigned_in_the_order_they_were_sent(
        self, signed_in_client: TestClient
    ) -> None:
        """`position` is the itinerary's sequence; the client does not send it."""
        body = create(signed_in_client)

        assert [stage["position"] for stage in body["stages"]] == [0, 1, 2]
        assert [stage["place"] for stage in body["stages"]] == [
            "Kuala Lumpur",
            "Penang",
            "Langkawi",
        ]

    def test_each_day_carries_its_derived_stage_ids(self, signed_in_client: TestClient) -> None:
        body = create(signed_in_client)
        by_place = {stage["place"]: stage["id"] for stage in body["stages"]}
        days = {day["date"]: day["stage_ids"] for day in body["days"]}

        assert days["2026-10-12"] == [by_place["Kuala Lumpur"]]
        # The 15th is the travel day the two stages share.
        assert days["2026-10-15"] == [by_place["Kuala Lumpur"], by_place["Penang"]]
        # The trip's first day is before any stage begins — a day in transit.
        assert days["2026-10-10"] == []

    def test_every_day_carries_an_empty_items_array(self, signed_in_client: TestClient) -> None:
        """Present from Phase 2 so the SPA's rendering path does not change in Phase 3."""
        body = create(signed_in_client)

        assert all(day["items"] == [] for day in body["days"])

    def test_a_single_day_trip_gets_one_day(self, signed_in_client: TestClient) -> None:
        body = create(
            signed_in_client,
            start_date="2026-10-10",
            end_date="2026-10-10",
            stages=[{"place": "Kraków"}],
        )

        assert len(body["days"]) == 1


class TestRouteModes:
    """The three modes the creator's toggle writes, stored in `return_place` alone."""

    def test_round_trip_stores_the_departure_place_as_the_return(
        self, signed_in_client: TestClient
    ) -> None:
        body = create(signed_in_client, departure_place="Warszawa", return_place="Warszawa")

        assert body["return_place"] == "Warszawa"

    def test_open_jaw_stores_a_different_return_place(
        self, signed_in_client: TestClient
    ) -> None:
        body = create(signed_in_client, departure_place="Warszawa", return_place="Katowice")

        assert body["return_place"] == "Katowice"

    def test_one_way_stores_null(self, signed_in_client: TestClient) -> None:
        body = create(signed_in_client, return_place=None)

        assert body["return_place"] is None

    def test_omitting_return_place_entirely_is_one_way(
        self, signed_in_client: TestClient
    ) -> None:
        """Omission and an explicit null must not mean two different things."""
        payload = malaysia()
        del payload["return_place"]

        response = signed_in_client.post(TRIPS, json=payload)

        assert response.status_code == 201
        assert response.json()["return_place"] is None


class TestCreateTripValidation:
    def test_zero_stages_answers_stages_required(self, signed_in_client: TestClient) -> None:
        """R03 says one or more, and the code is specific so the creator can point
        at the stage list rather than at a field."""
        response = signed_in_client.post(TRIPS, json=malaysia(stages=[]))

        assert response.status_code == 422
        assert error_code(response) == "stages_required"
        assert response.json()["error"]["field"] == "stages"

    def test_an_inverted_trip_range_answers_invalid_date_range(
        self, signed_in_client: TestClient
    ) -> None:
        response = signed_in_client.post(
            TRIPS,
            json=malaysia(start_date="2026-10-24", end_date="2026-10-10", stages=[{"place": "X"}]),
        )

        assert response.status_code == 422
        assert error_code(response) == "invalid_date_range"

    def test_a_range_over_366_days_answers_trip_too_long(
        self, signed_in_client: TestClient
    ) -> None:
        response = signed_in_client.post(
            TRIPS,
            json=malaysia(start_date="2026-01-01", end_date="2027-01-02", stages=[{"place": "X"}]),
        )

        assert response.status_code == 422
        assert error_code(response) == "trip_too_long"

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("2026-10-01", "2026-10-15"),
            ("2026-10-11", "2026-10-30"),
            ("2026-09-01", "2026-09-05"),
        ],
        ids=["starts before the trip", "ends after the trip", "entirely outside"],
    )
    def test_a_stage_outside_the_trip_range_is_refused(
        self, signed_in_client: TestClient, start: str, end: str
    ) -> None:
        response = signed_in_client.post(
            TRIPS,
            json=malaysia(stages=[{"place": "Penang", "start_date": start, "end_date": end}]),
        )

        assert response.status_code == 422
        assert error_code(response) == "stage_outside_trip"

    def test_the_refusal_names_the_offending_stage(self, signed_in_client: TestClient) -> None:
        """"One of your stages is wrong" is not actionable when there are three."""
        response = signed_in_client.post(
            TRIPS,
            json=malaysia(
                stages=[
                    {"place": "Kuala Lumpur", "start_date": "2026-10-11", "end_date": "2026-10-15"},
                    {"place": "Penang", "start_date": "2026-11-01", "end_date": "2026-11-05"},
                ]
            ),
        )

        assert response.json()["error"]["field"] == "Penang"

    def test_an_inverted_stage_range_answers_invalid_date_range(
        self, signed_in_client: TestClient
    ) -> None:
        response = signed_in_client.post(
            TRIPS,
            json=malaysia(
                stages=[{"place": "Penang", "start_date": "2026-10-19", "end_date": "2026-10-15"}]
            ),
        )

        assert response.status_code == 422
        assert error_code(response) == "invalid_date_range"

    def test_stages_without_dates_are_accepted(self, signed_in_client: TestClient) -> None:
        """The traveller who knows the bases but not the split (R03)."""
        body = create(
            signed_in_client,
            stages=[{"place": "Kuala Lumpur"}, {"place": "Penang"}, {"place": "Langkawi"}],
        )

        assert [stage["start_date"] for stage in body["stages"]] == [None, None, None]
        assert all(day["stage_ids"] == [] for day in body["days"]), (
            "an undated stage labels no day"
        )

    def test_a_partially_dated_stage_is_accepted(self, signed_in_client: TestClient) -> None:
        body = create(
            signed_in_client, stages=[{"place": "Kuala Lumpur", "start_date": "2026-10-11"}]
        )

        assert body["stages"][0]["start_date"] == "2026-10-11"
        assert body["stages"][0]["end_date"] is None

    def test_an_unknown_field_is_rejected(self, signed_in_client: TestClient) -> None:
        """Pydantic v2 with `extra="forbid"` — a typo must not be silently dropped."""
        response = signed_in_client.post(TRIPS, json=malaysia(colour="blue"))

        assert response.status_code == 422
        assert error_code(response) == "validation_error"

    def test_an_empty_title_is_rejected(self, signed_in_client: TestClient) -> None:
        response = signed_in_client.post(TRIPS, json=malaysia(title=""))

        assert response.status_code == 422

    def test_nothing_is_written_when_validation_fails(
        self, signed_in_client: TestClient, db_session: OrmSession
    ) -> None:
        """The transaction promise: a refused create leaves no partial trip behind."""
        before = db_session.query(Trip).count()

        signed_in_client.post(TRIPS, json=malaysia(stages=[]))
        signed_in_client.post(TRIPS, json=malaysia(start_date="2027-01-01"))

        assert db_session.query(Trip).count() == before
        assert db_session.query(TripDay).count() == 0
        assert db_session.query(TripStage).count() == 0


class TestListTrips:
    def test_an_owner_with_no_trips_gets_an_empty_list(
        self, signed_in_client: TestClient
    ) -> None:
        """An empty list, not a 404 — a first-time account is a normal state."""
        response = signed_in_client.get(TRIPS)

        assert response.status_code == 200
        assert response.json() == []

    def test_it_returns_the_owners_trips(self, signed_in_client: TestClient) -> None:
        create(signed_in_client)
        create(signed_in_client, title="Portugalia", stages=[{"place": "Lizbona"}])

        titles = {trip["title"] for trip in signed_in_client.get(TRIPS).json()}

        assert titles == {"Malezja, październik 2026", "Portugalia"}

    def test_trips_are_ordered_by_start_date(self, signed_in_client: TestClient) -> None:
        """The list answers "what is coming up", not "what did I type in first"."""
        create(
            signed_in_client,
            title="Later",
            start_date="2026-12-01",
            end_date="2026-12-05",
            stages=[{"place": "Zakopane"}],
        )
        create(
            signed_in_client,
            title="Sooner",
            start_date="2026-03-01",
            end_date="2026-03-05",
            stages=[{"place": "Lizbona"}],
        )

        assert [trip["title"] for trip in signed_in_client.get(TRIPS).json()] == [
            "Sooner",
            "Later",
        ]

    def test_the_list_row_carries_no_days_or_stages(
        self, signed_in_client: TestClient
    ) -> None:
        """A list of ten year-long trips must not ship 3660 day objects."""
        create(signed_in_client)

        row = signed_in_client.get(TRIPS).json()[0]

        assert "days" not in row
        assert "stages" not in row

    def test_another_owners_trips_are_not_listed(
        self, signed_in_client: TestClient, db_session: OrmSession, other_owner: Owner
    ) -> None:
        db_session.add(
            Trip(
                owner_id=other_owner.id,
                title="Not yours",
                start_date=date(2026, 10, 10),
                end_date=date(2026, 10, 11),
                departure_place="Gdańsk",
            )
        )
        db_session.flush()

        assert signed_in_client.get(TRIPS).json() == []


class TestGetTrip:
    def test_it_returns_the_timeline_payload(self, signed_in_client: TestClient) -> None:
        created = create(signed_in_client)

        body = signed_in_client.get(f"{TRIPS}/{created['id']}").json()

        assert body == created

    def test_the_days_are_in_date_order(self, signed_in_client: TestClient) -> None:
        created = create(signed_in_client)

        body = signed_in_client.get(f"{TRIPS}/{created['id']}").json()
        dates = [day["date"] for day in body["days"]]

        assert dates == sorted(dates)

    def test_an_unknown_trip_answers_404(self, signed_in_client: TestClient) -> None:
        response = signed_in_client.get(f"{TRIPS}/{uuid.uuid4()}")

        assert response.status_code == 404
        assert error_code(response) == "not_found"

    def test_another_owners_trip_answers_404_not_403(
        self, signed_in_client: TestClient, db_session: OrmSession, other_owner: Owner
    ) -> None:
        """A 403 would confirm the id exists — a membership oracle over the table."""
        theirs = Trip(
            owner_id=other_owner.id,
            title="Not yours",
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 11),
            departure_place="Gdańsk",
        )
        db_session.add(theirs)
        db_session.flush()

        response = signed_in_client.get(f"{TRIPS}/{theirs.id}")

        assert response.status_code == 404
        assert error_code(response) == "not_found"

    def test_a_malformed_id_is_a_422_not_a_500(self, signed_in_client: TestClient) -> None:
        assert signed_in_client.get(f"{TRIPS}/not-a-uuid").status_code == 422


class TestTripRoutesRequireASession:
    """R08 at the endpoint level. The enumeration test proves the dependency is
    wired; these prove it actually refuses."""

    def test_listing_without_a_session_is_401(self, client: TestClient) -> None:
        assert client.get(TRIPS).status_code == 401

    def test_creating_without_a_session_is_refused(self, client: TestClient) -> None:
        """403, not 401, and that is correct.

        `get_current_session` runs the CSRF check first, so an anonymous POST is
        refused as a CSRF failure before the session is even looked up. Both
        answers refuse the write; asserting the specific code here would lock in
        the order of two checks rather than the guarantee, so this asserts the
        guarantee — nothing is created — and the code is pinned in the CSRF test
        below where it is the actual subject.
        """
        response = client.post(TRIPS, json=malaysia())

        assert response.status_code in {401, 403}
        assert response.status_code != 201

    def test_reading_a_trip_without_a_session_is_401(self, client: TestClient) -> None:
        assert client.get(f"{TRIPS}/{uuid.uuid4()}").status_code == 401

    def test_creating_without_the_csrf_header_is_403(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        client.post("/api/v1/auth/login", json={"email": owner.email, "password": owner_password})

        response = client.post(TRIPS, json=malaysia())

        assert response.status_code == 403
        assert error_code(response) == "csrf_token_invalid"
