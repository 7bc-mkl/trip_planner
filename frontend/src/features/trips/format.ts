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

/**
 * ISO 4217's shape, mirroring `CURRENCY_CODE_PATTERN` in
 * `backend/trip_planner/domain/money.py`: three upper-case letters, nothing
 * else. Not an allow-list — the server deliberately keeps none, and a second,
 * stricter list on this side would refuse costs the API happily accepts.
 */
export const CURRENCY_CODE_PATTERN = /^[A-Z]{3}$/u

/**
 * The wire shape of a cost amount, mirroring the server's rules for one
 * (`validate_cost`): digits, no sign, at most two decimal places. `0` and
 * `0.00` both match — a free museum day is a real cost of zero, not an absent
 * one — while `-1` and `1.234` both fail, which is exactly the `422
 * invalid_cost` the spec's Edge Cases table names.
 */
export const COST_AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/u

/**
 * A typed amount, normalised into the decimal string the wire takes.
 *
 * **The comma is a decimal separator here.** This is a Polish-first product
 * (R01, R09) and `249,50` is how a Polish keyboard writes two hundred
 * forty-nine fifty; `NUMERIC(12,2)` and `domain/money.py` take `249.50`.
 * Translating between the two is this function's whole job, done once on the
 * way to the wire rather than at each of the places an amount is read.
 *
 * Three things are normalised, and no more:
 *
 * - **Whitespace anywhere is dropped**, which covers a leading or trailing
 *   space and the group separator in `1 250,50` — including the
 *   *non-breaking* space `Intl` itself renders under `pl`, since `\s` under
 *   the `u` flag matches it. So this reads back what `formatCurrency` prints.
 * - **Every comma becomes a dot.** A second comma then leaves two dots, which
 *   `COST_AMOUNT_PATTERN` refuses — `1,250,50` is reported as invalid rather
 *   than guessed at.
 * - **A trailing separator is dropped**, so the half-typed `249,` reads as
 *   `249` instead of flashing an error message between two keystrokes.
 *
 * **Deliberately not handled**, because this is not a locale-aware number
 * parser and must not grow into one: the English grouping style `1,250.50`
 * (whose comma this reads as a decimal separator, so it is refused rather
 * than silently misread by a factor of a thousand); a leading `+`; a currency
 * symbol or code typed into the amount box; non-ASCII digits; scientific
 * notation. Each of those fails `COST_AMOUNT_PATTERN`, which marks the field
 * rather than sending the server a guess.
 */
export function normaliseAmount(amount: string): string {
  return amount
    .replace(/\s/gu, '')
    .replace(/,/gu, '.')
    .replace(/\.$/u, '')
}

/**
 * A stored reservation cost, rendered as money through **one**
 * `Intl.NumberFormat` call — the spec's cross-cutting rule that a currency
 * goes through `Intl`, never through concatenation. `amount` arrives as the
 * wire's decimal string (`NUMERIC(12,2)` is never a JS `float`; see
 * `domain/money.py`), so turning it into a number happens here, at the one
 * point it is about to be rendered, and nowhere else.
 *
 * This call produces both required shapes: `1 250,00 zł` under `pl` —
 * Polish groups thousands with a *non-breaking* space, not a plain one, so
 * a caller comparing this output should match that rather than fight it —
 * and `PLN 1,250.00` under `en`, where `PLN` has no currency glyph `Intl`
 * knows, so it falls back to the ISO code as the currency's own display
 * form. Neither shape is assembled by hand.
 *
 * `useGrouping: 'always'` is not decoration: Polish's CLDR data sets a
 * `minimumGroupingDigits` of 2, so the locale-default `'auto'` silently
 * drops the separator on any four-digit amount (`1250,00 zł`, no space) and
 * only groups from five digits up — which would make this exact, spec-cited
 * example fail to reproduce on the very Node/ICU build this runs on.
 * `'always'` is the one option that turns grouping back on without
 * hand-rolling the separator.
 *
 * **It never renders `NaN`, and never throws.** `Number('')` is `0` and
 * `Number('abc')` is `NaN`, so an unguarded call used to put a literal
 * `NaN €` on the screen the moment a Polish user typed the Polish decimal
 * comma (Step 3.4-review-fix-2), and a currency of `P` — two keystrokes into
 * `PLN` — makes `Intl.NumberFormat` throw a `RangeError` outright. An amount
 * that is empty or does not parse, or a currency that is not ISO-4217 shaped,
 * therefore renders **nothing at all**: an empty string is the honest answer
 * where a rounded guess or the word `NaN` would be a lie about the user's
 * money. The caller decides what to do with nothing — `ReservationPanel`
 * renders no cost element at all, which is also what its no-nagging
 * invariant requires.
 *
 * The comma is normalised here as well as in `reservationInput`, so a live
 * draft value and a saved wire value both render the same way through the
 * same call.
 */
export function formatCurrency(amount: string, currency: string, locale: string): string {
  const normalised = normaliseAmount(amount)
  const value = Number(normalised)

  if (normalised === '' || !Number.isFinite(value) || !CURRENCY_CODE_PATTERN.test(currency)) {
    return ''
  }

  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    useGrouping: 'always',
  }).format(value)
}
