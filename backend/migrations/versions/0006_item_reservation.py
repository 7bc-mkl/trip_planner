"""item reservation

Revision ID: 0006_item_reservation
Revises: 0005_attachment
Create Date: 2026-09-06

Phase 3 of the attachments slice: the three nullable columns R04's reservation
data lands in — `confirmation_number`, `cost_amount` and `cost_currency` — on the
`item` table that already exists.

**This is a separate revision from `0005_attachment` on purpose (assumption A1).**
Reservation data and attachments share no table and no endpoint, so splitting the
two revisions is what makes "roll back reservation data and keep attachments
working" a thing an operator can actually do, rather than a sentence in a spec.
It also means the columns never exist during a phase that cannot populate them.

Against `BACKWARD_COMPATIBILITY.md` §2 this is the safe form of the rule:
**nullable, no default, no backfill.** Every trip already stored keeps loading
unchanged, because the columns mean nothing when absent — `NULL` here is "no
reservation data recorded", which is the state every existing row is genuinely in.
A `NOT NULL` column with a default would have had to invent a cost for a museum
visit nobody has booked.

The four CHECKs are the point of doing this in the database rather than only in
`domain/money.py`:

- `ck_item_confirmation_number` bounds the one otherwise-unbounded free-text
  input in the feature at 500 characters, and refuses `''` — so "cleared" has
  exactly one representation, `NULL`, and no query has to test for two.
- `ck_item_cost_amount` refuses a negative price. Zero is deliberately allowed:
  a free museum day is a real, arranged item with a real, arranged cost.
- `ck_item_cost_currency` restates ISO 4217's *shape* (three upper-case letters),
  not an allow-list — `domain/money.py` argues at length why an allow-list is the
  wrong thing for a feature that performs no arithmetic on the amount.
- `ck_item_cost_paired` is the one that carries the modelling: an amount never
  exists without its unit. A bare number whose currency lives in someone's head
  is the named worst case of `BACKWARD_COMPATIBILITY.md`, and this makes it
  unrepresentable rather than merely discouraged.

**There are deliberately no `reservation_start` / `reservation_end` columns.**
R04's "dates" are the item's *existing* `start_time` / `end_time` / `end_date`
span. A second pair here would create two answers to "when is this booked for" —
the duplication the foundation spec already refused once.

A downgrade drops the columns and therefore the reservation data in them. That is
what downgrading a feature migration means, and it is written down here so nobody
discovers it at 02:00.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_item_reservation"
down_revision: str | None = "0005_attachment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("item", sa.Column("confirmation_number", sa.Text(), nullable=True))
    op.add_column(
        "item", sa.Column("cost_amount", sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column("item", sa.Column("cost_currency", sa.CHAR(length=3), nullable=True))

    op.create_check_constraint(
        "ck_item_confirmation_number",
        "item",
        "confirmation_number <> '' AND length(confirmation_number) <= 500",
    )
    op.create_check_constraint("ck_item_cost_amount", "item", "cost_amount >= 0")
    op.create_check_constraint("ck_item_cost_currency", "item", "cost_currency ~ '^[A-Z]{3}$'")
    op.create_check_constraint(
        "ck_item_cost_paired",
        "item",
        "(cost_amount IS NULL) = (cost_currency IS NULL)",
    )


def downgrade() -> None:
    # The constraints go first: dropping a column would take its own constraints
    # with it, but `ck_item_cost_paired` names two columns and would otherwise
    # briefly reference one that no longer exists.
    op.drop_constraint("ck_item_cost_paired", "item", type_="check")
    op.drop_constraint("ck_item_cost_currency", "item", type_="check")
    op.drop_constraint("ck_item_cost_amount", "item", type_="check")
    op.drop_constraint("ck_item_confirmation_number", "item", type_="check")

    op.drop_column("item", "cost_currency")
    op.drop_column("item", "cost_amount")
    op.drop_column("item", "confirmation_number")
