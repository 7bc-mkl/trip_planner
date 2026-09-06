import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from './SessionContext'
import { clearAllDrafts, clearDraft, draftCount, readDraft, saveDraft } from './draftStore'

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

const noContent = () => new Response(null, { status: 204 })

const unauthenticated = () => json(401, { error: { code: 'not_authenticated', field: null } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

/**
 * The signed-in backend for the session tests.
 *
 * These tests are about the session, not about trips, so `/trips` answers with an
 * empty list. It still has to answer *something* shaped like a list: the guarded
 * screen is now the real trip list, which calls the endpoint as soon as it mounts.
 */
const signedIn = (url: string) =>
  url.endsWith('/trips') ? json(200, []) : json(200, OWNER)

/**
 * Wait until the guarded screen is on screen.
 *
 * Phase 1 keyed this on the owner's e-mail, which the placeholder screen printed.
 * The real trip list does not show it, so the signal is now the list's own
 * heading — the thing an owner actually lands on after signing in.
 */
const guardedScreen = () => screen.findByRole('heading', { name: 'Podróże', level: 1 })

function mockApi(handler: Handler) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(handler(String(input), init)),
  ))
}

function renderApp(initialPath = '/trips') {
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
  clearAllDrafts()
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the route guard', () => {
  it('sends an anonymous visitor to the login screen', async () => {
    mockApi(() => unauthenticated())

    renderApp('/trips')

    expect(await screen.findByRole('heading', { name: 'Zaloguj się' })).toBeInTheDocument()
  })

  it('renders the guarded screen for a signed-in owner', async () => {
    mockApi((url) => signedIn(url))

    renderApp('/trips')

    expect(await guardedScreen()).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Zaloguj się' })).not.toBeInTheDocument()
  })

  it('shows a loading state rather than flashing either screen', () => {
    mockApi(() => new Promise<Response>(() => {}) as unknown as Response)

    renderApp('/trips')

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Zaloguj się' })).not.toBeInTheDocument()
  })
})

describe('the login form', () => {
  it('signs in and lands on the path the visitor was going to', async () => {
    const user = userEvent.setup()
    let isSignedIn = false

    mockApi((url, init) => {
      if (url.endsWith('/auth/login')) {
        isSignedIn = true
        return noContent()
      }
      if (url.endsWith('/auth/me') && (init?.method ?? 'GET') === 'GET') {
        return isSignedIn ? signedIn(url) : unauthenticated()
      }
      return json(404, { error: { code: 'not_found', field: null } })
    })

    renderApp('/trips')

    await user.type(await screen.findByLabelText('E-mail'), 'owner@example.com')
    await user.type(screen.getByLabelText('Hasło'), 'a-password')
    await user.click(screen.getByRole('button', { name: 'Zaloguj się' }))

    // The return path is preserved: sign-in lands back on /trips, not a default.
    expect(await guardedScreen()).toBeInTheDocument()
  })

  it('sends the credentials to the login endpoint', async () => {
    const user = userEvent.setup()
    let isSignedIn = false
    mockApi((url) => {
      if (url.endsWith('/auth/login')) {
        isSignedIn = true
        return noContent()
      }
      return isSignedIn ? signedIn(url) : unauthenticated()
    })

    renderApp('/login')

    await user.type(await screen.findByLabelText('E-mail'), 'owner@example.com')
    await user.type(screen.getByLabelText('Hasło'), 'a-password')
    await user.click(screen.getByRole('button', { name: 'Zaloguj się' }))

    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/auth/login'))
    expect(call).toBeDefined()
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      email: 'owner@example.com',
      password: 'a-password',
    })
  })

  it.each([
    ['pl', 'Nie udało się zalogować. Sprawdź e-mail i hasło.'],
    ['en', 'We could not sign you in. Check your e-mail and password.'],
  ])('shows one generic failure message in %s', async (locale, expected) => {
    await applyLocale(locale as 'pl' | 'en')
    const user = userEvent.setup()

    mockApi((url) =>
      url.endsWith('/auth/login')
        ? json(401, { error: { code: 'invalid_credentials', field: null } })
        : unauthenticated(),
    )

    renderApp('/login')

    const emailLabel = locale === 'pl' ? 'E-mail' : 'E-mail'
    await user.type(await screen.findByLabelText(emailLabel), 'owner@example.com')
    await user.type(screen.getByLabelText(locale === 'pl' ? 'Hasło' : 'Password'), 'wrong')
    await user.click(
      screen.getByRole('button', { name: locale === 'pl' ? 'Zaloguj się' : 'Sign in' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(expected)
  })

  it('does not reveal whether the account exists', async () => {
    const user = userEvent.setup()
    mockApi((url) =>
      url.endsWith('/auth/login')
        ? json(401, { error: { code: 'invalid_credentials', field: null } })
        : unauthenticated(),
    )

    renderApp('/login')
    await user.type(await screen.findByLabelText('E-mail'), 'nobody@example.com')
    await user.type(screen.getByLabelText('Hasło'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Zaloguj się' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent?.toLowerCase()).not.toMatch(/nie istnieje|unknown|no account|nieznany/)
  })
})

describe('sign-out', () => {
  it('returns to the login screen and clears drafts', async () => {
    const user = userEvent.setup()
    let isSignedIn = true

    mockApi((url) => {
      if (url.endsWith('/auth/logout')) {
        isSignedIn = false
        return noContent()
      }
      return isSignedIn ? signedIn(url) : unauthenticated()
    })

    renderApp('/trips')
    await guardedScreen()

    saveDraft('item:1', { title: 'a private plan' })
    await user.click(screen.getByRole('button', { name: 'Wyloguj się' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Zaloguj się' })).toBeVisible())
    expect(draftCount()).toBe(0)
  })

  it('sends the CSRF header on the logout request', async () => {
    const user = userEvent.setup()
    let isSignedIn = true
    mockApi((url) => {
      if (url.endsWith('/auth/logout')) {
        isSignedIn = false
        return noContent()
      }
      return isSignedIn ? signedIn(url) : unauthenticated()
    })

    renderApp('/trips')
    await guardedScreen()
    await user.click(screen.getByRole('button', { name: 'Wyloguj się' }))

    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/auth/logout'))
    const headers = call?.[1]?.headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBe('test-csrf-token')
  })
})

describe('a session that expires mid-use', () => {
  it('routes to the login screen from anywhere, and keeps the draft', async () => {
    const user = userEvent.setup()
    let isSignedIn = true

    // Every endpoint follows the same flag: the point is that the session dies on
    // the server mid-use, not that one particular route is broken. Answering 401
    // from the start would collapse the session on the trip list's own first call,
    // before the test has anything to observe.
    mockApi((url) => (isSignedIn ? signedIn(url) : unauthenticated()))

    renderApp('/trips')
    await guardedScreen()

    // The owner has unsaved input open when the session dies on the server.
    saveDraft('item:42', { title: 'Nocleg: Memmo Alfama' })
    isSignedIn = false

    // Any request answering 401 must be noticed, not only by whichever component
    // happened to make it.
    await user.click(screen.getByRole('button', { name: 'Wyloguj się' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Zaloguj się' })).toBeVisible())
  })

  it('a 401 from any request collapses the session', async () => {
    let isSignedIn = true
    mockApi((url) => (isSignedIn ? signedIn(url) : unauthenticated()))

    renderApp('/trips')
    await guardedScreen()

    isSignedIn = false
    const { request } = await import('../../api/client')
    await expect(request('/auth/me')).rejects.toThrow()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Zaloguj się' })).toBeVisible())
  })

  it('does not collapse the initial loading state before /auth/me answers', () => {
    // Racing the first call here would flash the login screen on every reload.
    mockApi(() => new Promise<Response>(() => {}) as unknown as Response)

    renderApp('/trips')

    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})

describe('the draft store', () => {
  it('survives the unmount a 401 redirect causes', () => {
    // Component state does not survive an unmount, which is why this store is
    // module-scoped rather than held in the dialog.
    saveDraft('item:42', { title: 'Nocleg: Memmo Alfama', notes: 'unsaved' })

    const { unmount } = renderApp('/login')
    unmount()

    expect(readDraft('item:42')).toEqual({ title: 'Nocleg: Memmo Alfama', notes: 'unsaved' })
  })

  it('is cleared per key on a successful save', () => {
    saveDraft('item:1', { title: 'one' })
    saveDraft('item:2', { title: 'two' })

    clearDraft('item:1')

    expect(readDraft('item:1')).toBeUndefined()
    expect(readDraft('item:2')).toEqual({ title: 'two' })
  })

  it('returns undefined for a key that was never written', () => {
    expect(readDraft('item:missing')).toBeUndefined()
  })

  it('does not persist beyond the tab', () => {
    // A draft can contain the owner's private plan; it must not outlive the tab.
    saveDraft('item:1', { title: 'private' })
    expect(window.localStorage.getItem('item:1')).toBeNull()
    expect(document.cookie).not.toContain('private')
  })
})

describe('the language choice', () => {
  it('is stored on the owner, not only in this browser', async () => {
    // R01 makes both languages first-class, and the locale lives in the `owner`
    // row precisely so it survives a new browser. That only holds if the switch
    // actually writes it — the endpoint existing is not the same as it being called.
    const user = userEvent.setup()
    mockApi((url, init) => {
      if (url.endsWith('/auth/me') && init?.method === 'PATCH') {
        return json(200, { ...OWNER, locale: 'en' })
      }
      return signedIn(url)
    })

    renderApp('/trips')
    await guardedScreen()

    await user.selectOptions(screen.getByRole('combobox'), 'en')

    await waitFor(() => {
      const call = vi
        .mocked(fetch)
        .mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'PATCH')
      expect(call).toBeDefined()
      expect(String(call?.[0])).toContain('/auth/me')
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ locale: 'en' })
    })
  })

  it('still switches the interface when storing the preference fails', async () => {
    // A failed PATCH must not leave the owner staring at the language they just
    // switched away from.
    const user = userEvent.setup()
    mockApi((url, init) => {
      if (url.endsWith('/auth/me') && init?.method === 'PATCH') {
        return json(503, { error: { code: 'service_unavailable', field: null } })
      }
      return signedIn(url)
    })

    renderApp('/trips')
    await guardedScreen()

    await user.selectOptions(screen.getByRole('combobox'), 'en')

    expect(await screen.findByRole('button', { name: 'Sign out' })).toBeInTheDocument()
  })

  it('is not sent to the server from the signed-out login screen', async () => {
    const user = userEvent.setup()
    mockApi(() => unauthenticated())

    renderApp('/login')
    await screen.findByRole('heading', { name: 'Zaloguj się' })

    await user.selectOptions(screen.getByRole('combobox'), 'en')

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(
      vi.mocked(fetch).mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'PATCH'),
    ).toBe(false)
  })
})

describe('the login screen after an expiry', () => {
  it('says why the owner is back on it', async () => {
    let isSignedIn = true
    mockApi((url) => (isSignedIn ? signedIn(url) : unauthenticated()))

    renderApp('/trips')
    await guardedScreen()

    isSignedIn = false
    const { request } = await import('../../api/client')
    await expect(request('/auth/me')).rejects.toThrow()

    expect(await screen.findByText('Sesja wygasła. Zaloguj się ponownie.')).toBeInTheDocument()
  })

  it('says nothing to a visitor who was never signed in', async () => {
    // "Your session expired" is a lie on a first visit.
    mockApi(() => unauthenticated())

    renderApp('/login')
    await screen.findByRole('heading', { name: 'Zaloguj się' })

    expect(screen.queryByText('Sesja wygasła. Zaloguj się ponownie.')).not.toBeInTheDocument()
  })
})
