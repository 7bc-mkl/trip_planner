import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import App from '../../App'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { FakeXhr } from '../../test/fakeXhr'
import { SessionProvider } from '../auth/SessionContext'
import { DayAttachments } from './DayAttachments'
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

  /**
   * Step 3.3: the word *optional* is what this spec substitutes for the cut
   * auto-expand nudge — a user who has just attached a voucher discovers the
   * panel by reading its own label, not by the app opening it for them. So
   * the collapsed summary has to actually carry that word, in both locales,
   * checked independently of the "labels the heading" tests above (which
   * assert the whole string matches, not that this particular word is in it).
   */
  it('names the panel "optional" in the collapsed Polish summary', () => {
    render(<ReservationPanel value={EMPTY} onChange={vi.fn()} />)

    expect(pl.item.reservation.heading).toMatch(/opcjonalne/iu)
    expect(screen.getByText(pl.item.reservation.heading)).toBeInTheDocument()
  })

  it('names the panel "optional" in the collapsed English summary', async () => {
    await applyLocale('en')
    render(<ReservationPanel value={EMPTY} onChange={vi.fn()} />)

    expect(en.item.reservation.heading).toMatch(/optional/iu)
    expect(screen.getByText(en.item.reservation.heading)).toBeInTheDocument()
  })

  /**
   * Step 3.3's sharpest rule: nothing ever opens this panel for the user.
   * `ReservationPanel`'s own props are exactly `{ value, onChange }` — there
   * is no `open`, `defaultOpen` or `forceOpen` channel for a caller to push
   * through, so a re-render carrying brand-new props (a fresh `value` object
   * and a fresh `onChange` — exactly what an upload landing on the item, or
   * any other state change in `ItemDialog`, produces) cannot move `open`
   * either way. This is the strongest assertion this file can make without
   * static analysis of every call site: it proves the *only* prop surface
   * the panel exposes cannot carry an open signal, across many distinct
   * re-renders.
   */
  it('cannot be opened by a re-render, no matter how the props change', () => {
    const { rerender } = render(<ReservationPanel value={EMPTY} onChange={vi.fn()} />)
    const details = document.querySelector('details.reservation-panel') as HTMLDetailsElement
    expect(details.open).toBe(false)

    const values: ReservationValue[] = [
      { confirmationNumber: 'SX-9912L', costAmount: '', costCurrency: '' },
      { confirmationNumber: '', costAmount: '249.00', costCurrency: 'PLN' },
      EMPTY,
    ]
    for (const value of values) {
      rerender(<ReservationPanel value={value} onChange={vi.fn()} />)
      expect(details.open).toBe(false)
    }
  })

  /**
   * A compile-time backstop for the same guarantee: `ReservationPanel`'s
   * props are exactly `{ value, onChange }` (see the type above this
   * component). There is no `open` prop today, so passing one is a type
   * error — the line below only compiles *because* `@ts-expect-error`
   * suppresses that error. If a future edit adds an `open`/`defaultOpen`
   * escape hatch to the props, this line stops having an error to suppress
   * and `tsc -b` fails, catching the regression before it ships. This never
   * executes — it is caught by `npm run typecheck` / `npm run build`, not by
   * this test runner — so it is a static guard layered on top of, not a
   * substitute for, the runtime tests above and below.
   */
  it('has no open-forcing prop in its type — enforced at compile time, not here', () => {
    function TypeGuardOnly() {
      // @ts-expect-error — ReservationPanel takes only `value` and `onChange`.
      return <ReservationPanel value={EMPTY} onChange={vi.fn()} open />
    }
    expect(TypeGuardOnly).toBeDefined()
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

  /**
   * Step 3.4: the currency field defaults to `PLN` rather than blank, on
   * both a brand-new item and an existing one that never had a cost.
   */
  it('defaults the currency field to PLN on a fresh item', async () => {
    const user = userEvent.setup()
    renderApp()
    await screen.findByText('Batu Caves')
    await user.click(screen.getByRole('button', { name: pl.item.add }))

    await user.click(screen.getByText(pl.item.reservation.heading))
    expect(screen.getByLabelText(pl.item.reservation.currencyLabel)).toHaveValue('PLN')
  })

  it('defaults the currency field to PLN on an existing item with no cost yet', async () => {
    const user = userEvent.setup()
    await openItem(user)

    await user.click(screen.getByText(pl.item.reservation.heading))
    expect(screen.getByLabelText(pl.item.reservation.currencyLabel)).toHaveValue('PLN')
  })

  /**
   * The gap Step 3.2 deliberately left open: `reservationInput` clears the
   * whole cost pair the moment either half is blank, which used to mean a
   * cost typed with no currency was silently dropped rather than saved.
   * With the currency now defaulting to `PLN` (`itemDraft.ts`), typing only
   * the amount and touching nothing else must still persist — this is the
   * test that pins that down, rather than trusting the default by
   * inspection alone.
   */
  it('persists a typed amount under the default PLN currency when the currency field is never touched', async () => {
    const user = userEvent.setup()
    await openItem(user)

    await user.click(screen.getByText(pl.item.reservation.heading))
    expect(screen.getByLabelText(pl.item.reservation.currencyLabel)).toHaveValue('PLN')
    await user.type(screen.getByLabelText(pl.item.reservation.costLabel), '249.00')

    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(patchCalls[0]).toMatchObject({
      cost_amount: '249.00',
      cost_currency: 'PLN',
    })
  })

  it('sits directly beneath the item attachment list, with nothing between them', async () => {
    const user = userEvent.setup()
    await openItem(user)

    const attachments = document.querySelector('.item-attachments')
    const panel = document.querySelector('details.reservation-panel')
    expect(attachments).not.toBeNull()
    expect(panel).not.toBeNull()
    // Adjacent siblings in the DOM — the spec's "directly beneath the
    // attachment list" is this, exactly, not "somewhere lower on the page".
    expect(attachments!.nextElementSibling).toBe(panel)
  })

  /**
   * The regression an earlier, cut draft of this spec would have caused: it
   * had this exact upload spring the panel open, reasoning that this is the
   * one moment the user is looking at a voucher. That was cut for breaking
   * invariant 4 ("no nagging, ever") — see `ReservationPanel`'s own doc — and
   * this is the test that pins the cut down. It drives a real upload through
   * the real dropzone inside the real dialog, the same `FakeXhr` machinery
   * `itemAttachments.test.tsx` uses, rather than asserting against a mock
   * that could not have sprung the panel open even if the code tried to.
   */
  it('stays collapsed even once an upload to the item completes', async () => {
    FakeXhr.reset()
    vi.stubGlobal('XMLHttpRequest', FakeXhr as unknown as typeof XMLHttpRequest)
    document.cookie = 'csrf_token=test-csrf-token; path=/'

    const user = userEvent.setup()
    await openItem(user)

    const details = document.querySelector('details.reservation-panel') as HTMLDetailsElement
    expect(details.open).toBe(false)

    const file = new File(['%PDF-1.4 …'], 'voucher.pdf', { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: 2048 })
    const dialog = within(screen.getByRole('dialog'))
    await user.upload(dialog.getByLabelText(new RegExp(pl.upload.add)), file)
    FakeXhr.instances[0]!.respond(201, {
      id: 'attachment-fresh',
      filename: 'voucher.pdf',
      content_type: 'application/pdf',
      byte_size: 2048,
      sha256: 'voucher-sha',
      created_at: '2026-09-06T10:11:12Z',
      item_id: MUSEUM.id,
      trip_day_id: null,
    } satisfies Attachment)

    await waitFor(() => expect(screen.getAllByText('voucher.pdf')).toHaveLength(1))
    expect(details.open).toBe(false)
  })
})

describe('the disclosure does not exist at all for a day-level attachment list', () => {
  beforeEach(async () => {
    initI18n('pl')
    await applyLocale('pl')
  })

  it("renders no reservation panel beside a day's attachments — a day is not booked; an item is", () => {
    render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(document.querySelector('.reservation-panel')).toBeNull()
    expect(document.querySelector('details')).toBeNull()
    expect(screen.queryByText(pl.item.reservation.heading)).not.toBeInTheDocument()
  })
})
