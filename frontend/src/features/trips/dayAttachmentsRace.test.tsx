import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'
import { FakeXhr } from '../../test/fakeXhr'

/**
 * The day panel against out-of-order day responses.
 *
 * A browser walk found a 4.3 MB upload announcing "Dodano big3.png" and then
 * showing up **nowhere** — neither as an attachment row nor as a queue row —
 * while a reload proved the file was on the server all along. The ordering that
 * produces it needs a *slow* upload, which is why only big files showed it:
 *
 * 1. a day refetch is issued by something unrelated (an item edit) while the
 *    upload is still in flight;
 * 2. the upload finishes, `onUploaded` refetches the day, and that answer —
 *    which does carry the new attachment — renders;
 * 3. the *older* request from (1) finally answers, with a list that predates
 *    the upload, and overwrites the fresh one.
 *
 * By (3) the drop zone's queue row has already retired for good (it saw its
 * attachment listed in (2), and retirement is permanent by design), so the file
 * is left with no representation at all. Both suites below drive exactly that
 * ordering through the real screen, with the day responses held open by hand.
 */

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>

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

const UPLOADED = {
  id: 'attachment-fresh',
  filename: 'rezerwacja.pdf',
  content_type: 'application/pdf',
  byte_size: 4 * 1024 * 1024,
  sha256: 'fresh-sha',
  created_at: '2026-09-06T10:11:12Z',
  item_id: null,
  trip_day_id: 'day-1',
}

const DAY_PATH = '/trips/trip-1/days/2026-10-11'

/** The day GETs still waiting for an answer, oldest first — resolved by hand. */
let pendingDays: ((body: unknown) => void)[] = []

function mockApi() {
  const handler: Handler = (url, init) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    if (url.endsWith('/auth/me')) return json(200, OWNER)
    if (url.endsWith('/trips') && method === 'GET') return json(200, [TRIP])
    if (url.includes('/items/') && method === 'PATCH') return json(200, MUSEUM)
    if (url.includes('/days/') && method === 'GET') {
      return new Promise<Response>((resolve) => {
        pendingDays.push((body) => resolve(json(200, body)))
      })
    }
    if (/\/trips\/[^/]+$/u.test(url)) return json(200, TRIP)
    return json(404, { error: { code: 'not_found', field: null } })
  }

  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
      Promise.resolve(handler(String(input), init)),
    ),
  )
}

/** Answer the oldest day GET still open. */
async function answerOldestDay(body: unknown) {
  await waitFor(() => expect(pendingDays.length).toBeGreaterThan(0))
  pendingDays.shift()!(body)
}

/** Answer a specific day GET, identified by the order it was issued in. */
async function answerDay(index: number, body: unknown) {
  await waitFor(() => expect(pendingDays[index]).toBeDefined())
  const resolve = pendingDays[index]!
  pendingDays[index] = () => {}
  resolve(body)
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

/** The filenames the day panel is listing as attachment rows, in order. */
function listedFilenames(): string[] {
  return [...document.querySelectorAll('.day-attachments__list .attachment-row__name')].map(
    (node) => node.textContent ?? '',
  )
}

/** The day panel's own drop zone — never the item dialog's. */
function dayDropzoneInput(): HTMLElement {
  const panel = document.querySelector('.day-attachments')
  expect(panel).not.toBeNull()
  return within(panel as HTMLElement).getByLabelText(new RegExp(pl.upload.add))
}

beforeEach(async () => {
  pendingDays = []
  FakeXhr.reset()
  initI18n('pl')
  await applyLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
  vi.stubGlobal('XMLHttpRequest', FakeXhr as unknown as typeof XMLHttpRequest)
  mockApi()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the day documents panel against an out-of-order refetch', () => {
  it('keeps a just-uploaded file on screen when an older day response lands afterwards', async () => {
    const user = userEvent.setup()
    renderApp()

    // (0) the mount's own load.
    await answerOldestDay(DAY)
    await screen.findByText('Batu Caves')

    // A slow upload starts — nothing answers the XHR yet.
    const file = new File(['%PDF-1.4 …'], UPLOADED.filename, { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: UPLOADED.byte_size })
    await user.upload(dayDropzoneInput(), file)
    await waitFor(() => expect(FakeXhr.instances).toHaveLength(1))

    // (1) something unrelated refetches the day while the upload is in flight.
    await user.click(screen.getByRole('button', { name: /Batu Caves/u }))
    await user.click(screen.getByRole('button', { name: pl.item.save }))
    await waitFor(() => expect(pendingDays).toHaveLength(1))

    // (2) the upload finishes; its own refetch answers with the new attachment.
    FakeXhr.instances[0]!.respond(201, UPLOADED)
    await answerDay(1, { ...DAY, attachments: [UPLOADED] })
    await waitFor(() => expect(listedFilenames()).toEqual([UPLOADED.filename]))

    // (3) the older request from (1) finally answers, with the pre-upload list.
    await answerDay(0, DAY)

    // The file must still be exactly one thing on screen — a stale answer is
    // not allowed to unshow it, and the queue row must not come back either.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(listedFilenames()).toEqual([UPLOADED.filename])
    expect(screen.getAllByText(UPLOADED.filename)).toHaveLength(1)
    expect(screen.queryByRole('list', { name: pl.upload.list })).not.toBeInTheDocument()
  })

  it('shows a finished upload from the upload’s own answer, before the refetch replies', async () => {
    const user = userEvent.setup()
    renderApp()

    await answerOldestDay(DAY)
    await screen.findByText('Batu Caves')

    const file = new File(['%PDF-1.4 …'], UPLOADED.filename, { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: UPLOADED.byte_size })
    await user.upload(dayDropzoneInput(), file)
    await waitFor(() => expect(FakeXhr.instances).toHaveLength(1))
    FakeXhr.instances[0]!.respond(201, UPLOADED)

    // The refetch this triggers is deliberately left unanswered: the server has
    // already confirmed the file, so the panel must not wait for a round trip
    // to admit it exists — the same local-first shape the item strip has.
    await waitFor(() => expect(listedFilenames()).toEqual([UPLOADED.filename]))
    expect(screen.getAllByText(UPLOADED.filename)).toHaveLength(1)
    expect(screen.queryByRole('list', { name: pl.upload.list })).not.toBeInTheDocument()
  })

  it('does not let a refresh triggered by something else retire an upload still in flight', async () => {
    const user = userEvent.setup()
    renderApp()

    await answerOldestDay(DAY)
    await screen.findByText('Batu Caves')

    const file = new File(['%PDF-1.4 …'], UPLOADED.filename, { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: UPLOADED.byte_size })
    await user.upload(dayDropzoneInput(), file)
    await waitFor(() => expect(FakeXhr.instances).toHaveLength(1))
    FakeXhr.instances[0]!.progress(1024, UPLOADED.byte_size)

    // An unrelated edit refetches and answers *while* the upload is in flight.
    await user.click(screen.getByRole('button', { name: /Batu Caves/u }))
    await user.click(screen.getByRole('button', { name: pl.item.save }))
    await answerOldestDay(DAY)

    // The queue row is the only representation the file has right now, so it
    // has to survive that refresh.
    await waitFor(() =>
      expect(screen.getByRole('list', { name: pl.upload.list })).toBeInTheDocument(),
    )
    expect(within(screen.getByRole('list', { name: pl.upload.list })).getByText(UPLOADED.filename))
      .toBeInTheDocument()

    // Then it completes, and the file settles as exactly one attachment row.
    FakeXhr.instances[0]!.respond(201, UPLOADED)
    await answerOldestDay({ ...DAY, attachments: [UPLOADED] })

    await waitFor(() => expect(listedFilenames()).toEqual([UPLOADED.filename]))
    expect(screen.getAllByText(UPLOADED.filename)).toHaveLength(1)
    expect(screen.queryByRole('list', { name: pl.upload.list })).not.toBeInTheDocument()
  })
})
