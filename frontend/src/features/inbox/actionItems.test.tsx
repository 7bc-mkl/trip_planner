import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import type { Locale } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'

/**
 * The action-item region and the review sheet (Phase 3, D21).
 *
 * The sheet's contract is mostly about what it does **not** do: it never ticks
 * a field the owner already filled, never sends a field he did not tick, and
 * never retries a conflicted approval against values he has not seen. Each of
 * those is asserted on the request the sheet actually sends.
 */

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const TRIP = {
  id: 'trip-1',
  title: 'Malezja, październik 2026',
  start_date: '2026-10-10',
  end_date: '2026-10-24',
  departure_place: 'Warszawa',
  return_place: 'Warszawa',
  readiness: { arranged: 0, tracked: 1 },
}

const HOTEL = {
  id: 'item-hotel',
  position: 0,
  kind: 'accommodation',
  status: 'to_plan',
  start_time: null,
  end_time: null,
  end_date: null,
  title: 'Hotel Majestic',
  notes: null,
  attachment_count: 0,
  confirmation_number: 'HM-77',
  cost_amount: null,
  cost_currency: null,
}

const FERRY = { ...HOTEL, id: 'item-ferry', title: 'Ferry', confirmation_number: null }

const TRIP_DETAIL = {
  ...TRIP,
  stages: [],
  days: [
    { id: 'day-17', date: '2026-10-17', stage_ids: [], items: [HOTEL] },
    { id: 'day-18', date: '2026-10-18', stage_ids: [], items: [FERRY] },
  ],
}

const SUMMARY = {
  inbox_enabled: true,
  pending_action_items: 1,
  address: 'inbox@mail.planner.example.com',
  unrouted: 0,
  quarantined: 0,
  last_received_at: '2026-10-01T09:00:00+00:00',
  last_error_at: null,
  last_error: null,
}

const DOCUMENT = {
  id: 'attachment-1',
  filename: 'voucher.pdf',
  content_type: 'application/pdf',
  byte_size: 2048,
  sha256: 'a'.repeat(64),
  created_at: '2026-10-01T09:00:00+00:00',
  sent_externally_at: null,
}

const ACTION_ITEM = {
  id: 'action-1',
  message_id: 'message-1',
  subject: 'Booking confirmation HM-77',
  from_address: 'reservations@hotel.example',
  received_at: '2026-10-01T09:00:00+00:00',
  kind: 'update_item',
  state: 'pending',
  revision: 1,
  source: 'model',
  trip_id: TRIP.id,
  trip_title: TRIP.title,
  target_item_id: HOTEL.id,
  target_item_title: HOTEL.title,
  target_trip_day_id: null,
  target_date: '2026-10-17',
  target_reason: 'matched_confirmation_number',
  fields: [
    {
      name: 'title',
      current: 'Hotel Majestic',
      proposed: 'Majestic Hotel Kuala Lumpur',
      changed: true,
      default_ticked: false,
    },
    {
      name: 'cost',
      current: null,
      proposed: { amount: '480.00', currency: 'MYR' },
      changed: true,
      default_ticked: true,
    },
    {
      name: 'confirmation_number',
      current: 'HM-77',
      proposed: 'HM-77',
      changed: false,
      default_ticked: false,
    },
  ],
  status: { current: 'to_plan', proposed: 'done', changed: true, default_ticked: true },
  attachments: [DOCUMENT],
  alternatives: [],
  applied: null,
  decided_at: null,
  created_at: '2026-10-01T09:00:01+00:00',
}

const MESSAGE_DETAIL = {
  id: 'message-1',
  received_at: ACTION_ITEM.received_at,
  from_address: ACTION_ITEM.from_address,
  subject: ACTION_ITEM.subject,
  state: 'routed',
  trip_id: TRIP.id,
  routing_reason: 'routed_by_model',
  routing_reason_args: { trip: TRIP.title },
  last_error: null,
  attachment_count: 1,
  text_body: 'Your booking HM-77 at Majestic Hotel Kuala Lumpur. Total: MYR 480.00',
  attachments: [DOCUMENT],
  action_item_ids: ['action-1'],
}

let requests: { url: string; method: string; body: unknown }[] = []

function mockApi(handler: Handler) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      requests.push({
        url,
        method: (init?.method ?? 'GET').toUpperCase(),
        body: typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
      })
      return Promise.resolve(handler(url, init))
    }),
  )
}

type Overrides = {
  actionItem?: unknown
  reload?: unknown
  approve?: (body: unknown) => Response
  retarget?: unknown
  ownerLocale?: Locale
  summary?: unknown
}

function backend(overrides: Overrides = {}): Handler {
  let reloaded = false
  return (url, init) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined

    if (url.endsWith('/auth/me'))
      return json(200, { ...OWNER, locale: overrides.ownerLocale ?? 'pl' })
    if (url.endsWith('/inbox/summary')) return json(200, overrides.summary ?? SUMMARY)
    if (url.endsWith('/inbox/messages') && method === 'GET') return json(200, [])
    if (url.endsWith('/inbox/quarantine')) return json(200, [])
    if (url.endsWith('/inbox/action-items') && method === 'GET')
      return json(200, [overrides.actionItem ?? ACTION_ITEM])
    if (/\/inbox\/action-items\/[^/]+$/u.test(url) && method === 'GET') {
      const payload = reloaded && overrides.reload ? overrides.reload : overrides.actionItem
      return json(200, payload ?? ACTION_ITEM)
    }
    if (url.endsWith('/approve') && method === 'POST') {
      if (overrides.approve) {
        reloaded = true
        return overrides.approve(body)
      }
      return json(200, {
        ...ACTION_ITEM,
        state: 'approved',
        applied: {
          item_id: HOTEL.id,
          created: false,
          fields: ['cost'],
          status_changed: true,
          attachment_count: 1,
        },
      })
    }
    if (url.endsWith('/reject') && method === 'POST') return new Response(null, { status: 204 })
    if (url.endsWith('/undo') && method === 'POST')
      return json(200, { ...ACTION_ITEM, revision: 2 })
    if (url.endsWith('/retarget') && method === 'POST')
      return json(200, overrides.retarget ?? ACTION_ITEM)
    if (/\/inbox\/messages\/[^/]+$/u.test(url)) return json(200, MESSAGE_DETAIL)
    if (url.endsWith('/trips') && method === 'GET') return json(200, [TRIP])
    if (url.endsWith(`/trips/${TRIP.id}`)) return json(200, TRIP_DETAIL)

    return json(404, { error: { code: 'not_found', field: null } })
  }
}

async function renderInbox(overrides: Overrides = {}, locale: Locale = 'en') {
  await applyLocale(locale)
  mockApi(backend({ ...overrides, ownerLocale: locale }))
  render(
    <MemoryRouter initialEntries={['/inbox']}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  )
}

async function openSheet(overrides: Overrides = {}, locale: Locale = 'en') {
  await renderInbox(overrides, locale)
  const review = await screen.findByRole('button', { name: locale === 'en' ? 'Review' : 'Przejrzyj' })
  await userEvent.click(review)
  const dialog = await screen.findByRole('dialog')
  // Wait for the proposal itself, not only the frame.
  await within(dialog).findByText(ACTION_ITEM.subject)
  return dialog
}

function sent(path: string) {
  return requests.filter((one) => one.url.endsWith(path) && one.method === 'POST')
}

beforeEach(async () => {
  requests = []
  initI18n('en')
  await applyLocale('en')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the awaiting-you region', () => {
  it('lists a pending proposal first, with where it points', async () => {
    await renderInbox()

    const region = await screen.findByRole('region', { name: 'Awaiting you' })
    expect(within(region).getByText(ACTION_ITEM.subject)).toBeInTheDocument()
    expect(within(region).getByText(/Updates “Hotel Majestic”/)).toBeInTheDocument()
    expect(within(region).getByText(/3 fields/)).toBeInTheDocument()
  })

  it('counts pending proposals on the nav badge', async () => {
    await applyLocale('en')
    mockApi(
      backend({ summary: { ...SUMMARY, pending_action_items: 2, unrouted: 1 }, ownerLocale: 'en' }),
    )
    render(
      <MemoryRouter initialEntries={['/trips']}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </MemoryRouter>,
    )

    const badge = await screen.findByRole('link', { name: /Inbox/ })
    expect(within(badge).getByText('3 waiting')).toBeInTheDocument()
  })
})

describe('the review sheet', () => {
  it('ticks empty fields and leaves fields the owner filled unticked', async () => {
    const dialog = await openSheet()

    expect(within(dialog).getByRole('checkbox', { name: 'Cost' })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: 'Title' })).not.toBeChecked()
    // Identical values are a no-op: shown, unticked, and not offered.
    expect(within(dialog).getByRole('checkbox', { name: 'Confirmation number' })).toBeDisabled()
    // A forward status move is ticked.
    expect(within(dialog).getByRole('checkbox', { name: 'Status' })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: /voucher\.pdf/ })).toBeChecked()
    // Said in words, not only by colour.
    expect(within(dialog).getByText(/differs — not ticked by default/)).toBeInTheDocument()
  })

  it('shows the source message beside the proposal, as text', async () => {
    const dialog = await openSheet()

    expect(await within(dialog).findByText(MESSAGE_DETAIL.text_body)).toBeInTheDocument()
  })

  it('formats the proposed cost through Intl, never as a raw string', async () => {
    const dialog = await openSheet()

    const row = within(dialog).getByRole('checkbox', { name: 'Cost' }).closest('tr')
    expect(row).not.toBeNull()
    const expected = new Intl.NumberFormat('en', {
      style: 'currency',
      currency: 'MYR',
      useGrouping: 'always',
    }).format(480)
    // `textContent`, not `toHaveTextContent`: the latter normalises whitespace
    // and Intl separates the code from the amount with a no-break space.
    expect(row?.textContent).toContain(expected)
  })

  it('sends exactly the ticked fields, the documents and the revision', async () => {
    const dialog = await openSheet()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve selected' }))

    await waitFor(() => expect(sent('/approve')).toHaveLength(1))
    expect(sent('/approve')[0]?.body).toEqual({
      target_item_id: HOTEL.id,
      target_trip_day_id: null,
      fields: ['cost'],
      attachment_ids: [DOCUMENT.id],
      set_status: 'done',
      expected_revision: 1,
    })
    expect(await within(dialog).findByText(/Approved\./)).toBeInTheDocument()
  })

  it('sends a field only once the owner ticks it himself', async () => {
    const dialog = await openSheet()

    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Title' }))
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Cost' }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve selected' }))

    await waitFor(() => expect(sent('/approve')).toHaveLength(1))
    const body = sent('/approve')[0]?.body as { fields: string[] } | undefined
    expect(body?.fields).toEqual(['title'])
  })

  it('reloads with the current values on a conflict, rather than retrying', async () => {
    const reload = {
      ...ACTION_ITEM,
      revision: 2,
      fields: [{ ...ACTION_ITEM.fields[1], current: { amount: '400.00', currency: 'MYR' }, default_ticked: false }],
    }
    const dialog = await openSheet({
      reload,
      approve: () => json(409, { error: { code: 'action_item_conflict', field: 'cost' } }),
    })

    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve selected' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/Something changed/)
    await waitFor(() =>
      expect(within(dialog).getByRole('checkbox', { name: 'Cost' })).not.toBeChecked(),
    )
    expect(sent('/approve')).toHaveLength(1)
  })

  it('re-targets onto another item of the trip', async () => {
    const dialog = await openSheet({
      retarget: {
        ...ACTION_ITEM,
        revision: 2,
        target_item_id: FERRY.id,
        target_item_title: FERRY.title,
        target_date: '2026-10-18',
        target_reason: 'chosen_by_owner',
      },
    })

    const picker = await within(dialog).findByRole('combobox', { name: 'Point this proposal at' })
    await userEvent.selectOptions(picker, `item:${FERRY.id}`)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Change target' }))

    await waitFor(() => expect(sent('/retarget')).toHaveLength(1))
    expect(sent('/retarget')[0]?.body).toEqual({ target_item_id: FERRY.id, expected_revision: 1 })
    expect(await within(dialog).findByText(/Updates “Ferry”/)).toBeInTheDocument()
  })

  it('rejects without confirmation and closes', async () => {
    const dialog = await openSheet()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(sent('/reject')).toHaveLength(1)
  })

  it('offers undo after approving, and says what it will restore', async () => {
    const dialog = await openSheet()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve selected' }))

    expect(await within(dialog).findByText(/restores 2 fields and returns 1 document/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Undo' }))

    await waitFor(() => expect(sent('/undo')).toHaveLength(1))
  })

  it('moves focus in, closes on Escape, and returns focus to its trigger', async () => {
    await renderInbox()
    const review = await screen.findByRole('button', { name: 'Review' })
    await userEvent.click(review)
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByRole('button', { name: 'Close' })).toHaveFocus()
    await userEvent.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(review).toHaveFocus()
  })
})

describe('both locales', () => {
  it('renders the sheet in Polish, with its plural forms', async () => {
    const dialog = await openSheet({}, 'pl')

    expect(within(dialog).getByRole('heading', { name: 'Przejrzyj propozycję' })).toBeInTheDocument()
    expect(within(dialog).getByRole('checkbox', { name: 'Koszt' })).toBeChecked()
    // `few`: three fields is "3 pola", not "3 pól".
    expect(screen.getByText(/3 pola/)).toBeInTheDocument()
  })

  it('renders the sheet in English', async () => {
    const dialog = await openSheet({}, 'en')

    expect(within(dialog).getByRole('heading', { name: 'Review proposal' })).toBeInTheDocument()
  })
})
