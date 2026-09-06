"""The `attachment` table's constraints, asserted against the database.

Same reasoning as `test_models_item.py`: these go through `db_session.flush()`
and read the exception PostgreSQL raises, because the guarantee being tested is
that the *database* refuses. An attachment with no parent is unreachable, an
attachment with two parents means two contradictory things at once, and a fourth
content type would defeat the whole point of deriving the type from the bytes —
none of which may depend on every write path remembering to check.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session as OrmSession

from tests.test_models_item import make_item
from tests.test_models_trip import make_trip, rejected_by
from trip_planner.db.models import (
    ATTACHMENT_CONTENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    Attachment,
    AttachmentBlob,
    Item,
    Owner,
    TripDay,
)

SHA256_OF_NOTHING = "e" * 64


@pytest.fixture
def trip_day(db_session: OrmSession, owner: Owner) -> TripDay:
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    day = TripDay(trip_id=trip.id, date=date(2026, 10, 10))
    db_session.add(day)
    db_session.flush()
    return day


@pytest.fixture
def item(db_session: OrmSession, trip_day: TripDay) -> Item:
    record = make_item(trip_day)
    db_session.add(record)
    db_session.flush()
    return record


def make_attachment(**overrides: object) -> Attachment:
    fields: dict[str, object] = {
        "filename": "voucher.pdf",
        "content_type": "application/pdf",
        "byte_size": 2048,
        "sha256": SHA256_OF_NOTHING,
    }
    fields.update(overrides)
    return Attachment(**fields)


def test_the_database_rejects_an_attachment_with_two_parents(
    db_session: OrmSession, trip_day: TripDay, item: Item
) -> None:
    """A file pinned to both a day and an item means two contradictory things.

    It would show up twice, and deleting the item would delete a day attachment.
    """
    with rejected_by(db_session, "ck_attachment_exactly_one_parent"):
        db_session.add(make_attachment(trip_day_id=trip_day.id, item_id=item.id))


def test_the_database_rejects_an_attachment_with_no_parent(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    """An attachment nothing points at is storage nobody can reach or delete."""
    with rejected_by(db_session, "ck_attachment_exactly_one_parent"):
        db_session.add(make_attachment(trip_day_id=None, item_id=None))


def test_the_database_rejects_a_fourth_content_type(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    """The constraint that makes "derived from the bytes" structural.

    A write path that trusted the client's `Content-Type` header — or a future
    import script — still cannot land an HTML page or an executable in the table.
    """
    with rejected_by(db_session, "ck_attachment_content_type"):
        db_session.add(
            make_attachment(trip_day_id=trip_day.id, content_type="application/zip")
        )


@pytest.mark.parametrize("content_type", ATTACHMENT_CONTENT_TYPES)
def test_each_accepted_content_type_is_stored(
    db_session: OrmSession, trip_day: TripDay, content_type: str
) -> None:
    db_session.add(make_attachment(trip_day_id=trip_day.id, content_type=content_type))
    db_session.flush()  # no exception


@pytest.mark.parametrize("byte_size", [0, -1, MAX_ATTACHMENT_BYTES + 1])
def test_the_database_rejects_an_impossible_byte_size(
    db_session: OrmSession, trip_day: TripDay, byte_size: int
) -> None:
    """Zero bytes is not a document, and the per-file cap is not advisory."""
    with rejected_by(db_session, "ck_attachment_byte_size"):
        db_session.add(make_attachment(trip_day_id=trip_day.id, byte_size=byte_size))


def test_a_file_of_exactly_the_cap_is_accepted(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    db_session.add(make_attachment(trip_day_id=trip_day.id, byte_size=MAX_ATTACHMENT_BYTES))
    db_session.flush()  # no exception


def test_the_same_checksum_may_appear_twice(
    db_session: OrmSession, trip_day: TripDay, item: Item
) -> None:
    """The `sha256` index is not unique: one voucher on a day and on an item is two files."""
    db_session.add(make_attachment(trip_day_id=trip_day.id))
    db_session.add(make_attachment(item_id=item.id))
    db_session.flush()  # no exception


def test_deleting_an_attachment_deletes_its_bytes(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    attachment = make_attachment(trip_day_id=trip_day.id)
    attachment.blob = AttachmentBlob(data=b"%PDF-1.4 ...")
    db_session.add(attachment)
    db_session.flush()

    db_session.delete(attachment)
    db_session.flush()

    assert db_session.query(AttachmentBlob).count() == 0


def test_deleting_a_day_cascades_to_its_attachments_and_their_bytes(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    """The cascade that means deleting a trip needs no sweeper."""
    attachment = make_attachment(trip_day_id=trip_day.id)
    attachment.blob = AttachmentBlob(data=b"%PDF-1.4 ...")
    db_session.add(attachment)
    db_session.flush()

    db_session.delete(trip_day)
    db_session.flush()

    assert db_session.query(Attachment).count() == 0
    assert db_session.query(AttachmentBlob).count() == 0
