"""Seed the QA environment's inbox with routed mail and pending action items.

The QA environment has no SES and no model (`test-env-up.sh` configures the
inbox with inert values), so nothing can arrive by mail. This writes what the
worker would have written — routed messages, one voucher, and the proposals
`approvals.propose_from_routing` builds from them — straight into the QA
database, so the action-item screens can be exercised in a browser.

Run after `qa-seed.py` (it needs the trip that script creates):

    (cd backend && uv run python ../.ai/scripts/qa-seed-inbox.py [DATABASE_URL])

Three proposals: a hotel update with a voucher, a new ferry item, and a
deliberately long one (an 86-character title, a 34-character reference, a
seven-digit amount) that exists to stress the review sheet on a phone. Running
it twice adds a second set, which is also the "same mail forwarded twice" case.
QA data only — never point it at a real database.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from trip_planner import approvals
from trip_planner.db.models import Attachment, AttachmentBlob, InboundMessage, Owner, Trip
from trip_planner.domain.extraction import ExtractedFields

DEFAULT_URL = "postgresql+psycopg://trip_planner:trip_planner@127.0.0.1:55432/trip_planner_qa"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def main(url: str) -> None:
    if "trip_planner_qa" not in url:
        raise SystemExit("qa-seed-inbox: refusing to write to a database that is not trip_planner_qa")
    with Session(sa.create_engine(url)) as db:
        owner = db.scalars(sa.select(Owner)).one()
        trip = db.scalars(sa.select(Trip).where(Trip.owner_id == owner.id)).first()
        if trip is None:
            raise SystemExit("qa-seed-inbox: no trip yet — run qa-seed.py first")

        def message(subject: str, text: str) -> InboundMessage:
            record = InboundMessage(
                owner_id=owner.id,
                ses_message_id=f"qa-{uuid.uuid4().hex}",
                ses_sender_verdict="PASS",
                ses_scan_verdict="PASS",
                received_at=datetime.now(UTC),
                from_address="owner@qa.invalid",
                subject=subject,
                state="routed",
                trip_id=trip.id,
                text_body=text,
                routing_reason="routed_by_model",
                routing_reason_args={"trip": trip.title},
            )
            db.add(record)
            db.flush()
            return record

        hotel = message(
            "Fwd: Booking confirmation — Le Méridien Kota Kinabalu",
            "Your stay at Le Méridien Kota Kinabalu is confirmed.\n"
            "Check-in: 15 October 2026, 15:00\nBooking reference: LMK-48213\nTotal: MYR 612.40",
        )
        voucher = Attachment(
            inbound_message_id=hotel.id,
            filename="voucher-LMK-48213.pdf",
            content_type="application/pdf",
            byte_size=len(PDF),
            sha256=hashlib.sha256(PDF).hexdigest(),
        )
        db.add(voucher)
        db.flush()
        db.add(AttachmentBlob(attachment_id=voucher.id, data=PDF))
        db.flush()
        approvals.propose_from_routing(
            db,
            hotel,
            owner=owner,
            fields=ExtractedFields(
                title="Kota Kinabalu — nocleg przy nabrzeżu",
                kind="accommodation",
                confirmation_number="LMK-48213",
                start_date="2026-10-15",
                start_time="15:00",
                cost_amount="612.40",
                cost_currency="MYR",
            ),
        )

        ferry = message(
            "Potwierdzenie: prom do Pulau Manukan",
            "Prom Jesselton Point → Pulau Manukan\nData: 16 października 2026, 09:30\n"
            "Numer rezerwacji: JP-7781\nKwota: 90,00 MYR",
        )
        approvals.propose_from_routing(
            db,
            ferry,
            owner=owner,
            fields=ExtractedFields(
                title="Prom Jesselton Point → Pulau Manukan",
                kind="transport",
                confirmation_number="JP-7781",
                start_date="2026-10-16",
                start_time="09:30",
                cost_amount="90.00",
                cost_currency="MYR",
            ),
        )

        long = message(
            "Booking confirmation — Sabah Parks Mount Kinabalu Summit Climb",
            "Your Mount Kinabalu climb is confirmed. Reference SABAHPARKS-KINABALU-2026-000184213.",
        )
        approvals.propose_from_routing(
            db,
            long,
            owner=owner,
            fields=ExtractedFields(
                title=(
                    "Sabah Parks: Mount Kinabalu two-day summit climb "
                    "with Laban Rata Resthouse dormitory"
                ),
                kind="activity",
                confirmation_number="SABAHPARKS-KINABALU-2026-000184213",
                start_date="2026-10-19",
                start_time="07:00",
                cost_amount="1234567.89",
                cost_currency="MYR",
            ),
        )
        db.commit()
    print("qa-seed-inbox: seeded 3 routed messages and their proposals")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL)
