import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Item } from '../../api/items'
import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { clearAllDrafts } from '../auth/draftStore'
import { SessionProvider } from '../auth/SessionContext'

/**
 * Step 3.4-review-fix-2 — the cost input, walked the way the final gate
 * walked it, in a real editor rather than against the formatter alone.
 *
 * Two defects are pinned down here:
 *
 * 1. **`249,50` is a cost, not `NaN`.** The comma is the standard Polish
 *    decimal separator and this is a Polish-first product (R01, R09); typing
 *    it used to render a literal `NaN €` in the collapsed summary and then
 *    fail the save. It must round-trip: `249.50` on the wire, formatted
 *    money on the screen, in both locales.
 * 2. **A refused field is marked.** The save used to fail with "Sprawdź
 *    zaznaczone pola" while no input carried `aria-invalid` and no
 *    field-level message existed anywhere — the user was told to check the
 *    marked fields and nothing was marked. Asserted here through the
 *    accessibility attributes (`aria-invalid`, `aria-describedby` resolving
 *    to a real element with the translated text), not merely through the text
 *    being somewhere on the page.
 *
 * The expected Polish money strings below use a plain space where `Intl`
 * emits a non-breaking one, for the reason `reservationCost.test.tsx`
 * documents: `getByText` normalizes the *node's* text but never the matcher.
 * `format.test.ts` asserts the raw non-breaking form directly.
 */

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

/**
 * The signed-in owner. The locale lives here rather than only in `applyLocale`
 * because the app re-applies the *owner's* locale on load — an English test
 * that only called `applyLocale('en')` would be back in Polish by the time the
 * editor opened.
 */
let ownerLocale: 'pl' | 'en' = 'pl'
const owner = () => ({ id: 'owner-1', email: 'owner@example.com', locale: ownerLocale })

const STAGE = {
  id: 'stage-1',
  position: 0,
  place: 'Kuala Lumpur',
  start_date: '2026-10-10',
  end_date: '2026-10-13',
}

const MUSEUM: Item = {
  id: 'item-1',
  position: 0,
  kind: 'activity',
  status: 'to_plan',
  start_time: '10:30:00',
  end_time: '12:00:00',
  end_date: null,
  title: 'Batu Caves',
  notes: 'bring water',
  attachment_count: 0,
  attachments: [],
  confirmation_number: null,
  cost_amount: null,
  cost_currency: null,
}

const DAY_PATH = '/trips/trip-1/days/2026-10-11'

/** The server's copy of the item, mutated by PATCH so a round trip is real. */
let stored: Item
/** Every `PATCH /items/:id` body this suite issued, in order. */
let patchCalls: Record<string, unknown>[] = []

function day() {
  return {
    id: 'day-1',
    trip_id: 'trip-1',
    date: '2026-10-11',
    stages: [STAGE],
    items: [stored],
    attachments: [] as unknown[],
    previous_date: null,
    next_date: null,
  }
}

function trip() {
  return {
    id: 'trip-1',
    title: 'Malezja, październik 2026',
    start_date: '2026-10-10',
    end_date: '2026-10-13',
    departure_place: 'Warszawa',
    return_place: 'Katowice',
    readiness: { arranged: 0, tracked: 1 },
    stages: [STAGE],
    days: [{ id: 'day-1', date: '2026-10-11', stage_ids: ['stage-1'], items: [stored] }],
  }
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')

  stored = { ...MUSEUM }
  patchCalls = []
  ownerLocale = 'pl'
  // A blocked save deliberately leaves the draft behind so it can be retried
  // — which would otherwise leak a refused amount into the next test.
  clearAllDrafts()
  document.cookie = 'csrf_token=test-csrf-token; path=/'

  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()

      if (url.endsWith('/auth/me')) return Promise.resolve(json(200, owner()))
      if (url.endsWith('/trips') && method === 'GET') return Promise.resolve(json(200, [trip()]))
      if (url.includes('/items/') && method === 'PATCH') {
        const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}
        patchCalls.push(body)
        stored = { ...stored, ...(body as Partial<Item>) }
        return Promise.resolve(json(200, stored))
      }
      if (url.includes('/days/') && method === 'GET') return Promise.resolve(json(200, day()))
      if (/\/trips\/[^/]+$/u.test(url)) return Promise.resolve(json(200, trip()))
      return Promise.resolve(json(404, { error: { code: 'not_found', field: null } }))
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function renderApp() {
  return render(
    <MemoryRouter initialEntries={[DAY_PATH]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  )
}

async function openPanel(user: ReturnType<typeof userEvent.setup>, heading: string) {
  renderApp()
  await screen.findByText('Batu Caves')
  await user.click(screen.getByRole('button', { name: /Batu Caves/u }))
  await user.click(screen.getByText(heading))
}

/** The element an input's `aria-describedby` actually resolves to. */
function describedBy(field: HTMLElement): HTMLElement | null {
  const id = field.getAttribute('aria-describedby')
  return id === null ? null : document.getElementById(id)
}

describe('a Polish decimal comma is a cost, not NaN', () => {
  it('saves 249,50 as 249.50 and renders it as money, in Polish', async () => {
    const user = userEvent.setup()
    await openPanel(user, pl.item.reservation.heading)

    const amount = screen.getByLabelText(pl.item.reservation.costLabel)
    await user.type(amount, '249,50')

    // The defect, at the exact place it was seen: the collapsed summary.
    expect(amount).toBeValid()
    expect(document.body.textContent).not.toContain('NaN')
    expect(screen.getByText('249,50 zł')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(patchCalls[0]).toMatchObject({ cost_amount: '249.50', cost_currency: 'PLN' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    // And it comes back from the server the same way it went out.
    await user.click(await screen.findByRole('button', { name: /Batu Caves/u }))
    expect(screen.getByText('249,50 zł')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('NaN')
  })

  it('saves 249,50 as 249.50 and renders it as money, in English', async () => {
    ownerLocale = 'en'
    await applyLocale('en')
    const user = userEvent.setup()
    await openPanel(user, en.item.reservation.heading)

    await user.type(screen.getByLabelText(en.item.reservation.costLabel), '249,50')
    expect(screen.getByText('PLN 249.50')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: en.item.save }))

    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(patchCalls[0]).toMatchObject({ cost_amount: '249.50', cost_currency: 'PLN' })
    expect(document.body.textContent).not.toContain('NaN')
  })

  it('never shows NaN part-way through typing a comma amount', async () => {
    const user = userEvent.setup()
    await openPanel(user, pl.item.reservation.heading)

    const amount = screen.getByLabelText(pl.item.reservation.costLabel)
    for (const character of '1 250,50') {
      await user.type(amount, character)
      expect(document.body.textContent).not.toContain('NaN')
    }

    // A group separator is normalised away too, rather than refused.
    expect(amount).toBeValid()
    await user.click(screen.getByRole('button', { name: pl.item.save }))
    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(patchCalls[0]).toMatchObject({ cost_amount: '1250.50' })
  })
})

describe('a refused cost marks the field the message is about', () => {
  it('marks the amount, in Polish, and refuses the save while it is marked', async () => {
    const user = userEvent.setup()
    await openPanel(user, pl.item.reservation.heading)

    const amount = screen.getByLabelText(pl.item.reservation.costLabel)
    await user.type(amount, '249,555')

    // Marked, associated, and the association resolves to the real message.
    expect(amount).toHaveAttribute('aria-invalid', 'true')
    expect(amount).toBeInvalid()
    expect(describedBy(amount)).not.toBeNull()
    expect(describedBy(amount)).toHaveTextContent(pl.error.invalid_cost)
    expect(describedBy(amount)).toHaveAttribute('role', 'alert')

    // Nothing is sent — the generic "check the marked fields" answer is what
    // this replaces, so it must not be reachable this way any more.
    const save = screen.getByRole('button', { name: pl.item.save })
    expect(save).toBeDisabled()
    await user.click(save)
    expect(patchCalls).toHaveLength(0)

    // And it un-marks itself the moment the value becomes savable.
    await user.type(amount, '{Backspace}')
    expect(amount).not.toHaveAttribute('aria-invalid')
    expect(amount).toBeValid()
    expect(describedBy(amount)).toBeNull()
    expect(screen.getByRole('button', { name: pl.item.save })).toBeEnabled()
  })

  it('marks the amount, in English, with the English message', async () => {
    ownerLocale = 'en'
    await applyLocale('en')
    const user = userEvent.setup()
    await openPanel(user, en.item.reservation.heading)

    const amount = screen.getByLabelText(en.item.reservation.costLabel)
    await user.type(amount, '-40')

    expect(amount).toHaveAttribute('aria-invalid', 'true')
    expect(describedBy(amount)).toHaveTextContent(en.error.invalid_cost)
    expect(screen.getByRole('button', { name: en.item.save })).toBeDisabled()
  })

  it('marks the currency half, not the amount, when the currency is the bad one', async () => {
    const user = userEvent.setup()
    await openPanel(user, pl.item.reservation.heading)

    await user.type(screen.getByLabelText(pl.item.reservation.costLabel), '249,50')
    const currency = screen.getByLabelText(pl.item.reservation.currencyLabel)
    await user.clear(currency)
    await user.type(currency, 'PL')

    expect(currency).toHaveAttribute('aria-invalid', 'true')
    expect(describedBy(currency)).toHaveTextContent(pl.error.invalid_cost)
    expect(screen.getByLabelText(pl.item.reservation.costLabel)).not.toHaveAttribute('aria-invalid')
    // A cost that cannot be saved is not rendered as if it could be.
    expect(document.querySelector('.reservation-panel__cost')).toBeNull()
    expect(document.body.textContent).not.toContain('NaN')
  })

  it('marks nothing, and blocks nothing, while the cost is simply empty', async () => {
    const user = userEvent.setup()
    await openPanel(user, pl.item.reservation.heading)

    for (const label of [pl.item.reservation.costLabel, pl.item.reservation.currencyLabel]) {
      expect(screen.getByLabelText(label)).not.toHaveAttribute('aria-invalid')
    }
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    // A half-typed currency with no amount is not a refusal either: nothing
    // is sent, so there is nothing to refuse.
    const currency = screen.getByLabelText(pl.item.reservation.currencyLabel)
    await user.clear(currency)
    await user.type(currency, 'P')
    expect(currency).not.toHaveAttribute('aria-invalid')
    expect(screen.getByRole('button', { name: pl.item.save })).toBeEnabled()
  })
})
