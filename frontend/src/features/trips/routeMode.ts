import type { TripSummary } from '../../api/trips'
import { normalisePlace } from './format'

/**
 * The creator's route-mode toggle, and the derivation that keeps it honest.
 *
 * The mode is **not stored**. It is a reading of `return_place` (spec, Data Model):
 *
 * | Mode        | `return_place`                       |
 * |-------------|--------------------------------------|
 * | `roundTrip` | equal to `departure_place`           |
 * | `openJaw`   | different from `departure_place`     |
 * | `oneWay`    | `null`                               |
 *
 * Keeping the derivation in one exported function rather than inline in the
 * component means the trip header, the list row and the editor cannot disagree
 * about which mode a trip is in.
 */

export const ROUTE_MODES = ['roundTrip', 'openJaw', 'oneWay'] as const
export type RouteMode = (typeof ROUTE_MODES)[number]

export function routeModeOf(trip: Pick<TripSummary, 'departure_place' | 'return_place'>): RouteMode {
  if (trip.return_place === null) {
    return 'oneWay'
  }
  return normalisePlace(trip.return_place) === normalisePlace(trip.departure_place)
    ? 'roundTrip'
    : 'openJaw'
}

/**
 * The `return_place` a given mode implies.
 *
 * Round trip mirrors the departure place rather than asking for it again — the
 * export's toggle offers no second field in that mode, and a form that stored a
 * separately-typed "Warszawa" would drift out of round-trip mode on the first typo.
 */
export function returnPlaceFor(mode: RouteMode, departurePlace: string, typedReturn: string): string | null {
  switch (mode) {
    case 'roundTrip':
      return departurePlace
    case 'openJaw':
      return typedReturn
    case 'oneWay':
      return null
  }
}
