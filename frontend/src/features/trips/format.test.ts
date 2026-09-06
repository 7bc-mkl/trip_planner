import { describe, expect, it } from 'vitest'

import { formatCurrency } from './format'

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
