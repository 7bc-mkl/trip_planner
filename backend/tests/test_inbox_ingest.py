"""Ingestion: the sender policy, the bounded fetch, and what is stored afterwards.

The S3 client is a stub that **records every call**, because the claims worth
testing here are largely about calls that must *not* happen: a rejected sender
causes no GET, and a message is committed before its object is deleted. A stub
that only returned bytes would let both regress silently.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from email.message import EmailMessage

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from tests.test_domain_uploads import make_pdf, make_png
from trip_planner.config import InboxSettings
from trip_planner.db.models import (
    Attachment,
    AttachmentBlob,
    InboundDeliveryStatus,
    InboundMessage,
    InboundTrustedSender,
    Owner,
)
from trip_planner.inbound.ingest import (
    MAX_INGEST_ATTEMPTS,
    allowed_senders_for,
    claim_pending,
    delete_ingested_object,
    ingest_message,
)
from trip_planner.inbound.ses import ObjectGone

PREFIX = "inbound/"

INBOX = InboxSettings(
    recipient="inbox@mail.planner.example.com",
    aws_region="eu-central-1",
    sns_topic_arn="arn:aws:sns:eu-central-1:123456789012:trip-planner-inbound",
    s3_bucket="trip-planner-inbound-mime",
    s3_prefix=PREFIX,
    allowed_senders=frozenset({"rezerwacje@airline.example"}),
    max_message_bytes=40 * 1024 * 1024,
)


class StubS3:
    """An S3 that records what it was asked to do, and can be told to misbehave.

    Deliberately not a mock of `boto3`: the unit under test talks to `S3Fetcher`,
    so standing in for that seam keeps the tests about ingestion rather than
    about botocore's call shapes.
    """

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = objects or {}
        self.fetched: list[str] = []
        self.deleted: list[str] = []
        self.fail_with: Exception | None = None

    def fetch(self, key: str) -> bytes:
        self.fetched.append(key)
        if self.fail_with is not None:
            raise self.fail_with
        if key not in self.objects:
            raise ObjectGone(key)
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)


def mime(
    *,
    sender: str = "owner@example.com",
    text: str = "PNR: SX-9912L",
    documents: list[tuple[str, bytes, str]] | None = None,
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = "Potwierdzenie rezerwacji"
    message.set_content(text)
    for filename, data, content_type in documents or []:
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return message.as_bytes()


@pytest.fixture
def message(db_session: OrmSession, owner: Owner) -> InboundMessage:
    record = InboundMessage(
        owner_id=owner.id,
        ses_message_id=f"ses-{uuid.uuid4().hex}",
        s3_object_key=f"{PREFIX}ses-1",
        ses_sender_verdict="PASS",
        ses_scan_verdict="PASS",
        received_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        from_address=owner.email,
        subject="Potwierdzenie rezerwacji",
        state="pending_ingest",
    )
    db_session.add(record)
    db_session.flush()
    return record


def run(db: OrmSession, message: InboundMessage, owner: Owner, s3: StubS3):
    return ingest_message(db, message, owner=owner, inbox=INBOX, fetcher=s3)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# The allow-list
# --------------------------------------------------------------------------- #


def test_the_owner_s_own_address_is_always_allowed_without_being_configured(
    db_session: OrmSession, owner: Owner
) -> None:
    """An installation where he cannot forward his own mail to himself is broken.

    Requiring him to list himself is a configuration step whose only possible
    outcome is forgetting it.
    """
    assert owner.email.lower() in allowed_senders_for(db_session, owner, INBOX)


def test_the_allow_list_unions_configuration_and_what_the_owner_trusted(
    db_session: OrmSession, owner: Owner
) -> None:
    db_session.add(
        InboundTrustedSender(owner_id=owner.id, address="hotel@booking.example")
    )
    db_session.flush()

    allowed = allowed_senders_for(db_session, owner, INBOX)

    assert {"rezerwacje@airline.example", "hotel@booking.example"} <= allowed


# --------------------------------------------------------------------------- #
# The sender policy runs before the GET — the claim, and its proof
# --------------------------------------------------------------------------- #


def test_an_unknown_sender_is_quarantined_and_causes_no_s3_read(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """Nothing an unknown sender writes ever enters this application's storage.

    The assertion that carries the claim is `s3.fetched == []`: the quarantine
    row alone would be satisfied by a version that downloaded the MIME and then
    threw it away, which is a different — and much weaker — control.
    """
    message.from_address = "stranger@example.net"
    s3 = StubS3({f"{PREFIX}ses-1": mime()})

    outcome = run(db_session, message, owner, s3)

    assert outcome.state == "quarantined"
    assert outcome.reason == "unknown_sender"
    assert s3.fetched == []
    assert message.text_body == ""
    assert message.attachments == []


def test_an_allow_listed_sender_failing_dmarc_is_quarantined_without_a_read(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    message.ses_sender_verdict = "FAIL"
    s3 = StubS3({f"{PREFIX}ses-1": mime()})

    outcome = run(db_session, message, owner, s3)

    assert outcome.reason == "failed_authentication"
    assert s3.fetched == []


def test_a_failed_scan_is_quarantined_without_a_read(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    message.ses_scan_verdict = "FAIL"
    s3 = StubS3({f"{PREFIX}ses-1": mime()})

    outcome = run(db_session, message, owner, s3)

    assert outcome.reason == "failed_scan"
    assert s3.fetched == []


def test_a_message_recorded_with_an_unknown_verdict_quarantines(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """The endpoint stores "unknown" when SES reported nothing; it is not a pass."""
    message.ses_sender_verdict = "unknown"
    s3 = StubS3({f"{PREFIX}ses-1": mime()})

    assert run(db_session, message, owner, s3).state == "quarantined"
    assert s3.fetched == []


# --------------------------------------------------------------------------- #
# The accepted path
# --------------------------------------------------------------------------- #


def test_an_accepted_message_stores_its_text(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    s3 = StubS3({f"{PREFIX}ses-1": mime(text="PNR: SX-9912L")})

    outcome = run(db_session, message, owner, s3)

    assert outcome.state == "received"
    assert message.state == "received"
    assert message.text_body == "PNR: SX-9912L"
    assert s3.fetched == [f"{PREFIX}ses-1"]


def test_an_accepted_message_stores_its_documents_on_the_shipped_table(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """One attachment table, one blob table — the data claim, asserted directly."""
    s3 = StubS3(
        {f"{PREFIX}ses-1": mime(documents=[("voucher.pdf", make_pdf(), "application/pdf")])}
    )

    outcome = run(db_session, message, owner, s3)
    db_session.flush()

    assert outcome.documents_stored == 1
    stored = db_session.execute(
        sa.select(Attachment).where(Attachment.inbound_message_id == message.id)
    ).scalar_one()
    assert stored.filename == "voucher.pdf"
    assert stored.content_type == "application/pdf"
    assert stored.item_id is None and stored.trip_day_id is None
    assert db_session.get(AttachmentBlob, stored.id) is not None


def test_an_unsupported_part_is_dropped_while_the_text_survives(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """A calendar invite rides along with most airline confirmations.

    Losing the confirmation because of it would be the feature failing at the
    one thing it exists for.
    """
    s3 = StubS3(
        {
            f"{PREFIX}ses-1": mime(
                text="Twoj lot",
                documents=[("plan.ics", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", "text/calendar")],
            )
        }
    )

    outcome = run(db_session, message, owner, s3)

    assert outcome.state == "received"
    assert message.text_body == "Twoj lot"
    assert outcome.documents_stored == 0
    assert outcome.documents_dropped == 1


def test_the_derived_type_wins_over_the_declared_one(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    s3 = StubS3({f"{PREFIX}ses-1": mime(documents=[("mapa.pdf", make_png(), "application/pdf")])})

    run(db_session, message, owner, s3)
    db_session.flush()

    stored = db_session.execute(
        sa.select(Attachment).where(Attachment.inbound_message_id == message.id)
    ).scalar_one()
    assert stored.content_type == "image/png"


def test_a_message_from_an_address_the_owner_trusted_is_accepted(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """The recovery action's whole purpose, exercised through ingestion."""
    message.from_address = "hotel@booking.example"
    db_session.add(InboundTrustedSender(owner_id=owner.id, address="hotel@booking.example"))
    db_session.flush()
    s3 = StubS3({f"{PREFIX}ses-1": mime(sender="hotel@booking.example")})

    assert run(db_session, message, owner, s3).state == "received"


# --------------------------------------------------------------------------- #
# Failure, and the difference between its kinds
# --------------------------------------------------------------------------- #


def test_a_transient_s3_failure_leaves_the_message_retryable(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    s3 = StubS3()
    s3.fail_with = TimeoutError("s3 timed out")

    outcome = run(db_session, message, owner, s3)

    assert outcome.state == "pending_ingest"
    assert message.attempts == 1
    # A code, never the exception's text: third-party prose can echo the mail's
    # own content back into our logs and our database.
    assert message.last_error == "ingest_failed"


def test_a_transient_failure_stamps_the_freshness_row(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """So the screen cannot show "nothing new" through a day of failing ingestion."""
    s3 = StubS3()
    s3.fail_with = TimeoutError("s3 timed out")

    run(db_session, message, owner, s3)
    db_session.flush()

    status_row = db_session.get(InboundDeliveryStatus, owner.id)
    assert status_row is not None
    assert status_row.last_error == "ingest_failed"
    assert status_row.last_error_at is not None


def test_repeated_failures_land_the_message_in_the_queue_rather_than_looping(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """A broken integration degrades to a queue to clear by hand, never to lost mail.

    "Still retrying" is indistinguishable from "working" to the owner; a message
    in the unrouted queue with a reason is not.
    """
    s3 = StubS3()
    s3.fail_with = TimeoutError("s3 timed out")

    for _ in range(MAX_INGEST_ATTEMPTS):
        outcome = run(db_session, message, owner, s3)

    assert outcome.state == "unrouted"
    assert message.routing_reason == "ingest_failed"
    # The headers are still there, so it is a real piece of mail he can look at.
    assert message.subject == "Potwierdzenie rezerwacji"


def test_an_expired_object_goes_straight_to_the_queue_without_burning_retries(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """Not retryable, so retrying would spend the cap and keep it looking merely slow."""
    outcome = run(db_session, message, owner, StubS3())

    assert outcome.state == "unrouted"
    assert message.last_error == "inbox_object_unavailable"
    assert message.attempts == 0


# --------------------------------------------------------------------------- #
# Commit before delete
# --------------------------------------------------------------------------- #


def test_ingestion_itself_never_deletes_the_s3_object(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """The delete is the caller's, **after** the commit.

    This is the crash-safety property stated as an assertion: a process that dies
    between ingesting and deleting leaves a stored message and an orphaned object
    the lifecycle rule expires. The other order would leave no object and no
    message, which is the one outcome that loses the owner's mail.
    """
    s3 = StubS3({f"{PREFIX}ses-1": mime()})

    run(db_session, message, owner, s3)

    assert s3.deleted == []
    assert message.state == "received"
    assert message.s3_object_key == f"{PREFIX}ses-1"


def test_a_failed_delete_is_survivable_and_says_so(
    db_session: OrmSession, owner: Owner
) -> None:
    class Unreliable(StubS3):
        def delete(self, key: str) -> None:
            raise TimeoutError("s3 delete timed out")

    assert delete_ingested_object(Unreliable(), f"{PREFIX}ses-1") is False  # type: ignore[arg-type]


def test_a_successful_delete_reports_success(db_session: OrmSession) -> None:
    s3 = StubS3({f"{PREFIX}ses-1": mime()})

    assert delete_ingested_object(s3, f"{PREFIX}ses-1") is True  # type: ignore[arg-type]
    assert s3.deleted == [f"{PREFIX}ses-1"]


# --------------------------------------------------------------------------- #
# Claiming work
# --------------------------------------------------------------------------- #


def test_only_pending_and_deferred_messages_are_claimed(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """A `received` message must never be ingested twice — that is what would
    duplicate its documents onto the same row."""
    for state in ("received", "quarantined", "routed", "unrouted", "discarded"):
        db_session.add(
            InboundMessage(
                owner_id=owner.id,
                ses_message_id=f"ses-{state}-{uuid.uuid4().hex}",
                ses_sender_verdict="PASS",
                ses_scan_verdict="PASS",
                received_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
                from_address=owner.email,
                subject=state,
                state=state,
            )
        )
    db_session.flush()

    claimed = claim_pending(db_session)

    assert [one.id for one in claimed] == [message.id]


def test_a_deferred_message_is_claimed_again(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """An exhausted inbound window is a later retry, not a refusal."""
    message.state = "deferred"
    db_session.flush()

    assert [one.id for one in claim_pending(db_session)] == [message.id]


def test_claimed_messages_come_oldest_first(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    older = InboundMessage(
        owner_id=owner.id,
        ses_message_id=f"ses-{uuid.uuid4().hex}",
        s3_object_key=f"{PREFIX}ses-0",
        ses_sender_verdict="PASS",
        ses_scan_verdict="PASS",
        received_at=datetime(2026, 9, 30, 9, 0, tzinfo=UTC),
        from_address=owner.email,
        subject="Wczesniejsza",
        state="pending_ingest",
    )
    db_session.add(older)
    db_session.flush()

    assert [one.id for one in claim_pending(db_session)] == [older.id, message.id]


# --------------------------------------------------------------------------- #
# The inbox's own budget, and the shipped one it must not touch
# --------------------------------------------------------------------------- #


def test_an_exhausted_inbound_window_defers_without_reading_from_s3(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """Deferred, **not** quarantined — and the distinction matters to the owner.

    Quarantine is the sender policy's answer and means *we will not take this*.
    A full window means *not right now*: the row keeps its S3 locator and the
    worker picks it up again when capacity returns.
    """
    from trip_planner.security.quota import InboxQuota, set_inbox_quota

    s3 = StubS3({f"{PREFIX}ses-1": mime()})
    set_inbox_quota(InboxQuota(max_messages_per_window=1))
    try:
        outcome = run(db_session, message, owner, s3)
    finally:
        set_inbox_quota(InboxQuota())

    assert outcome.state == "deferred"
    assert outcome.reason == "inbox_rate_limited"
    assert s3.fetched == []
    assert message.s3_object_key == f"{PREFIX}ses-1"


def test_a_deferred_message_is_ingested_once_capacity_returns(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """The retry the deferral promises, exercised rather than assumed."""
    from trip_planner.security.quota import InboxQuota, set_inbox_quota

    s3 = StubS3({f"{PREFIX}ses-1": mime(text="PNR: SX-9912L")})
    set_inbox_quota(InboxQuota(max_messages_per_window=1))
    try:
        assert run(db_session, message, owner, s3).state == "deferred"
    finally:
        set_inbox_quota(InboxQuota())

    assert [one.id for one in claim_pending(db_session)] == [message.id]
    assert run(db_session, message, owner, s3).state == "received"
    assert message.text_body == "PNR: SX-9912L"


def test_a_full_inbox_defers_the_whole_message_rather_than_dropping_its_documents(
    db_session: OrmSession, owner: Owner, message: InboundMessage
) -> None:
    """Storing the text and dropping the voucher would lose a document to a
    ceiling the owner can clear in one click. Nothing is stored instead."""
    from trip_planner.security.quota import InboxQuota, set_inbox_quota

    s3 = StubS3(
        {f"{PREFIX}ses-1": mime(documents=[("voucher.pdf", make_pdf(), "application/pdf")])}
    )
    set_inbox_quota(InboxQuota(max_inbox_bytes=1))
    try:
        outcome = run(db_session, message, owner, s3)
    finally:
        set_inbox_quota(InboxQuota())

    assert outcome.state == "deferred"
    assert outcome.reason == "inbox_storage_full"
    assert message.text_body == ""
    assert message.attachments == []
    # Not deleted, so the retry has something to fetch.
    assert s3.deleted == []
