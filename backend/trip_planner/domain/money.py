"""What a reservation's cost is allowed to say, decided from the value alone.

A reservation's cost is two columns, `cost_amount` and `cost_currency`, and the
whole point of this module is that they are validated as **one** fact rather
than two independent ones — see `validate_cost`, which is the single path both
`POST` and any future `PATCH` call so the two verbs cannot disagree about what a
valid cost is, exactly the reason `domain/items.py` gives for `validate_span`
being one function rather than one per caller.

Everything here is a pure function over `decimal.Decimal` and `str` (AGENTS.md:
pure business rules go in `domain/`). `float` never appears: this is money, and
`float` cannot represent `10.10` exactly, so a naive `float` comparison could
accept a third decimal place that a `Decimal` correctly rejects.

Two things are deliberately *not* here:

- **A currency allow-list.** The spec's own resolved assumption (A7) is that the
  first version does no conversion, no total and no sum — a stored amount is
  never combined with another, so the only thing worth enforcing is that a code
  is present and shaped like ISO 4217, not that it names a currency this
  installation has ever heard of. A hand-maintained list would need updating for
  a country nobody here has been to yet, for a feature that does no arithmetic
  with the result. Lower-case is refused rather than upper-cased, because
  upper-casing on the way in would mean the API accepts `"pln"` and the
  database `CHECK` — which does not upper-case anything — would then have to
  accept it too, or the two layers would disagree about the same string.
- **Raising.** This module predates the `invalid_cost` `ErrorCode` member Step
  1.5 adds, and a pure function that returns its verdict stays testable without
  the HTTP layer — the same ordering `domain/uploads.py` resolved with its own
  `UploadRejection` enum instead of importing `errors.py` early.
"""

from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "CURRENCY_CODE_PATTERN",
    "MAX_COST_AMOUNT",
    "MAX_COST_DECIMAL_PLACES",
    "MAX_COST_DIGITS",
    "CostRejection",
    "validate_cost",
]

#: ISO 4217's shape: three upper-case letters, nothing else. Not an allow-list —
#: see the module docstring for why one is not wanted.
CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")

#: Money has cents, not thirds of a cent. A `NUMERIC(12,2)` column — Step 3.1's —
#: cannot even store a third decimal place; refusing it here is the same rule
#: stated before the insert rather than after it.
MAX_COST_DECIMAL_PLACES = 2

#: The other half of `NUMERIC(12,2)` — its *precision*. Twelve significant
#: digits, two of which are the cents, so the largest storable amount is
#: `9999999999.99`. Both halves of the column definition are stated here, once,
#: because a magnitude the column cannot hold is exactly the same class of fact
#: as a third decimal place: refused before the insert rather than raised by the
#: driver as a `DataError` after it, which the API layer would answer `500`.
MAX_COST_DIGITS = 12

#: The inclusive upper bound `MAX_COST_DIGITS` and `MAX_COST_DECIMAL_PLACES`
#: imply: `10 ** (12 - 2) - 0.01`. Derived, not typed out, so the two constants
#: above stay the only place `NUMERIC(12,2)` is written down.
MAX_COST_AMOUNT = Decimal(10) ** (MAX_COST_DIGITS - MAX_COST_DECIMAL_PLACES) - Decimal(
    10
) ** -MAX_COST_DECIMAL_PLACES


class CostRejection(StrEnum):
    """Why a cost was refused. The value is the wire code Step 1.5 maps it to."""

    #: Any of: the two halves were not both present or both absent; the amount
    #: is negative; the amount has more than `MAX_COST_DECIMAL_PLACES` decimal
    #: digits; the amount is larger than `MAX_COST_AMOUNT`; or the currency does
    #: not match `CURRENCY_CODE_PATTERN`. The spec's
    #: Edge Cases table does not split these into separate wire codes, so neither
    #: does this module.
    INVALID_COST = "invalid_cost"


def validate_cost(
    *, cost_amount: Decimal | None, cost_currency: str | None
) -> CostRejection | None:
    """The single entry point the item endpoints call to decide a cost.

    Returns `None` when the pair is acceptable, `CostRejection.INVALID_COST`
    otherwise. `None` is itself one of the acceptable outcomes: both halves
    absent is a reservation with no recorded cost yet, or a cost being cleared,
    and that is legitimate — nothing in this feature requires a cost to exist.

    The rules, in the order applied:

    1. **Paired nullability.** `cost_amount` and `cost_currency` must be
       supplied together or absent together. This is the API-level statement of
       the paired database `CHECK ((cost_amount IS NULL) = (cost_currency IS
       NULL))` that Step 3.1 adds — the same fact, checked once before the
       insert and once again by the column itself.
    2. **Non-negative, and zero is not the same question as absent.** A
       negative amount is refused, but `Decimal("0")` is accepted: a free
       museum day is a real, arranged item with a real, arranged cost of zero,
       not the same thing as "no cost recorded yet". A naive truthiness check
       — `if not cost_amount` — treats `Decimal("0")` as falsy and would need a
       second amount-was-never-set flag to tell the two apart; comparing
       against `None` explicitly avoids needing one.
    3. **At most two decimal places.** Three decimals is not a rounding
       question, it is a value the `NUMERIC(12,2)` column two steps from here
       cannot hold.
    4. **At most `MAX_COST_AMOUNT`.** The column's *precision*, the same fact
       from the other end: `12345678901.00` is as unstorable as `10.101`, and
       without this rule PostgreSQL answers it with a `numeric field overflow`
       `DataError` — an unhandled `500`, not the `422 invalid_cost` the Edge
       Cases table promises, with the failed statement poisoning the session for
       the rest of the request. `ItemUpdate` deliberately omits `max_digits` so
       that this is the one place the bound is written; that only works if the
       bound is actually written here.
    5. **ISO-4217 shape.** `^[A-Z]{3}$`, checked last so a badly-shaped
       currency does not also have to have a well-formed amount to be reported.
    """
    if (cost_amount is None) != (cost_currency is None):
        return CostRejection.INVALID_COST

    if cost_amount is None or cost_currency is None:
        return None

    if not cost_amount.is_finite() or cost_amount < 0:
        return CostRejection.INVALID_COST

    exponent = cost_amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -MAX_COST_DECIMAL_PLACES:
        return CostRejection.INVALID_COST

    if cost_amount > MAX_COST_AMOUNT:
        return CostRejection.INVALID_COST

    if CURRENCY_CODE_PATTERN.fullmatch(cost_currency) is None:
        return CostRejection.INVALID_COST

    return None
