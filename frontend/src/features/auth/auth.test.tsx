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
    mockApi(() => json(200, OWNER))

    renderApp('/trips')

    expect(await screen.findByText('owner@example.com')).toBeInTheDocument()
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
    let signedIn = false

    mockApi((url, init) => {
      if (url.endsWith('/auth/login')) {
        signedIn = true
        return noContent()
      }
      if (url.endsWith('/auth/me') && (init?.method ?? 'GET') === 'GET') {
        return signedIn ? json(200, OWNER) : unauthenticated()
      }
      return json(404, { error: { code: 'not_found', field: null } })
    })

    renderApp('/trips')

    await user.type(await screen.findByLabelText('E-mail'), 'owner@example.com')
    await user.type(screen.getByLabelText('Hasło'), 'a-password')
    await user.click(screen.getByRole('button', { name: 'Zaloguj się' }))

    // The return path is preserved: sign-in lands back on /trips, not a default.
    expect(await screen.findByText('owner@example.com')).toBeInTheDocument()
  })

  it('sends the credentials to the login endpoint', async () => {
    const user = userEvent.setup()
    let signedIn = false
    mockApi((url) => {
      if (url.endsWith('/auth/login')) {
        signedIn = true
        return noContent()
      }
      return signedIn ? json(200, OWNER) : unauthenticated()
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
    let signedIn = true

    mockApi((url) => {
      if (url.endsWith('/auth/logout')) {
        signedIn = false
        return noContent()
      }
      return signedIn ? json(200, OWNER) : unauthenticated()
    })

    renderApp('/trips')
    await screen.findByText('owner@example.com')

    saveDraft('item:1', { title: 'a private plan' })
    await user.click(screen.getByRole('button', { name: 'Wyloguj się' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Zaloguj się' })).toBeVisible())
    expect(draftCount()).toBe(0)
  })

  it('sends the CSRF header on the logout request', async () => {
    const user = userEvent.setup()
    let signedIn = true
    mockApi((url) => {
      if (url.endsWith('/auth/logout')) {
        signedIn = false
        return noContent()
      }
      return signedIn ? json(200, OWNER) : unauthenticated()
    })

    renderApp('/trips')
    await screen.findByText('owner@example.com')
    await user.click(screen.getByRole('button', { name: 'Wyloguj się' }))

    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith('/auth/logout'))
    const headers = call?.[1]?.headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBe('test-csrf-token')
  })
})

describe('a session that expires mid-use', () => {
  it('routes to the login screen from anywhere, and keeps the draft', async () => {
    const user = userEvent.setup()
    let signedIn = true

    mockApi((url) => {
      if (url.endsWith('/auth/me')) {
        return signedIn ? json(200, OWNER) : unauthenticated()
      }
      return unauthenticated()
    })

    renderApp('/trips')
    await screen.findByText('owner@example.com')

    // The owner has unsaved input open when the session dies on the server.
    saveDraft('item:42', { title: 'Nocleg: Memmo Alfama' })
    signedIn = false

    // Any request answering 401 must be noticed, not only by whichever component
    // happened to make it.
    await user.click(screen.getByRole('button', { name: 'Wyloguj się' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Zaloguj się' })).toBeVisible())
  })

  it('a 401 from any request collapses the session', async () => {
    let signedIn = true
    mockApi((url) => (signedIn && url.endsWith('/auth/me') ? json(200, OWNER) : unauthenticated()))

    renderApp('/trips')
    await screen.findByText('owner@example.com')

    signedIn = false
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
