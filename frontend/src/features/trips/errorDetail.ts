import { ApiError } from '../../api/client'
import type { ErrorCode } from '../../api/errorCodes'
import { formatDate } from './format'

/**
 * The four range refusals, rendered with the days and places the server named.
 *
 * `PATCH /trips/{id}` refuses a date edit rather than destroying anything, and
 * it always says *what* is in the way: `error.field` carries a comma-separated
 * list of ISO dates for the three date rules and of place names for the stage
 * rule. Nothing read that field before this module existed, so the owner was
 * told "those days already have items on them" and left to guess which.
 *
 * Two deliberate asymmetries between the two kinds of list:
 *
 * - **Dates are split, validated and formatted through the locale**, then
 *   joined with `Intl.ListFormat`. An ISO date can never contain a comma, so
 *   splitting is lossless; and a raw `2026-10-24` on a Polish screen is exactly
 *   the hand-built string the repository's i18n rules forbid.
 * - **Places are rendered verbatim, as one string.** A place name *can* contain
 *   a comma ("Kuala Lumpur, Malezja") and the server's join does not escape it,
 *   so splitting would cut a real name in half and invent a second destination.
 *   The server's joined string is already human-readable; it is passed through
 *   as an ICU argument, so React escapes it and a place called `<b>` is text.
 *
 * Anything unparseable — a missing `field`, a token that is not an ISO date —
 * falls back to the code's existing generic message. A vague sentence is a poor
 * message; a confident sentence naming the wrong day is a worse one.
 */

/** Translate a key with optional ICU arguments — the `t` from `useTranslation`. */
export type Translate = (key: string, options?: Record<string, unknown>) => string

/** Codes whose `field` is a list of ISO dates. */
const DATE_DETAIL_CODES: readonly ErrorCode[] = [
  'days_have_items',
  'days_have_attachments',
  'items_outside_new_range',
]

/** Codes whose `field` is a list of place names. */
const PLACE_DETAIL_CODES: readonly ErrorCode[] = ['stages_outside_new_range']

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/u

/**
 * Which field group a refusal belongs to, so the screen can anchor its message
 * to the control that caused it rather than only to the form as a whole.
 */
export type RefusalAnchor = 'dates' | 'stages' | null

export function refusalAnchor(error: unknown): RefusalAnchor {
  if (!(error instanceof ApiError)) {
    return null
  }
  if (DATE_DETAIL_CODES.includes(error.code as ErrorCode)) {
    return 'dates'
  }
  if (PLACE_DETAIL_CODES.includes(error.code as ErrorCode)) {
    return 'stages'
  }
  return null
}

/**
 * The message to show for a failed request: the detailed form when the server
 * named what is in the way, the existing generic copy otherwise.
 *
 * `locale` is the active i18n language, used for the date formatting and the
 * list join; `translate` is the `t` the caller already holds.
 */
export function detailedErrorMessage(
  error: unknown,
  translate: Translate,
  locale: string,
): string {
  if (!(error instanceof ApiError)) {
    return translate('error.unknown')
  }

  const generic = translate(error.translationKey)
  const raw = error.field?.trim() ?? ''

  if (raw === '') {
    return generic
  }

  const code = error.code as ErrorCode

  if (PLACE_DETAIL_CODES.includes(code)) {
    return translate(`error.${code}_detail`, { places: raw })
  }

  if (!DATE_DETAIL_CODES.includes(code)) {
    return generic
  }

  const tokens = raw.split(',').map((token) => token.trim())

  if (tokens.length === 0 || !tokens.every((token) => ISO_DATE.test(token))) {
    return generic
  }

  return translate(`error.${code}_detail`, { dates: formatDateList(tokens, locale) })
}

/**
 * "24 października 2026" · "23 and 24 October 2026" — the conjunction is the
 * locale's, not a comma this module chose.
 */
function formatDateList(isoDates: readonly string[], locale: string): string {
  const formatted = isoDates.map((iso) => formatDate(iso, locale))

  return new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(formatted)
}
