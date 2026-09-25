import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'
import { parseIsoDate, toIsoDate } from './format'

/**
 * Issue #8's own scenario, end to end: **the owner gets a date wrong.**
 *
 * Before this feature the only way out was deleting the trip, which took every
 * item, day and attachment with it. The walk below is the one that has to keep
 * working, because it is the whole reason the feature exists:
 *
 *   put an item on the last day → try to move the end date earlier
 *   → read a refusal that names *that* day → move the item off it
 *   → retry → the trip is shorter and the item survived.
 *
 * The backend here is **stateful and enforces the real rule** rather than
 * replaying a canned 409: it recomputes, per request, which days would be
 * dropped and whether any of them still carries an item — the same check
 * `_refuse_if_days_would_be_lost` runs in `backend/trip_planner/api/trips.py`.
 * A mock that always refused would pass even if the screen never sent a second
 * request, and one that never refused would pass even if the copy were wrong.
 */

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

type Day = { id: string; date: string; stage_ids: string[]; items: unknown[] }

/**
 * Every date from `start` to `end` inclusive — the client-side `generate_days`.
 *
 * Through the app's own `parseIsoDate` / `toIsoDate` rather than
 * `new Date(iso).toISOString()`: the latter round-trips through UTC and would
 * hand back the *previous* day for every zone east of Greenwich, which is the
 * exact off-by-one those two helpers exist to prevent.
 */
function datesBetween(start: string, end: string): string[] {
  const dates: string[] = []
  for (const cursor = parseIsoDate(start); ; cursor.setDate(cursor.getDate() + 1)) {
    const iso = toIsoDate(cursor)
    dates.push(iso)
    if (iso >= end) break
  }
  return dates
}

const FLIGHT_HOME = {
  id: 'item-1',
  position: 0,
  kind: 'transport',
  status: 'to_book',
  start_time: '21:15:00',
  end_time: null,
  end_date: null,
  title: 'Lot powrotny',
  notes: null,
  attachment_count: 0,
  confirmation_number: null,
  cost_amount: null,
  cost_currency: null,
}

/**
 * A trip from the 10th to the 13th whose **last day carries one item**, plus
 * the `PATCH` rule that refuses to drop it.
 */
function statefulBackend() {
  const trip = {
    id: 'trip-1',
    title: 'Malezja, październik 2026',
    start_date: '2026-10-10',
    end_date: '2026-10-13',
    departure_place: 'Warszawa',
    return_place: 'Warszawa',
    readiness: { arranged: 0, tracked: 1 },
    stages: [
      { id: 'stage-1', position: 0, place: 'Kuala Lumpur', start_date: null, end_date: null },
    ],
    days: datesBetween('2026-10-10', '2026-10-13').map<Day>((date, index) => ({
      id: `day-${index + 1}`,
      date,
      stage_ids: [],
      items: date === '2026-10-13' ? [FLIGHT_HOME] : [],
    })),
  }

  /** Drop the item from the day it is on — the owner "moving it off" that day. */
  const clearLastDay = () => {
    for (const day of trip.days) {
      day.items = []
    }
    trip.readiness = { arranged: 0, tracked: 0 }
  }

  const handler = (url: string, init?: RequestInit): Response => {
    if (url.endsWith('/auth/me')) return json(200, OWNER)

    if (/\/trips\/[^/]+$/u.test(url) && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body)) as { start_date: string; end_date: string }
      const wanted = new Set(datesBetween(body.start_date, body.end_date))
      const losing = trip.days
        .filter((day) => !wanted.has(day.date) && day.items.length > 0)
        .map((day) => day.date)

      if (losing.length > 0) {
        // Nothing is mutated — the refusal leaves the trip exactly as it was.
        return json(409, { error: { code: 'days_have_items', field: losing.join(', ') } })
      }

      trip.start_date = body.start_date
      trip.end_date = body.end_date
      trip.days = [...wanted]
        .sort()
        .map((date) => trip.days.find((day) => day.date === date) ?? {
          id: `day-${date}`,
          date,
          stage_ids: [],
          items: [],
        })
      return json(200, trip)
    }

    if (/\/trips\/[^/]+$/u.test(url)) return json(200, trip)
    if (url.endsWith('/trips')) return json(200, [trip])
    return json(404, { error: { code: 'not_found', field: null } })
  }

  return { handler, clearLastDay, trip }
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  )
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("issue #8's scenario: the owner got a date wrong", () => {
  it(
    'refuses the shortening, names the day in the way, and succeeds once it is clear',
    { timeout: 20_000 },
    async () => {
      const user = userEvent.setup()
      const api = statefulBackend()
      vi.stubGlobal(
        'fetch',
        vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
          Promise.resolve(api.handler(String(input), init)),
        ),
      )

      // ── The owner is on the trip and reaches for the editor ─────────────────
      renderApp('/trips/trip-1')
      await user.click(await screen.findByRole('link', { name: 'Edytuj podróż' }))

      const endDate = await screen.findByLabelText('Data zakończenia')
      expect(endDate).toHaveValue('2026-10-13')

      // ── Move the end date back past the day that carries the flight home ────
      await user.clear(endDate)
      await user.type(endDate, '2026-10-11')
      await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

      // The refusal names THAT day — not "something went wrong", and not a
      // vague "some days have items on them".
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent('13 października 2026')
      expect(alert).toHaveTextContent('Te dni mają już zaplanowane pozycje')

      // Nothing was changed and nothing was retyped away.
      expect(api.trip.end_date).toBe('2026-10-13')
      expect(screen.getByLabelText('Data zakończenia')).toHaveValue('2026-10-11')
      expect(screen.getByRole('heading', { name: 'Edytuj podróż' })).toBeInTheDocument()

      // ── The owner moves the item off that day, then retries ─────────────────
      api.clearLastDay()
      await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

      // Back on the timeline, and the trip really is shorter: the 12th and the
      // 13th are gone from the rail.
      expect(await screen.findByRole('button', { name: 'Usuń podróż' })).toBeInTheDocument()
      expect(api.trip.end_date).toBe('2026-10-11')
      expect(api.trip.days.map((day) => day.date)).toEqual(['2026-10-10', '2026-10-11'])
      expect(screen.getByText('2 dni')).toBeInTheDocument()
    },
  )
})
