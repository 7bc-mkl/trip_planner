"""The inbox tables' constraints, asserted against the database.

Same reasoning as `test_models_attachment.py`: these go through
`db_session.flush()` and read the exception PostgreSQL raises, because what is
being tested is that the **database** refuses — not that some write path
remembers to check.

The widened parent `CHECK` gets its own attention here. Its old cases (zero
parents, two parents) live in `test_models_attachment.py` and were deliberately
left untouched by this slice: if widening the constraint had weakened it, those
tests would fail, which is exactly the signal wanted. What this file adds is the
third column's own cases — the new parent accepted alone, and refused alongside
either of the other two.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from tests.test_models_attachment import make_attachment
from tests.test_models_item import make_item
from tests.test_models_trip import make_trip, rejected_by
from trip_planner.db.models import (
    MAX_INBOUND_SUBJECT_CHARS,
    MAX_INBOUND_TEXT_CHARS,
    Attachment,
    AttachmentBlob,
    InboundDeliveryStatus,
    InboundMessage,
    InboundTrustedSender,
    Owner,
    Trip,
    TripDay,
    normalise_address,
)


def make_message(owner: Owner, **overrides: object) -> InboundMessage:
    fields: dict[str, object] = {
        "owner_id": owner.id,
        "ses_message_id": f"ses-{uuid.uuid4().hex}",
        "s3_object_key": "inbox/ses-1",
        "ses_sender_verdict": "PASS",
        "ses_scan_verdict": "PASS",
        "received_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        "from_address": "owner@example.com",
        "subject": "Potwierdzenie rezerwacji",
        "state": "received",
    }
    fields.update(overrides)
    return InboundMessage(**fields)


@pytest.fixture
def trip(db_session: OrmSession, owner: Owner) -> Trip:
    record = make_trip(owner)
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def message(db_session: OrmSession, owner: Owner) -> InboundMessage:
    record = make_message(owner)
    db_session.add(record)
    db_session.flush()
    return record


# --------------------------------------------------------------------------- #
# The idempotency boundary
# --------------------------------------------------------------------------- #


def test_the_same_ses_message_id_cannot_be_stored_twice_for_one_owner(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """SNS delivers at least once, so the duplicate is routine rather than exotic.

    The unique key is what turns a redelivered notification into an idempotent
    success instead of a second copy of the same confirmation.
    """
    with rejected_by(db_session, "uq_inbound_message_ses_id"):
        db_session.add(make_message(owner, ses_message_id=message.ses_message_id))


def test_the_same_ses_message_id_is_allowed_for_a_different_owner(
    db_session: OrmSession, message: InboundMessage, other_owner: Owner
) -> None:
    """The key is `(owner_id, ses_message_id)`, and the owner half is not decoration.

    D15 says there is one owner today; the column is what keeps that a fact about
    the deployment rather than a premise baked into the schema.
    """
    db_session.add(make_message(other_owner, ses_message_id=message.ses_message_id))
    db_session.flush()


def test_the_database_rejects_an_unknown_state(db_session: OrmSession, owner: Owner) -> None:
    with rejected_by(db_session, "ck_inbound_message_state"):
        db_session.add(make_message(owner, state="processing"))


def test_the_database_rejects_a_subject_past_its_bound(
    db_session: OrmSession, owner: Owner
) -> None:
    """The endpoint truncates; the constraint is what makes truncation structural."""
    with rejected_by(db_session, "ck_inbound_message_subject"):
        db_session.add(make_message(owner, subject="x" * (MAX_INBOUND_SUBJECT_CHARS + 1)))


def test_the_database_rejects_a_text_body_past_its_bound(
    db_session: OrmSession, owner: Owner
) -> None:
    with rejected_by(db_session, "ck_inbound_message_text_body"):
        db_session.add(make_message(owner, text_body="x" * (MAX_INBOUND_TEXT_CHARS + 1)))


def test_a_message_defaults_to_pending_ingest_with_no_body(
    db_session: OrmSession, owner: Owner
) -> None:
    """The state a verified SNS event is committed in, before any S3 byte is fetched."""
    record = InboundMessage(
        owner_id=owner.id,
        ses_message_id=f"ses-{uuid.uuid4().hex}",
        s3_object_key="inbox/ses-9",
        ses_sender_verdict="PASS",
        ses_scan_verdict="PASS",
        received_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        from_address="owner@example.com",
        subject="Potwierdzenie",
    )
    db_session.add(record)
    db_session.flush()
    db_session.refresh(record)

    assert record.state == "pending_ingest"
    assert record.text_body == ""
    assert record.attempts == 0


# --------------------------------------------------------------------------- #
# A deleted trip unroutes its mail; a deleted message takes its documents
# --------------------------------------------------------------------------- #


def test_deleting_a_trip_returns_its_mail_to_the_unrouted_queue(
    db_session: OrmSession, owner: Owner, trip: Trip
) -> None:
    """`ON DELETE SET NULL`, and the distinction from `CASCADE` is the whole point.

    Deleting a trip must not silently destroy the confirmations that arrived for
    it. The message survives with no trip, which is the honest state and is
    exactly what the unrouted queue is for.
    """
    record = make_message(owner, trip_id=trip.id, state="routed")
    db_session.add(record)
    db_session.flush()

    db_session.execute(sa.delete(Trip).where(Trip.id == trip.id))
    db_session.flush()
    db_session.refresh(record)

    assert record.trip_id is None


def test_deleting_a_message_deletes_its_documents_and_their_bytes(
    db_session: OrmSession, message: InboundMessage
) -> None:
    """Transactionally, like every other delete in this product — no sweeper."""
    attachment = make_attachment(inbound_message_id=message.id)
    db_session.add(attachment)
    db_session.flush()
    db_session.add(AttachmentBlob(attachment_id=attachment.id, data=b"%PDF-1.4 ..."))
    db_session.flush()
    attachment_id = attachment.id

    db_session.execute(sa.delete(InboundMessage).where(InboundMessage.id == message.id))
    db_session.flush()
    # The database did the deleting, so the session's identity map still holds
    # the rows it loaded. Expiring is what makes the assertion a question about
    # the table rather than about what this session happens to remember.
    db_session.expire_all()

    assert db_session.get(Attachment, attachment_id) is None
    assert db_session.get(AttachmentBlob, attachment_id) is None


# --------------------------------------------------------------------------- #
# The widened parent CHECK — the third column's own cases
# --------------------------------------------------------------------------- #


def test_an_inbound_message_is_an_accepted_third_parent(
    db_session: OrmSession, message: InboundMessage
) -> None:
    """The widening, from the only angle that proves it happened."""
    db_session.add(make_attachment(inbound_message_id=message.id))
    db_session.flush()


@pytest.mark.parametrize("other_parent", ["trip_day", "item"])
def test_the_database_rejects_an_inbox_document_that_also_has_a_plan_parent(
    db_session: OrmSession,
    message: InboundMessage,
    trip: Trip,
    other_parent: str,
) -> None:
    """Still *exactly* one parent — the widening changed the arity, not the rule.

    A row parented to both a message and an item is the state an approval would
    produce if it set `item_id` and forgot to clear `inbound_message_id`. It has
    to be unrepresentable, or the document shows up in the plan and in the inbox
    at once and each place's delete is a surprise to the other.
    """
    day = TripDay(trip_id=trip.id, date=date(2026, 10, 10))
    db_session.add(day)
    db_session.flush()

    parents: dict[str, object] = {"inbound_message_id": message.id}
    if other_parent == "trip_day":
        parents["trip_day_id"] = day.id
    else:
        item = make_item(day)
        db_session.add(item)
        db_session.flush()
        parents["item_id"] = item.id

    with rejected_by(db_session, "ck_attachment_exactly_one_parent"):
        db_session.add(make_attachment(**parents))


def test_approval_re_points_a_document_without_copying_bytes(
    db_session: OrmSession, message: InboundMessage, trip: Trip
) -> None:
    """The move an approval makes, asserted at the level it actually happens.

    Phase 3 writes this statement; the *schema* has to permit it now, and the
    property worth locking down is that it is an `UPDATE` of one row — the blob
    is untouched, so a 9 MB voucher is never duplicated and never rewritten.
    """
    day = TripDay(trip_id=trip.id, date=date(2026, 10, 10))
    db_session.add(day)
    db_session.flush()
    item = make_item(day)
    db_session.add(item)
    db_session.flush()

    attachment = make_attachment(inbound_message_id=message.id)
    db_session.add(attachment)
    db_session.flush()

    db_session.execute(
        sa.update(Attachment)
        .where(Attachment.id == attachment.id)
        .values(item_id=item.id, inbound_message_id=None)
    )
    db_session.flush()
    db_session.refresh(attachment)

    assert attachment.item_id == item.id
    assert attachment.inbound_message_id is None


def test_sent_externally_at_is_null_on_every_document_phase_one_stores(
    db_session: OrmSession, message: InboundMessage
) -> None:
    """Phase 1 has no model and therefore no egress. The column ships unwritten."""
    attachment = make_attachment(inbound_message_id=message.id)
    db_session.add(attachment)
    db_session.flush()
    db_session.refresh(attachment)

    assert attachment.sent_externally_at is None


# --------------------------------------------------------------------------- #
# The two small tables
# --------------------------------------------------------------------------- #


def test_an_owner_has_at_most_one_delivery_status(
    db_session: OrmSession, owner: Owner
) -> None:
    """The primary key *is* the foreign key, so "one row per owner" is schema.

    Otherwise whichever code path upserts it decides, and a second row makes the
    screen's freshness claim depend on which one the query happened to read.
    """
    db_session.add(InboundDeliveryStatus(owner_id=owner.id))
    db_session.flush()

    with rejected_by(db_session, "inbound_delivery_status_pkey"):
        db_session.add(InboundDeliveryStatus(owner_id=owner.id))


def test_trusting_the_same_address_twice_is_refused_by_the_key(
    db_session: OrmSession, owner: Owner
) -> None:
    """A no-op at the schema level, so the union query never has to de-duplicate."""
    address = normalise_address("Rezerwacje@Airline.example ")
    db_session.add(InboundTrustedSender(owner_id=owner.id, address=address))
    db_session.flush()

    with rejected_by(db_session, "inbound_trusted_sender_pkey"):
        db_session.add(InboundTrustedSender(owner_id=owner.id, address=address))


def test_normalise_address_is_the_form_the_policy_compares_on() -> None:
    assert normalise_address("  Rezerwacje@Airline.Example  ") == "rezerwacje@airline.example"


def test_a_message_repr_carries_neither_subject_nor_body(
    db_session: OrmSession, owner: Owner
) -> None:
    """Both are the owner's own mail and have no business in a log line."""
    record = make_message(owner, subject="Rezerwacja KL-4411", text_body="PNR: SX-9912L")
    rendered = repr(record)

    assert "KL-4411" not in rendered
    assert "SX-9912L" not in rendered
