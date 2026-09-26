import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import type { Locale } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'

/**
 * `/trips/:id/edit` — the screen that finally reaches `PATCH /trips/{id}`.
 *
 * Rendered through the real `<App/>` and a `MemoryRouter`, like the other trip
 * screens: the route wiring and the navigation after a save are part of what
 * has to work, and a component mounted directly proves neither.
 *
 * The assertions that matter most are the refusals. The endpoint's whole design
 * is that a date edit which would destroy something is refused and names what
 * is in the way; a screen that swallowed that into "something went wrong" would
 * leave the owner exactly where they were before this feature existed.
 */

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const KUALA_LUMPUR = {
  id: 'stage-1',
  position: 0,
  place: 'Kuala Lumpur',
  start_date: '2026-10-10',
  end_date: '2026-10-12',
}
const PENANG = {
  id: 'stage-2',
  position: 1,
  place: 'Penang',
  start_date: null,
  end_date: null,
}

const TRIP = {
  id: 'trip-1',
  title: 'Malezja, październik 2026',
  start_date: '2026-10-10',
  end_date: '2026-10-13',
  departure_place: 'Warszawa',
  return_place: 'Warszawa',
  readiness: { arranged: 0, tracked: 0 },
  stages: [KUALA_LUMPUR, PENANG],
  days: [
    { id: 'day-1', date: '2026-10-10', stage_ids: ['stage-1'], items: [] },
    { id: 'day-2', date: '2026-10-11', stage_ids: ['stage-1'], items: [] },
    { id: 'day-3', date: '2026-10-12', stage_ids: ['stage-1'], items: [] },
    { id: 'day-4', date: '2026-10-13', stage_ids: [], items: [] },
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

/** A backend that serves `trip` and answers `PATCH /trips/{id}` however asked. */
function backend(trip: unknown = TRIP, onPatch: () => Response = () => json(200, trip)): Handler {
  return (url, init) => {
    // The locale switch persists the owner's choice, and the app applies what
    // comes back — so a stub that always answered `pl` would drag the UI back
    // to Polish the moment anyone switched.
    if (url.endsWith('/auth/me') && init?.method === 'PATCH') {
      const { locale } = JSON.parse(String(init.body)) as { locale: string }
      return json(200, { ...OWNER, locale })
    }
    if (url.endsWith('/auth/me')) return json(200, OWNER)
    if (url.endsWith('/trips') && (init?.method ?? 'GET') === 'GET') return json(200, [trip])
    if (/\/trips\/[^/]+$/u.test(url) && init?.method === 'PATCH') return onPatch()
    if (/\/trips\/[^/]+$/u.test(url)) return json(200, trip)
    return json(404, { error: { code: 'not_found', field: null } })
  }
}

const refusal = (code: string, field: string) =>
  json(409, { error: { code, field } })

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

/**
 * Replace an input's value, deterministically.
 *
 * `user.clear()` followed straight by `user.type()` is a race on a *controlled*
 * input: clear dispatches its event, but if React has not re-rendered with the
 * empty value by the time typing starts, the new text is appended to the old
 * one and the assertion fails somewhere far away with "no element has that
 * value". Waiting for the box to actually be empty is what makes it honest.
 */
async function retype(
  user: ReturnType<typeof userEvent.setup>,
  input: HTMLElement,
  value: string,
) {
  await user.clear(input)
  await waitFor(() => expect(input).toHaveValue(''))
  await user.type(input, value)
}

const patches = () => requests.filter((request) => request.method === 'PATCH')

beforeEach(async () => {
  requests = []
  await useLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('reaching the editor', () => {
  it('is linked from the timeline, beside the delete action', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1')

    const edit = await screen.findByRole('link', { name: 'Edytuj podróż' })
    expect(edit).toHaveAttribute('href', '/trips/trip-1/edit')
    // The destructive action it used to be the only substitute for is still there.
    expect(screen.getByRole('button', { name: 'Usuń podróż' })).toBeInTheDocument()
  })

  it('renders the editor on its own route', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    expect(await screen.findByRole('heading', { name: 'Edytuj podróż' })).toBeInTheDocument()
  })

  it('sends an unauthenticated visitor to the login screen', async () => {
    mockApi((url) => {
      if (url.endsWith('/auth/me')) return json(401, { error: { code: 'not_authenticated' } })
      return json(404, {})
    })

    renderApp('/trips/trip-1/edit')

    expect(await screen.findByRole('heading', { name: 'Zaloguj się' })).toBeInTheDocument()
  })
})

describe('the loaded form', () => {
  it('prefills every field from the trip', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    expect(await screen.findByLabelText('Nazwa podróży')).toHaveValue(TRIP.title)
    expect(screen.getByLabelText('Data rozpoczęcia')).toHaveValue('2026-10-10')
    expect(screen.getByLabelText('Data zakończenia')).toHaveValue('2026-10-13')
    expect(screen.getByLabelText('Wyjazd z')).toHaveValue('Warszawa')
  })

  it('reads a round trip as a round trip and asks for no return place', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    expect(await screen.findByRole('radio', { name: 'W obie strony' })).toBeChecked()
    expect(screen.queryByLabelText('Powrót do')).not.toBeInTheDocument()
  })

  it('reads an open-jaw trip and shows its return place', async () => {
    mockApi(backend({ ...TRIP, return_place: 'Katowice' }))

    renderApp('/trips/trip-1/edit')

    expect(
      await screen.findByRole('radio', { name: 'Inne miasto powrotu (open-jaw)' }),
    ).toBeChecked()
    expect(screen.getByLabelText('Powrót do')).toHaveValue('Katowice')
  })

  it('reads a one-way trip as one way', async () => {
    mockApi(backend({ ...TRIP, return_place: null }))

    renderApp('/trips/trip-1/edit')

    expect(await screen.findByRole('radio', { name: 'W jedną stronę' })).toBeChecked()
  })

  it('shows the trip’s bases, including one whose dates are undecided', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    // Editable cards, so the places are field values rather than text nodes;
    // a base whose dates were never decided has two empty date boxes.
    expect(await screen.findByDisplayValue('Kuala Lumpur')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Penang')).toBeInTheDocument()
    expect(document.querySelector('#stage-start-stage-2')).toHaveValue('')
  })

  it('says the service is unavailable rather than showing an empty form', async () => {
    mockApi((url) => {
      if (url.endsWith('/auth/me')) return json(200, OWNER)
      return json(503, { error: { code: 'service_unavailable', field: null } })
    })

    renderApp('/trips/trip-1/edit')

    expect(await screen.findByRole('alert')).toHaveTextContent('niedostępna')
    expect(screen.queryByLabelText('Nazwa podróży')).not.toBeInTheDocument()
  })
})

describe('saving', () => {
  it('keeps Save disabled until something actually changes, and after an undo', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    const save = await screen.findByRole('button', { name: 'Zapisz zmiany' })
    expect(save).toBeDisabled()

    const title = screen.getByLabelText('Nazwa podróży')
    await user.type(title, '!')
    expect(save).toBeEnabled()

    await user.type(title, '{backspace}')
    expect(save).toBeDisabled()
  })

  it('sends all five trip fields and no stage key', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    await user.type(await screen.findByLabelText('Nazwa podróży'), ' — poprawka')
    await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    await waitFor(() => expect(patches()).toHaveLength(1))
    expect(patches()[0]?.body).toEqual({
      title: `${TRIP.title} — poprawka`,
      start_date: '2026-10-10',
      end_date: '2026-10-13',
      departure_place: 'Warszawa',
      return_place: 'Warszawa',
    })
  })

  it('mirrors an edited departure place into the return place of a round trip', async () => {
    // The server would do this for a partial body; sending it explicitly is what
    // keeps the mode the owner can see and the mode that is saved the same one.
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    await retype(user, await screen.findByLabelText('Wyjazd z'), 'Kraków')
    await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    await waitFor(() => expect(patches()).toHaveLength(1))
    expect(patches()[0]?.body).toMatchObject({
      departure_place: 'Kraków',
      return_place: 'Kraków',
    })
  })

  it('sends a null return place when the trip becomes one way', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    await user.click(await screen.findByRole('radio', { name: 'W jedną stronę' }))
    await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    await waitFor(() => expect(patches()).toHaveLength(1))
    expect(patches()[0]?.body).toMatchObject({ return_place: null })
  })

  it('returns to the timeline once the save lands', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    await user.type(await screen.findByLabelText('Nazwa podróży'), '!')
    await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    // The timeline's own action is the proof we landed on it.
    expect(await screen.findByRole('button', { name: 'Usuń podróż' })).toBeInTheDocument()
  })

  it('refuses to send an end date before the start date', async () => {
    const user = userEvent.setup()
    mockApi(backend())

    renderApp('/trips/trip-1/edit')

    await retype(user, await screen.findByLabelText('Data zakończenia'), '2026-10-01')

    expect(screen.getByRole('button', { name: 'Zapisz zmiany' })).toBeDisabled()
    expect(patches()).toHaveLength(0)
  })
})

describe('the four refusals', () => {
  async function refuse(code: string, field: string) {
    const user = userEvent.setup()
    mockApi(backend(TRIP, () => refusal(code, field)))

    renderApp('/trips/trip-1/edit')

    await retype(user, await screen.findByLabelText('Data zakończenia'), '2026-10-11')
    await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    return await screen.findByText(/Te dni|Pozycje|Te cele/u)
  }

  it('names the days that still carry items', async () => {
    const alert = await refuse('days_have_items', '2026-10-12,2026-10-13')

    expect(alert).toHaveTextContent('12 października 2026')
    expect(alert).toHaveTextContent('13 października 2026')
  })

  it('names the days that still carry attachments', async () => {
    const alert = await refuse('days_have_attachments', '2026-10-13')

    expect(alert).toHaveTextContent('13 października 2026')
    expect(alert).toHaveTextContent('załączniki')
  })

  it('names the start days of items that would reach past the new end', async () => {
    const alert = await refuse('items_outside_new_range', '2026-10-10')

    expect(alert).toHaveTextContent('10 października 2026')
  })

  it('names the destinations that fall outside the new dates', async () => {
    const alert = await refuse('stages_outside_new_range', 'Kuala Lumpur')

    expect(alert).toHaveTextContent('Kuala Lumpur')
  })

  it('moves focus to the refusal, so it is not missed at the foot of the form', async () => {
    const alert = await refuse('days_have_items', '2026-10-13')

    await waitFor(() => expect(alert).toHaveFocus())
  })

  it('keeps every typed value, so the edit is corrected rather than retyped', async () => {
    await refuse('days_have_items', '2026-10-13')

    expect(screen.getByLabelText('Data zakończenia')).toHaveValue('2026-10-11')
    expect(screen.getByLabelText('Nazwa podróży')).toHaveValue(TRIP.title)
    // And it stays on the editor rather than navigating away from a failure.
    expect(screen.getByRole('heading', { name: 'Edytuj podróż' })).toBeInTheDocument()
  })

  it('does not throw away the edit when the owner switches language', async () => {
    // QA finding: the load effect depended on `t`, whose identity changes with
    // the language — so switching the locale re-fetched the trip and re-seeded
    // the form, wiping everything typed into it.
    const user = userEvent.setup()
    await refuse('days_have_items', '2026-10-13')

    expect(screen.getByLabelText('Data zakończenia')).toHaveValue('2026-10-11')

    await user.selectOptions(screen.getByRole('combobox'), 'en')

    expect(await screen.findByLabelText('End date')).toHaveValue('2026-10-11')
  })

  it('re-renders the refusal in the language the owner switches to', async () => {
    // QA finding: the message used to be formatted once and stored, so it
    // stayed Polish on an otherwise English page. The error is the fact; the
    // sentence is a rendering of it.
    const user = userEvent.setup()
    await refuse('days_have_items', '2026-10-13')

    await user.selectOptions(screen.getByRole('combobox'), 'en')

    const alert = await screen.findByText(/These days already have items/u)
    expect(alert).toHaveTextContent('October 13, 2026')
    expect(alert).not.toHaveTextContent('października')
  })

  it('marks the date fields when the refusal is about the dates', async () => {
    await refuse('days_have_items', '2026-10-13')

    expect(screen.getByLabelText('Data rozpoczęcia')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Data zakończenia')).toHaveAttribute('aria-invalid', 'true')
  })

  it('leaves the date fields unmarked when the refusal is about a destination', async () => {
    // The dates are fine; it is a base that falls outside them, so marking the
    // date boxes would point the owner at the wrong control.
    await refuse('stages_outside_new_range', 'Kuala Lumpur')

    expect(screen.getByLabelText('Data zakończenia')).not.toHaveAttribute('aria-invalid')
  })

  it('lets the owner try again after correcting the conflict', async () => {
    const user = userEvent.setup()
    let attempt = 0
    mockApi(
      backend(TRIP, () => {
        attempt += 1
        return attempt === 1 ? refusal('days_have_items', '2026-10-13') : json(200, TRIP)
      }),
    )

    renderApp('/trips/trip-1/edit')

    const endDate = await screen.findByLabelText('Data zakończenia')
    await retype(user, endDate, '2026-10-11')
    await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('13 października 2026')

    // The same button, still enabled: the refusal is a correctable state, not a
    // dead end that needs a reload.
    await user.click(screen.getByRole('button', { name: 'Zapisz zmiany' }))
    expect(await screen.findByRole('button', { name: 'Usuń podróż' })).toBeInTheDocument()
    expect(patches()).toHaveLength(2)
  })
})
