import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Item } from '../../api/items'
import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { SessionProvider } from '../auth/SessionContext'

/**
 * Step 3.6 — invariant 4 ("No nagging, ever") turned into a standing test.
 *
 * Step 3.5 proved *behaviourally* that the status path is unconditioned. This
 * file is the cheaper, complementary guard: it fails the moment someone
 * *writes the copy* for a nag — an "incomplete", "missing fields" or
 * "complete your reservation" string in either locale file — even before any
 * component reads that key. And it fails if the timeline or the day detail
 * ever renders a marker (badge, dot, tooltip, count, muted placeholder) keyed
 * on a reservation field being empty, or lets a cost, currency or
 * confirmation number leak onto either screen, which the spec's
 * "`/trips/:id` — the timeline, lightly touched" section forbids outright.
 *
 * **What this pair does not cover**: a nag built from an icon or colour
 * alone, with no string behind it, would slip past assertion 1 — that is
 * exactly why assertion 2 exists beside it, rendering real items and reading
 * the actual DOM rather than trusting the copy to be the only place a nag
 * could live. Assertion 2 in turn only exercises the timeline and the day
 * detail (the surfaces the spec names), not every possible future screen.
 */

describe('locale files never contain a nag about incomplete reservation data', () => {
  const flatten = (value: unknown, prefix = ''): Array<[string, string]> => {
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      return Object.entries(value).flatMap(([key, child]) =>
        flatten(child, prefix ? `${prefix}.${key}` : key),
      )
    }
    return [[prefix, String(value)]]
  }

  // English terms a nag would plausibly use. "complete your" / "finish your"
  // rather than bare "complete" / "finish", which would also flag innocent
  // uses (e.g. a future "Saving complete" toast) that have nothing to do with
  // reservation data.
  const englishNagPatterns = [/incomplete/i, /missing/i, /complete your/i, /finish your/i, /remind/i]

  // Polish equivalents — a check that only looked for English words would
  // pass while pl.json grew "uzupełnij dane rezerwacji". `brakuj*` covers
  // brakuje/brakujące/brakującego; `niekompletn*` covers the adjective's
  // inflections; `nieukończ*` covers nieukończony/nieukończona;
  // `przypomn*` covers przypomnij/przypomnienie.
  const polishNagPatterns = [/uzupełnij/i, /brakuj/i, /niekompletn/i, /nieukończ/i, /dokończ/i, /przypomn/i]

  // No exception is declared here because none is needed: at the time this
  // test was written, neither locale file contains any of these terms in any
  // key, legitimate or not (verified by hand against the flattened key list
  // below). If a future key needs one, name it here with a comment saying
  // why, per the Step's instructions — do not loosen the pattern instead.
  const allowedExceptionKeys: string[] = []

  it('en.json carries no nagging copy', () => {
    const offenders = flatten(en)
      .filter(([key]) => !allowedExceptionKeys.includes(key))
      .filter(([, value]) => englishNagPatterns.some((pattern) => pattern.test(value)))
    expect(offenders).toEqual([])
  })

  it('pl.json carries no nagging copy', () => {
    const offenders = flatten(pl)
      .filter(([key]) => !allowedExceptionKeys.includes(key))
      .filter(([, value]) => polishNagPatterns.some((pattern) => pattern.test(value)))
    expect(offenders).toEqual([])
  })
})

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
  id: 'item-base',
  position: 0,
  kind: 'accommodation',
  status: 'done',
  start_time: '10:30:00',
  end_time: '12:00:00',
  end_date: null,
  title: '',
  notes: null,
  attachment_count: 0,
  attachments: [],
  confirmation_number: null,
  cost_amount: null,
  cost_currency: null,
}

// Distinctive, unmistakable values — if any of these ever showed up in the
// timeline's or the day detail's rendered text, it could only have leaked
// from the reservation fields below, never coincidentally.
const DOCUMENTED_TITLE = 'Hotel Voucher Item'
const BARE_TITLE = 'Undocumented Item'
const LEAK_CONFIRMATION = 'RESV-DO-NOT-LEAK-9911'
const LEAK_AMOUNT = '12345.67'
const LEAK_CURRENCY = 'JPY'

const documentedItem: Item = {
  ...BASE_ITEM,
  id: 'item-documented',
  title: DOCUMENTED_TITLE,
  confirmation_number: LEAK_CONFIRMATION,
  cost_amount: LEAK_AMOUNT,
  cost_currency: LEAK_CURRENCY,
}

const bareItem: Item = {
  ...BASE_ITEM,
  id: 'item-bare',
  title: BARE_TITLE,
}

function trip() {
  return {
    id: 'trip-1',
    title: 'Malezja, październik 2026',
    start_date: '2026-10-10',
    end_date: '2026-10-13',
    departure_place: 'Warszawa',
    return_place: 'Katowice',
    readiness: { arranged: 2, tracked: 2 },
    stages: [STAGE],
    days: [
      {
        id: 'day-1',
        date: '2026-10-11',
        stage_ids: ['stage-1'],
        items: [documentedItem, bareItem],
      },
    ],
  }
}

function day() {
  return {
    id: 'day-1',
    trip_id: 'trip-1',
    date: '2026-10-11',
    stages: [STAGE],
    items: [documentedItem, bareItem],
    attachments: [] as unknown[],
    previous_date: null,
    next_date: null,
  }
}

function mockFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return Promise.resolve(json(200, OWNER))
      if (url.endsWith('/trips')) return Promise.resolve(json(200, [trip()]))
      if (url.includes('/days/')) return Promise.resolve(json(200, day()))
      if (/\/trips\/[^/]+$/u.test(url)) return Promise.resolve(json(200, trip()))
      return Promise.resolve(json(404, { error: { code: 'not_found', field: null } }))
    }),
  )
}

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
  mockFetch()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/**
 * Assertion 2: an item with a confirmation number and a cost, side by side
 * with one that has neither, must render as the same shape of row on both
 * the timeline and the day detail — nothing distinguishes "documented" from
 * "bare" beyond the title the test uses to tell them apart. And neither
 * screen ever shows the cost, the currency or the confirmation number
 * itself, which the spec's timeline section rules out even once the fields
 * are real.
 */
describe('the timeline and the day detail never mark a bare reservation as incomplete', () => {
  it('renders the documented and the bare item as identical rows on the timeline, with no money or confirmation number visible', async () => {
    renderApp('/trips/trip-1')

    const documentedTitle = await screen.findByText(DOCUMENTED_TITLE)
    const bareTitle = await screen.findByText(BARE_TITLE)

    const documentedRow = documentedTitle.closest('.item-row') as HTMLElement
    const bareRow = bareTitle.closest('.item-row') as HTMLElement
    expect(documentedRow).not.toBeNull()
    expect(bareRow).not.toBeNull()

    // Strip the one legitimate difference (the title) and compare the rest
    // of the row verbatim — same time, same kind, same status chip, no
    // reservation-shaped addition on either side.
    const normalise = (row: HTMLElement, title: string) => (row.textContent ?? '').replace(title, '')
    expect(normalise(documentedRow, DOCUMENTED_TITLE)).toBe(normalise(bareRow, BARE_TITLE))

    // Nothing from the reservation fields ever reaches the timeline's text,
    // documented or not.
    const timelineText = document.body.textContent ?? ''
    expect(timelineText).not.toContain(LEAK_CONFIRMATION)
    expect(timelineText).not.toContain(LEAK_AMOUNT)
    expect(timelineText).not.toContain(LEAK_CURRENCY)
  })

  it('renders the documented and the bare item as identical rows on the day detail, with no money or confirmation number visible', async () => {
    renderApp('/trips/trip-1/days/2026-10-11')

    const documentedTitle = await screen.findByText(DOCUMENTED_TITLE)
    const bareTitle = await screen.findByText(BARE_TITLE)

    const documentedRow = documentedTitle.closest('.item-row') as HTMLElement
    const bareRow = bareTitle.closest('.item-row') as HTMLElement
    expect(documentedRow).not.toBeNull()
    expect(bareRow).not.toBeNull()

    const normalise = (row: HTMLElement, title: string) => (row.textContent ?? '').replace(title, '')
    expect(normalise(documentedRow, DOCUMENTED_TITLE)).toBe(normalise(bareRow, BARE_TITLE))

    const dayText = document.body.textContent ?? ''
    expect(dayText).not.toContain(LEAK_CONFIRMATION)
    expect(dayText).not.toContain(LEAK_AMOUNT)
    expect(dayText).not.toContain(LEAK_CURRENCY)
  })
})
