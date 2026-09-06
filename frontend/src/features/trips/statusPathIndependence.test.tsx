import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Item } from '../../api/items'
import App from '../../App'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'

/**
 * Step 3.5 — R04's "never demanded", expressed as a test.
 *
 * The whole reservation feature (Phase 3) must not have made moving an item
 * to *done* any harder, and the readiness counter (R02) must not have quietly
 * started meaning "arranged *and* documented". If either had happened, it
 * would be a real defect in an earlier Step of this phase — this file's job
 * is only to prove it did not, by driving the real status control the way an
 * owner does, not by inspecting `ItemDialog` or `readiness.py` in isolation.
 *
 * The arithmetic half of assertion 2 — the cheaper, more decisive place a
 * "done means done *and* documented" regression would actually be caught —
 * lives in `backend/tests/test_domain_readiness.py` and
 * `backend/tests/test_items_api.py`. This file's own readiness assertions are
 * the frontend's confirmation that nothing between the server and the
 * screen invents a distinction the server itself does not make.
 */

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const STAGE = {
  id: 'stage-1',
  position: 0,
  place: 'Kuala Lumpur',
  start_date: '2026-10-10',
  end_date: '2026-10-13',
}

const BASE_ITEM: Item = {
  id: 'item-1',
  position: 0,
  kind: 'activity',
  status: 'to_book',
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

function renderApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  )
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('moving an item to done through the status control', () => {
  /** Every `PATCH /items/:id` this suite issued, body already parsed. */
  let patchCalls: Record<string, unknown>[] = []
  /** The server's own idea of the item — mutated only by a PATCH, exactly as
      the real API would answer a second request after a status change. */
  let item: Item = { ...BASE_ITEM }

  function trip() {
    // The same arithmetic `readiness.py` implements, over the one item this
    // trip carries — not asserted against here, only used to make the mock
    // behave like the real API a status change would actually reach.
    const tracked = item.status !== 'to_plan' ? 1 : 0
    const arranged = item.status === 'done' ? 1 : 0
    return {
      id: 'trip-1',
      title: 'Malezja, październik 2026',
      start_date: '2026-10-10',
      end_date: '2026-10-13',
      departure_place: 'Warszawa',
      return_place: 'Katowice',
      readiness: { arranged, tracked },
      stages: [STAGE],
      days: [{ id: 'day-1', date: '2026-10-11', stage_ids: ['stage-1'], items: [item] }],
    }
  }

  function day() {
    return {
      id: 'day-1',
      trip_id: 'trip-1',
      date: '2026-10-11',
      stages: [STAGE],
      items: [item],
      attachments: [] as unknown[],
      previous_date: null,
      next_date: null,
    }
  }

  beforeEach(() => {
    patchCalls = []
    item = { ...BASE_ITEM }
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method ?? 'GET').toUpperCase()

        if (url.endsWith('/auth/me')) return Promise.resolve(json(200, OWNER))
        if (url.endsWith('/trips') && method === 'GET') return Promise.resolve(json(200, [trip()]))
        if (url.includes('/items/') && method === 'PATCH') {
          const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}
          patchCalls.push(body)
          item = { ...item, ...(body as Partial<Item>) }
          return Promise.resolve(json(200, item))
        }
        if (url.includes('/days/') && method === 'GET') return Promise.resolve(json(200, day()))
        if (/\/trips\/[^/]+$/u.test(url)) return Promise.resolve(json(200, trip()))
        return Promise.resolve(json(404, { error: { code: 'not_found', field: null } }))
      }),
    )
  })

  /**
   * Assertions 1 and 3 (Step 3.5): the request carries the status change and
   * nothing reservation-shaped, no dialog/banner/panel opens beyond the one
   * editor already on screen, and the control stays exactly one click —
   * choosing the pill fires no request of its own, and Save needs nothing
   * else typed or confirmed.
   */
  it('sends only the status change, opens nothing extra, and moves the counter', async () => {
    const user = userEvent.setup()
    renderApp(DAY_PATH)

    await screen.findByText('Batu Caves')
    await user.click(screen.getByRole('button', { name: /Batu Caves/u }))

    // Exactly the one dialog the click opened — the reservation disclosure
    // inside it is a plain part of that dialog and stays collapsed.
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    const reservation = document.querySelector('details.reservation-panel') as HTMLDetailsElement
    expect(reservation).not.toBeNull()
    expect(reservation.open).toBe(false)

    // The one click the control is: picking "Gotowe" is a local radio change
    // — no request, no second dialog, no error banner.
    await user.click(screen.getByRole('radio', { name: pl.item.status.done }))

    expect(patchCalls).toHaveLength(0)
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(reservation.open).toBe(false)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    // Save is the only further action, and it is a plain click — nothing to
    // confirm, nothing required to fill in first.
    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() => expect(patchCalls).toHaveLength(1))
    expect(patchCalls[0]).toMatchObject({
      status: 'done',
      confirmation_number: null,
      cost_amount: null,
      cost_currency: null,
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    // Back to the timeline: the counter the whole product exists to show has
    // moved, purely from the status change just made — nothing about the
    // still-empty reservation fields held it back.
    await user.click(screen.getByRole('link', { name: pl.day.backToTimeline }))
    expect(await screen.findByText('1 z 1 załatwionych')).toBeInTheDocument()
  })
})

describe('the readiness counter does not distinguish a documented done item from a bare one', () => {
  const documented: Item = {
    ...BASE_ITEM,
    id: 'item-documented',
    title: 'Nocleg udokumentowany',
    status: 'done',
    confirmation_number: 'SX-9912L',
    cost_amount: '249.00',
    cost_currency: 'PLN',
  }

  const undocumented: Item = {
    ...BASE_ITEM,
    id: 'item-undocumented',
    title: 'Nocleg bez danych',
    status: 'done',
  }

  function tripWith(items: Item[]) {
    return {
      id: 'trip-1',
      title: 'Malezja, październik 2026',
      start_date: '2026-10-10',
      end_date: '2026-10-13',
      departure_place: 'Warszawa',
      return_place: 'Katowice',
      readiness: { arranged: items.length, tracked: items.length },
      stages: [STAGE],
      days: [{ id: 'day-1', date: '2026-10-11', stage_ids: ['stage-1'], items }],
    }
  }

  function mockTrip(trip: ReturnType<typeof tripWith>) {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.endsWith('/auth/me')) return Promise.resolve(json(200, OWNER))
        if (url.endsWith('/trips')) return Promise.resolve(json(200, [trip]))
        if (/\/trips\/[^/]+$/u.test(url)) return Promise.resolve(json(200, trip))
        return Promise.resolve(json(404, { error: { code: 'not_found', field: null } }))
      }),
    )
  }

  /**
   * Assertion 2 (Step 3.5), the frontend half: this is the test a later
   * "arranged means arranged *and* documented" regression would have to
   * break. Two `done` items, one carrying a confirmation number and a cost
   * and one carrying neither, must count — and render — exactly the same.
   */
  it('renders "2 z 2 załatwionych" whether or not either done item carries reservation data', async () => {
    mockTrip(tripWith([documented, undocumented]))

    renderApp('/trips/trip-1')

    expect(await screen.findByText('2 z 2 załatwionych')).toBeInTheDocument()
    // Both status chips render identically — the same translated word, the
    // same glyph — with nothing beside either one keyed on the reservation
    // fields that differ between the two items.
    expect(screen.getAllByText(pl.item.status.done)).toHaveLength(2)
  })

  it('renders the identical fraction once neither done item carries reservation data', async () => {
    // The counterfactual: the same two-done-item trip, with the reservation
    // fields on the previously-documented item wiped. If the served counter
    // — or anything downstream of it — were secretly sensitive to reservation
    // data, this render would differ from the one above; it must not.
    const bareTwin: Item = { ...documented, confirmation_number: null, cost_amount: null, cost_currency: null }
    mockTrip(tripWith([bareTwin, undocumented]))

    renderApp('/trips/trip-1')

    expect(await screen.findByText('2 z 2 załatwionych')).toBeInTheDocument()
  })
})
