"""End-to-end proof of the cascade chain from the spec's Data Model.

`attachment_blob` cascades from `attachment`, which cascades from `item` and
from `trip_day`, which cascade from `trip`. Steps 1.1 and 1.7 already put
`ON DELETE CASCADE` on every link, so this module is expected to be test-only
(spec, assumption A2): deleting a trip deletes its files, transactionally, with
no sweeper, no reaper and no eventual consistency. That is the strongest
operational argument for storing bytes in PostgreSQL, so it deserves a test
that fails loudly the day someone moves the bytes out or drops a link.

Every test also proves the *negative*: that the same operation leaves a second
trip's rows — including its blob rows, checked directly rather than inferred
from the attachment count — completely alone. That is the assertion that would
catch a cascade written against the wrong column.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.test_attachments_api import day_attachments_url, item_attachments_url, upload
from tests.test_domain_uploads import make_pdf
from tests.test_items_api import add_item
from tests.test_trips_api import TRIPS, create
from trip_planner.db.models import Attachment, AttachmentBlob, TripDay


@pytest.fixture
def trip(signed_in_client: TestClient) -> dict:
    return create(signed_in_client)


def item_url(trip: dict, item: dict) -> str:
    return f"{TRIPS}/{trip['id']}/items/{item['id']}"


def stored_on_item(client: TestClient, trip: dict, item: dict) -> dict:
    response = upload(client, item_attachments_url(trip, item), make_pdf())
    assert response.status_code == 201, response.text
    return response.json()


def stored_on_day(client: TestClient, trip: dict, day: str) -> dict:
    response = upload(client, day_attachments_url(trip, day), make_pdf())
    assert response.status_code == 201, response.text
    return response.json()


def attachment_exists(db_session: OrmSession, attachment_id: str) -> bool:
    return db_session.get(Attachment, uuid.UUID(attachment_id)) is not None


def blob_exists(db_session: OrmSession, attachment_id: str) -> bool:
    """A direct query against `attachment_blob` — never inferred from `attachment`."""
    return db_session.get(AttachmentBlob, uuid.UUID(attachment_id)) is not None


class TestDeletingAnItem:
    def test_it_removes_the_items_attachments_and_their_blobs(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        item = add_item(signed_in_client, trip)
        first = stored_on_item(signed_in_client, trip, item)
        second = stored_on_item(signed_in_client, trip, item)

        response = signed_in_client.delete(item_url(trip, item))

        assert response.status_code == 204
        for attachment_id in (first["id"], second["id"]):
            assert not attachment_exists(db_session, attachment_id)
            assert not blob_exists(db_session, attachment_id)

    def test_it_leaves_another_trips_attachments_and_blobs_alone(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        item = add_item(signed_in_client, trip)
        mine = stored_on_item(signed_in_client, trip, item)

        other = create(signed_in_client, title="Another trip")
        other_item = add_item(signed_in_client, other)
        theirs = stored_on_item(signed_in_client, other, other_item)

        response = signed_in_client.delete(item_url(trip, item))

        assert response.status_code == 204
        assert not attachment_exists(db_session, mine["id"])
        assert not blob_exists(db_session, mine["id"])
        assert attachment_exists(db_session, theirs["id"])
        assert blob_exists(db_session, theirs["id"])


class TestDeletingATrip:
    def test_it_removes_every_attachment_and_blob_item_and_day_parented(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        item = add_item(signed_in_client, trip)
        on_item = stored_on_item(signed_in_client, trip, item)
        on_day = stored_on_day(signed_in_client, trip, "2026-10-12")

        response = signed_in_client.delete(f"{TRIPS}/{trip['id']}")

        assert response.status_code == 204
        for attachment_id in (on_item["id"], on_day["id"]):
            assert not attachment_exists(db_session, attachment_id)
            assert not blob_exists(db_session, attachment_id)

    def test_it_leaves_another_trips_attachments_and_blobs_alone(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        item = add_item(signed_in_client, trip)
        stored_on_item(signed_in_client, trip, item)
        stored_on_day(signed_in_client, trip, "2026-10-12")

        other = create(signed_in_client, title="Another trip")
        other_item = add_item(signed_in_client, other)
        theirs_item_attachment = stored_on_item(signed_in_client, other, other_item)
        theirs_day_attachment = stored_on_day(signed_in_client, other, "2026-10-11")

        response = signed_in_client.delete(f"{TRIPS}/{trip['id']}")

        assert response.status_code == 204
        for attachment_id in (theirs_item_attachment["id"], theirs_day_attachment["id"]):
            assert attachment_exists(db_session, attachment_id)
            assert blob_exists(db_session, attachment_id)


class TestADayRemovedByADateRangeEdit:
    """The third parent in the chain: a `trip_day` dropped by shortening a range.

    Step 1.10 is about to make `PATCH /trips/{tripId}` refuse a range edit that
    would drop a day still holding attachments (`409 days_have_attachments`), so
    exercising this cascade through the endpoint today would pin a `204` that
    1.10's own Step is about to turn into a `409` — a test that would need
    rewriting the moment its sibling Step lands, for a behaviour the sibling
    Step, not this one, is supposed to fix. Instead this proves the cascade at
    exactly the level `_resize_days` operates on: deleting the `trip_day` row a
    range edit would drop, through Core SQL rather than `db.delete(day)`, so the
    assertion below is answered by the database's own `ON DELETE CASCADE` and
    not by the ORM's in-session bookkeeping of a relationship it was told to
    cascade. The session is committed and the rows are re-queried in a fresh
    statement for the same reason.
    """

    def _drop_day(self, db_session: OrmSession, trip_id: str, day: date) -> uuid.UUID:
        day_id = db_session.execute(
            sa.select(TripDay.id).where(
                TripDay.trip_id == uuid.UUID(trip_id), TripDay.date == day
            )
        ).scalar_one()

        db_session.execute(sa.delete(TripDay).where(TripDay.id == day_id))
        db_session.commit()
        return day_id

    def test_the_days_attachments_and_blobs_go_with_it(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        created = stored_on_day(signed_in_client, trip, "2026-10-12")

        day_id = self._drop_day(db_session, trip["id"], date(2026, 10, 12))

        assert db_session.get(TripDay, day_id) is None
        assert not attachment_exists(db_session, created["id"])
        assert not blob_exists(db_session, created["id"])

    def test_another_trips_day_is_untouched(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        stored_on_day(signed_in_client, trip, "2026-10-12")

        other = create(signed_in_client, title="Another trip")
        theirs = stored_on_day(signed_in_client, other, "2026-10-11")

        self._drop_day(db_session, trip["id"], date(2026, 10, 12))

        assert attachment_exists(db_session, theirs["id"])
        assert blob_exists(db_session, theirs["id"])
