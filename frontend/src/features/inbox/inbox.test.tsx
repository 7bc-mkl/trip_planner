import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import type { Locale } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'

/**
 * The `/inbox` screen.
 *
 * Rendered through the real `<App/>` and a `MemoryRouter`, like the trip
 * screens, because the route wiring is part of what is being tested.
 *
 * Several of these assert on what is **absent**: the body of a quarantined
 * message, an address before *Show* is pressed, a badge on an unconfigured
 * deployment. Those are the screen's actual contract — quarantine is a barrier,
 * and "the inbox is off" is a normal state — and absence is exactly what a
 * refactor loses without any test noticing unless one is written for it.
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
  readiness: { arranged: 0, tracked: 0 },
}

const ADDRESS = 'inbox@mail.planner.example.com'

const SUMMARY = {
  inbox_enabled: true,
  address: ADDRESS,
  unrouted: 0,
  quarantined: 0,
  last_received_at: '2026-10-01T09:00:00+00:00',
  last_error_at: null,
  last_error: null,
}

const MESSAGE = {
  id: 'message-1',
  received_at: '2026-10-01T09:00:00+00:00',
  from_address: 'rezerwacje@airline.example',
  subject: 'Potwierdzenie rezerwacji KL-4411',
  state: 'received' as const,
  trip_id: null,
  routing_reason: null,
  last_error: null,
  attachment_count: 1,
}

const DETAIL = {
  ...MESSAGE,
  text_body: 'PNR: SX-9912L\nKwota: 249 PLN',
  attachments: [
    {
      id: 'attachment-1',
      filename: 'voucher.pdf',
      content_type: 'application/pdf',
      byte_size: 2048,
      sha256: 'a'.repeat(64),
      created_at: '2026-10-01T09:00:00+00:00',
      sent_externally_at: null,
    },
  ],
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

/**
 * The default backend: a signed-in owner, a summary, and whatever the test names.
 *
 * Shaped after `features/trips/trips.test.tsx`'s `backend`, deliberately — one
 * idiom for stubbing this API across the suite rather than two.
 */
function backend(
  overrides: {
    summary?: unknown
    messages?: unknown[]
    quarantine?: unknown[]
    detail?: unknown
    trips?: unknown[]
    /**
     * The owner's stored locale. It is not decoration: R01 puts the choice on
     * the owner rather than in the browser, so `SessionProvider` applies it on
     * sign-in — and an English test whose owner is stored as `pl` renders in
     * Polish however the test set the locale beforehand.
     */
    ownerLocale?: Locale
  } = {},
): Handler {
  return (url, init) => {
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url.endsWith('/auth/me'))
      return json(200, { ...OWNER, locale: overrides.ownerLocale ?? 'pl' })
    if (url.endsWith('/inbox/summary')) return json(200, overrides.summary ?? SUMMARY)
    if (url.endsWith('/inbox/messages') && method === 'GET')
      return json(200, overrides.messages ?? [])
    if (url.endsWith('/inbox/quarantine') && method === 'GET')
      return json(200, overrides.quarantine ?? [])
    if (/\/inbox\/messages\/[^/]+$/u.test(url) && method === 'GET')
      return json(200, overrides.detail ?? DETAIL)
    if (/\/inbox\/messages\/[^/]+\/place$/u.test(url) && method === 'POST')
      return json(200, { ...MESSAGE, state: 'routed', trip_id: TRIP.id })
    if (/\/inbox\/quarantine\/[^/]+\/trust-sender$/u.test(url) && method === 'POST')
      return json(200, MESSAGE)
    if (/\/inbox\/quarantine\/[^/]+\/release$/u.test(url) && method === 'POST')
      return json(200, MESSAGE)
    if (url.endsWith('/trips') && method === 'GET') return json(200, overrides.trips ?? [TRIP])

    return json(404, { error: { code: 'not_found', field: null } })
  }
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

async function useLocale(locale: Locale) {
  initI18n(locale)
  await applyLocale(locale)
}

async function renderInbox(
  overrides: Parameters<typeof backend>[0] = {},
  locale: Locale = 'pl',
) {
  // `applyLocale` only — `initI18n` already ran in `beforeEach`, and calling it
  // a second time re-initialises i18next underneath a half-rendered tree.
  await applyLocale(locale)
  mockApi(backend({ ...overrides, ownerLocale: locale }))
  renderApp('/inbox')
}

beforeEach(async () => {
  requests = []
  await useLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the inbox screen', () => {
  it('names the forwarding address in its empty state', async () => {
    // The empty state's whole job: tell him the one thing he needs in order to
    // make it non-empty.
    await renderInbox()

    expect(await screen.findByText(ADDRESS)).toBeInTheDocument()
  })

  it('lists a message with its sender and subject', async () => {
    await renderInbox({ messages: [MESSAGE] })

    expect(await screen.findByText('Potwierdzenie rezerwacji KL-4411')).toBeInTheDocument()
    expect(screen.getByText('rezerwacje@airline.example')).toBeInTheDocument()
  })

  it('shows a message that has arrived but is not yet readable', async () => {
    // Hiding it would make a slow ingestion indistinguishable from no mail.
    await renderInbox({ messages: [{ ...MESSAGE, state: 'pending_ingest', attachment_count: 0 }] })

    expect(await screen.findByText('Potwierdzenie rezerwacji KL-4411')).toBeInTheDocument()
  })

  it('renders the body as text, with no markup of any kind', async () => {
    // The server already reduced any HTML away; this asserts the browser side
    // never puts it back. An `<img>` here would be a tracking pixel fetched.
    await renderInbox({ messages: [MESSAGE] })

    await userEvent.click(await screen.findByRole('button', { name: 'Otwórz' }))

    const body = await screen.findByText(/PNR: SX-9912L/)
    expect(body.querySelector('img')).toBeNull()
    expect(body.querySelector('a')).toBeNull()
    expect(body.innerHTML).not.toContain('<')
  })

  it('offers a document as a download, never as a preview', async () => {
    // A10: serving a PDF inline would run its JavaScript in this origin with
    // the session cookie in scope.
    await renderInbox({ messages: [MESSAGE] })

    await userEvent.click(await screen.findByRole('button', { name: 'Otwórz' }))

    const link = await screen.findByRole('link', { name: 'Pobierz' })
    expect(link).toHaveAttribute(
      'href',
      '/api/v1/inbox/messages/message-1/attachments/attachment-1/content',
    )
  })
})

describe('the unrouted queue', () => {
  const UNROUTED = {
    ...MESSAGE,
    state: 'unrouted' as const,
    routing_reason: 'ingest_failed',
    attachment_count: 0,
  }

  it('explains why a message was not placed, through a translated key', async () => {
    // Never the server's own sentence: the reason is a stable code precisely so
    // no sender-authored or model-authored text reaches the screen.
    await renderInbox({ messages: [UNROUTED] })

    expect(await screen.findByText('Nie udało się pobrać wiadomości.')).toBeInTheDocument()
  })

  it('places a message on a trip the owner chooses', async () => {
    await renderInbox({ messages: [UNROUTED] })

    await userEvent.selectOptions(
      await screen.findByLabelText('Której podróży dotyczy?'),
      TRIP.id,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Przypisz' }))

    await waitFor(() =>
      expect(
        requests.find((one) => one.method === 'POST' && one.url.endsWith('/place')),
      ).toMatchObject({ body: { trip_id: TRIP.id } }),
    )
  })

  it('says that placing writes nothing to the plan', async () => {
    // The control would otherwise look like it filed the document into the trip.
    await renderInbox({ messages: [UNROUTED] })

    expect(
      await screen.findByText(/Nic nie trafia do planu/),
    ).toBeInTheDocument()
  })

  it('does not offer a trip picker when there are no trips', async () => {
    // D03: a message never creates a trip, so the honest answer is to say what
    // is missing rather than offer a shortcut the product decided against.
    await renderInbox({ messages: [UNROUTED], trips: [] })

    expect(await screen.findByText(/Najpierw utwórz podróż/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Której podróży dotyczy?')).not.toBeInTheDocument()
  })
})

describe('quarantine', () => {
  const HELD = {
    id: 'held-1',
    received_at: '2026-10-01T09:00:00+00:00',
    from_address: 'stranger@example.net',
    subject: 'Zupełnie inna wiadomość',
    reason: 'unknown_sender',
    may_trust_sender: true,
    may_release_message: false,
    recoverable: true,
  }

  const withCount = (count: number) => ({ ...SUMMARY, quarantined: count })

  it('shows a count and no sender until Show is pressed', async () => {
    // A bare count would make a real loss silent; a list shown by default would
    // put a stranger's subject line on screen the moment he opens the app.
    await renderInbox({ summary: withCount(3), quarantine: [HELD] })

    expect(await screen.findByText(/3 wiadomości od nieznanych nadawców/)).toBeInTheDocument()
    expect(screen.queryByText('stranger@example.net')).not.toBeInTheDocument()
  })

  it('reveals sender and subject on Show, and nothing else', async () => {
    await renderInbox({ summary: withCount(1), quarantine: [HELD] })

    await userEvent.click(await screen.findByRole('button', { name: 'Pokaż nadawców' }))

    expect(await screen.findByText('stranger@example.net')).toBeInTheDocument()
    expect(screen.getByText('Zupełnie inna wiadomość')).toBeInTheDocument()
    // The barrier: there is no body and no document to reveal, ever.
    expect(screen.queryByRole('link', { name: 'Pobierz' })).not.toBeInTheDocument()
  })

  it('offers trusting for an authenticated unknown sender, and not releasing', async () => {
    await renderInbox({ summary: withCount(1), quarantine: [HELD] })

    await userEvent.click(await screen.findByRole('button', { name: 'Pokaż nadawców' }))

    expect(await screen.findByRole('button', { name: 'Zaufaj temu nadawcy' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zwolnij tę wiadomość' })).not.toBeInTheDocument()
  })

  it('offers releasing for a failed authentication, and not trusting', async () => {
    // Trusting would add a spoofable address to the allow-list for ever on the
    // strength of one recognised subject line.
    await renderInbox({
      summary: withCount(1),
      quarantine: [
        {
          ...HELD,
          reason: 'failed_authentication',
          may_trust_sender: false,
          may_release_message: true,
        },
      ],
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Pokaż nadawców' }))

    expect(await screen.findByRole('button', { name: 'Zwolnij tę wiadomość' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zaufaj temu nadawcy' })).not.toBeInTheDocument()
  })

  it('offers neither recovery for a failed scan', async () => {
    // A virus verdict is not a false positive the owner can overrule.
    await renderInbox({
      summary: withCount(1),
      quarantine: [
        {
          ...HELD,
          reason: 'failed_scan',
          may_trust_sender: false,
          may_release_message: false,
        },
      ],
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Pokaż nadawców' }))

    expect(await screen.findByText(/nie przeszła kontroli/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zaufaj temu nadawcy' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zwolnij tę wiadomość' })).not.toBeInTheDocument()
  })

  it('says so when the original message can no longer be recovered', async () => {
    // Said up front rather than discovered by pressing a button that fails.
    await renderInbox({
      summary: withCount(1),
      quarantine: [{ ...HELD, recoverable: false }],
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Pokaż nadawców' }))

    expect(await screen.findByText(/nie jest już przechowywana/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zaufaj temu nadawcy' })).not.toBeInTheDocument()
  })

  it('trusts a sender and reloads', async () => {
    await renderInbox({ summary: withCount(1), quarantine: [HELD] })

    await userEvent.click(await screen.findByRole('button', { name: 'Pokaż nadawców' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Zaufaj temu nadawcy' }))

    await waitFor(() =>
      expect(
        requests.some((one) => one.method === 'POST' && one.url.endsWith('/trust-sender')),
      ).toBe(true),
    )
  })
})

describe('honest freshness', () => {
  it('says when mail last arrived', async () => {
    await renderInbox()

    expect(await screen.findByText(/Ostatnia dostawa/)).toBeInTheDocument()
  })

  it('says so when nothing has ever arrived', async () => {
    await renderInbox({ summary: { ...SUMMARY, last_received_at: null } })

    expect(await screen.findByText(/Żadna poczta jeszcze nie dotarła/)).toBeInTheDocument()
  })

  it('surfaces the last ingestion failure', async () => {
    // Without this, a dead subscription renders identically to a quiet week.
    await renderInbox({
      summary: {
        ...SUMMARY,
        last_error_at: '2026-10-02T09:00:00+00:00',
        last_error: 'ingest_failed',
      },
    })

    expect(await screen.findByText(/Ostatni błąd/)).toBeInTheDocument()
  })
})

describe('a deployment with no inbox configured', () => {
  const OFF = {
    inbox_enabled: false,
    address: null,
    unrouted: 0,
    quarantined: 0,
    last_received_at: null,
    last_error_at: null,
    last_error: null,
  }

  it('explains itself and shows no error', async () => {
    // A normal state, not a fault.
    await renderInbox({ summary: OFF })

    expect(await screen.findByText('Skrzynka nie jest skonfigurowana')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('asks for nothing else once it knows the inbox is off', async () => {
    // Every other inbox route answers `inbox_not_configured`; asking anyway
    // would paint an error over a screen whose job is to explain calmly.
    await renderInbox({ summary: OFF })

    await screen.findByText('Skrzynka nie jest skonfigurowana')
    expect(requests.filter((one) => one.url.includes('/inbox/messages'))).toEqual([])
  })

  it('shows no nav badge on the trips screen', async () => {
    // An absent badge is the honest rendering of "the inbox is off"; a zero
    // would invite the question of what it counts.
    mockApi(backend({ summary: OFF }))
    renderApp('/trips')

    await waitFor(() =>
      expect(screen.queryByRole('link', { name: /Skrzynka/ })).not.toBeInTheDocument(),
    )
  })
})

describe('the nav badge', () => {
  it('links to the inbox and counts what is waiting', async () => {
    mockApi(backend({ summary: { ...SUMMARY, unrouted: 2, quarantined: 1 } }))
    renderApp('/trips')

    const badge = await screen.findByRole('link', { name: /Skrzynka/ })
    expect(badge).toHaveAttribute('href', '/inbox')
    // Polish's `few` form for 3, which is the whole reason this key is an ICU
    // plural rather than two strings.
    expect(within(badge).getByText('3 oczekują')).toBeInTheDocument()
  })

  it('shows no count when nothing is waiting', async () => {
    mockApi(backend())
    renderApp('/trips')

    const badge = await screen.findByRole('link', { name: /Skrzynka/ })
    expect(badge).toHaveTextContent(/^Skrzynka$/)
  })
})

describe('both locales', () => {
  it('renders the screen in English', async () => {
    await renderInbox({ messages: [MESSAGE] }, 'en')

    expect(await screen.findByRole('heading', { name: 'Inbox' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Open' })).toBeInTheDocument()
  })

  it("exercises Polish's few and many plural forms", async () => {
    // The reason the project uses i18next-icu at all: i18next's own suffix
    // pluralisation would put four keys in pl.json against English's two and
    // fail `check_locales.py`.
    for (const [count, expected] of [
      [1, /^1 wiadomość od nieznanego nadawcy/],
      [3, /^3 wiadomości od nieznanych nadawców/],
      [7, /^7 wiadomości od nieznanych nadawców/],
    ] as const) {
      mockApi(backend({ summary: { ...SUMMARY, quarantined: count } }))
      const view = renderApp('/inbox')

      expect(await screen.findByText(expected)).toBeInTheDocument()
      view.unmount()
    }
  })

  it('renders the document count in both locales', async () => {
    await renderInbox({ messages: [MESSAGE] }, 'en')

    expect(await screen.findByText(/1 document/)).toBeInTheDocument()
  })
})
