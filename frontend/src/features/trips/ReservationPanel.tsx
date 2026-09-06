import { useTranslation } from 'react-i18next'

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
  const amount = value.costAmount.trim()
  const currency = value.costCurrency.trim()
  const hasCost = amount !== '' && currency !== ''

  return {
    confirmation_number: value.confirmationNumber.trim() === '' ? null : value.confirmationNumber,
    cost_amount: hasCost ? amount : null,
    cost_currency: hasCost ? currency : null,
  }
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
 */
export function ReservationPanel({
  value,
  onChange,
}: {
  value: ReservationValue
  onChange: (next: ReservationValue) => void
}) {
  const { t } = useTranslation()

  return (
    <details className="reservation-panel">
      <summary className="reservation-panel__summary">{t('item.reservation.heading')}</summary>

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
            <input
              id="item-cost-amount"
              inputMode="decimal"
              value={value.costAmount}
              onChange={(event) => onChange({ ...value, costAmount: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor="item-cost-currency">{t('item.reservation.currencyLabel')}</label>
            <input
              id="item-cost-currency"
              value={value.costCurrency}
              maxLength={3}
              onChange={(event) =>
                onChange({ ...value, costCurrency: event.target.value.toUpperCase() })
              }
            />
          </div>
        </div>
      </div>
    </details>
  )
}
