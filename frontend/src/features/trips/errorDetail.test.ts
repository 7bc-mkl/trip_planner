import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { detailedErrorMessage, refusalAnchor } from './errorDetail'

/**
 * The refusal copy is the part of this feature that is not mechanical: a
 * message naming the wrong day is worse than the vague one it replaces. So the
 * tests here are about *which* days and places come out, in both locales, and
 * about every path that must fall back rather than guess.
 *
 * `translate` is a real ICU-ish substitution over the shipped locale files
 * rather than a `vi.fn()` returning its key — a test that asserts on key names
 * cannot notice a message whose placeholder never got filled in.
 */

type Locale = 'en' | 'pl'

const MESSAGES: Record<Locale, Record<string, string>> = {
  en: en.error as Record<string, string>,
  pl: pl.error as Record<string, string>,
}

function translatorFor(locale: Locale) {
  return (key: string, options?: Record<string, unknown>): string => {
    const message = MESSAGES[locale][key.replace(/^error\./u, '')]
    if (message === undefined) {
      throw new Error(`missing ${locale} key: ${key}`)
    }
    return message.replace(/\{(\w+)\}/gu, (whole, name: string) =>
      options?.[name] === undefined ? whole : String(options[name]),
    )
  }
}

const inEnglish = translatorFor('en')
const inPolish = translatorFor('pl')

describe('detailedErrorMessage', () => {
  it('names every day the server refused to drop', () => {
    const error = new ApiError(409, 'days_have_items', '2026-10-23,2026-10-24')

    const message = detailedErrorMessage(error, inEnglish, 'en')

    expect(message).toContain('October 23, 2026')
    expect(message).toContain('October 24, 2026')
    // Not the ISO form the wire carried, and not the vague fallback.
    expect(message).not.toContain('2026-10-23')
    expect(message).not.toBe(en.error.days_have_items)
  })

  it('names the days that carry attachments', () => {
    const message = detailedErrorMessage(
      new ApiError(409, 'days_have_attachments', '2026-10-24'),
      inEnglish,
      'en',
    )

    expect(message).toContain('October 24, 2026')
    expect(message).toContain('attachments')
  })

  it('names the start days of items that would reach past the new end', () => {
    const message = detailedErrorMessage(
      new ApiError(409, 'items_outside_new_range', '2026-10-10'),
      inEnglish,
      'en',
    )

    expect(message).toContain('October 10, 2026')
    expect(message).toContain('starting on')
  })

  it('names the destinations that fall outside the new dates', () => {
    const message = detailedErrorMessage(
      new ApiError(409, 'stages_outside_new_range', 'Penang, Langkawi'),
      inEnglish,
      'en',
    )

    expect(message).toContain('Penang, Langkawi')
  })

  it('keeps a place name that itself contains a comma in one piece', () => {
    // The server joins places with ", " and escapes nothing, so splitting would
    // invent a destination called "Malezja". The whole field is passed through.
    const message = detailedErrorMessage(
      new ApiError(409, 'stages_outside_new_range', 'Kuala Lumpur, Malezja'),
      inEnglish,
      'en',
    )

    expect(message).toContain('Kuala Lumpur, Malezja')
  })

  it('formats the dates in the active locale, not in one fixed language', () => {
    const error = new ApiError(409, 'days_have_items', '2026-10-24')

    const english = detailedErrorMessage(error, inEnglish, 'en')
    const polish = detailedErrorMessage(error, inPolish, 'pl')

    expect(english).toContain('October 24, 2026')
    expect(polish).toContain('24 października 2026')
    expect(polish).not.toContain('October')
  })

  it('joins several dates with the locale conjunction rather than a hard-coded comma', () => {
    const error = new ApiError(409, 'days_have_items', '2026-10-23,2026-10-24')

    expect(detailedErrorMessage(error, inEnglish, 'en')).toContain('and')
    expect(detailedErrorMessage(error, inPolish, 'pl')).toContain('i')
  })

  it('falls back to the generic message when the server named nothing', () => {
    expect(detailedErrorMessage(new ApiError(409, 'days_have_items', null), inEnglish, 'en')).toBe(
      en.error.days_have_items,
    )
    expect(detailedErrorMessage(new ApiError(409, 'days_have_items', '   '), inEnglish, 'en')).toBe(
      en.error.days_have_items,
    )
  })

  it('falls back rather than guessing when a date token is not a date', () => {
    // A confident sentence naming the wrong day is worse than a vague one.
    const message = detailedErrorMessage(
      new ApiError(409, 'days_have_items', '2026-10-24,sometime'),
      inEnglish,
      'en',
    )

    expect(message).toBe(en.error.days_have_items)
  })

  it('leaves codes that carry no list alone', () => {
    expect(
      detailedErrorMessage(new ApiError(422, 'invalid_date_range', 'end_date'), inEnglish, 'en'),
    ).toBe(en.error.invalid_date_range)
  })

  it('answers the unknown-error copy for anything that is not an ApiError', () => {
    expect(detailedErrorMessage(new Error('boom'), inEnglish, 'en')).toBe(en.error.unknown)
  })
})

describe('refusalAnchor', () => {
  it('points the three date refusals at the date fields', () => {
    expect(refusalAnchor(new ApiError(409, 'days_have_items', '2026-10-24'))).toBe('dates')
    expect(refusalAnchor(new ApiError(409, 'days_have_attachments', '2026-10-24'))).toBe('dates')
    expect(refusalAnchor(new ApiError(409, 'items_outside_new_range', '2026-10-24'))).toBe('dates')
  })

  it('points the stage refusal at the stage list', () => {
    expect(refusalAnchor(new ApiError(409, 'stages_outside_new_range', 'Penang'))).toBe('stages')
  })

  it('anchors nothing for an error about no particular group', () => {
    expect(refusalAnchor(new ApiError(503, 'service_unavailable', null))).toBeNull()
    expect(refusalAnchor(new Error('boom'))).toBeNull()
  })
})

describe('the locale files', () => {
  it('carry every detail key this module can produce, in both languages', () => {
    const keys = [
      'days_have_items_detail',
      'days_have_attachments_detail',
      'items_outside_new_range_detail',
      'stages_outside_new_range_detail',
    ]

    for (const key of keys) {
      expect(MESSAGES.en[key], `en.${key}`).toBeTruthy()
      expect(MESSAGES.pl[key], `pl.${key}`).toBeTruthy()
    }
  })
})
