import { describe, expect, it } from 'vitest'

import {
  COST_AMOUNT_PATTERN,
  MAX_COST_AMOUNT,
  exceedsMaxCostAmount,
  formatCurrency,
  normaliseAmount,
} from './format'

/**
 * Step 3.4: a stored reservation cost renders as money through **one**
 * `Intl.NumberFormat` call, never through string concatenation — the spec's
 * cross-cutting UI rule and this repository's own rule for numbers.
 *
 * Both expected strings below use `\u00A0` (a non-breaking space) rather
 * than a literal space, because that is exactly what `Intl` renders as the
 * group separator in both cases — asserted with that in mind rather than
 * fought with a plain space that would never match.
 */
describe('formatCurrency', () => {
  it('renders a PLN amount in Polish, grouped with a non-breaking space', () => {
    expect(formatCurrency('1250.00', 'PLN', 'pl')).toBe('1\u00A0250,00\u00A0zł')
  })

  it('renders the same amount in English, falling back to the ISO code', () => {
    expect(formatCurrency('1250.00', 'PLN', 'en')).toBe('PLN\u00A01,250.00')
  })

  it('never assembles the string by concatenation — both shapes fall out of one call', () => {
    // A hand-built string would produce "PLN 1250.00" or "1250,00 PLN" —
    // neither matches what `Intl.NumberFormat` actually renders.
    expect(formatCurrency('1250.00', 'PLN', 'pl')).not.toContain('PLN')
    expect(formatCurrency('1250.00', 'PLN', 'en')).not.toBe('PLN1250.00')
  })
})

/**
 * Step 3.4-review-fix-2. The final gate's browser walk typed `249,50` — the
 * standard Polish decimal separator, in the Polish UI — and got a literal
 * `NaN €` on the screen, because `Number('249,50')` is `NaN` and nothing
 * guarded it. Two rules come out of that: the comma is accepted, and no
 * input of any kind can make this function print `NaN`.
 */
describe('normaliseAmount — the Polish comma on the way to the wire', () => {
  it('reads the Polish decimal comma as a decimal point', () => {
    expect(normaliseAmount('249,50')).toBe('249.50')
  })

  it('leaves an already-dotted amount exactly as it was', () => {
    expect(normaliseAmount('1250.00')).toBe('1250.00')
  })

  it('drops surrounding whitespace', () => {
    expect(normaliseAmount('  249,50 ')).toBe('249.50')
  })

  it('drops a group separator, including the non-breaking space Intl renders', () => {
    expect(normaliseAmount('1 250,50')).toBe('1250.50')
    expect(normaliseAmount('1\u00A0250,50')).toBe('1250.50')
  })

  it('drops a trailing separator, so a half-typed amount is not an error yet', () => {
    expect(normaliseAmount('249,')).toBe('249')
    expect(normaliseAmount('249.')).toBe('249')
  })

  it('leaves an empty or blank amount empty rather than turning it into a zero', () => {
    expect(normaliseAmount('')).toBe('')
    expect(normaliseAmount('   ')).toBe('')
  })

  /**
   * The line this deliberately does not cross: an English-grouped
   * `1,250.50` is *refused*, not reinterpreted. Reading its comma as a
   * decimal point is the documented trade-off of not building a
   * locale-aware parser — and the result fails the wire pattern, so the
   * field is marked rather than the server being sent a number a thousand
   * times too small.
   */
  it('refuses an English-grouped amount instead of misreading it by a factor of a thousand', () => {
    expect(COST_AMOUNT_PATTERN.test(normaliseAmount('1,250.50'))).toBe(false)
  })
})

describe('COST_AMOUNT_PATTERN mirrors the server rules in domain/money.py', () => {
  it.each(['0', '0.00', '249', '249.5', '249.50', '1250.00'])('accepts %s', (amount) => {
    expect(COST_AMOUNT_PATTERN.test(amount)).toBe(true)
  })

  it.each(['-1', '-0.01', '1.234', 'abc', '', '1e3', '+1'])('refuses %s', (amount) => {
    expect(COST_AMOUNT_PATTERN.test(amount)).toBe(false)
  })
})

/**
 * The magnitude half of the same server rule, which the pattern above cannot
 * carry: `NUMERIC(12,2)` stops at `9999999999.99`, and `validate_cost` refuses
 * anything larger. Without this, a well-shaped but unstorable amount was the
 * one cost refusal the client did not mark.
 */
describe('exceedsMaxCostAmount mirrors the precision half of domain/money.py', () => {
  it('derives the same bound the server derives from NUMERIC(12,2)', () => {
    expect(MAX_COST_AMOUNT).toBe(9999999999.99)
  })

  it.each(['0', '249.50', '9999999999.99', '9999999999'])('accepts %s', (amount) => {
    expect(exceedsMaxCostAmount(amount)).toBe(false)
  })

  it.each(['10000000000', '10000000000.00', '12345678901.00', '99999999999999'])(
    'refuses %s',
    (amount) => {
      expect(exceedsMaxCostAmount(amount)).toBe(true)
    },
  )

  it('says nothing about an amount the pattern already refuses', () => {
    // Not this function's question: `abc` and `` are refused for a
    // better-stated reason, and answering "too large" for them would be wrong.
    expect(exceedsMaxCostAmount('abc')).toBe(false)
    expect(exceedsMaxCostAmount('')).toBe(false)
  })
})

describe('formatCurrency never renders NaN', () => {
  it('renders a comma-typed Polish amount as money rather than NaN', () => {
    expect(formatCurrency('249,50', 'PLN', 'pl')).toBe('249,50\u00A0zł')
  })

  it.each([
    ['an empty amount', '', 'PLN'],
    ['a blank amount', '   ', 'PLN'],
    ['letters', 'abc', 'PLN'],
    ['two decimal separators', '1,250.50', 'PLN'],
    ['the word itself', 'NaN', 'PLN'],
    ['a half-typed currency', '249.50', 'P'],
    ['a lower-case currency', '249.50', 'pln'],
  ])('renders nothing at all for %s', (_case, amount, currency) => {
    for (const locale of ['pl', 'en']) {
      const rendered = formatCurrency(amount, currency, locale)
      expect(rendered).toBe('')
      expect(rendered).not.toContain('NaN')
    }
  })

  it('does not throw on a currency Intl would refuse', () => {
    // `new Intl.NumberFormat('pl', { currency: 'P' })` is a RangeError — two
    // keystrokes into typing `PLN` used to crash the editor.
    expect(() => formatCurrency('249.50', 'P', 'pl')).not.toThrow()
  })

  it('still renders a zero cost, which is a real amount and not an absent one', () => {
    expect(formatCurrency('0', 'PLN', 'pl')).toBe('0,00\u00A0zł')
  })
})
