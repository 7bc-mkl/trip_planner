import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'

/** Phase 4 step 4: deleting a trip, behind a confirmation that names it. */

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const TRIP = {
  id: 'trip-1',
  title: 'Malezja, październik 2026',
  start_date: '2026-10-10',
  end_date: '2026-10-10',
  departure_place: 'Warszawa',
  return_place: 'Katowice',
  readiness: { arranged: 0, tracked: 0 },
  stages: [],
  days: [{ id: 'day-1', date: '2026-10-10', stage_ids: [], items: [] }],
}

let requests: { url: string; method: string }[] = []

function mockApi(onDelete?: () => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      requests.push({ url, method })

      if (url.endsWith('/auth/me')) return Promise.resolve(json(200, OWNER))
      if (method === 'DELETE') {
        return Promise.resolve(onDelete?.() ?? new Response(null, { status: 204 }))
      }
      if (url.endsWith('/trips')) return Promise.resolve(json(200, []))
      return Promise.resolve(json(200, TRIP))
    }),
  )
}

function renderTimeline() {
  return render(
    <MemoryRouter initialEntries={['/trips/trip-1']}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  )
}

beforeEach(async () => {
  requests = []
  initI18n('pl')
  await applyLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('deleting a trip', () => {
  async function openConfirmation() {
    const user = userEvent.setup()
    mockApi()
    renderTimeline()
    await screen.findByRole('heading', { name: TRIP.title })
    await user.click(screen.getByRole('button', { name: 'Usuń podróż' }))
    return user
  }

  it('asks for confirmation instead of deleting straight away', async () => {
    await openConfirmation()

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(requests.some((entry) => entry.method === 'DELETE')).toBe(false)
  })

  it('names the trip rather than asking "are you sure?"', async () => {
    await openConfirmation()

    // There is no undo, so the owner has to be able to tell *what* is going.
    expect(screen.getByRole('dialog')).toHaveTextContent('Malezja, październik 2026')
  })

  it('warns that everything in the trip goes with it', async () => {
    await openConfirmation()

    expect(screen.getByRole('dialog')).toHaveTextContent('Tej operacji nie można cofnąć.')
  })

  it('opens focused on cancel, not on the destructive action', async () => {
    await openConfirmation()

    // A stray Return on a dialog that appeared unexpectedly must not delete a trip.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Anuluj' })).toHaveFocus())
  })

  it('cancelling deletes nothing and closes the dialog', async () => {
    const user = await openConfirmation()

    await user.click(screen.getByRole('button', { name: 'Anuluj' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(requests.some((entry) => entry.method === 'DELETE')).toBe(false)
  })

  it('Escape cancels', async () => {
    const user = await openConfirmation()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(requests.some((entry) => entry.method === 'DELETE')).toBe(false)
  })

  it('confirming deletes the trip and returns to the list', async () => {
    const user = await openConfirmation()

    // Scoped to the dialog: the trigger behind it carries the same label, which
    // is correct — the confirm button should say what it does, not "OK".
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Usuń podróż' }),
    )

    await waitFor(() =>
      expect(
        requests.some(
          (entry) => entry.method === 'DELETE' && entry.url.endsWith('/trips/trip-1'),
        ),
      ).toBe(true),
    )
    expect(await screen.findByRole('heading', { name: 'Nie masz jeszcze żadnej podróży' }))
      .toBeInTheDocument()
  })

  it('returns focus to the trigger when the dialog closes', async () => {
    const user = userEvent.setup()
    mockApi()
    renderTimeline()
    await screen.findByRole('heading', { name: TRIP.title })

    const trigger = screen.getByRole('button', { name: 'Usuń podróż' })
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: 'Anuluj' }))

    await waitFor(() => expect(trigger).toHaveFocus())
  })
})
