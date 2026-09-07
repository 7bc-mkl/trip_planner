import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { applyLocale, initI18n } from '../../i18n'
import { ReservationPanel } from './ReservationPanel'
import type { ReservationValue } from './ReservationPanel'

/**
 * Step 3.4-review-fix-1: Step 3.7's walk found `formatCurrency` had no call
 * site anywhere in the app — the saved cost only ever showed up as the raw
 * `1250.00` in the editable input, so the spec's `Intl` rendering rule
 * governed nothing a user could actually see. This file is that rule's first
 * real call site: the collapsed reservation summary shows the saved cost,
 * formatted, in both locales — and shows nothing at all when there is none,
 * which is what keeps this from becoming the nag Step 3.6 rules out.
 *
 * `formatCurrency` renders `Intl`'s group separator as a non-breaking space
 * (`format.test.ts` asserts that directly against the raw return value), but
 * the expected strings below use a plain space instead — deliberately, not
 * by oversight. `@testing-library/dom`'s `getByText` only normalizes the
 * *node's* text before comparing (collapsing a non-breaking space to a plain
 * one, among other whitespace), never the matcher string itself, so a query
 * written with a literal non-breaking space fails against that normalized
 * text. A plain space is what actually matches here.
 */

const WITH_COST: ReservationValue = {
  confirmationNumber: '',
  costAmount: '1250.00',
  costCurrency: 'PLN',
}

const WITHOUT_COST: ReservationValue = {
  confirmationNumber: '',
  costAmount: '',
  costCurrency: '',
}

const PL_FORMATTED = '1 250,00 zł'
const EN_FORMATTED = 'PLN 1,250.00'

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the collapsed summary shows the saved cost through Intl', () => {
  it('renders the Polish grouped form when a cost is set', () => {
    render(<ReservationPanel value={WITH_COST} onChange={vi.fn()} />)

    expect(screen.getByText(PL_FORMATTED)).toBeInTheDocument()
  })

  it('renders the English ISO-code form when a cost is set', async () => {
    await applyLocale('en')
    render(<ReservationPanel value={WITH_COST} onChange={vi.fn()} />)

    expect(screen.getByText(EN_FORMATTED)).toBeInTheDocument()
  })

  it('renders no cost-shaped element at all when the item has no cost, in Polish', () => {
    render(<ReservationPanel value={WITHOUT_COST} onChange={vi.fn()} />)

    expect(document.querySelector('.reservation-panel__cost')).toBeNull()
  })

  it('renders no cost-shaped element at all when the item has no cost, in English', async () => {
    await applyLocale('en')
    render(<ReservationPanel value={WITHOUT_COST} onChange={vi.fn()} />)

    expect(document.querySelector('.reservation-panel__cost')).toBeNull()
  })

  it('renders nothing when only one half of the pair is present, mirroring reservationInput', () => {
    render(
      <ReservationPanel
        value={{ confirmationNumber: '', costAmount: '249.00', costCurrency: '' }}
        onChange={vi.fn()}
      />,
    )

    expect(document.querySelector('.reservation-panel__cost')).toBeNull()
  })
})
