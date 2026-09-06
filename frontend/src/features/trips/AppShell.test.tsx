import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'
import { AppShell } from './AppShell'

/**
 * The shell's own contract, asserted directly rather than through a screen.
 *
 * Every prop the design-system adoption adds to `AppShell` is **optional**, and
 * that is the compatibility promise the spec makes: four screens render it
 * today passing `{ title, breadcrumb?, actions?, children }` and none of them
 * may have to change. A shell that quietly required its new slots would break
 * every one of them, so the optional case is the case worth a test.
 */

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

function renderShell(props: Parameters<typeof AppShell>[0]) {
  return render(
    <MemoryRouter>
      <SessionProvider>
        <AppShell {...props} />
      </SessionProvider>
    </MemoryRouter>,
  )
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(OWNER), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the app shell', () => {
  it('renders the header, the heading and the page without a context line', () => {
    renderShell({ title: 'Malezja', children: <p>zawartość</p> })

    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Smart Trip Planner' })).toHaveAttribute(
      'href',
      '/trips',
    )
    expect(screen.getByRole('button', { name: 'Wyloguj się' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Malezja' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveTextContent('zawartość')

    // The prop is optional, so nothing of it is rendered when it is absent.
    expect(screen.getByRole('banner').querySelector('.app-header__context')).toBeNull()
  })

  it('names the trip in the header when a context line is passed', () => {
    renderShell({
      title: 'Malezja',
      context: 'Malezja · 10–13 paź 2026',
      children: <p>zawartość</p>,
    })

    expect(screen.getByRole('banner')).toHaveTextContent('Malezja · 10–13 paź 2026')
  })
})
