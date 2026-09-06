"""The upload limits, asserted against a real PostgreSQL.

Every test here goes to the database on purpose: the counters live in Postgres
rather than in a process dictionary (see `security/quota.py`), so a test with a
fake session would be evidence about a limiter nobody deploys.

The last class is the reason the advisory lock is specified at all. It runs two
**real, separate connections**, interleaved deliberately, and it fails against an
unlocked `SUM` — with the lock removed from `check_byte_quotas` both transactions
pass a quota only one of them fits in.
"""

from __future__ import annotations

import inspect
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from tests.test_models_item import make_item
from tests.test_models_trip import make_trip
from trip_planner.db.models import (
    MAX_ATTACHMENT_BYTES,
    Attachment,
    Item,
    Owner,
    Trip,
    TripDay,
    UploadEvent,
)
from trip_planner.security.passwords import hash_password
from trip_planner.security.quota import (
    MAX_ATTACHMENTS_PER_PARENT,
    MAX_TRIP_BYTES,
    MAX_UPLOADS_PER_RATE_WINDOW,
    MAX_VOLUME_BYTES_PER_WINDOW,
    QuotaRejection,
    UploadQuota,
    get_upload_quota,
    set_upload_quota,
)

SHA256_OF_NOTHING = "e" * 64


def make_attachment(**overrides: object) -> Attachment:
    fields: dict[str, object] = {
        "filename": "voucher.pdf",
        "content_type": "application/pdf",
        "byte_size": 2048,
        "sha256": SHA256_OF_NOTHING,
    }
    fields.update(overrides)
    return Attachment(**fields)


@pytest.fixture
def trip(db_session: OrmSession, owner: Owner) -> Trip:
    record = make_trip(owner)
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def trip_day(db_session: OrmSession, trip: Trip) -> TripDay:
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


class TestTheRateWindow:
    def test_it_engages_exactly_at_its_boundary(self, db_session: OrmSession, owner: Owner) -> None:
        """The 30th upload passes; the 31st is refused."""
        quota = UploadQuota()

        for _ in range(MAX_UPLOADS_PER_RATE_WINDOW):
            assert quota.check_rate(db_session, owner_id=owner.id) is None
            quota.record_upload(db_session, owner_id=owner.id, byte_size=1)

        assert quota.check_rate(db_session, owner_id=owner.id) is QuotaRejection.RATE_LIMITED

    def test_the_volume_window_engages_at_its_own_boundary(
        self, db_session: OrmSession, owner: Owner
    ) -> None:
        """200 MB in an hour, counted even when the upload *count* is nowhere near 30."""
        quota = UploadQuota()
        per_file = MAX_ATTACHMENT_BYTES
        files = MAX_VOLUME_BYTES_PER_WINDOW // per_file

        for _ in range(files - 1):
            quota.record_upload(db_session, owner_id=owner.id, byte_size=per_file)
        assert quota.check_rate(db_session, owner_id=owner.id) is None

        quota.record_upload(db_session, owner_id=owner.id, byte_size=per_file)
        assert quota.check_rate(db_session, owner_id=owner.id) is QuotaRejection.RATE_LIMITED
        assert files < MAX_UPLOADS_PER_RATE_WINDOW, "the count window would have fired instead"

    def test_another_owners_uploads_do_not_count(
        self, db_session: OrmSession, owner: Owner, other_owner: Owner
    ) -> None:
        quota = UploadQuota()
        for _ in range(MAX_UPLOADS_PER_RATE_WINDOW):
            quota.record_upload(db_session, owner_id=other_owner.id, byte_size=1)

        assert quota.check_rate(db_session, owner_id=owner.id) is None

    def test_uploads_outside_the_window_do_not_count(
        self, db_session: OrmSession, owner: Owner
    ) -> None:
        long_ago = datetime.now(UTC) - timedelta(hours=3)
        for _ in range(MAX_UPLOADS_PER_RATE_WINDOW + 5):
            db_session.add(
                UploadEvent(owner_id=owner.id, byte_size=MAX_ATTACHMENT_BYTES, occurred_at=long_ago)
            )
        db_session.flush()

        assert UploadQuota().check_rate(db_session, owner_id=owner.id) is None

    def test_a_check_prunes_rows_that_aged_out(self, db_session: OrmSession, owner: Owner) -> None:
        """Lazy pruning on read — there is no scheduler in this milestone."""
        db_session.add(
            UploadEvent(
                owner_id=owner.id,
                byte_size=1,
                occurred_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        db_session.flush()

        UploadQuota().check_rate(db_session, owner_id=owner.id)

        remaining = db_session.execute(
            sa.select(sa.func.count())
            .select_from(UploadEvent)
            .where(UploadEvent.owner_id == owner.id)
        ).scalar_one()
        assert remaining == 0

    def test_pruning_keeps_rows_the_longer_window_still_needs(
        self, db_session: OrmSession, owner: Owner
    ) -> None:
        """A row 30 minutes old is out of the 10-minute count window and inside the hour.

        Pruning to the shorter window would silently disarm the volume limit.
        """
        db_session.add(
            UploadEvent(
                owner_id=owner.id,
                byte_size=MAX_VOLUME_BYTES_PER_WINDOW,
                occurred_at=datetime.now(UTC) - timedelta(minutes=30),
            )
        )
        db_session.flush()

        verdict = UploadQuota().check_rate(db_session, owner_id=owner.id)
        assert verdict is QuotaRejection.RATE_LIMITED

    def test_the_pre_read_check_needs_only_the_owner_and_the_session(self) -> None:
        """The memory control: it must be callable *before* the body is read.

        A limiter that runs after 10 MB has already been pulled into memory
        refuses to store the flood but not to absorb it. Asserted at the level
        this module can — the callable takes no payload, so an endpoint cannot
        accidentally need one before calling it.
        """
        parameters = inspect.signature(UploadQuota.check_rate).parameters
        assert set(parameters) == {"self", "db", "owner_id", "now"}
        assert parameters["now"].default is None


class TestAttachmentsPerParent:
    def test_the_twentieth_passes_and_the_twenty_first_is_refused(
        self, db_session: OrmSession, trip_day: TripDay
    ) -> None:
        quota = UploadQuota()

        for _ in range(MAX_ATTACHMENTS_PER_PARENT):
            assert quota.check_parent_capacity(db_session, trip_day_id=trip_day.id) is None
            db_session.add(make_attachment(trip_day_id=trip_day.id))
            db_session.flush()

        assert (
            quota.check_parent_capacity(db_session, trip_day_id=trip_day.id)
            is QuotaRejection.ATTACHMENT_LIMIT_REACHED
        )

    def test_an_items_count_is_independent_of_its_days(
        self, db_session: OrmSession, trip_day: TripDay, item: Item
    ) -> None:
        """20 per item and 20 per day are two limits, not one shared budget."""
        quota = UploadQuota()
        for _ in range(MAX_ATTACHMENTS_PER_PARENT):
            db_session.add(make_attachment(trip_day_id=trip_day.id))
        db_session.flush()

        assert quota.check_parent_capacity(db_session, item_id=item.id) is None

    @pytest.mark.parametrize(
        "kwargs",
        [{}, {"item_id": uuid.uuid4(), "trip_day_id": uuid.uuid4()}],
    )
    def test_neither_or_both_parents_is_a_programming_error(
        self, db_session: OrmSession, kwargs: dict[str, uuid.UUID]
    ) -> None:
        """The schema's `CHECK` says an attachment has exactly one parent."""
        with pytest.raises(ValueError, match="exactly one"):
            UploadQuota().check_parent_capacity(db_session, **kwargs)


class TestTheByteQuotas:
    def _fill_trip(self, db_session: OrmSession, day: TripDay, total: int) -> None:
        remaining = total
        while remaining:
            chunk = min(remaining, MAX_ATTACHMENT_BYTES)
            db_session.add(make_attachment(trip_day_id=day.id, byte_size=chunk))
            remaining -= chunk
        db_session.flush()

    def test_a_trip_at_its_cap_refuses_the_next_byte(
        self, db_session: OrmSession, trip: Trip, trip_day: TripDay
    ) -> None:
        quota = UploadQuota()
        self._fill_trip(db_session, trip_day, MAX_TRIP_BYTES - MAX_ATTACHMENT_BYTES)

        # The last file that still fits, exactly.
        assert (
            quota.check_byte_quotas(
                db_session, trip_id=trip.id, incoming_bytes=MAX_ATTACHMENT_BYTES
            )
            is None
        )
        assert (
            quota.check_byte_quotas(
                db_session, trip_id=trip.id, incoming_bytes=MAX_ATTACHMENT_BYTES + 1
            )
            is QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED
        )

    def test_an_items_attachments_count_against_its_trip(
        self, db_session: OrmSession, trip: Trip, item: Item
    ) -> None:
        """`attachment` has no `trip_id`; the sum walks `item → trip_day → trip`."""
        quota = UploadQuota(max_trip_bytes=4096)
        db_session.add(make_attachment(item_id=item.id, byte_size=4096))
        db_session.flush()

        assert (
            quota.check_byte_quotas(db_session, trip_id=trip.id, incoming_bytes=1)
            is QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED
        )

    def test_another_trips_attachments_do_not_count(
        self, db_session: OrmSession, owner: Owner, trip: Trip, trip_day: TripDay
    ) -> None:
        other = make_trip(owner, title="Another trip")
        db_session.add(other)
        db_session.flush()
        db_session.add(make_attachment(trip_day_id=trip_day.id, byte_size=4096))
        db_session.flush()

        assert (
            UploadQuota(max_trip_bytes=4096).check_byte_quotas(
                db_session, trip_id=other.id, incoming_bytes=4096
            )
            is None
        )

    def test_the_installation_cap_refuses_what_the_trip_cap_would_allow(
        self, db_session: OrmSession, trip: Trip, trip_day: TripDay
    ) -> None:
        """The same error code, deliberately: the owner's remedy is the same."""
        quota = UploadQuota(max_trip_bytes=MAX_TRIP_BYTES, max_installation_bytes=4096)
        db_session.add(make_attachment(trip_day_id=trip_day.id, byte_size=4096))
        db_session.flush()

        assert (
            quota.check_byte_quotas(db_session, trip_id=trip.id, incoming_bytes=1)
            is QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED
        )

    def test_the_combined_in_transaction_check_reports_the_first_failure(
        self, db_session: OrmSession, owner: Owner, trip: Trip, trip_day: TripDay
    ) -> None:
        quota = UploadQuota(max_attachments_per_parent=1, max_trip_bytes=1)
        db_session.add(make_attachment(trip_day_id=trip_day.id, byte_size=1))
        db_session.flush()

        assert (
            quota.check_within_transaction(
                db_session,
                owner_id=owner.id,
                trip_id=trip.id,
                trip_day_id=trip_day.id,
                incoming_bytes=1,
            )
            is QuotaRejection.ATTACHMENT_LIMIT_REACHED
        )


class TestTheModuleLevelQuota:
    def test_it_can_be_swapped_and_restored(self) -> None:
        previous = get_upload_quota()
        try:
            set_upload_quota(UploadQuota(max_trip_bytes=1))
            assert get_upload_quota().max_trip_bytes == 1
        finally:
            set_upload_quota(previous)
        assert get_upload_quota() is previous


class TestTwoConcurrentTransactions:
    """The reason `pg_advisory_xact_lock` is in the module at all.

    Two real connections, interleaved by hand: the first checks the quota and
    inserts without committing, the second then runs the same check. Under
    `READ COMMITTED` an unlocked `SUM` would see only committed rows, miss the
    first transaction's insert, and let both consume the same last slot. The
    lock makes the second wait for the first's commit and then see it.
    """

    #: The trip's cap for this test, and the size of each of the two uploads
    #: racing for the one slot left under it.
    CAP = 1000
    ALREADY_STORED = 600
    UPLOAD = 400

    @pytest.fixture
    def committed_trip(self, engine: sa.Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
        """A trip and a day **committed**, so two other connections can both see them.

        The shared `db_session` fixture never commits, so its rows are invisible
        outside its own connection — which is exactly what this test cannot use.
        Everything is deleted through the owner afterwards, and every table
        involved cascades from it.
        """
        from sqlalchemy.orm import Session

        with Session(engine) as setup:
            owner = Owner(
                email=f"concurrency-{uuid.uuid4().hex[:8]}@example.com",
                password_hash=hash_password("irrelevant"),
            )
            setup.add(owner)
            setup.flush()
            trip = make_trip(owner)
            setup.add(trip)
            setup.flush()
            day = TripDay(trip_id=trip.id, date=date(2026, 10, 10))
            setup.add(day)
            setup.flush()
            setup.add(make_attachment(trip_day_id=day.id, byte_size=self.ALREADY_STORED))
            setup.commit()
            owner_id, trip_id, day_id = owner.id, trip.id, day.id

        try:
            yield trip_id, day_id
        finally:
            with Session(engine) as teardown:
                teardown.execute(sa.delete(Owner).where(Owner.id == owner_id))
                teardown.commit()

    def test_they_cannot_both_consume_the_last_of_a_trips_quota(
        self, engine: sa.Engine, committed_trip: tuple[uuid.UUID, uuid.UUID]
    ) -> None:
        from sqlalchemy.orm import Session

        trip_id, day_id = committed_trip
        quota = UploadQuota(max_trip_bytes=self.CAP, max_installation_bytes=10**12)

        first_has_inserted = threading.Event()
        second_has_started = threading.Event()
        verdicts: dict[str, QuotaRejection | None] = {}

        def first() -> None:
            with Session(engine) as session:
                verdicts["first"] = quota.check_byte_quotas(
                    session, trip_id=trip_id, incoming_bytes=self.UPLOAD
                )
                if verdicts["first"] is None:
                    session.add(make_attachment(trip_day_id=day_id, byte_size=self.UPLOAD))
                    session.flush()
                first_has_inserted.set()
                # Hold the transaction open long enough that an *unlocked* second
                # check would run its SUM here and see the pre-insert total.
                second_has_started.wait(timeout=5)
                time.sleep(0.5)
                session.commit()

        def second() -> None:
            with Session(engine) as session:
                assert first_has_inserted.wait(timeout=5)
                second_has_started.set()
                verdicts["second"] = quota.check_byte_quotas(
                    session, trip_id=trip_id, incoming_bytes=self.UPLOAD
                )
                if verdicts["second"] is None:
                    session.add(make_attachment(trip_day_id=day_id, byte_size=self.UPLOAD))
                    session.flush()
                session.commit()

        threads = [threading.Thread(target=first), threading.Thread(target=second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads), "a transaction never finished"

        assert verdicts["first"] is None, "the first upload fitted and must have been accepted"
        assert verdicts["second"] is QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED, (
            "both transactions consumed the same last slot — the advisory lock is not holding"
        )

        with Session(engine) as reader:
            stored = quota._trip_bytes(reader, trip_id=trip_id)
        assert stored == self.ALREADY_STORED + self.UPLOAD <= self.CAP
