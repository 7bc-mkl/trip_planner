import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import type { Item } from '../../api/items'
import App from '../../App'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { FakeXhr } from '../../test/fakeXhr'
import { SessionProvider } from '../auth/SessionContext'

/**
 * Step 3.7 — the product brief's own "arranging one item" journey, walked from
 * end to end in one test:
 *
 *   open a day → open an item → set its details → attach a voucher PDF →
 *   save the confirmation number and cost → move the status to *gotowe* →
 *   **the readiness counter changes.**
 *
 * **What this file is, plainly.** It is a *full-app integration test*, not
 * browser E2E. This repository has no browser-driven runner and this Step was
 * not the place to introduce one, so it follows the pattern the phase already
 * established — `statusPathIndependence.test.tsx` and `reservationPanel.test.tsx`
 * — driving the real `App` under a `MemoryRouter` against a stubbed `fetch` that
 * *behaves like the server*: it stores what a POST or PATCH sends it and answers
 * the next GET from that stored state, so "the value came back" means a real
 * round trip and not an echo of the request. Uploads run on the shared
 * `FakeXhr`, because `api/attachments.ts` deliberately uses `XMLHttpRequest`.
 *
 * The browser half of this Step's evidence — the same flow walked by hand
 * against the production app factory, with screenshots and the readiness
 * counter before and after — lives in the run folder's
 * `step-3.7-artifacts/browser-session.log`. Neither half substitutes for the
 * other: this file is what CI can re-run on every commit; the walk is what
 * proves the built SPA does it against a real database.
 *
 * Nothing here is asserted twice from a cheaper angle for its own sake. The
 * per-leg guarantees each already have a focused test (the panel's collapse in
 * `reservationPanel.test.tsx`, the status path in `statusPathIndependence.test.tsx`,
 * the upload in `itemAttachments.test.tsx`). What only this file can show is
 * that the legs *compose* — that arranging one item, the whole way, works.
 */

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const TRIP_ID = 'trip-1'
const DATE = '2026-10-11'
const DAY_PATH = `/trips/${TRIP_ID}/days/${DATE}`

const STAGE = {
  id: 'stage-1',
  position: 0,
  place: 'Kuala Lumpur',
  start_date: '2026-10-10',
  end_date: '2026-10-13',
}

/** The voucher the flow attaches — a PDF, exactly as the brief's step names. */
const VOUCHER: Attachment = {
  id: 'attachment-voucher',
  filename: 'voucher-batu-caves.pdf',
  content_type: 'application/pdf',
  byte_size: 2048,
  sha256: 'voucher-sha',
  created_at: '2026-09-06T10:11:12Z',
  item_id: 'item-1',
  trip_day_id: null,
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("the brief's arranging-one-item flow, end to end", () => {
  /** The server's own state — mutated only by the requests the screen issues. */
  let items: Item[] = []
  let attachments: Attachment[] = []

  /** The readiness arithmetic `domain/readiness.py` implements, over that state. */
  function readiness() {
    return {
      arranged: items.filter((i) => i.status === 'done').length,
      tracked: items.filter((i) => i.status !== 'to_plan').length,
    }
  }

  function trip() {
    return {
      id: TRIP_ID,
      title: 'Malezja, październik 2026',
      start_date: '2026-10-10',
      end_date: '2026-10-13',
      departure_place: 'Warszawa',
      return_place: 'Warszawa',
      readiness: readiness(),
      stages: [STAGE],
      days: [
        { id: 'day-10', date: '2026-10-10', stage_ids: ['stage-1'], items: [] },
        {
          id: 'day-11',
          date: DATE,
          stage_ids: ['stage-1'],
          // The timeline's leaner shape: a count, never the attachment rows.
          items: items.map(({ attachments: _ignored, ...rest }) => rest),
        },
      ],
    }
  }

  function day() {
    return {
      id: 'day-11',
      trip_id: TRIP_ID,
      date: DATE,
      stages: [STAGE],
      // The day-detail shape: each item carries its own files.
      items: items.map((item) => ({
        ...item,
        attachments: attachments.filter((a) => a.item_id === item.id),
      })),
      attachments: attachments.filter((a) => a.trip_day_id !== null),
      previous_date: '2026-10-10',
      next_date: null,
    }
  }

  beforeEach(() => {
    items = []
    attachments = []
    FakeXhr.reset()
    vi.stubGlobal('XMLHttpRequest', FakeXhr as unknown as typeof XMLHttpRequest)
    document.cookie = 'csrf_token=test-csrf-token; path=/'

    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method ?? 'GET').toUpperCase()
        const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {}

        if (url.endsWith('/auth/me')) return Promise.resolve(json(200, OWNER))
        if (url.endsWith('/trips') && method === 'GET') return Promise.resolve(json(200, [trip()]))

        if (url.includes('/items') && method === 'POST') {
          const created: Item = {
            id: 'item-1',
            position: 0,
            kind: 'activity',
            status: 'to_plan',
            start_time: null,
            end_time: null,
            end_date: null,
            title: '',
            notes: null,
            attachment_count: 0,
            attachments: [],
            confirmation_number: null,
            cost_amount: null,
            cost_currency: null,
            ...(body as Partial<Item>),
          }
          items = [...items, created]
          return Promise.resolve(json(201, created))
        }

        if (url.includes('/items/') && method === 'PATCH') {
          items = items.map((item) => (item.id === 'item-1' ? { ...item, ...body } : item))
          return Promise.resolve(json(200, items[0]))
        }

        if (url.includes('/days/') && method === 'GET') return Promise.resolve(json(200, day()))
        if (/\/trips\/[^/]+$/u.test(url)) return Promise.resolve(json(200, trip()))
        return Promise.resolve(json(404, { error: { code: 'not_found', field: null } }))
      }),
    )
  })

  function renderApp(initialPath: string) {
    return render(
      <MemoryRouter initialEntries={[initialPath]}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </MemoryRouter>,
    )
  }

  /** The disclosure, as the screen currently holds it. */
  const panel = () => document.querySelector('details.reservation-panel') as HTMLDetailsElement

  /** Nothing opened by itself, nothing complained: checked at every leg. */
  function nothingNags() {
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(panel().open).toBe(false)
  }

  it('walks open a day → set details → attach a voucher → save cost → gotowe → the counter changes', async () => {
    const user = userEvent.setup()
    renderApp(DAY_PATH)

    // ── Open a day, open an item, set its details ────────────────────────────
    await user.click(await screen.findByRole('button', { name: pl.item.add }))
    // The disclosure exists on a brand-new item and is already collapsed.
    nothingNags()

    await user.type(screen.getByLabelText(pl.item.titleLabel), 'Batu Caves')
    await user.selectOptions(screen.getByLabelText(pl.item.kindLabel), pl.item.kind.activity)
    await user.type(screen.getByLabelText(pl.item.notesLabel), 'zabrać wodę')
    await user.click(screen.getByRole('radio', { name: pl.item.status.to_book }))
    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() => expect(items).toHaveLength(1))
    expect(items[0]).toMatchObject({ title: 'Batu Caves', status: 'to_book' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    // ── The counter, before ─────────────────────────────────────────────────
    await user.click(screen.getByRole('link', { name: pl.day.backToTimeline }))
    expect(await screen.findByText('0 z 1 załatwionych')).toBeInTheDocument()

    // ── Back into the day, and open the item that is now on it ──────────────
    const dayLink = document.querySelector(`a[href$="/days/${DATE}"]`) as HTMLAnchorElement
    expect(dayLink).not.toBeNull()
    await user.click(dayLink)
    await user.click(await screen.findByRole('button', { name: /Batu Caves/u }))

    // ── Attach a voucher PDF ────────────────────────────────────────────────
    const file = new File(['%PDF-1.4 …'], VOUCHER.filename, { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: VOUCHER.byte_size })
    await user.upload(
      within(screen.getByRole('dialog')).getByLabelText(new RegExp(pl.upload.add)),
      file,
    )
    attachments = [...attachments, VOUCHER]
    items = items.map((item) => ({ ...item, attachment_count: 1 }))
    FakeXhr.instances[0]!.respond(201, VOUCHER)

    await waitFor(() => expect(screen.getAllByText(VOUCHER.filename).length).toBeGreaterThan(0))
    // The one moment an earlier draft of the spec wanted the panel to spring
    // open. It does not, and nothing else appeared either.
    nothingNags()

    // ── Save the confirmation number and cost ───────────────────────────────
    await user.click(screen.getByText(pl.item.reservation.heading))
    await user.type(
      screen.getByLabelText(pl.item.reservation.confirmationNumberLabel),
      'SX-9912L',
    )
    await user.type(screen.getByLabelText(pl.item.reservation.costLabel), '1250.00')
    // The currency was never touched: it defaults to PLN and carries the amount.
    expect(screen.getByLabelText(pl.item.reservation.currencyLabel)).toHaveValue('PLN')
    await user.click(screen.getByRole('button', { name: pl.item.save }))

    await waitFor(() =>
      expect(items[0]).toMatchObject({
        confirmation_number: 'SX-9912L',
        cost_amount: '1250.00',
        cost_currency: 'PLN',
        // Still to_book: saving reservation data arranged nothing by itself.
        status: 'to_book',
      }),
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    // ── It comes back: a second GET of the day, then the editor reopened ────
    await user.click(screen.getByRole('link', { name: pl.day.backToTimeline }))
    expect(await screen.findByText('0 z 1 załatwionych')).toBeInTheDocument()
    await user.click(document.querySelector(`a[href$="/days/${DATE}"]`) as HTMLAnchorElement)
    await user.click(await screen.findByRole('button', { name: /Batu Caves/u }))

    // Collapsed even now, with data in it — the panel is opened by the user or
    // by nobody. The values are the server's answer, not the draft kept alive.
    nothingNags()
    await user.click(screen.getByText(pl.item.reservation.heading))
    expect(screen.getByLabelText(pl.item.reservation.confirmationNumberLabel)).toHaveValue(
      'SX-9912L',
    )
    expect(screen.getByLabelText(pl.item.reservation.costLabel)).toHaveValue('1250.00')
    expect(screen.getAllByText(VOUCHER.filename).length).toBeGreaterThan(0)

    // ── Move the status to *gotowe* ─────────────────────────────────────────
    await user.click(screen.getByRole('radio', { name: pl.item.status.done }))
    // Choosing the pill is a local change: no request, no prompt, no second dialog.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getAllByRole('dialog')).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: pl.item.save }))
    await waitFor(() => expect(items[0]!.status).toBe('done'))
    // The reservation data it was carrying went along unharmed.
    expect(items[0]).toMatchObject({
      confirmation_number: 'SX-9912L',
      cost_amount: '1250.00',
      cost_currency: 'PLN',
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    // ── The readiness counter changes ───────────────────────────────────────
    await user.click(screen.getByRole('link', { name: pl.day.backToTimeline }))
    expect(await screen.findByText('1 z 1 załatwionych')).toBeInTheDocument()
    expect(screen.queryByText('0 z 1 załatwionych')).not.toBeInTheDocument()
    // And the card carries the paperclip badge the voucher earned it.
    expect(screen.getByText('1 plik')).toBeInTheDocument()
    // The whole way through, on the screen the owner ends up looking at,
    // nothing asked him for anything.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
