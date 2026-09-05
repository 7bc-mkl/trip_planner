import type { Item } from './items'
import { request } from './client'

/**
 * The trip API, typed to match `backend/trip_planner/api/trips.py`.
 *
 * Dates are ISO `YYYY-MM-DD` strings and times are `HH:MM`, both local wall-clock
 * with no timezone — deliberately (spec, Edge Cases). They are kept as strings
 * here rather than parsed into `Date` at the boundary, because `new Date('2026-10-10')`
 * parses as UTC midnight and renders as the 9th of October for anyone west of
 * Greenwich. `parseIsoDate` in `features/trips/format.ts` is the one place that
 * turns them into a `Date`, and it does it in local time.
 */

export type Stage = {
  id: string
  position: number
  place: string
  start_date: string | null
  end_date: string | null
}

export type Day = {
  id: string
  date: string
  /** Derived server-side by date containment; never stored. */
  stage_ids: string[]
  items: Item[]
}

/**
 * The readiness counter (R02).
 *
 * `tracked`, never `total`: a trip with ten items all still `to_plan` has
 * `tracked = 0`. A consumer reading this as the item count would be wrong in
 * exactly the case the counter exists to describe.
 */
export type Readiness = {
  arranged: number
  tracked: number
}

export type TripSummary = {
  id: string
  title: string
  start_date: string
  end_date: string
  departure_place: string
  /** `null` means one-way: the trip does not return. */
  return_place: string | null
  readiness: Readiness
}

export type TripDetail = TripSummary & {
  stages: Stage[]
  days: Day[]
}

export type StageInput = {
  place: string
  start_date?: string | null
  end_date?: string | null
}

export type TripInput = {
  title: string
  start_date: string
  end_date: string
  departure_place: string
  return_place: string | null
  stages: StageInput[]
}

export function listTrips(signal?: AbortSignal): Promise<TripSummary[]> {
  return request<TripSummary[]>('/trips', { signal })
}

export function fetchTrip(tripId: string, signal?: AbortSignal): Promise<TripDetail> {
  return request<TripDetail>(`/trips/${tripId}`, { signal })
}

export function createTrip(input: TripInput): Promise<TripDetail> {
  return request<TripDetail>('/trips', { method: 'POST', body: input })
}
