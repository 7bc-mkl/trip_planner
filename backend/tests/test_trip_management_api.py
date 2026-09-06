"""Editing and deleting a trip, and managing its stages.

Phase 4's backend. The rules under test all protect something the owner did not
ask to lose: an item, an attachment, a stage, or the route mode of the trip.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.test_attachments_api import (
    day_attachments_url,
    item_attachments_url,
    upload,
)
from tests.test_domain_uploads import make_pdf
from tests.test_items_api import add_item
from tests.test_trips_api import TRIPS, create, error_code
from trip_planner.db.models import Attachment, Item, Owner, Trip, TripDay, TripStage


@pytest.fixture
def trip(signed_in_client: TestClient) -> dict:
    return create(signed_in_client)


def patch(client: TestClient, trip: dict, **fields: object):
    return client.patch(f"{TRIPS}/{trip['id']}", json=fields)


def dates_of(client: TestClient, trip: dict) -> list[str]:
    return [day["date"] for day in client.get(f"{TRIPS}/{trip['id']}").json()["days"]]


class TestUpdateTripFields:
    def test_it_renames_a_trip(self, signed_in_client: TestClient, trip: dict) -> None:
        response = patch(signed_in_client, trip, title="Malezja i Singapur")

        assert response.status_code == 200
        assert response.json()["title"] == "Malezja i Singapur"

    def test_an_omitted_field_is_left_alone(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = patch(signed_in_client, trip, title="Nowa nazwa").json()

        assert body["departure_place"] == "Warszawa"
        assert body["start_date"] == "2026-10-10"

    def test_an_unknown_field_is_rejected(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        assert patch(signed_in_client, trip, colour="blue").status_code == 422

    def test_another_owners_trip_answers_404(self, signed_in_client: TestClient) -> None:
        response = signed_in_client.patch(f"{TRIPS}/{uuid.uuid4()}", json={"title": "x"})

        assert response.status_code == 404


class TestModeStability:
    """The rule that stops a typo correction from changing what kind of trip it is."""

    def test_editing_the_departure_place_rewrites_the_return_on_a_round_trip(
        self, signed_in_client: TestClient
    ) -> None:
        trip = create(signed_in_client, departure_place="Warszawa", return_place="Warszawa")

        body = patch(signed_in_client, trip, departure_place="Warsaw").json()

        assert body["departure_place"] == "Warsaw"
        assert body["return_place"] == "Warsaw", (
            "without the rewrite, correcting the departure city silently converts "
            "the round trip into an open-jaw one"
        )

    def test_the_rewrite_survives_a_whitespace_only_difference(
        self, signed_in_client: TestClient
    ) -> None:
        """The mode is derived by comparison, so it must use the same normalisation."""
        trip = create(signed_in_client, departure_place="Warszawa", return_place="Warszawa ")

        body = patch(signed_in_client, trip, departure_place="Kraków").json()

        assert body["return_place"] == "Kraków"

    def test_an_open_jaw_trip_is_left_alone(self, signed_in_client: TestClient) -> None:
        """The return place is a separate decision here and must not be overwritten."""
        trip = create(signed_in_client, departure_place="Warszawa", return_place="Katowice")

        body = patch(signed_in_client, trip, departure_place="Kraków").json()

        assert body["return_place"] == "Katowice"

    def test_a_one_way_trip_stays_one_way(self, signed_in_client: TestClient) -> None:
        trip = create(signed_in_client, return_place=None)

        body = patch(signed_in_client, trip, departure_place="Kraków").json()

        assert body["return_place"] is None

    def test_an_explicit_return_place_always_wins(
        self, signed_in_client: TestClient
    ) -> None:
        """The owner asked for a specific mode; the server must not overrule it."""
        trip = create(signed_in_client, departure_place="Warszawa", return_place="Warszawa")

        body = patch(
            signed_in_client, trip, departure_place="Kraków", return_place="Katowice"
        ).json()

        assert body["return_place"] == "Katowice"

    def test_an_explicit_null_switches_to_one_way(
        self, signed_in_client: TestClient
    ) -> None:
        trip = create(signed_in_client, departure_place="Warszawa", return_place="Warszawa")

        body = patch(signed_in_client, trip, return_place=None).json()

        assert body["return_place"] is None

    def test_the_round_trip_state_is_read_before_the_edit(
        self, signed_in_client: TestClient
    ) -> None:
        """Reading it afterwards would compare the new departure place against the
        old return place and conclude the trip was never a round trip."""
        trip = create(signed_in_client, departure_place="Warszawa", return_place="Warszawa")

        body = patch(signed_in_client, trip, departure_place="Gdańsk").json()

        assert body["return_place"] == "Gdańsk"


class TestDateRangeChanges:
    def test_extending_the_range_adds_days(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        patch(signed_in_client, trip, end_date="2026-10-26")

        dates = dates_of(signed_in_client, trip)

        assert len(dates) == 17
        assert dates[-1] == "2026-10-26"

    def test_extending_backwards_adds_days_at_the_start(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        patch(signed_in_client, trip, start_date="2026-10-08")

        dates = dates_of(signed_in_client, trip)

        assert dates[0] == "2026-10-08"

    def test_existing_days_and_items_are_untouched_by_an_extension(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        add_item(signed_in_client, trip, day="2026-10-11", title="Batu Caves")

        patch(signed_in_client, trip, end_date="2026-10-26")

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()
        eleventh = next(day for day in body["days"] if day["date"] == "2026-10-11")
        assert [item["title"] for item in eleventh["items"]] == ["Batu Caves"]

    def test_shortening_past_an_empty_day_removes_it(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """An empty day carries no decision, so dropping it loses nothing."""
        # The last stage ends on the 23rd, so shortening to the 23rd keeps them all.
        assert patch(signed_in_client, trip, end_date="2026-10-23").status_code == 200

        dates = dates_of(signed_in_client, trip)

        assert dates[-1] == "2026-10-23"
        assert len(dates) == 14

    def test_shortening_past_a_day_with_items_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        add_item(signed_in_client, trip, day="2026-10-23", title="Ostatni wieczór")

        response = patch(signed_in_client, trip, end_date="2026-10-22")

        assert response.status_code == 409
        assert error_code(response) == "days_have_items"

    def test_the_refusal_names_the_offending_dates(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        add_item(signed_in_client, trip, day="2026-10-23", title="a")
        add_item(signed_in_client, trip, day="2026-10-24", title="b")

        response = patch(signed_in_client, trip, end_date="2026-10-22")

        assert response.json()["error"]["field"] == "2026-10-23, 2026-10-24"

    def test_a_refused_shortening_changes_nothing(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """No item is ever destroyed by a date edit — and no half-edit is left."""
        add_item(signed_in_client, trip, day="2026-10-23", title="Ostatni wieczór")

        patch(signed_in_client, trip, end_date="2026-10-22", title="Nowa nazwa")

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()
        assert body["end_date"] == "2026-10-24"
        assert body["title"] == "Malezja, październik 2026"
        assert len(body["days"]) == 15

    def test_shortening_past_a_stage_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Symmetric with the day rule: a stage is a decision too."""
        response = patch(signed_in_client, trip, end_date="2026-10-20")

        assert response.status_code == 409
        assert error_code(response) == "stages_outside_new_range"

    def test_the_stage_refusal_names_the_stages(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = patch(signed_in_client, trip, end_date="2026-10-16")

        assert response.json()["error"]["field"] == "Penang, Langkawi"

    def test_an_inverted_range_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = patch(signed_in_client, trip, start_date="2026-10-30")

        assert response.status_code == 422
        assert error_code(response) == "invalid_date_range"

    def test_a_range_over_the_bound_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = patch(signed_in_client, trip, end_date="2028-10-24")

        assert response.status_code == 422
        assert error_code(response) == "trip_too_long"

    def test_shortening_past_a_surviving_items_span_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Regression: the third rule, which the first draft of this endpoint missed.

        A hotel booked on the 11th running to the trip's last day. Its own start
        day survives a shortening, so `days_have_items` says nothing — and before
        this check the trip was happily left ending on the 20th with an item
        claiming to end on the 24th, a state `validate_span` refuses to create.
        """
        # An undated stage, so the stage rule cannot fire first and mask this one.
        trip = create(signed_in_client, stages=[{"place": "Kuala Lumpur"}])
        add_item(
            signed_in_client,
            trip,
            day="2026-10-11",
            kind="accommodation",
            title="Nocleg: Mandarin Oriental KL",
            end_date="2026-10-24",
        )

        response = patch(signed_in_client, trip, end_date="2026-10-20")

        assert response.status_code == 409
        assert error_code(response) == "items_outside_new_range"

    def test_that_refusal_names_the_day_the_item_starts_on(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The start day is where the owner has to go to shorten the item."""
        trip = create(signed_in_client, stages=[{"place": "Kuala Lumpur"}])
        add_item(
            signed_in_client, trip, day="2026-10-11", kind="accommodation",
            title="Nocleg", end_date="2026-10-24",
        )

        response = patch(signed_in_client, trip, end_date="2026-10-20")

        assert response.json()["error"]["field"] == "2026-10-11"

    def test_that_refusal_changes_nothing(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        trip = create(signed_in_client, stages=[{"place": "Kuala Lumpur"}])
        add_item(
            signed_in_client, trip, day="2026-10-11", kind="accommodation",
            title="Nocleg", end_date="2026-10-24",
        )

        patch(signed_in_client, trip, end_date="2026-10-20")

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()
        assert body["end_date"] == "2026-10-24"
        assert len(body["days"]) == 15

    def test_a_span_that_still_fits_the_new_range_is_allowed(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The check must not refuse a shortening the item survives intact."""
        add_item(
            signed_in_client, trip, day="2026-10-11", kind="accommodation",
            title="Nocleg", end_date="2026-10-15",
        )

        assert patch(signed_in_client, trip, end_date="2026-10-23").status_code == 200

    def test_an_item_with_no_span_never_blocks_a_shortening(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """`end_date` is null for most items; they are none of this rule's business."""
        add_item(signed_in_client, trip, day="2026-10-11", title="Batu Caves")

        assert patch(signed_in_client, trip, end_date="2026-10-23").status_code == 200

    def test_shortening_the_start_past_a_span_is_refused_too(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The rule is about the range, not only its end.

        Trimming the front of the trip removes days an item's span may still
        point into, even though the trip's end never moved.
        """
        trip = create(signed_in_client, stages=[{"place": "Kuala Lumpur"}])
        add_item(
            signed_in_client, trip, day="2026-10-11", kind="accommodation",
            title="Nocleg", end_date="2026-10-13",
        )

        response = patch(signed_in_client, trip, start_date="2026-10-14")

        assert response.status_code == 409

    def test_shortening_past_a_day_holding_only_a_voucher_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """A day with a document and no items is not empty.

        Without this guard the day would be dropped silently and its voucher
        deleted by the cascade — a date edit destroying data, which A10 forbids.
        """
        upload(signed_in_client, day_attachments_url(trip, "2026-10-23"), make_pdf())

        response = patch(signed_in_client, trip, end_date="2026-10-22")

        assert response.status_code == 409
        assert error_code(response) == "days_have_attachments"
        assert response.json()["error"]["field"] == "2026-10-23"

    def test_that_refusal_changes_nothing_at_all(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        """Dates, days and the file itself all survive the refused edit."""
        stored = upload(
            signed_in_client, day_attachments_url(trip, "2026-10-23"), make_pdf()
        ).json()

        patch(signed_in_client, trip, end_date="2026-10-22", title="Nowa nazwa")

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()
        assert body["end_date"] == "2026-10-24"
        assert body["title"] == "Malezja, październik 2026"
        assert len(body["days"]) == 15
        assert db_session.get(Attachment, uuid.UUID(stored["id"])) is not None

    def test_shortening_past_a_day_with_neither_items_nor_files_still_removes_it(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The silent removal is narrowed, not withdrawn: a truly empty day still goes.

        A file on *another* day proves the guard looks at the days being dropped
        rather than at the trip as a whole.
        """
        upload(signed_in_client, day_attachments_url(trip, "2026-10-11"), make_pdf())

        assert patch(signed_in_client, trip, end_date="2026-10-23").status_code == 200
        assert dates_of(signed_in_client, trip)[-1] == "2026-10-23"

    def test_a_day_with_both_items_and_files_answers_days_have_items(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The deliberate choice: `days_have_items` wins when a day has both.

        Either code would be truthful. `days_have_items` is the one a client
        shipped before this feature already branches on, so keeping it means no
        existing client meets an unknown code for a case it already handles —
        and the owner's fix is the same either way: clear that day.
        """
        add_item(signed_in_client, trip, day="2026-10-23", title="Ostatni wieczór")
        upload(signed_in_client, day_attachments_url(trip, "2026-10-23"), make_pdf())

        response = patch(signed_in_client, trip, end_date="2026-10-22")

        assert response.status_code == 409
        assert error_code(response) == "days_have_items"

    def test_a_file_pinned_to_an_item_on_a_dropped_day_is_protected_too(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """`days_have_items` covers this today; the attachment guard does not rely on it."""
        item = add_item(signed_in_client, trip, day="2026-10-23", title="Nocleg")
        upload(signed_in_client, item_attachments_url(trip, item), make_pdf())

        assert patch(signed_in_client, trip, end_date="2026-10-22").status_code == 409

    def test_editing_only_the_title_leaves_the_days_alone(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The resize must not run — and must not churn rows — when nothing moved."""
        before = dates_of(signed_in_client, trip)

        patch(signed_in_client, trip, title="Nowa nazwa")

        assert dates_of(signed_in_client, trip) == before


class TestDeleteTrip:
    def test_it_deletes_the_trip(self, signed_in_client: TestClient, trip: dict) -> None:
        response = signed_in_client.delete(f"{TRIPS}/{trip['id']}")

        assert response.status_code == 204
        assert signed_in_client.get(f"{TRIPS}/{trip['id']}").status_code == 404

    def test_the_cascade_removes_stages_days_and_items(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        add_item(signed_in_client, trip, day="2026-10-11", title="Batu Caves")

        signed_in_client.delete(f"{TRIPS}/{trip['id']}")

        trip_id = uuid.UUID(trip["id"])
        assert db_session.scalar(
            sa.select(sa.func.count()).select_from(TripStage).where(TripStage.trip_id == trip_id)
        ) == 0
        assert db_session.scalar(
            sa.select(sa.func.count()).select_from(TripDay).where(TripDay.trip_id == trip_id)
        ) == 0
        assert db_session.scalar(sa.select(sa.func.count()).select_from(Item)) == 0

    def test_it_takes_none_of_another_trips_rows(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        other = create(signed_in_client, title="Portugalia", stages=[{"place": "Lizbona"}])
        add_item(signed_in_client, other, day="2026-10-11", title="Pasteis de Belem")

        signed_in_client.delete(f"{TRIPS}/{trip['id']}")

        kept = signed_in_client.get(f"{TRIPS}/{other['id']}").json()
        assert len(kept["days"]) == 15
        assert sum(len(day["items"]) for day in kept["days"]) == 1

    def test_deleting_an_unknown_trip_answers_404(
        self, signed_in_client: TestClient
    ) -> None:
        assert signed_in_client.delete(f"{TRIPS}/{uuid.uuid4()}").status_code == 404

    def test_another_owners_trip_cannot_be_deleted(
        self, signed_in_client: TestClient, db_session: OrmSession, other_owner: Owner
    ) -> None:
        from datetime import date

        theirs = Trip(
            owner_id=other_owner.id,
            title="Not yours",
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 11),
            departure_place="Gdańsk",
        )
        db_session.add(theirs)
        db_session.flush()

        assert signed_in_client.delete(f"{TRIPS}/{theirs.id}").status_code == 404
        assert db_session.get(Trip, theirs.id) is not None


class TestStages:
    def stages_of(self, client: TestClient, trip: dict) -> list[dict]:
        return client.get(f"{TRIPS}/{trip['id']}").json()["stages"]

    def test_it_appends_a_stage_at_the_end(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{TRIPS}/{trip['id']}/stages", json={"place": "Singapur"}
        )

        assert response.status_code == 201
        assert response.json()["position"] == 3

    def test_a_stage_outside_the_trip_range_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            f"{TRIPS}/{trip['id']}/stages",
            json={"place": "Singapur", "start_date": "2026-11-01", "end_date": "2026-11-03"},
        )

        assert response.status_code == 422
        assert error_code(response) == "stage_outside_trip"

    def test_it_edits_a_stage(self, signed_in_client: TestClient, trip: dict) -> None:
        stage = self.stages_of(signed_in_client, trip)[0]

        response = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/stages/{stage['id']}", json={"place": "KL"}
        )

        assert response.status_code == 200
        assert response.json()["place"] == "KL"

    def test_an_explicit_null_clears_a_stage_date(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Back to an undecided base — a real state, not a deletion."""
        stage = self.stages_of(signed_in_client, trip)[0]

        body = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/stages/{stage['id']}",
            json={"start_date": None, "end_date": None},
        ).json()

        assert body["start_date"] is None
        assert body["end_date"] is None

    def test_editing_a_stage_out_of_the_trip_range_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        stage = self.stages_of(signed_in_client, trip)[0]

        response = signed_in_client.patch(
            f"{TRIPS}/{trip['id']}/stages/{stage['id']}", json={"end_date": "2026-11-30"}
        )

        assert response.status_code == 422
        assert error_code(response) == "stage_outside_trip"

    def test_deleting_from_the_middle_keeps_positions_dense(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The property the deferred unique constraint exists for."""
        middle = self.stages_of(signed_in_client, trip)[1]

        assert (
            signed_in_client.delete(f"{TRIPS}/{trip['id']}/stages/{middle['id']}").status_code
            == 204
        )

        remaining = self.stages_of(signed_in_client, trip)
        assert [stage["position"] for stage in remaining] == [0, 1]
        assert [stage["place"] for stage in remaining] == ["Kuala Lumpur", "Langkawi"]

    def test_deleting_the_first_stage_keeps_positions_dense(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        first = self.stages_of(signed_in_client, trip)[0]

        signed_in_client.delete(f"{TRIPS}/{trip['id']}/stages/{first['id']}")

        assert [stage["position"] for stage in self.stages_of(signed_in_client, trip)] == [0, 1]

    def test_deleting_the_last_stage_needs_no_renumbering(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        last = self.stages_of(signed_in_client, trip)[2]

        signed_in_client.delete(f"{TRIPS}/{trip['id']}/stages/{last['id']}")

        assert [stage["position"] for stage in self.stages_of(signed_in_client, trip)] == [0, 1]

    def test_a_new_stage_after_a_delete_does_not_collide(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Proves the renumbering actually committed: appending computes max+1, so
        a stale position would produce a duplicate the constraint then rejects."""
        middle = self.stages_of(signed_in_client, trip)[1]
        signed_in_client.delete(f"{TRIPS}/{trip['id']}/stages/{middle['id']}")

        response = signed_in_client.post(
            f"{TRIPS}/{trip['id']}/stages", json={"place": "Singapur"}
        )

        assert response.status_code == 201
        assert response.json()["position"] == 2
        assert [stage["position"] for stage in self.stages_of(signed_in_client, trip)] == [0, 1, 2]

    def test_deleting_a_stage_keeps_the_days_and_items(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Days belong to the trip, not the stage. Only the derived label changes."""
        add_item(signed_in_client, trip, day="2026-10-12", title="Batu Caves")
        stage = self.stages_of(signed_in_client, trip)[0]

        signed_in_client.delete(f"{TRIPS}/{trip['id']}/stages/{stage['id']}")

        body = signed_in_client.get(f"{TRIPS}/{trip['id']}").json()
        twelfth = next(day for day in body["days"] if day["date"] == "2026-10-12")
        assert len(body["days"]) == 15
        assert [item["title"] for item in twelfth["items"]] == ["Batu Caves"]
        assert twelfth["stage_ids"] == [], "only the derived label changed"

    def test_the_last_stage_cannot_be_deleted(self, signed_in_client: TestClient) -> None:
        """R03 says one or more — a trip with no bases is a gap in the data."""
        trip = create(signed_in_client, stages=[{"place": "Kuala Lumpur"}])
        stage = self.stages_of(signed_in_client, trip)[0]

        response = signed_in_client.delete(f"{TRIPS}/{trip['id']}/stages/{stage['id']}")

        assert response.status_code == 422
        assert error_code(response) == "stages_required"

    def test_a_stage_of_another_trip_answers_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        other = create(signed_in_client, title="Portugalia", stages=[{"place": "Lizbona"}])
        stage = self.stages_of(signed_in_client, trip)[0]

        response = signed_in_client.delete(f"{TRIPS}/{other['id']}/stages/{stage['id']}")

        assert response.status_code == 404

    def test_stage_routes_require_a_session(self, client: TestClient) -> None:
        assert client.get(f"{TRIPS}/{uuid.uuid4()}").status_code == 401
