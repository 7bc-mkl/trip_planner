import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyFilter, countByKind, matchesFilter } from './filter'
import type { Item } from '../../api/items'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'

/**
 * Phase 4 step 1 and 2: the *All* / *Only outstanding* filter and the per-type chips.
 */

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

function item(overrides: Partial<Item> & { id: string }): Item {
  return {
    position: 0,
    kind: 'activity',
    status: 'to_plan',
    start_time: null,
    end_time: null,
    end_date: null,
    title: overrides.id,
    notes: null,
    attachment_count: 0,
    ...overrides,
  }
}

const TO_PLAN = item({ id: 'to-plan', title: 'Batu Caves', status: 'to_plan' })
const TO_BOOK = item({ id: 'to-book', title: 'Nocleg w KL', status: 'to_book', kind: 'accommodation' })
const DONE = item({ id: 'done', title: 'Lot do KL', status: 'done', kind: 'transport' })

const TRIP = {
  id: 'trip-1',
  title: 'Malezja, październik 2026',
  start_date: '2026-10-10',
  end_date: '2026-10-11',
  departure_place: 'Warszawa',
  return_place: 'Katowice',
  readiness: { arranged: 1, tracked: 2 },
  stages: [],
  days: [
    { id: 'day-1', date: '2026-10-10', stage_ids: [], items: [TO_PLAN, TO_BOOK, DONE] },
    { id: 'day-2', date: '2026-10-11', stage_ids: [], items: [] },
  ],
}

function mockApi(trip: unknown = TRIP) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return Promise.resolve(json(200, OWNER))
      return Promise.resolve(json(200, trip))
    }),
  )
}

/** Exposes the router's current query string so the URL contract is assertable. */
function LocationSpy() {
  const location = useLocation()
  return <span data-testid="location-search">{location.search}</span>
}

function renderTimeline(path = '/trips/trip-1') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <App />
        <LocationSpy />
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

describe('the filter rule', () => {
  it('"only outstanding" keeps both to_plan and to_book', () => {
    // Not `status === 'to_plan'`: something decided but not yet booked is still
    // something you have to touch.
    expect(matchesFilter(TO_PLAN, 'outstanding')).toBe(true)
    expect(matchesFilter(TO_BOOK, 'outstanding')).toBe(true)
  })

  it('"only outstanding" drops done', () => {
    expect(matchesFilter(DONE, 'outstanding')).toBe(false)
  })

  it('"all" keeps everything', () => {
    expect(applyFilter([TO_PLAN, TO_BOOK, DONE], 'all')).toHaveLength(3)
  })

  it('preserves the order it was given', () => {
    expect(applyFilter([TO_PLAN, TO_BOOK, DONE], 'outstanding').map((i) => i.id)).toEqual([
      'to-plan',
      'to-book',
    ])
  })
})

describe('countByKind', () => {
  it('counts each kind', () => {
    const counts = countByKind([TO_PLAN, TO_BOOK, DONE])

    expect(counts.activity).toBe(1)
    expect(counts.accommodation).toBe(1)
    expect(counts.transport).toBe(1)
  })

  it('reports zero for a kind the trip has none of', () => {
    expect(countByKind([TO_PLAN]).meal).toBe(0)
  })

  it('sums to the item total', () => {
    const items = [TO_PLAN, TO_BOOK, DONE, item({ id: 'x', kind: 'meal' })]
    const counts = countByKind(items)

    expect(Object.values(counts).reduce((a, b) => a + b, 0)).toBe(items.length)
  })

  it('sums to the total even when every item shares a kind', () => {
    const items = [item({ id: 'a', kind: 'meal' }), item({ id: 'b', kind: 'meal' })]

    expect(Object.values(countByKind(items)).reduce((a, b) => a + b, 0)).toBe(2)
  })
})

describe('the filter bar on the timeline', () => {
  it('is a real radio group, not styled buttons', async () => {
    mockApi()

    renderTimeline()

    expect(await screen.findByRole('radio', { name: 'Wszystko' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Tylko do zrobienia' })).toBeInTheDocument()
  })

  it('starts on "all"', async () => {
    mockApi()

    renderTimeline()

    expect(await screen.findByRole('radio', { name: 'Wszystko' })).toBeChecked()
  })

  it('changes the item list when switched', async () => {
    const user = userEvent.setup()
    mockApi()

    renderTimeline()

    expect(await screen.findByText('Lot do KL')).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'Tylko do zrobienia' }))

    expect(screen.queryByText('Lot do KL')).not.toBeInTheDocument()
    expect(screen.getByText('Batu Caves')).toBeInTheDocument()
    expect(screen.getByText('Nocleg w KL')).toBeInTheDocument()
  })

  it('leaves the counter untouched', async () => {
    const user = userEvent.setup()
    mockApi()

    renderTimeline()

    expect(await screen.findByText('1 z 2 załatwionych')).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'Tylko do zrobienia' }))

    // The counter answers "how much is arranged"; the filter answers "what do I
    // still have to touch". One must not move the other.
    expect(screen.getByText('1 z 2 załatwionych')).toBeInTheDocument()
  })

  it('leaves the per-type chips untouched', async () => {
    const user = userEvent.setup()
    mockApi()

    renderTimeline()

    await screen.findByText('Transport (1)')

    await user.click(screen.getByRole('radio', { name: 'Tylko do zrobienia' }))

    // The chips describe what the trip is made of, not what is on screen.
    expect(screen.getByText('Transport (1)')).toBeInTheDocument()
  })

  it('reflects the filter in the URL', async () => {
    const user = userEvent.setup()
    mockApi()

    renderTimeline()

    await screen.findByRole('radio', { name: 'Tylko do zrobienia' })
    await user.click(screen.getByRole('radio', { name: 'Tylko do zrobienia' }))

    expect(screen.getByTestId('location-search')).toHaveTextContent('?filter=outstanding')
  })

  it('drops the parameter again when switched back to the default', async () => {
    const user = userEvent.setup()
    mockApi()

    renderTimeline('/trips/trip-1?filter=outstanding')

    await user.click(await screen.findByRole('radio', { name: 'Wszystko' }))

    // /trips/1 and /trips/1?filter=all are the same view; they should not be two
    // URLs, or every share of an unfiltered timeline carries noise.
    expect(screen.getByTestId('location-search')).toHaveTextContent('')
    expect(screen.queryByTestId('location-search')?.textContent).toBe('')
  })

  it('restores the filter from the URL, so a filtered view is linkable', async () => {
    mockApi()

    renderTimeline('/trips/trip-1?filter=outstanding')

    expect(await screen.findByRole('radio', { name: 'Tylko do zrobienia' })).toBeChecked()
    expect(screen.queryByText('Lot do KL')).not.toBeInTheDocument()
  })

  it('falls back to "all" for an unrecognised filter rather than hiding the plan', async () => {
    mockApi()

    renderTimeline('/trips/trip-1?filter=nonsense')

    expect(await screen.findByRole('radio', { name: 'Wszystko' })).toBeChecked()
    expect(screen.getByText('Lot do KL')).toBeInTheDocument()
  })

  it('says so when a day’s items are all filtered out', async () => {
    const user = userEvent.setup()
    mockApi({
      ...TRIP,
      days: [{ id: 'day-1', date: '2026-10-10', stage_ids: [], items: [DONE] }],
    })

    renderTimeline()

    await screen.findByText('Lot do KL')
    await user.click(screen.getByRole('radio', { name: 'Tylko do zrobienia' }))

    // Not the "nothing planned yet" copy: the day *has* a plan, it is just done.
    expect(screen.getByText('Wszystko tutaj jest już gotowe')).toBeInTheDocument()
    expect(screen.queryByText('Nic jeszcze nie zaplanowano')).not.toBeInTheDocument()
  })

  it('shows only the kinds the trip actually has', async () => {
    mockApi()

    renderTimeline()

    await screen.findByText('Transport (1)')
    expect(screen.queryByText(/Jedzenie/u)).not.toBeInTheDocument()
  })
})
