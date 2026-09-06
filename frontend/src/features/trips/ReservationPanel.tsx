import { useTranslation } from 'react-i18next'

import {
  COST_AMOUNT_PATTERN,
  CURRENCY_CODE_PATTERN,
  formatCurrency,
  normaliseAmount,
} from './format'

/**
 * The three reservation fields, exactly as they live flattened on `ItemDraft`.
 * A narrower type of its own — rather than importing `ItemDraft` — so this
 * module reads and writes exactly the fields it owns and knows nothing about
 * the editor's other ones.
 */
export type ReservationValue = {
  confirmationNumber: string
  costAmount: string
  costCurrency: string
}

/**
 * The reservation trio, translated into the wire fields `PATCH
 * /trips/{tripId}/items/{itemId}` accepts (`ItemUpdate` in
 * `backend/trip_planner/api/items.py`).
 *
 * **Never call this for a create.** `ItemCreate` takes none of these three
 * and forbids extra keys — a reservation arrives "with material the user
 * already has" (R04, D07), and a brand-new item has no material yet. Every
 * caller here is `ItemDialog`, and it only spreads this in when `item` is not
 * `null`.
 *
 * The confirmation number rides through as typed: `""` is itself the
 * server's own signal to clear the field (`cleared_when_blank` on the
 * server), so there is nothing to reproduce on this side.
 *
 * The cost pair is the one place a client *can* construct `422 invalid_cost`:
 * `ck_item_cost_paired` refuses one half present without the other, judged
 * against what the item **ends up holding**. Rather than send only the one
 * half this edit touched, both halves are cleared together the moment
 * *either* is blank — the rule that keeps ordinary use inside the pair the
 * `CHECK` allows. `itemDraft.ts`'s `draftOf` defaults the currency field to
 * `PLN` for exactly this reason (Step 3.4, assumption A7): with the currency
 * pre-filled, typing only an amount no longer leaves either half blank, so
 * the pair persists rather than being silently dropped. The one way a typed
 * amount can still vanish is the user *clearing* the pre-filled currency by
 * hand while an amount is present — a deliberate edit of a field they were
 * never asked to touch, not the ordinary path this rule protects.
 */
export function reservationInput(value: ReservationValue): {
  confirmation_number: string | null
  cost_amount: string | null
  cost_currency: string | null
} {
  // `normaliseAmount` rather than `trim`: the Polish decimal comma has to
  // become the wire's dot here, at the one point the draft turns into a
  // request body, or `249,50` reaches a `NUMERIC(12,2)` as a string it cannot
  // parse. See that function for what it deliberately does not translate.
  const amount = normaliseAmount(value.costAmount)
  const currency = value.costCurrency.trim()
  const hasCost = amount !== '' && currency !== ''

  return {
    confirmation_number: value.confirmationNumber.trim() === '' ? null : value.confirmationNumber,
    cost_amount: hasCost ? amount : null,
    cost_currency: hasCost ? currency : null,
  }
}

/**
 * The id of the one field-level cost message, shared by both halves of the
 * pair through `aria-describedby`. A module constant rather than a `useId`
 * because every other control in this panel already carries a fixed id
 * (`item-cost-amount`, `item-cost-currency`) that its `<label>` points at,
 * and one dialog is on screen at a time.
 */
const COST_ERROR_ID = 'item-cost-error'

/**
 * Which half of the cost the app would be refused on — the client side of
 * `422 invalid_cost`.
 *
 * The same rules `domain/money.py` applies (`COST_AMOUNT_PATTERN` and
 * `CURRENCY_CODE_PATTERN` mirror it directly), checked here so the user is
 * told *which box* to fix while they are still looking at it. Before this,
 * a bad amount produced the server's generic "check the marked fields" with
 * nothing marked anywhere: a dead end and an accessibility failure at once.
 *
 * **Judged only on a pair that would actually be sent** — the same `hasCost`
 * rule `reservationInput` above uses. A malformed half beside a blank one is
 * dropped rather than transmitted, so complaining about it would be a
 * complaint about a value the server will never see: that is the nagging
 * invariant 4 rules out, and it would also fire on the ordinary way through
 * `PLN` (`P`, then `PL`) while the amount box is still empty.
 *
 * An empty pair is never an error. No reservation field is ever required
 * (invariant 1) and this does not make one required by the back door.
 */
export function costFieldErrors(value: ReservationValue): {
  amount: boolean
  currency: boolean
} {
  const amount = normaliseAmount(value.costAmount)
  const currency = value.costCurrency.trim()

  if (amount === '' || currency === '') {
    return { amount: false, currency: false }
  }

  return {
    amount: !COST_AMOUNT_PATTERN.test(amount),
    currency: !CURRENCY_CODE_PATTERN.test(currency),
  }
}

/** Whether a save must be refused because the cost pair cannot be saved. */
export function hasCostError(value: ReservationValue): boolean {
  const errors = costFieldErrors(value)
  return errors.amount || errors.currency
}

/**
 * The collapsed disclosure inside `ItemDialog`, beneath `ItemAttachments` —
 * the spec's "below the notes field" and this codebase's "beneath the
 * attachment strip" are the same spot, since notes already sit directly
 * above the attachment strip. Step 3.3 owns pinning that placement down with
 * its own test; this Step only has to build in the right place.
 *
 * A native `<details>`/`<summary>` rather than a hand-rolled toggle: it is
 * collapsed by default with no state to initialise, it is keyboard-operable
 * and announced as a disclosure with no ARIA to add, and there is no way to
 * make it a modal by accident — which is exactly invariant 3 below.
 *
 * Four invariants (R04, D07 — spec, "The reservation panel"), restated here
 * because this is the file that could most easily betray one of them:
 *
 * 1. **No reservation field is ever required.** Not to save an item, not to
 *    attach a file, not to move a status. Every input below is a plain,
 *    optional text field — no `required`, no `pattern`, no client-side
 *    refusal of an empty value.
 * 2. **Moving an item to *done* never asks for anything.** This panel has no
 *    opinion about `status` at all; it does not read it, write it, or gate
 *    on it.
 * 3. **Nothing is ever a modal in the way, and nothing blocks.** Inline,
 *    collapsed by default, dismissible by clicking the summary again.
 * 4. **No nagging, ever.** No empty-state prompt, no "complete your
 *    reservation details" banner, no count of missing fields, no reminder —
 *    this component renders the same three empty fields on the thirtieth
 *    item of a trip as on the first, forever, if that is what the owner
 *    wants.
 *
 * **It is never auto-expanded, and nothing here ever opens it for the user**
 * — there is no prop, no effect and no condition anywhere in this file that
 * sets `open`. See the spec for why an earlier draft's auto-expand-on-upload
 * was removed.
 *
 * **Dates are not in this panel.** The reservation's dates are the item's own
 * start day, times and `end_date`, edited in the controls the editor already
 * has a few rows above — a second date control here would be a second,
 * contradictory answer to when the booking is for.
 *
 * **The collapsed summary shows the saved cost, formatted through
 * `formatCurrency` (Step 3.4-review-fix-1).** Step 3.4 built `formatCurrency`
 * but gave it no call site, so the spec's `Intl` rule governed nothing a user
 * could see. This is the fix: the same amount/currency pair this panel already
 * holds, rendered beside the heading whenever both halves are non-blank — the
 * same `hasCost` the wire translation above uses, so the two never disagree
 * about what counts as "a cost". Nothing renders when there is none: no
 * placeholder, no dash, no "not set" — invariant 4 above forbids a marker keyed
 * on an *empty* field, and a muted "no cost yet" would be exactly that.
 *
 * **A refused cost marks the box it is about (Step 3.4-review-fix-2).** The
 * two cost inputs take `aria-invalid` and an `aria-describedby` pointing at a
 * single translated `error.invalid_cost` message, on exactly the halves
 * `costFieldErrors` refuses. This does not weaken invariant 1: an empty field
 * is never marked and never blocks anything; only a value the user actually
 * typed, which the server would answer with `422 invalid_cost`, is. The
 * collapsed summary goes quiet for the same values rather than rendering a
 * rounded guess of an amount that cannot be saved.
 */
export function ReservationPanel({
  value,
  onChange,
}: {
  value: ReservationValue
  onChange: (next: ReservationValue) => void
}) {
  const { t, i18n } = useTranslation()

  const trimmedAmount = normaliseAmount(value.costAmount)
  const trimmedCurrency = value.costCurrency.trim()
  const hasCost = trimmedAmount !== '' && trimmedCurrency !== ''
  const errors = costFieldErrors(value)
  const formattedCost =
    hasCost && !errors.amount && !errors.currency
      ? formatCurrency(trimmedAmount, trimmedCurrency, i18n.language)
      : ''

  return (
    <details className="reservation-panel">
      <summary className="reservation-panel__summary">
        {t('item.reservation.heading')}
        {formattedCost !== '' && <span className="reservation-panel__cost">{formattedCost}</span>}
      </summary>

      <div className="reservation-panel__body">
        <label htmlFor="item-confirmation-number">
          {t('item.reservation.confirmationNumberLabel')}
        </label>
        <input
          id="item-confirmation-number"
          value={value.confirmationNumber}
          onChange={(event) => onChange({ ...value, confirmationNumber: event.target.value })}
        />

        <div className="field-row">
          <div>
            <label htmlFor="item-cost-amount">{t('item.reservation.costLabel')}</label>
            {/* `aria-invalid` and `aria-describedby` are set only while the
                field is actually refused, never as a permanent attribute: an
                untouched, empty cost box is valid, and announcing it as
                invalid would make an optional field sound required. */}
            <input
              id="item-cost-amount"
              inputMode="decimal"
              value={value.costAmount}
              aria-invalid={errors.amount ? true : undefined}
              aria-describedby={errors.amount ? COST_ERROR_ID : undefined}
              onChange={(event) => onChange({ ...value, costAmount: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="item-cost-currency">{t('item.reservation.currencyLabel')}</label>
            <input
              id="item-cost-currency"
              value={value.costCurrency}
              maxLength={3}
              aria-invalid={errors.currency ? true : undefined}
              aria-describedby={errors.currency ? COST_ERROR_ID : undefined}
              onChange={(event) =>
                onChange({ ...value, costCurrency: event.target.value.toUpperCase() })
              }
            />
          </div>
        </div>

        {/* The message the marked fields point at — the same
            `<p role="alert">` beneath the offending field that
            `TripCreatePage` renders for a stage whose dates fall outside the
            trip, and the same `error.invalid_cost` string the server's own
            422 maps to, so the client's refusal and the server's read
            identically. One message for the pair, because the cost is one
            fact in two boxes and `domain/money.py` refuses it with one
            code. */}
        {(errors.amount || errors.currency) && (
          <p id={COST_ERROR_ID} role="alert">
            {t('error.invalid_cost')}
          </p>
        )}
      </div>
    </details>
  )
}
