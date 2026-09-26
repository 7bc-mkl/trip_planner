"""The quarantine timer, the deletes it finishes, and the objects it clears out of S3.

The distinction these tests are really protecting is **whose data has a timer**.
Quarantine is the only thing in this product a stranger can grow, so it is the
only thing that expires; the owner's own mail is kept until he deletes it, and an
app that quietly deleted a confirmation on a schedule would be the failure A03
is about. Half of this file exists to make sure a later "tidy up old messages"
change fails a test rather than shipping.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session as OrmSession

from tests.test_inbox_ingest import PREFIX, StubS3
from trip_planner.db.models import InboundMessage, Owner
from trip_planner.inbound.cleanup import (
    QUARANTINE_RETENTION,
    S3_LIFECYCLE,
    STALE_OBJECT_ALARM_MARGIN,
    run_cleanup,
)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def make_message(db: OrmSession, owner: Owner, **overrides: object) -> InboundMessage:
    fields: dict[str, object] = {
        "owner_id": owner.id,
        "ses_message_id": f"ses-{uuid.uuid4().hex}",
        "s3_object_key": f"{PREFIX}ses-{uuid.uuid4().hex}",
        "ses_sender_verdict": "PASS",
        "ses_scan_verdict": "PASS",
        "received_at": NOW,
        "from_address": owner.email,
        "subject": "Potwierdzenie rezerwacji",
        "state": "received",
    }
    fields.update(overrides)
    record = InboundMessage(**fields)
    db.add(record)
    db.flush()
    return record


def run(db: OrmSession, s3: StubS3, *, now: datetime = NOW):
    return run_cleanup(db, s3, now=now)  # type: ignore[arg-type]


def long_ago(days_past_retention: int = 1) -> datetime:
    return NOW - QUARANTINE_RETENTION - timedelta(days=days_past_retention)


# --------------------------------------------------------------------------- #
# The quarantine timer
# --------------------------------------------------------------------------- #


def test_an_expired_quarantine_row_and_its_object_are_both_removed(
    db_session: OrmSession, owner: Owner
) -> None:
    message = make_message(
        db_session, owner, state="quarantined", received_at=long_ago(), text_body=""
    )
    key = message.s3_object_key
    s3 = StubS3({key: b"raw mime"})

    report = run(db_session, s3)

    assert report.quarantine_purged == 1
    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is None
    assert s3.deleted == [key]


def test_a_quarantine_row_inside_its_retention_is_left_alone(
    db_session: OrmSession, owner: Owner
) -> None:
    message = make_message(
        db_session,
        owner,
        state="quarantined",
        received_at=NOW - QUARANTINE_RETENTION + timedelta(days=1),
        text_body="",
    )
    s3 = StubS3({message.s3_object_key: b"raw mime"})

    assert run(db_session, s3).quarantine_purged == 0
    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is not None
    assert s3.deleted == []


@pytest.mark.parametrize("state", ["received", "routed", "unrouted", "deferred"])
def test_the_owner_s_own_mail_has_no_timer_however_old_it_is(
    db_session: OrmSession, owner: Owner, state: str
) -> None:
    """A05 and A10, asserted so a later "tidy up old messages" fails here.

    His own mail is his data. An application deleting a confirmation on a
    schedule is exactly the failure A03 is about, and quarantine is the only
    thing with a timer because it is the only thing a stranger can grow.
    """
    message = make_message(
        db_session, owner, state=state, received_at=NOW - timedelta(days=400)
    )

    run(db_session, StubS3())

    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is not None


def test_a_purge_that_cannot_delete_its_object_leaves_the_row_for_next_time(
    db_session: OrmSession, owner: Owner
) -> None:
    """The order is the opposite of ingestion's, on purpose.

    Ingestion commits first because losing the *message* is the unacceptable
    outcome. A purge is deleting the message deliberately, so the unacceptable
    outcome is the reverse — the row gone while a stranger's raw mail stays in
    the bucket.
    """

    class Unreliable(StubS3):
        def delete(self, key: str) -> None:
            raise TimeoutError("s3 delete timed out")

    message = make_message(
        db_session, owner, state="quarantined", received_at=long_ago(), text_body=""
    )

    assert run(db_session, Unreliable()).quarantine_purged == 0
    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is not None


def test_an_object_already_gone_does_not_block_the_purge(
    db_session: OrmSession, owner: Owner
) -> None:
    """The lifecycle rule may simply have got there first, which is a success."""
    message = make_message(
        db_session, owner, state="quarantined", received_at=long_ago(), text_body=""
    )

    # StubS3 raises ObjectGone for a key it does not hold.
    assert run(db_session, StubS3()).quarantine_purged == 1
    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is None


def test_a_released_message_survives_the_purge_as_an_ordinary_one(
    db_session: OrmSession, owner: Owner
) -> None:
    """Recovery moves it out of `quarantined`, so the timer stops applying to it.

    Worth asserting because the alternative — a message that was *once*
    quarantined keeping its expiry — would delete a confirmation the owner
    deliberately rescued.
    """
    message = make_message(
        db_session, owner, state="received", received_at=long_ago(), text_body="PNR: SX-9912L"
    )

    run(db_session, StubS3())

    db_session.expire_all()
    stored = db_session.get(InboundMessage, message.id)
    assert stored is not None and stored.text_body == "PNR: SX-9912L"


# --------------------------------------------------------------------------- #
# Finishing a discard
# --------------------------------------------------------------------------- #


def test_a_tombstone_has_its_object_deleted_and_is_then_removed(
    db_session: OrmSession, owner: Owner
) -> None:
    """The second half of `DELETE /inbox/messages/{id}`.

    The route leaves the tombstone precisely so the S3 key survives long enough
    to be used; deleting the row first would leave a private copy of his
    confirmation in the bucket until the lifecycle rule noticed a month later.
    """
    message = make_message(db_session, owner, state="discarded")
    key = message.s3_object_key
    s3 = StubS3({key: b"raw mime"})

    assert run(db_session, s3).discards_completed == 1
    assert s3.deleted == [key]
    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is None


def test_a_tombstone_whose_object_cannot_be_deleted_survives_to_be_retried(
    db_session: OrmSession, owner: Owner
) -> None:
    class Unreliable(StubS3):
        def delete(self, key: str) -> None:
            raise TimeoutError("s3 delete timed out")

    message = make_message(db_session, owner, state="discarded")

    assert run(db_session, Unreliable()).discards_completed == 0
    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is not None


# --------------------------------------------------------------------------- #
# Retrying an orphaned delete
# --------------------------------------------------------------------------- #


def test_an_object_a_failed_delete_left_behind_is_deleted_and_the_locator_cleared(
    db_session: OrmSession, owner: Owner
) -> None:
    """Ingestion commits before it deletes, so a failed delete leaves exactly this.

    Retried here rather than left to the lifecycle rule, which would keep a
    second copy of the owner's mail in AWS for a month for no reason.
    """
    message = make_message(db_session, owner, state="received")
    key = message.s3_object_key
    s3 = StubS3({key: b"raw mime"})

    assert run(db_session, s3).orphan_objects_deleted == 1
    assert s3.deleted == [key]
    db_session.expire_all()
    stored = db_session.get(InboundMessage, message.id)
    assert stored is not None and stored.s3_object_key is None


def test_a_message_with_no_locator_is_not_touched(
    db_session: OrmSession, owner: Owner
) -> None:
    make_message(db_session, owner, state="received", s3_object_key=None)
    s3 = StubS3()

    assert run(db_session, s3).orphan_objects_deleted == 0
    assert s3.deleted == []


def test_a_deferred_message_keeps_its_object(
    db_session: OrmSession, owner: Owner
) -> None:
    """It has not been ingested yet, so deleting the object would lose the message.

    The single most damaging thing this pass could get wrong, which is why
    `deferred` is not in the states it cleans up after.
    """
    message = make_message(db_session, owner, state="deferred")
    key = message.s3_object_key
    s3 = StubS3({key: b"raw mime"})

    run(db_session, s3)

    assert s3.deleted == []
    db_session.expire_all()
    stored = db_session.get(InboundMessage, message.id)
    assert stored is not None and stored.s3_object_key == key


# --------------------------------------------------------------------------- #
# The stale-object alarm
# --------------------------------------------------------------------------- #


def test_a_deferred_object_approaching_expiry_is_alarmed(
    db_session: OrmSession, owner: Owner
) -> None:
    """This application cannot stop the bucket's clock, so it says so while there
    is still time. A deferred message that expires quietly is mail the owner
    never learns arrived — the failure this whole feature exists to prevent."""
    make_message(
        db_session,
        owner,
        state="deferred",
        received_at=NOW - S3_LIFECYCLE + STALE_OBJECT_ALARM_MARGIN - timedelta(days=1),
    )

    # A real handler rather than `caplog`: the alarm's *level* is the point —
    # this is the one inbox condition an operator has to act on before a
    # deadline nothing in this application controls — and asserting it directly
    # does not depend on pytest's capture plumbing being configured a particular
    # way.
    records: list[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Collector()
    alarm_logger = logging.getLogger("trip_planner.inbound.cleanup")
    alarm_logger.addHandler(handler)
    try:
        report = run(db_session, StubS3())
    finally:
        alarm_logger.removeHandler(handler)

    assert report.stale_objects_alarmed == 1
    alarms = [record for record in records if record.levelno >= logging.ERROR]
    assert alarms and "expiring" in alarms[0].getMessage()


def test_a_recently_deferred_object_is_not_alarmed(
    db_session: OrmSession, owner: Owner
) -> None:
    make_message(db_session, owner, state="deferred", received_at=NOW - timedelta(days=1))

    assert run(db_session, StubS3()).stale_objects_alarmed == 0


def test_the_alarm_margin_leaves_real_time_to_act() -> None:
    """A week, so an operator can clear a full inbox or fix an integration by hand."""
    assert timedelta(days=7) <= STALE_OBJECT_ALARM_MARGIN
    assert STALE_OBJECT_ALARM_MARGIN < S3_LIFECYCLE


def test_a_quiet_installation_produces_an_empty_report(
    db_session: OrmSession, owner: Owner
) -> None:
    from trip_planner.inbound.cleanup import CleanupReport

    assert run(db_session, StubS3()) == CleanupReport()
