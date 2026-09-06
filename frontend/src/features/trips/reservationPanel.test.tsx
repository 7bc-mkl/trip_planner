import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'
import { ReservationPanel, reservationInput } from './ReservationPanel'
import type { ReservationValue } from './ReservationPanel'

/**
 * Step 3.2: the reservation disclosure inside the item editor.
 *
 * Two levels: `ReservationPanel` and `reservationInput` are exercised on
 * their own (no dialog, no `fetch`), and the save path is exercised through
 * the real screen — `ItemDialog` owns the draft and the submit, so that is
 * the only place "what actually gets sent" can be observed honestly.
 */

const EMPTY: ReservationValue = { confirmationNumber: '', costAmount: '', costCurrency: '' }

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the reservation panel on its own', () => {
  it('is collapsed on first render', () => {
    render(<ReservationPanel value={EMPTY} onChange={vi.fn()} />)

    const details = document.querySelector('details.reservation-panel') as HTMLDetailsElement
    expect(details).not.toBeNull()
    expect(details.open).toBe(false)
  })

  it('labels the heading and the three controls in Polish', () => {
    render(<ReservationPanel value={EMPTY} onChange={vi.fn()} />)

    expect(screen.getByText(pl.item.reservation.heading)).toBeInTheDocument()
    expect(
      screen.getByLabelText(pl.item.reservation.confirmationNumberLabel),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(pl.item.reservation.costLabel)).toBeInTheDocument()
    expect(screen.getByLabelText(pl.item.reservation.currencyLabel)).toBeInTheDocument()
  })

  it('labels the heading and the three controls in English', async () => {
    await applyLocale('en')
    render(<ReservationPanel value={EMPTY} onChange={vi.fn()} />)

    expect(screen.getByText(en.item.reservation.heading)).toBeInTheDocument()
    expect(
      screen.getByLabelText(en.item.reservation.confirmationNumberLabel),
    ).toBeInTheDocument()
    expect(screen.getByLabelText(en.item.reservation.costLabel)).toBeInTheDocument()
    expect(screen.getByLabelText(en.item.reservation.currencyLabel)).toBeInTheDocument()
  })

  it('never marks a field required or invalid while empty — invariant 1, from the field side', () => {
    render(<ReservationPanel value={EMPTY} onChange={vi.fn()} />)

    for (const label of [
      pl.item.reservation.confirmationNumberLabel,
      pl.item.reservation.costLabel,
      pl.item.reservation.currencyLabel,
    ]) {
      const field = screen.getByLabelText(label)
      expect(field).not.toBeRequired()
      expect(field).toBeValid()
    }
  })
})

describe('reservationInput — the draft-to-wire translation', () => {
  it('sends every field cleared when the draft is entirely empty', () => {
    expect(reservationInput(EMPTY)).toEqual({
      confirmation_number: null,
      cost_amount: null,
      cost_currency: null,
    })
  })

  it('clears the cost pair together when only the amount was typed', () => {
    expect(
      reservationInput({ confirmationNumber: '', costAmount: '249.00', costCurrency: '' }),
    ).toEqual({ confirmation_number: null, cost_amount: null, cost_currency: null })
  })

  it('clears the cost pair together when only the currency was typed', () => {
    expect(
      reservationInput({ confirmationNumber: '', costAmount: '', costCurrency: 'PLN' }),
    ).toEqual({ confirmation_number: null, cost_amount: null, cost_currency: null })
  })

  it('sends the cost pair together, as strings, when both halves are present', () => {
    expect(
      reservationInput({
        confirmationNumber: 'SX-9912L',
        costAmount: '249.00',
        costCurrency: 'PLN',
      }),
    ).toEqual({
      confirmation_number: 'SX-9912L',
      cost_amount: '249.00',
      cost_currency: 'PLN',
    })
  })
})

describe('the reservation panel wired into the real item editor', () => {
  const json = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })

  const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

  const STAGE = {
    id: 'stage-1',
    position: 0,
    place: 'Kuala Lumpur',
    start_date: '2026-10-10',
    end_date: '2026-10-13',
  }

  const MUSEUM = {
    id: 'item-1',
    position: 0,
    kind: 'activity' as const,
    status: 'to_plan' as const,
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

  const DAY = {
    id: 'day-1',
    trip_id: 'trip-1',
    date: '2026-10-11',
    stages: [STAGE],
    items: [MUSEUM],
    attachments: [] as unknown[],
    previous_date: null,
    next_date: null,
  }

  const TRIP = {
    id: 'trip-1',
    title: 'Malezja, październik 2026',
    start_date: '2026-10-10',
    end_date: '2026-10-13',
    departure_place: 'Warszawa',
    return_place: 'Katowice',
    readiness: { arranged: 0, tracked: 1 },
    stages: [STAGE],
    days: [{ id: 'day-1', date: '2026-10-11', stage_ids: ['stage-1'], items: [MUSEUM] }],
  }

  const DAY_PATH = '/trips/trip-1/days/2026-10-11'

  /** Every `PATCH /items/:id` this suite issued, in order, body already parsed. */
  let patchCalls: Record<string, unknown>[] = []

  function mockApi() {
    patchCalls = []
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method ?? 'GET').toUpperCase()

        if (url.endsWith('/auth/me')) return Promise.resolve(json(200, OWNER))
        if (url.endsWith('/trips') && method === 'GET') return Promise.resolve(json(200, [TRIP]))
        if (url.includes('/items/') && method === 'PATCH') {
          const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}
          patchCalls.push(body)
          return Promise.resolve(json(200, { ...MUSEUM, ...body }))
        }
        if (url.includes('/days/') && method === 'GET') return Promise.resolve(json(200, DAY))
        if (/\/trips\/[^/]+$/u.test(url)) return Promise.resolve(json(200, TRIP))
        return Promise.resolve(json(404, { error: { code: 'not_found', field: null } }))
      }),
    )
  }

  function renderApp() {
    return render(
      <MemoryRouter initialEntries={[DAY_PATH]}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </MemoryRouter>,
    )
  }

  async function openItem(user: ReturnType<typeof userEvent.setup>) {
    renderApp()
    await screen.findByText('Batu Caves')
    await user.click(screen.getByRole('button', { name: /Batu Caves/u }))
  }

  beforeEach(() => {
    mockApi()
  })

  it('renders the panel collapsed the moment the editor opens', async () => {
    const user = userEvent.setup()
    await openItem(user)

    const details = document.querySelector('details.reservation-panel') as HTMLDetailsElement
    expect(details).not.toBeNull()
    expect(details.open).toBe(false)
  })

  it('saves an existing item with every reservation field left empty', async () => {
    const user = userEvent.setup()
    await openItem(user)

    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(patchCalls[0]).toMatchObject({
      confirmation_number: null,
      cost_amount: null,
      cost_currency: null,
    })
    // The dialog closed on a clean save — nothing complained about an empty field.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('never raises a validation error for a reservation field typed into and then cleared', async () => {
    const user = userEvent.setup()
    await openItem(user)

    await user.click(screen.getByText(pl.item.reservation.heading))
    const amount = screen.getByLabelText(pl.item.reservation.costLabel)
    await user.type(amount, '10')
    await user.clear(amount)
    expect(amount).toBeValid()

    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('sends a typed confirmation number and cost through, on save', async () => {
    const user = userEvent.setup()
    await openItem(user)

    await user.click(screen.getByText(pl.item.reservation.heading))
    await user.type(screen.getByLabelText(pl.item.reservation.confirmationNumberLabel), 'SX-9912L')
    await user.type(screen.getByLabelText(pl.item.reservation.costLabel), '249.00')
    await user.type(screen.getByLabelText(pl.item.reservation.currencyLabel), 'PLN')

    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(patchCalls[0]).toMatchObject({
      confirmation_number: 'SX-9912L',
      cost_amount: '249.00',
      cost_currency: 'PLN',
    })
  })
})
