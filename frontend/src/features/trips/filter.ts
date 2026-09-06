import { ITEM_KINDS } from '../../api/items'
import type { Item, ItemKind } from '../../api/items'

/**
 * The timeline filter — applied in the browser, never on the server.
 *
 * A11 says the timeline payload is complete, so filtering is a pure function
 * over what has already been fetched. That is also why there is no `?status=`
 * query parameter: it would be a contract surface with no caller.
 *
 * **The filter never changes the counter.** *Only outstanding* answers "what do
 * I still have to touch"; the counter answers "how much is arranged". They are
 * different and equally useful questions, and making one move the other would
 * mean the number changes depending on what you are looking at.
 */

export const FILTERS = ['all', 'outstanding'] as const
export type Filter = (typeof FILTERS)[number]

export const DEFAULT_FILTER: Filter = 'all'

export function isFilter(value: unknown): value is Filter {
  return typeof value === 'string' && (FILTERS as readonly string[]).includes(value)
}

/**
 * *Only outstanding* is `status !== 'done'` — both *do zaplanowania* and *do
 * zarezerwowania*.
 *
 * Not `status === 'to_plan'`: an item you have decided on but not yet booked is
 * still something you have to touch, and leaving it out would make the filter
 * quietly disagree with the question it asks.
 */
export function matchesFilter(item: Item, filter: Filter): boolean {
  return filter === 'all' || item.status !== 'done'
}

export function applyFilter(items: readonly Item[], filter: Filter): Item[] {
  return items.filter((item) => matchesFilter(item, filter))
}

/** How many items of each kind the trip has — the per-type chips' counts. */
export function countByKind(items: readonly Item[]): Record<ItemKind, number> {
  const counts = Object.fromEntries(ITEM_KINDS.map((kind) => [kind, 0])) as Record<
    ItemKind,
    number
  >

  for (const item of items) {
    counts[item.kind] += 1
  }

  return counts
}
