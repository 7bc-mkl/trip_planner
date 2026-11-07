"""Review regressions at the worker, spending and owner-action boundaries."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa

from tests.test_inbox_ingest import StubS3
from tests.test_inbox_router import (
    client_returning,
    egress_rows,
    run,
)
from tests.test_inbox_router import (
    message as message,
)
from tests.test_inbox_router import (
    trip as trip,
)
from tests.test_integrations_model import settings_for
from tests.test_scheduler import (
    add_message,
    reload,
)
from tests.test_scheduler import (
    committed_owner as committed_owner,
)
from tests.test_scheduler import (
    inbox_settings as inbox_settings,
)
from tests.test_scheduler import (
    worker_sessions as worker_sessions,
)
from trip_planner.db.models import InboundMessage
from trip_planner.inbound.router import month_spend
from trip_planner.scheduler import InboxWorker


def test_unknown_usage_is_not_free(db_session, owner, message, trip, monkeypatch):
    client, transport = client_returning('{"trip_id": null}')
    transport.raise_with = TimeoutError()
    run(db_session, message, owner, client)
    from trip_planner.config import get_settings

    monkeypatch.setattr(
        "trip_planner.config.get_settings",
        lambda: replace(get_settings(), model=settings_for("anthropic")),
    )
    assert month_spend(db_session, now=datetime.now(UTC)) is None


def test_each_actual_dispatch_has_an_audit_row(db_session, owner, message, trip):
    client, transport = client_returning('{"trip_id": null}')
    transport.raise_with = TimeoutError()
    run(db_session, message, owner, client)
    assert len(egress_rows(db_session, message)) == len(transport.calls)


def test_worker_routes_already_received_without_fetching_s3(
    inbox_settings,
    worker_sessions,
    committed_owner,
):
    settings = replace(inbox_settings, model=settings_for("anthropic"))
    message_id = add_message(
        worker_sessions, committed_owner, state="received", text_body="No travel dates", key=None
    )
    worker = InboxWorker(settings, worker_sessions, fetcher=StubS3({}))
    worker.run_once()
    assert reload(worker_sessions, message_id).state == "unrouted"


def test_rejected_proposal_still_records_usage(db_session, owner, message, trip):
    client, _ = client_returning("not JSON")
    run(db_session, message, owner, client)
    row = egress_rows(db_session, message)[0]
    assert (row.input_tokens, row.output_tokens) == (120, 8)


def test_deleting_mail_does_not_refund_spend(db_session, owner, message, trip, monkeypatch):
    client, _ = client_returning('{"trip_id": null}')
    run(db_session, message, owner, client)
    from trip_planner.config import get_settings

    monkeypatch.setattr(
        "trip_planner.config.get_settings",
        lambda: replace(get_settings(), model=settings_for("anthropic")),
    )
    before = month_spend(db_session, now=datetime.now(UTC))
    assert before > Decimal(0)
    db_session.execute(sa.delete(InboundMessage).where(InboundMessage.id == message.id))
    db_session.flush()
    assert month_spend(db_session, now=datetime.now(UTC)) == before


def test_owner_discard_during_model_call_is_preserved(db_session, owner, message, trip):
    client, transport = client_returning('{"trip_id": "' + str(trip.id) + '"}')
    original_post = transport.post_json

    def discard_then_answer(*args, **kwargs):
        db_session.execute(
            sa.update(InboundMessage)
            .where(
                InboundMessage.id == message.id,
            )
            .values(state="discarded"),
            execution_options={"synchronize_session": False},
        )
        return original_post(*args, **kwargs)

    transport.post_json = discard_then_answer
    run(db_session, message, owner, client)
    db_session.flush()
    db_session.refresh(message)
    assert message.state == "discarded"
    assert message.trip_id is None


def test_spend_uses_call_prices_and_resets_next_utc_month(db_session, owner, message, trip):
    client, _ = client_returning('{"trip_id": null}')
    october = datetime(2026, 10, 31, 23, 59, tzinfo=UTC)
    run(db_session, message, owner, client, now=october)
    assert month_spend(db_session, now=october) == Decimal("0.00016")
    assert month_spend(db_session, now=datetime(2026, 11, 1, tzinfo=UTC)) == Decimal(0)


def test_deletion_during_dispatch_keeps_spend_without_resurrecting_mail(
    db_session,
    owner,
    message,
    trip,
):
    client, transport = client_returning('{"trip_id": null}')
    original_post = transport.post_json
    message_id = message.id

    def delete_then_answer(*args, **kwargs):
        db_session.execute(
            sa.delete(InboundMessage).where(
                InboundMessage.id == message_id,
            ),
            execution_options={"synchronize_session": False},
        )
        return original_post(*args, **kwargs)

    transport.post_json = delete_then_answer
    result = run(db_session, message, owner, client)
    assert result.state == "discarded"
    assert (
        db_session.scalar(
            sa.select(InboundMessage.id).where(
                InboundMessage.id == message_id,
            )
        )
        is None
    )
    assert month_spend(db_session, now=datetime.now(UTC)) == Decimal("0.00016")


def test_worker_stops_on_unknown_usage_even_after_mail_is_deleted(
    inbox_settings,
    worker_sessions,
    committed_owner,
):
    from datetime import date

    from tests.test_models_trip import make_trip
    from trip_planner.db.models import InboundModelEgress, ModelBillingMonth

    settings = replace(inbox_settings, model=settings_for("anthropic"))
    with worker_sessions() as db:
        trip_record = make_trip(committed_owner)
        trip_record.start_date = date(2026, 10, 2)
        trip_record.end_date = date(2026, 10, 25)
        db.add(trip_record)
        db.commit()
    first = add_message(
        worker_sessions, committed_owner, key=None, state="received", text_body="17 October 2026"
    )
    second = add_message(
        worker_sessions, committed_owner, key=None, state="received", text_body="18 October 2026"
    )
    client, transport = client_returning('{"trip_id": null}')
    original_post = transport.post_json

    def inspect_committed_audit(*args, **kwargs):
        # This independent connection proves the audit is durable before send.
        with worker_sessions() as db:
            assert db.scalar(sa.select(sa.func.count()).select_from(InboundModelEgress)) == 1
            assert month_spend(db, now=datetime.now(UTC)) is None
        original_post(*args, **kwargs)
        raise TimeoutError("simulated unknown usage")

    transport.post_json = inspect_committed_audit
    worker = InboxWorker(settings, worker_sessions, fetcher=StubS3({}), model_client=client)
    try:
        worker.run_once()
        assert len(transport.calls) == 1
        assert reload(worker_sessions, second).routing_reason == "routing_budget_unavailable"
        with worker_sessions() as db:
            db.execute(sa.delete(InboundMessage).where(InboundMessage.id == first))
            db.commit()
        worker.run_once()
        assert len(transport.calls) == 1
        assert reload(worker_sessions, second).state == "received"
    finally:
        with worker_sessions() as db:
            db.execute(sa.delete(ModelBillingMonth))
            db.commit()
