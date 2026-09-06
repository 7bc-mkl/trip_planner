import { request } from './client'
import type { Stage } from './trips'

/**
 * The item API, typed to match `backend/trip_planner/api/items.py`.
 *
 * `ITEM_KINDS` and `ITEM_STATUSES` mirror the tuples that build the database
 * CHECK constraints. They are const arrays rather than bare unions because the
 * UI iterates them — the editor's type selector and the filter bar's chips are
 * both built from `ITEM_KINDS`, so a sixth kind reaches the screen by being
 * added here rather than in three places.
 */

export const ITEM_KINDS = ['accommodation', 'transport', 'activity', 'meal', 'other'] as const
export type ItemKind = (typeof ITEM_KINDS)[number]

/** In the order they progress: nothing decided → decided, not booked → booked. */
export const ITEM_STATUSES = ['to_plan', 'to_book', 'done'] as const
export type ItemStatus = (typeof ITEM_STATUSES)[number]

export type Item = {
  id: string
  position: number
  kind: ItemKind
  status: ItemStatus
  /** `HH:MM:SS` local wall-clock, or null for "sometime that day". */
  start_time: string | null
  end_time: string | null
  /** `null` means the item ends on its start day. */
  end_date: string | null
  title: string
  notes: string | null
}

export type DayDetail = {
  id: string
  trip_id: string
  date: string
  stages: Stage[]
  items: Item[]
  previous_date: string | null
  next_date: string | null
}

export type ItemInput = {
  kind: ItemKind
  status: ItemStatus
  start_time: string | null
  end_time: string | null
  end_date: string | null
  title: string
  notes: string | null
}

export function fetchDay(
  tripId: string,
  date: string,
  signal?: AbortSignal,
): Promise<DayDetail> {
  return request<DayDetail>(`/trips/${tripId}/days/${date}`, { signal })
}

export function createItem(tripId: string, date: string, input: ItemInput): Promise<Item> {
  return request<Item>(`/trips/${tripId}/days/${date}/items`, { method: 'POST', body: input })
}

export function updateItem(
  tripId: string,
  itemId: string,
  input: Partial<ItemInput>,
): Promise<Item> {
  return request<Item>(`/trips/${tripId}/items/${itemId}`, { method: 'PATCH', body: input })
}

export function deleteItem(tripId: string, itemId: string): Promise<void> {
  return request<void>(`/trips/${tripId}/items/${itemId}`, { method: 'DELETE' })
}

/**
 * `HH:MM:SS` from the API to the `HH:MM` an `<input type="time">` expects.
 *
 * The seconds are always zero — the API stores a wall-clock plan, not a
 * stopwatch — but sending them back into a time input silently blanks it in
 * some browsers.
 */
export function toTimeInput(value: string | null): string {
  return value === null ? '' : value.slice(0, 5)
}

/** The reverse: an empty input is "sometime that day", which is null, not "". */
export function fromTimeInput(value: string): string | null {
  return value === '' ? null : value
}
