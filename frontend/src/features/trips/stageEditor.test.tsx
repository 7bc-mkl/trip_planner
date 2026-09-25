import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import { applyLocale, initI18n } from '../../i18n'
import { SessionProvider } from '../auth/SessionContext'

/**
 * Adding, editing and removing a trip's bases, on `/trips/:id/edit`.
 *
 * The behaviours worth guarding are the ones that come from the shape of the
 * API rather than from the form: each card is its own request, every success
 * refetches the trip because `position` and the day→stage derivation are the
 * server's, the last base cannot be removed (R03), and the two save paths lock
 * each other out so neither can land against state the other is replacing.
 */

const OWNER = { id: 'owner-1', email: 'owner@example.com', locale: 'pl' as const }

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

type Stage = {
  id: string
  position: number
  place: string
  start_date: string | null
  end_date: string | null
}

const KUALA_LUMPUR: Stage = {
  id: 'stage-1',
  position: 0,
  place: 'Kuala Lumpur',
  start_date: '2026-10-10',
  end_date: '2026-10-12',
}
const PENANG: Stage = {
  id: 'stage-2',
  position: 1,
  place: 'Penang',
  start_date: null,
  end_date: null,
}

const tripWith = (stages: Stage[]) => ({
  id: 'trip-1',
  title: 'Malezja, październik 2026',
  start_date: '2026-10-10',
  end_date: '2026-10-13',
  departure_place: 'Warszawa',
  return_place: 'Warszawa',
  readiness: { arranged: 0, tracked: 0 },
  stages,
  days: [
    { id: 'day-1', date: '2026-10-10', stage_ids: [], items: [] },
    { id: 'day-2', date: '2026-10-11', stage_ids: [], items: [] },
    { id: 'day-3', date: '2026-10-12', stage_ids: [], items: [] },
    { id: 'day-4', date: '2026-10-13', stage_ids: [], items: [] },
  ],
})

let requests: { url: string; method: string; body: unknown }[] = []

type Overrides = {
  onCreate?: () => Response
  onPatch?: () => Response
  onDelete?: () => Response
}

/**
 * A stateful backend: stage writes really mutate the list the next `GET`
 * serves, so "the card disappeared after the refetch" is a fact rather than a
 * mock's opinion.
 */
function backend(initial: Stage[] = [KUALA_LUMPUR, PENANG], overrides: Overrides = {}) {
  let stages = [...initial]

  const handler = (url: string, init?: RequestInit): Response => {
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    requests.push({ url, method, body })

    if (url.endsWith('/auth/me')) return json(200, OWNER)

    if (url.endsWith('/stages') && method === 'POST') {
      if (overrides.onCreate) return overrides.onCreate()
      const created: Stage = {
        id: `stage-${stages.length + 1}`,
        position: stages.length,
        place: body.place,
        start_date: body.start_date,
        end_date: body.end_date,
      }
      stages = [...stages, created]
      return json(201, created)
    }

    if (/\/stages\/[^/]+$/u.test(url) && method === 'PATCH') {
      if (overrides.onPatch) return overrides.onPatch()
      stages = stages.map((stage) =>
        url.endsWith(stage.id) ? { ...stage, ...body } : stage,
      )
      return json(200, stages.find((stage) => url.endsWith(stage.id)))
    }

    if (/\/stages\/[^/]+$/u.test(url) && method === 'DELETE') {
      if (overrides.onDelete) return overrides.onDelete()
      stages = stages
        .filter((stage) => !url.endsWith(stage.id))
        .map((stage, position) => ({ ...stage, position }))
      return new Response(null, { status: 204 })
    }

    if (/\/trips\/[^/]+$/u.test(url)) return json(200, tripWith(stages))
    if (url.endsWith('/trips')) return json(200, [tripWith(stages)])
    return json(404, { error: { code: 'not_found', field: null } })
  }

  return { handler, stagesNow: () => stages }
}

function mount(api: { handler: (url: string, init?: RequestInit) => Response }) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
      Promise.resolve(api.handler(String(input), init)),
    ),
  )

  return render(
    <MemoryRouter initialEntries={['/trips/trip-1/edit']}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  )
}

/** The card holding a given place field value. */
function cardFor(place: string): HTMLElement {
  const input = screen.getByDisplayValue(place)
  const card = input.closest('.stage-card')
  if (card === null) throw new Error(`no stage card for ${place}`)
  return card as HTMLElement
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

/**
 * A field inside a stage card, by id, once it is really there.
 *
 * By id rather than by label or value because several cards share the labels
 * "Od" and "Do", and a stage date can coincide with the trip's own. Through
 * `waitFor` because a card only appears after the refetch that follows a save:
 * a bare `querySelector` returns `null` and the failure lands on whatever is
 * read off it next, saying nothing about the wait that was missing.
 */
async function field(id: string): Promise<HTMLInputElement> {
  return await waitFor(() => {
    const input = document.querySelector<HTMLInputElement>(`#${id}`)
    if (input === null) throw new Error(`no field ${id} yet`)
    return input
  })
}

const stageWrites = () =>
  requests.filter((one) => one.url.includes('/stages') && one.method !== 'GET')

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

describe('editing a base', () => {
  it('sends only what changed and leaves an untouched date alone', async () => {
    const user = userEvent.setup()
    mount(backend())

    const place = await screen.findByDisplayValue('Kuala Lumpur')
    await retype(user, place, 'Johor Bahru')
    await user.click(within(cardFor('Johor Bahru')).getByRole('button', { name: 'Zapisz cel' }))

    await waitFor(() => expect(stageWrites()).toHaveLength(1))
    const [write] = stageWrites()
    expect(write?.method).toBe('PATCH')
    expect(write?.url).toContain('/stages/stage-1')
    // The two dates were not touched, so they are absent rather than echoed —
    // omission is what says "leave this as it is".
    expect(write?.body).toEqual({ place: 'Johor Bahru' })
  })

  it('clears a date to null rather than sending an empty string', async () => {
    const user = userEvent.setup()
    mount(backend())

    await screen.findByDisplayValue('Kuala Lumpur')
    await user.clear(await field('stage-end-stage-1'))

    // Assert the button is live before clicking it: a click on a disabled
    // button is a silent no-op, and the failure it produces three lines later
    // ("no request was sent") says nothing about why.
    const save = within(cardFor('Kuala Lumpur')).getByRole('button', { name: 'Zapisz cel' })
    await waitFor(() => expect(save).toBeEnabled())
    await user.click(save)

    await waitFor(() => expect(stageWrites()).toHaveLength(1))
    expect(stageWrites()[0]?.body).toEqual({ end_date: null })
  })

  it('refetches the trip so the derived list is the server’s, not a local guess', async () => {
    const user = userEvent.setup()
    mount(backend())

    const before = requests.filter((one) => one.method === 'GET').length

    const place = await screen.findByDisplayValue('Penang')
    await retype(user, place, 'Langkawi')
    await user.click(within(cardFor('Langkawi')).getByRole('button', { name: 'Zapisz cel' }))

    await waitFor(() =>
      expect(requests.filter((one) => one.method === 'GET').length).toBeGreaterThan(before),
    )
  })

  it('keeps Save off until the card differs from the server', async () => {
    const user = userEvent.setup()
    mount(backend())

    await screen.findByDisplayValue('Kuala Lumpur')
    const save = within(cardFor('Kuala Lumpur')).getByRole('button', { name: 'Zapisz cel' })
    expect(save).toBeDisabled()

    await user.type(screen.getByDisplayValue('Kuala Lumpur'), '!')
    expect(within(cardFor('Kuala Lumpur!')).getByRole('button', { name: 'Zapisz cel' })).toBeEnabled()
  })

  it('refuses a base whose dates fall outside the trip, before sending anything', async () => {
    const user = userEvent.setup()
    mount(backend())

    await screen.findByDisplayValue('Kuala Lumpur')
    // By id, not by value: the trip's own start date is the same day.
    await retype(user, await field('stage-start-stage-1'), '2026-09-01')

    const card = cardFor('Kuala Lumpur')
    expect(within(card).getByRole('alert')).toHaveTextContent('poza')
    expect(within(card).getByRole('button', { name: 'Zapisz cel' })).toBeDisabled()
    expect(stageWrites()).toHaveLength(0)
  })

  it('reports a refused save on the card that caused it, and only there', async () => {
    const user = userEvent.setup()
    mount(
      backend([KUALA_LUMPUR, PENANG], {
        onPatch: () => json(409, { error: { code: 'stage_outside_trip', field: 'Penang' } }),
      }),
    )

    const place = await screen.findByDisplayValue('Penang')
    await retype(user, place, 'Perhentian')
    await user.click(within(cardFor('Perhentian')).getByRole('button', { name: 'Zapisz cel' }))

    await waitFor(() =>
      expect(within(cardFor('Perhentian')).getByRole('alert')).toBeInTheDocument(),
    )
    expect(within(cardFor('Kuala Lumpur')).queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('what the refetch after a save may not throw away', () => {
  it('keeps unsaved edits in the other cards', async () => {
    // Review finding: every stage write refetches the trip, and the rebuild
    // used to replace every card with the server's copy — so typing into one
    // base and then saving a different one silently reverted the first.
    const user = userEvent.setup()
    const api = backend()
    mount(api)

    await retype(user, await screen.findByDisplayValue('Kuala Lumpur'), 'Johor Bahru')

    // Save the *other* card, which triggers the refetch.
    await retype(user, screen.getByDisplayValue('Penang'), 'Langkawi')
    await user.click(within(cardFor('Langkawi')).getByRole('button', { name: 'Zapisz cel' }))

    // Wait for the rebuild to have actually happened — asserting before it
    // lands would pass whether or not the bug is fixed.
    await waitFor(() => expect(api.stagesNow()[1]?.place).toBe('Langkawi'))
    await waitFor(() => expect(screen.getAllByDisplayValue('Langkawi')).toHaveLength(1))

    // The untouched-on-the-server card still holds what was typed into it.
    expect(screen.getByDisplayValue('Johor Bahru')).toBeInTheDocument()
  })

  it('does take the server’s value when that base really changed', async () => {
    // The other side of the same rule: a stale local copy must not win over a
    // value the server has since changed.
    const user = userEvent.setup()
    const api = backend()
    mount(api)

    await retype(user, await screen.findByDisplayValue('Penang'), 'Langkawi')
    await user.click(within(cardFor('Langkawi')).getByRole('button', { name: 'Zapisz cel' }))

    await waitFor(() => expect(api.stagesNow()[1]?.place).toBe('Langkawi'))
    // One card showing the saved value, not two showing two versions of it.
    await waitFor(() => expect(screen.getAllByDisplayValue('Langkawi')).toHaveLength(1))
    expect(screen.queryByDisplayValue('Penang')).not.toBeInTheDocument()
  })
})

describe('adding a base', () => {
  it('appends a blank card that sends a POST once it has a place', async () => {
    const user = userEvent.setup()
    const api = backend()
    mount(api)

    await user.click(await screen.findByRole('button', { name: 'Dodaj cel' }))

    const blank = screen.getByLabelText('Cel 3')
    await user.type(blank, 'Langkawi')
    await user.type(screen.getByLabelText(/^Od$/u, { selector: `#stage-start-new-1` }), '2026-10-12')
    await user.click(within(cardFor('Langkawi')).getByRole('button', { name: 'Zapisz cel' }))

    await waitFor(() => expect(stageWrites()).toHaveLength(1))
    expect(stageWrites()[0]?.method).toBe('POST')
    expect(stageWrites()[0]?.body).toEqual({
      place: 'Langkawi',
      start_date: '2026-10-12',
      end_date: null,
    })
    // And it comes back from the refetch exactly once, not twice.
    await waitFor(() => expect(screen.getAllByDisplayValue('Langkawi')).toHaveLength(1))
    expect(api.stagesNow()).toHaveLength(3)
  })

  it('sends nothing for a blank card that was never saved', async () => {
    const user = userEvent.setup()
    mount(backend())

    await user.click(await screen.findByRole('button', { name: 'Dodaj cel' }))

    expect(
      within(cardFor('Kuala Lumpur')).getByRole('button', { name: 'Zapisz cel' }),
    ).toBeDisabled()
    expect(stageWrites()).toHaveLength(0)
  })
})

describe('removing a base', () => {
  it('names the base in a confirmation before deleting it', async () => {
    const user = userEvent.setup()
    const api = backend()
    mount(api)

    await screen.findByDisplayValue('Penang')
    await user.click(within(cardFor('Penang')).getByRole('button', { name: 'Usuń' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Penang')

    await user.click(within(dialog).getByRole('button', { name: 'Usuń' }))

    await waitFor(() => expect(api.stagesNow()).toHaveLength(1))
    expect(screen.queryByDisplayValue('Penang')).not.toBeInTheDocument()
  })

  it('sends nothing when the confirmation is cancelled', async () => {
    const user = userEvent.setup()
    mount(backend())

    await screen.findByDisplayValue('Penang')
    await user.click(within(cardFor('Penang')).getByRole('button', { name: 'Usuń' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Anuluj' }))

    expect(stageWrites()).toHaveLength(0)
    expect(screen.getByDisplayValue('Penang')).toBeInTheDocument()
  })

  it('will not let the last base go — the rule is explained, not refused', async () => {
    mount(backend([KUALA_LUMPUR]))

    await screen.findByDisplayValue('Kuala Lumpur')
    expect(within(cardFor('Kuala Lumpur')).getByRole('button', { name: 'Usuń' })).toBeDisabled()
  })

  it('reports a refused delete inside the dialog, where the retry is', async () => {
    const user = userEvent.setup()
    mount(
      backend([KUALA_LUMPUR, PENANG], {
        onDelete: () => json(409, { error: { code: 'stages_required', field: 'stage_id' } }),
      }),
    )

    await screen.findByDisplayValue('Penang')
    await user.click(within(cardFor('Penang')).getByRole('button', { name: 'Usuń' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Usuń' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('co najmniej jeden cel')
    expect(screen.getByDisplayValue('Penang')).toBeInTheDocument()
  })
})

describe('the whole base-management walk', () => {
  it(
    'adds a base, edits its dates, removes it — and the timeline reflects each step',
    { timeout: 20_000 },
    async () => {
      const user = userEvent.setup()
      const api = backend([KUALA_LUMPUR])
      mount(api)

      // ── Add ────────────────────────────────────────────────────────────────
      await user.click(await screen.findByRole('button', { name: 'Dodaj cel' }))
      await user.type(screen.getByLabelText('Cel 2'), 'Penang')
      await user.click(within(cardFor('Penang')).getByRole('button', { name: 'Zapisz cel' }))
      await waitFor(() => expect(api.stagesNow()).toHaveLength(2))

      // ── Edit its dates ─────────────────────────────────────────────────────
      const added = api.stagesNow()[1]
      await user.type(await field(`stage-start-${added?.id}`), '2026-10-12')
      await user.click(within(cardFor('Penang')).getByRole('button', { name: 'Zapisz cel' }))
      await waitFor(() => expect(api.stagesNow()[1]?.start_date).toBe('2026-10-12'))

      // The dock's live count follows: two bases now, not one.
      expect(screen.getByRole('status')).toHaveTextContent('2 bazy')

      // ── Remove ─────────────────────────────────────────────────────────────
      await user.click(within(cardFor('Penang')).getByRole('button', { name: 'Usuń' }))
      await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Usuń' }))

      await waitFor(() => expect(api.stagesNow()).toHaveLength(1))
      // Waited on the *screen*, not just the fake backend: the backend drops
      // the row during the DELETE, while the card only goes when the refetch
      // that follows has landed and been reconciled.
      await waitFor(() => expect(screen.queryByDisplayValue('Penang')).not.toBeInTheDocument())
      // Back to one base, which can no longer be removed.
      expect(within(cardFor('Kuala Lumpur')).getByRole('button', { name: 'Usuń' })).toBeDisabled()
    },
  )
})

describe('the two saves lock each other out', () => {
  it('disables the trip’s Save while a stage request is in flight', async () => {
    const user = userEvent.setup()
    let release: (() => void) | undefined
    const api = backend()
    const held = new Promise<void>((resolve) => {
      release = resolve
    })

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/stages') && (init?.method ?? 'GET') !== 'GET') {
          await held
        }
        return api.handler(url, init)
      }),
    )

    render(
      <MemoryRouter initialEntries={['/trips/trip-1/edit']}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </MemoryRouter>,
    )

    // Make the trip dirty first, so Save would otherwise be enabled.
    await user.type(await screen.findByLabelText('Nazwa podróży'), '!')
    expect(screen.getByRole('button', { name: 'Zapisz zmiany' })).toBeEnabled()

    const place = screen.getByDisplayValue('Kuala Lumpur')
    await retype(user, place, 'Johor')
    await user.click(within(cardFor('Johor')).getByRole('button', { name: 'Zapisz cel' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Zapisz zmiany' })).toBeDisabled(),
    )

    release?.()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Zapisz zmiany' })).toBeEnabled(),
    )
  })
})
