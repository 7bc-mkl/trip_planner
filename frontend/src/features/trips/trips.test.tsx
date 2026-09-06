import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import type { Locale } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'
import { routeSummary, stageLabel } from './format'

/**
 * The Phase 2 screens: the trip list, the multi-stop creator and the empty timeline.
 *
 * These render the real `<App/>` through a `MemoryRouter` rather than mounting a
 * page component directly, because the route wiring is part of what is being
 * tested — a creator that builds the right body but navigates nowhere afterwards
 * is not a working screen.
 */

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const KUALA_LUMPUR = {
  id: 'stage-1',
  position: 0,
  place: 'Kuala Lumpur',
  start_date: '2026-10-11',
  end_date: '2026-10-15',
}
const PENANG = {
  id: 'stage-2',
  position: 1,
  place: 'Penang',
  start_date: '2026-10-15',
  end_date: '2026-10-17',
}

const TRIP = {
  id: 'trip-1',
  title: 'Malezja, październik 2026',
  start_date: '2026-10-10',
  end_date: '2026-10-13',
  departure_place: 'Warszawa',
  return_place: 'Katowice',
  readiness: { arranged: 0, tracked: 0 },
  stages: [KUALA_LUMPUR],
  days: [
    { id: 'day-1', date: '2026-10-10', stage_ids: [], items: [] },
    { id: 'day-2', date: '2026-10-11', stage_ids: ['stage-1'], items: [] },
    { id: 'day-3', date: '2026-10-12', stage_ids: ['stage-1'], items: [] },
    { id: 'day-4', date: '2026-10-13', stage_ids: ['stage-1'], items: [] },
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

/** The default backend: a signed-in owner and whatever trips the test names. */
function backend(trips: unknown[] = [], detail: unknown = TRIP): Handler {
  return (url, init) => {
    if (url.endsWith('/auth/me')) return json(200, OWNER)
    if (url.endsWith('/trips') && (init?.method ?? 'GET') === 'GET') return json(200, trips)
    if (url.endsWith('/trips') && init?.method === 'POST') return json(201, detail)
    if (/\/trips\/[^/]+$/u.test(url)) return json(200, detail)
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

beforeEach(async () => {
  requests = []
  await useLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the trip list', () => {
  it('shows a deliberate empty state for a first-time account', async () => {
    mockApi(backend([]))

    renderApp('/trips')

    expect(
      await screen.findByRole('heading', { name: 'Nie masz jeszcze żadnej podróży' }),
    ).toBeInTheDocument()
  })

  it('lists the trips with their dates and route summary', async () => {
    mockApi(backend([TRIP]))

    renderApp('/trips')

    expect(await screen.findByRole('heading', { name: TRIP.title })).toBeInTheDocument()
    expect(screen.getByText('Warszawa → Katowice')).toBeInTheDocument()
  })

  it('links each row to that trip’s timeline', async () => {
    mockApi(backend([TRIP]))

    renderApp('/trips')

    const link = await screen.findByRole('link', { name: /Malezja/u })
    expect(link).toHaveAttribute('href', '/trips/trip-1')
  })
})

describe('the multi-stop creator', () => {
  /** Fill in everything the form needs to be valid, leaving the route mode alone. */
  async function fillTheBasics(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText('Nazwa podróży'), 'Malezja')
    await user.type(screen.getByLabelText('Data rozpoczęcia'), '2026-10-10')
    await user.type(screen.getByLabelText('Data zakończenia'), '2026-10-24')
    await user.type(screen.getByLabelText('Wyjazd z'), 'Warszawa')
    await user.type(screen.getByLabelText('Cel 1'), 'Kuala Lumpur')
  }

  it('keeps the primary action disabled until the form is valid', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/new')

    const submit = await screen.findByRole('button', {
      name: 'Utwórz pustą oś czasu do ręcznego planowania',
    })
    expect(submit).toBeDisabled()

    await fillTheBasics(user)

    await waitFor(() => expect(submit).toBeEnabled())
  })

  it('stays disabled when a title is present but the date range is backwards', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/new')

    await screen.findByLabelText('Nazwa podróży')
    await user.type(screen.getByLabelText('Nazwa podróży'), 'Malezja')
    await user.type(screen.getByLabelText('Data rozpoczęcia'), '2026-10-24')
    await user.type(screen.getByLabelText('Data zakończenia'), '2026-10-10')
    await user.type(screen.getByLabelText('Wyjazd z'), 'Warszawa')
    await user.type(screen.getByLabelText('Cel 1'), 'Kuala Lumpur')

    expect(
      screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
    ).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Data zakończenia nie może być wcześniejsza niż data rozpoczęcia.',
    )
  })

  it('stays disabled while a stage range escapes the trip range', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/new')

    await screen.findByLabelText('Nazwa podróży')
    await fillTheBasics(user)
    await user.type(screen.getByLabelText('Od'), '2026-11-01')
    await user.type(screen.getByLabelText('Do'), '2026-11-05')

    expect(
      screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
    ).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Daty jednego z celów wykraczają poza daty podróży.',
    )
  })

  it('sends null for an undated stage rather than an empty string', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/new')

    await screen.findByLabelText('Nazwa podróży')
    await fillTheBasics(user)
    await user.click(
      screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
    )

    await waitFor(() => expect(postedTrip()).not.toBeUndefined())
    expect(postedTrip()?.stages).toEqual([
      { place: 'Kuala Lumpur', start_date: null, end_date: null },
    ])
  })

  it('navigates to the new trip’s timeline once it is created', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/new')

    await screen.findByLabelText('Nazwa podróży')
    await fillTheBasics(user)
    await user.click(
      screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
    )

    expect(await screen.findByRole('heading', { name: TRIP.title })).toBeInTheDocument()
  })

  it('adds and removes stage rows, but never the last one', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/new')

    await screen.findByLabelText('Cel 1')
    expect(screen.getAllByRole('button', { name: 'Usuń' })[0]).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Dodaj cel' }))

    expect(screen.getByLabelText('Cel 2')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Usuń' })[0]).toBeEnabled()

    await user.click(screen.getAllByRole('button', { name: 'Usuń' })[1]!)

    expect(screen.queryByLabelText('Cel 2')).not.toBeInTheDocument()
  })

  // The remove control is an icon button, and an icon button whose name lives
  // only in a tooltip is exactly what this screen does not ship: the word is
  // rendered beside the glyph, the glyph slot is `aria-hidden`, and the
  // accessible name is that visible word and nothing else.
  it('names the remove control with its own visible text', async () => {
    mockApi(backend())

    renderApp('/trips/new')

    const remove = await screen.findByRole('button', { name: 'Usuń' })
    expect(remove).toHaveAccessibleName('Usuń')
    expect(remove).toHaveTextContent('Usuń')
  })

  it('shows the live summary in the active locale', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/new')

    await screen.findByLabelText('Nazwa podróży')
    await fillTheBasics(user)

    // 10 to 24 October inclusive: 15 days, 14 nights, 1 base. The Polish plural
    // categories here are the ones i18next's default pluralisation would get wrong.
    expect(screen.getByRole('status')).toHaveTextContent('15 dni / 14 nocy · 1 baza')
  })

  describe('the route mode toggle writes the three return_place states', () => {
    async function submitWithMode(name: string) {
      const user = userEvent.setup()
      mockApi(backend())

      renderApp('/trips/new')
      await screen.findByLabelText('Nazwa podróży')
      await fillTheBasics(user)
      await user.click(screen.getByRole('radio', { name }))
      return user
    }

    it('round trip mirrors the departure place', async () => {
      const user = await submitWithMode('W obie strony')
      await user.click(
        screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
      )

      await waitFor(() => expect(postedTrip()).not.toBeUndefined())
      expect(postedTrip()?.return_place).toBe('Warszawa')
    })

    it('open-jaw sends the separately typed return place', async () => {
      const user = await submitWithMode('Inne miasto powrotu (open-jaw)')
      await user.type(screen.getByLabelText('Powrót do'), 'Katowice')
      await user.click(
        screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
      )

      await waitFor(() => expect(postedTrip()).not.toBeUndefined())
      expect(postedTrip()?.return_place).toBe('Katowice')
    })

    it('one way sends null', async () => {
      const user = await submitWithMode('W jedną stronę')
      await user.click(
        screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
      )

      await waitFor(() => expect(postedTrip()).not.toBeUndefined())
      expect(postedTrip()?.return_place).toBeNull()
    })

    it('open-jaw stays disabled until the return place is given', async () => {
      await submitWithMode('Inne miasto powrotu (open-jaw)')

      expect(
        screen.getByRole('button', { name: 'Utwórz pustą oś czasu do ręcznego planowania' }),
      ).toBeDisabled()
    })

    it('only open-jaw asks for a return place', async () => {
      await submitWithMode('W obie strony')

      expect(screen.queryByLabelText('Powrót do')).not.toBeInTheDocument()
    })
  })
})

function postedTrip() {
  const posted = requests.find((entry) => entry.method === 'POST' && entry.url.endsWith('/trips'))
  return posted?.body as
    | { return_place: string | null; stages: { place: string; start_date: string | null }[] }
    | undefined
}

describe('the empty timeline', () => {
  it('renders every day of the trip, not a blank page', async () => {
    mockApi(backend([], TRIP))

    renderApp('/trips/trip-1')

    await screen.findByRole('heading', { name: TRIP.title })
    const days = screen.getAllByRole('listitem')

    expect(days).toHaveLength(4)
  })

  it('shows the empty-state copy in Polish', async () => {
    mockApi(backend([], TRIP))

    renderApp('/trips/trip-1')

    expect(
      await screen.findByText('Ta oś czasu jest pusta. Otwórz dzień i dodaj pierwszy element.'),
    ).toBeInTheDocument()
  })

  it('shows the empty-state copy in English', async () => {
    // The owner's stored locale is the source of truth once signed in (R01), so
    // switching languages here means switching the *owner*, not just i18next —
    // setting the latter alone would be overridden the moment /auth/me answers.
    mockApi((url, init) => {
      if (url.endsWith('/auth/me')) return json(200, { ...OWNER, locale: 'en' })
      return backend([], TRIP)(url, init)
    })

    renderApp('/trips/trip-1')

    expect(
      await screen.findByText('This timeline is empty. Open a day and add your first item.'),
    ).toBeInTheDocument()
  })

  it('invites the first item on each empty day', async () => {
    mockApi(backend([], TRIP))

    renderApp('/trips/trip-1')

    await screen.findByRole('heading', { name: TRIP.title })

    expect(screen.getAllByText('Nic jeszcze nie zaplanowano')).toHaveLength(4)
  })

  it('labels a day with the stage covering it, and leaves a transit day unlabelled', async () => {
    mockApi(backend([], TRIP))

    renderApp('/trips/trip-1')

    await screen.findByRole('heading', { name: TRIP.title })
    const days = screen.getAllByRole('listitem')

    // 10 October is before the first stage begins — a day in transit.
    expect(within(days[0]!).queryByText('Kuala Lumpur')).not.toBeInTheDocument()
    expect(within(days[1]!).getByText('Kuala Lumpur')).toBeInTheDocument()
  })

  it('links each day to its day detail', async () => {
    mockApi(backend([], TRIP))

    renderApp('/trips/trip-1')

    await screen.findByRole('heading', { name: TRIP.title })

    expect(screen.getAllByRole('link', { name: /10/u })[0]).toHaveAttribute(
      'href',
      '/trips/trip-1/days/2026-10-10',
    )
  })
})

describe('stageLabel', () => {
  it('joins two places with an arrow', () => {
    expect(stageLabel([KUALA_LUMPUR, PENANG])).toBe('Kuala Lumpur → Penang')
  })

  it('truncates after two with the number hidden', () => {
    const extra = { ...PENANG, id: 'stage-3', place: 'Langkawi' }
    expect(stageLabel([KUALA_LUMPUR, PENANG, extra])).toBe('Kuala Lumpur → Penang +1')
  })

  it('is empty for a day in no stage, so nothing untranslated is rendered', () => {
    expect(stageLabel([])).toBe('')
  })
})

describe('routeSummary', () => {
  it('chains the departure place, the stages and the return place', () => {
    expect(routeSummary(TRIP, [KUALA_LUMPUR, PENANG])).toBe(
      'Warszawa → Kuala Lumpur → Penang → Katowice',
    )
  })

  it('does not repeat a return place identical to the last stage', () => {
    const trip = { ...TRIP, return_place: 'Penang' }
    expect(routeSummary(trip, [KUALA_LUMPUR, PENANG])).toBe('Warszawa → Kuala Lumpur → Penang')
  })

  it('omits the return place entirely for a one-way trip', () => {
    const trip = { ...TRIP, return_place: null }
    expect(routeSummary(trip, [KUALA_LUMPUR])).toBe('Warszawa → Kuala Lumpur')
  })
})
