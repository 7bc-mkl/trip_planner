import type { Stage, TripSummary } from '../../api/trips'

/** How many places a day label names before it collapses into a count. */
const MAX_LABELLED_STAGES = 2

/**
 * Locale-aware formatting for the trip screens.
 *
 * The spec's cross-cutting UI rules require dates and numbers to go through
 * `Intl` with the active locale, never string concatenation — so this module is
 * where every user-visible date is built, and no component formats one itself.
 */

/**
 * Parse an ISO `YYYY-MM-DD` into a **local** date.
 *
 * `new Date('2026-10-10')` is specified to parse as UTC midnight, which renders
 * as the 9th of October for every user west of Greenwich. Since a trip day is a
 * calendar date and not an instant, that off-by-one would be visible on the
 * timeline. Splitting the string and using the local-time constructor avoids it.
 */
export function parseIsoDate(iso: string): Date {
  const [year = NaN, month = NaN, day = NaN] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

/** The reverse, for building request bodies without a UTC round trip. */
export function toIsoDate(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${value.getFullYear()}-${month}-${day}`
}

export function formatDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(parseIsoDate(iso))
}

/** "10–24 October 2026" where the locale supports it, "10 Oct – 24 Oct" where it does not. */
export function formatDateRange(startIso: string, endIso: string, locale: string): string {
  const formatter = new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
  return formatter.formatRange(parseIsoDate(startIso), parseIsoDate(endIso))
}

/** The short "→ dd.MM" marker on an item that spans into a later day. */
export function formatShortDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit' }).format(
    parseIsoDate(iso),
  )
}

/**
 * The two halves of a timeline day anchor: `PAŹ` above `10`.
 *
 * Two calls rather than one string split in the component, because a locale's
 * abbreviated month and its day number do not join in a fixed order anywhere —
 * and the anchor stacks them, so it needs them apart. Both go through `Intl`
 * with the active locale; the uppercasing of the month is CSS, not data.
 */
export function formatAnchorMonth(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { month: 'short' }).format(parseIsoDate(iso))
}

export function formatAnchorDay(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: 'numeric' }).format(parseIsoDate(iso))
}

/** Inclusive day count — the same arithmetic as the server's `generate_days`. */
export function dayCount(startIso: string, endIso: string): number {
  const start = parseIsoDate(startIso).getTime()
  const end = parseIsoDate(endIso).getTime()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return 0
  }
  return Math.round((end - start) / 86_400_000) + 1
}

/** Nights: one fewer than the days, and never negative. */
export function nightCount(startIso: string, endIso: string): number {
  return Math.max(dayCount(startIso, endIso) - 1, 0)
}

/**
 * The route summary shown on a list row and in the trip header:
 * `Warszawa → Kuala Lumpur → Penang → Katowice`.
 *
 * Built from the departure place, the stages in order, and the return place — and
 * a return place identical to the last stage is not repeated, because
 * "… → Katowice → Katowice" reads as a mistake rather than as a round trip.
 */
export function routeSummary(trip: TripSummary, stages: readonly Stage[] = []): string {
  const places = [trip.departure_place, ...stages.map((stage) => stage.place)]

  if (trip.return_place !== null) {
    places.push(trip.return_place)
  }

  return places
    .filter((place, index) => {
      const previous = places[index - 1]
      return previous === undefined || normalisePlace(place) !== normalisePlace(previous)
    })
    .join(' → ')
}

/**
 * The comparison form for a free-text place — the same rule as the server's
 * `normalise_place`, and for the same reason: the route mode is *derived* from a
 * string comparison, so `"Warszawa"` and `"Warszawa "` must not read as two cities.
 */
export function normalisePlace(place: string): string {
  return place.trim().replace(/\s+/gu, ' ').toLocaleLowerCase()
}

/**
 * The `→`-joined day label, truncated after two with `+n`.
 *
 * Mirrors `stage_label` in `backend/trip_planner/domain/stages.py`: the same rule
 * has to hold on both sides, because the timeline renders the label from the
 * derived `stage_ids` rather than from a string the server sent.
 *
 * An empty list gives an empty string rather than dash copy — a day in no stage
 * renders *without* a label, and a "—" here would be an untranslated string on
 * the screen.
 */
export function stageLabel(stages: readonly Stage[]): string {
  const places = stages.map((stage) => stage.place)
  if (places.length <= MAX_LABELLED_STAGES) {
    return places.join(' → ')
  }
  return `${places.slice(0, MAX_LABELLED_STAGES).join(' → ')} +${places.length - MAX_LABELLED_STAGES}`
}

/**
 * A wall-clock time (`HH:MM` or `HH:MM:SS`) rendered in the active locale.
 *
 * Through `Intl` rather than by slicing the string, for the same reason every
 * date on these screens goes through it: the repository's review rules put
 * dates, times and numbers behind the locale, never behind hand-built strings.
 * A locale that writes 11:50 PM should get 11:50 PM.
 *
 * The date the time is attached to is irrelevant here — only the clock face is
 * rendered — so an arbitrary local date carries it into the formatter.
 */
export function formatTime(value: string | null, locale: string): string {
  if (value === null) {
    return ''
  }

  const [hours = NaN, minutes = NaN] = value.split(':').map(Number)
  return new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(
    new Date(2000, 0, 1, hours, minutes),
  )
}

const BYTE_SIZE_UNITS = ['B', 'KB', 'MB'] as const
export type ByteSizeUnit = (typeof BYTE_SIZE_UNITS)[number]

/**
 * Splits a byte count into the `{value, unit}` pair the `attachment.size` ICU
 * key renders — never a pre-built string. `value` is a plain number, not a
 * string this module has already formatted: the key's `{value, number}`
 * argument is what hands it to `Intl.NumberFormat` under the active locale, so
 * the decimal separator (`1.8` vs `1,8`) falls out of the translation call
 * rather than being decided here.
 */
export function splitByteSize(bytes: number): { value: number; unit: ByteSizeUnit } {
  const KB = 1024
  const MB = KB * 1024
  if (bytes >= MB) {
    return { value: Math.round((bytes / MB) * 10) / 10, unit: 'MB' }
  }
  if (bytes >= KB) {
    return { value: Math.round(bytes / KB), unit: 'KB' }
  }
  return { value: bytes, unit: 'B' }
}
