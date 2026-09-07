import type { Item, ItemInput } from '../../api/items'
import { toTimeInput } from '../../api/items'

/**
 * The shape of an in-progress item edit, and where it is stored.
 *
 * Separate from `ItemDialog.tsx` so that file exports only its component: mixing
 * a component and plain helpers in one module breaks React Fast Refresh, which
 * then reloads the whole tree on every edit — losing the very dialog state this
 * type describes.
 *
 * Strings rather than the API's nullable types because these are form-control
 * values: an `<input type="time">` holds `''`, never `null`, and converting at
 * the boundary keeps the "empty means sometime that day" rule in one place.
 */
export type ItemDraft = {
  kind: ItemInput['kind']
  status: ItemInput['status']
  startTime: string
  endTime: string
  endDate: string
  title: string
  notes: string
  /** The reservation trio `ReservationPanel` reads and writes — see its own doc. */
  confirmationNumber: string
  costAmount: string
  costCurrency: string
}

/** The key a draft is stored under. `new` for an item that does not exist yet. */
export function draftKey(itemId: string | null): string {
  return `item:${itemId ?? 'new'}`
}

/** The starting draft: an existing item's values, or the defaults for a new one. */
export function draftOf(item: Item | null): ItemDraft {
  return {
    kind: item?.kind ?? 'activity',
    status: item?.status ?? 'to_plan',
    startTime: toTimeInput(item?.start_time ?? null),
    endTime: toTimeInput(item?.end_time ?? null),
    endDate: item?.end_date ?? '',
    title: item?.title ?? '',
    notes: item?.notes ?? '',
    confirmationNumber: item?.confirmation_number ?? '',
    costAmount: item?.cost_amount ?? '',
    // `PLN` whenever the item does not already carry a currency of its own —
    // a fresh item and an existing one with no cost yet both land here. This
    // is the plain default assumption A7 settles for (no conversion, no
    // locale-driven guess), and it is also what keeps `reservationInput`'s
    // paired cost rule from silently dropping a typed amount: that rule
    // clears the whole pair the moment either half is blank, and with the
    // currency pre-filled it no longer can be, in ordinary use, just because
    // the user only touched the amount field.
    costCurrency: item?.cost_currency ?? 'PLN',
  }
}
