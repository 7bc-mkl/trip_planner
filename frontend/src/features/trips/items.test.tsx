import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../../App'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { ITEM_STATUSES } from '../../api/items'
import { applyLocale, initI18n } from '../../i18n'
import { clearAllDrafts, readDraft } from '../auth/draftStore'
import { SessionProvider } from '../auth/SessionContext'
import { ItemRow } from './ItemRow'
import { StatusChip } from './StatusChip'
import { draftKey } from './itemDraft'
import type { ItemDraft } from './itemDraft'

/**
 * Phase 3: the day-detail screen, the item editor, the status chips and the
 * readiness counter.
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
}

const HOTEL = {
  id: 'item-2',
  position: 1,
  kind: 'accommodation' as const,
  status: 'done' as const,
  start_time: null,
  end_time: null,
  end_date: '2026-10-13',
  title: 'Nocleg: Memmo Alfama',
  notes: null,
}

const DAY = {
  id: 'day-1',
  trip_id: 'trip-1',
  date: '2026-10-11',
  stages: [STAGE],
  items: [MUSEUM, HOTEL],
  previous_date: '2026-10-10',
  next_date: '2026-10-12',
}

const TRIP = {
  id: 'trip-1',
  title: 'Malezja, październik 2026',
  start_date: '2026-10-10',
  end_date: '2026-10-13',
  departure_place: 'Warszawa',
  return_place: 'Katowice',
  readiness: { arranged: 1, tracked: 2 },
  stages: [STAGE],
  days: [
    { id: 'day-0', date: '2026-10-10', stage_ids: ['stage-1'], items: [] },
    { id: 'day-1', date: '2026-10-11', stage_ids: ['stage-1'], items: [MUSEUM, HOTEL] },
    { id: 'day-2', date: '2026-10-12', stage_ids: ['stage-1'], items: [] },
    { id: 'day-3', date: '2026-10-13', stage_ids: ['stage-1'], items: [] },
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

function backend(overrides: { day?: unknown; trip?: unknown; owner?: unknown } = {}): Handler {
  return (url, init) => {
    const method = (init?.method ?? 'GET').toUpperCase()
    if (url.endsWith('/auth/me')) return json(200, overrides.owner ?? OWNER)
    if (url.endsWith('/trips') && method === 'GET') return json(200, [overrides.trip ?? TRIP])
    if (url.includes('/days/') && url.endsWith('/items') && method === 'POST') {
      return json(201, { ...MUSEUM, id: 'item-new' })
    }
    if (url.includes('/items/') && method === 'PATCH') return json(200, MUSEUM)
    if (url.includes('/items/') && method === 'DELETE') return new Response(null, { status: 204 })
    if (url.includes('/days/')) return json(200, overrides.day ?? DAY)
    if (/\/trips\/[^/]+$/u.test(url)) return json(200, overrides.trip ?? TRIP)
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

const DAY_PATH = '/trips/trip-1/days/2026-10-11'

beforeEach(async () => {
  requests = []
  clearAllDrafts()
  initI18n('pl')
  await applyLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the day detail', () => {
  it('lists the day’s items in the order the server sent them', async () => {
    mockApi(backend())

    renderApp(DAY_PATH)

    await screen.findByText('Batu Caves')
    const titles = screen.getAllByRole('listitem').map((row) => row.textContent)

    expect(titles[0]).toContain('Batu Caves')
    expect(titles[1]).toContain('Nocleg: Memmo Alfama')
  })

  it('shows the day’s derived stage', async () => {
    mockApi(backend())

    renderApp(DAY_PATH)

    expect(await screen.findByText('Kuala Lumpur')).toBeInTheDocument()
  })

  it('renders a time range, a bare start, and "all day"', async () => {
    mockApi(backend())

    renderApp(DAY_PATH)

    // A range for the museum, "all day" for the hotel, which has no times.
    expect(await screen.findByText('10:30–12:00')).toBeInTheDocument()
    expect(screen.getByText('Cały dzień')).toBeInTheDocument()
  })

  it('marks an item that spans into a later day', async () => {
    mockApi(backend())

    renderApp(DAY_PATH)

    expect(await screen.findByText('→ 13.10')).toBeInTheDocument()
  })

  it('navigates to the previous and next day', async () => {
    mockApi(backend())

    renderApp(DAY_PATH)

    expect(await screen.findByRole('link', { name: 'Poprzedni dzień' })).toHaveAttribute(
      'href',
      '/trips/trip-1/days/2026-10-10',
    )
    expect(screen.getByRole('link', { name: 'Następny dzień' })).toHaveAttribute(
      'href',
      '/trips/trip-1/days/2026-10-12',
    )
  })

  it('disables the navigator at the trip’s boundaries rather than hiding it', async () => {
    mockApi(backend({ day: { ...DAY, previous_date: null, next_date: null } }))

    renderApp(DAY_PATH)

    await screen.findByText('Batu Caves')

    expect(screen.queryByRole('link', { name: 'Poprzedni dzień' })).not.toBeInTheDocument()
    expect(screen.getByText('Poprzedni dzień')).toBeInTheDocument()
  })

  it('invites the first item on an empty day', async () => {
    mockApi(backend({ day: { ...DAY, items: [] } }))

    renderApp(DAY_PATH)

    expect(
      await screen.findByText('Nic jeszcze nie zaplanowano na ten dzień. Dodaj pierwszy element.'),
    ).toBeInTheDocument()
  })
})

describe('the item editor', () => {
  async function openNewItem() {
    const user = userEvent.setup()
    mockApi(backend())
    renderApp(DAY_PATH)
    await screen.findByText('Batu Caves')
    await user.click(screen.getByRole('button', { name: 'Dodaj element' }))
    return user
  }

  it('creates an item', async () => {
    const user = await openNewItem()

    await user.type(screen.getByLabelText('Nazwa'), 'Kolacja')
    await user.selectOptions(screen.getByLabelText('Typ'), 'meal')
    await user.type(screen.getByLabelText('Godzina rozpoczęcia'), '19:00')
    await user.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => expect(posted()).not.toBeUndefined())
    expect(posted()).toMatchObject({
      kind: 'meal',
      title: 'Kolacja',
      start_time: '19:00',
      status: 'to_plan',
    })
  })

  it('sends null for an empty time rather than an empty string', async () => {
    const user = await openNewItem()

    await user.type(screen.getByLabelText('Nazwa'), 'Kiedyś tego dnia')
    await user.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => expect(posted()).not.toBeUndefined())
    expect(posted()).toMatchObject({ start_time: null, end_time: null, end_date: null })
  })

  it('edits an existing item, pre-filled with its values', async () => {
    const user = userEvent.setup()
    mockApi(backend())
    renderApp(DAY_PATH)

    await user.click(await screen.findByRole('button', { name: /Batu Caves/u }))

    expect(screen.getByLabelText('Nazwa')).toHaveValue('Batu Caves')
    expect(screen.getByLabelText('Godzina rozpoczęcia')).toHaveValue('10:30')

    await user.selectOptions(screen.getByLabelText('Status'), 'done')
    await user.click(screen.getByRole('button', { name: 'Zapisz' }))

    await waitFor(() => expect(patched()).not.toBeUndefined())
    expect(patched()).toMatchObject({ status: 'done' })
  })

  it('deletes an item', async () => {
    const user = userEvent.setup()
    mockApi(backend())
    renderApp(DAY_PATH)

    await user.click(await screen.findByRole('button', { name: /Batu Caves/u }))
    await user.click(screen.getByRole('button', { name: 'Usuń' }))

    await waitFor(() =>
      expect(
        requests.some((entry) => entry.method === 'DELETE' && entry.url.includes('/items/item-1')),
      ).toBe(true),
    )
  })

  it('returns focus to the trigger when it closes', async () => {
    const user = userEvent.setup()
    mockApi(backend())
    renderApp(DAY_PATH)

    const trigger = await screen.findByRole('button', { name: /Batu Caves/u })
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: 'Anuluj' }))

    // Without this, focus falls back to <body> and a keyboard user is dropped at
    // the top of the page every time they close the editor.
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('moves focus into the dialog when it opens', async () => {
    const user = await openNewItem()

    await waitFor(() =>
      expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true),
    )
    expect(user).toBeDefined()
  })

  it('closes on Escape', async () => {
    const user = await openNewItem()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps the primary action disabled until the item has a title', async () => {
    const user = await openNewItem()

    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeDisabled()

    await user.type(screen.getByLabelText('Nazwa'), 'Kolacja')

    expect(screen.getByRole('button', { name: 'Zapisz' })).toBeEnabled()
  })

  it('discards the draft when the edit is cancelled', async () => {
    const user = userEvent.setup()
    mockApi(backend())
    renderApp(DAY_PATH)

    await user.click(await screen.findByRole('button', { name: /Batu Caves/u }))
    await user.clear(screen.getByLabelText('Nazwa'))
    await user.type(screen.getByLabelText('Nazwa'), 'coś zupełnie innego')
    await user.click(screen.getByRole('button', { name: 'Anuluj' }))

    // Checked here, while the dialog is closed: reopening legitimately re-seeds
    // the store from the saved item, so afterwards it is non-empty again.
    expect(readDraft<ItemDraft>(draftKey('item-1'))).toBeUndefined()

    // And the visible consequence: reopening shows the saved item, not the edit
    // the owner threw away.
    await user.click(screen.getByRole('button', { name: /Batu Caves/u }))

    expect(screen.getByLabelText('Nazwa')).toHaveValue('Batu Caves')
  })

  it('discards the draft on Escape too', async () => {
    const user = await openNewItem()

    await user.type(screen.getByLabelText('Nazwa'), 'porzucone')
    await user.keyboard('{Escape}')

    expect(readDraft<ItemDraft>(draftKey(null))).toBeUndefined()
  })

  it('keeps the draft when the session expires mid-edit', async () => {
    const user = userEvent.setup()
    mockApi((url, init) => {
      if (url.endsWith('/auth/me')) return json(200, OWNER)
      if (url.includes('/items') && (init?.method ?? 'GET') !== 'GET') {
        return json(401, { error: { code: 'not_authenticated', field: null } })
      }
      return backend()(url, init)
    })

    renderApp(DAY_PATH)
    await screen.findByText('Batu Caves')
    await user.click(screen.getByRole('button', { name: 'Dodaj element' }))
    await user.type(screen.getByLabelText('Nazwa'), 'Nocleg: Memmo Alfama')
    await user.click(screen.getByRole('button', { name: 'Zapisz' }))

    // The router has taken the owner to /login and unmounted the dialog. The
    // draft is what makes coming back not mean retyping.
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Zaloguj się' })).toBeInTheDocument(),
    )
    expect(readDraft<ItemDraft>(draftKey(null))?.title).toBe('Nocleg: Memmo Alfama')
  })
})

describe('status chips', () => {
  it('render a translated text node, not only a colour', async () => {
    mockApi(backend())

    renderApp(DAY_PATH)

    // Both chips: the museum is to_plan, the hotel is done.
    expect(await screen.findByText('Do zaplanowania')).toBeInTheDocument()
    expect(screen.getByText('Gotowe')).toBeInTheDocument()
  })

  it('carry a data-status attribute so the status is assertable and iconifiable', async () => {
    mockApi(backend())

    renderApp(DAY_PATH)

    const chip = (await screen.findByText('Gotowe')).closest('.status-chip')

    expect(chip).toHaveAttribute('data-status', 'done')
  })

  it('translate into English too', async () => {
    mockApi(backend({ owner: { ...OWNER, locale: 'en' } }))

    renderApp(DAY_PATH)

    expect(await screen.findByText('To plan')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
  })

  it.each(ITEM_STATUSES)(
    'exposes both a glyph and the translated label for %s — the colour-blind contract',
    (status) => {
      // The design adds a 6px dot to each chip. A dot is paint, and paint is
      // exactly what a colour-blind reader, a screen reader and a stylesheet
      // failure all lose. So the assertion is that the two things that survive
      // all three are still there and still distinct: a glyph that differs per
      // status, and the status as a translated word.
      //
      // jsdom cannot see colour, and that is the point — this is a test about
      // text nodes and attributes, which is all the contract has ever been.
      render(<StatusChip status={status} />)

      const chip = screen.getByText(pl.item.status[status]).closest('.status-chip')

      expect(chip).toHaveAttribute('data-status', status)

      const glyph = chip?.querySelector('.status-chip__glyph')
      expect(glyph?.textContent?.trim()).toBeTruthy()
      expect(glyph).toHaveAttribute('aria-hidden', 'true')

      // The dot is decoration: hidden from assistive technology, and carrying
      // no text of its own, so it can neither replace nor displace the glyph.
      const dot = chip?.querySelector('.status-chip__dot')
      expect(dot).toHaveAttribute('aria-hidden', 'true')
      expect(dot?.textContent).toBe('')
    },
  )

  it('gives every status a distinct glyph, so the shapes alone tell them apart', () => {
    const glyphs = ITEM_STATUSES.map((status) => {
      const { container } = render(<StatusChip status={status} />)
      return container.querySelector('.status-chip__glyph')?.textContent
    })

    expect(new Set(glyphs).size).toBe(ITEM_STATUSES.length)
  })

  it.each(ITEM_STATUSES)('has a non-empty label in both locales for %s', (status) => {
    // The check `scripts/check_locales.py` structurally cannot make: it compares
    // the two files with each other, not against the statuses the code renders.
    expect(en.item.status[status]).toBeTruthy()
    expect(pl.item.status[status]).toBeTruthy()
  })
})

describe('the readiness counter', () => {
  it('shows the fraction on the timeline', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1')

    expect(await screen.findByText('1 z 2 załatwionych')).toBeInTheDocument()
  })

  it('shows the zero state instead of a fraction when nothing is tracked', async () => {
    mockApi(backend({ trip: { ...TRIP, readiness: { arranged: 0, tracked: 0 } } }))

    renderApp('/trips/trip-1')

    expect(await screen.findByText('Nic jeszcze nie załatwione')).toBeInTheDocument()
    expect(screen.queryByText(/z 0/u)).not.toBeInTheDocument()
  })

  it('shows the zero state for ten items that are all still to plan', async () => {
    // The case that proves the denominator is `tracked` and not the item count.
    const items = Array.from({ length: 10 }, (_, index) => ({
      ...MUSEUM,
      id: `item-${index}`,
      status: 'to_plan' as const,
    }))
    mockApi(
      backend({
        trip: {
          ...TRIP,
          readiness: { arranged: 0, tracked: 0 },
          days: [{ id: 'day-1', date: '2026-10-11', stage_ids: [], items }],
        },
      }),
    )

    renderApp('/trips/trip-1')

    expect(await screen.findByText('Nic jeszcze nie załatwione')).toBeInTheDocument()
  })

  it('shows the zero state in English', async () => {
    mockApi(
      backend({
        owner: { ...OWNER, locale: 'en' },
        trip: { ...TRIP, readiness: { arranged: 0, tracked: 0 } },
      }),
    )

    renderApp('/trips/trip-1')

    expect(await screen.findByText('Nothing arranged yet')).toBeInTheDocument()
  })

  it('renders no progress bar and no percentage in either state', async () => {
    mockApi(backend())

    const { container } = renderApp('/trips/trip-1')
    await screen.findByText('1 z 2 załatwionych')

    expect(container.querySelector('progress')).toBeNull()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText(/%/u)).not.toBeInTheDocument()
  })

  it('appears on the trip list row as well', async () => {
    mockApi(backend())

    renderApp('/trips')

    expect(await screen.findByText('1 z 2 załatwionych')).toBeInTheDocument()
  })

  /**
   * The R02 regression guard for the readiness ring (spec step 19).
   *
   * The ring is the one thing on this tile that could quietly re-introduce the
   * failure the zero state exists to prevent: a disc drawn at a zero
   * denominator is a 0% reading of an undefined percentage, and it says "you
   * are failing" where the truth is "you have not decided anything yet".
   */
  it('draws the ring above a zero denominator, beside the untouched text', async () => {
    mockApi(backend())

    const { container } = renderApp('/trips/trip-1')
    await screen.findByText('1 z 2 załatwionych')

    const ring = container.querySelector('.readiness__ring')

    expect(ring).not.toBeNull()
    // Decoration only: no text node, and hidden from the accessibility tree.
    expect(ring).toHaveAttribute('aria-hidden', 'true')
    expect(ring?.textContent).toBe('')
  })

  it('renders no ring and no percentage at a zero denominator', async () => {
    mockApi(backend({ trip: { ...TRIP, readiness: { arranged: 0, tracked: 0 } } }))

    const { container } = renderApp('/trips/trip-1')
    await screen.findByText('Nic jeszcze nie załatwione')

    expect(container.querySelector('.readiness__ring')).toBeNull()
    expect(screen.queryByText(/%/u)).not.toBeInTheDocument()

    // The state hook and the text node are exactly what they were before the
    // ring existed — the tile still says it in words, and says only that.
    const tile = container.querySelector('.readiness[data-nothing-tracked="true"]')
    expect(tile?.querySelector('.readiness__value')?.textContent).toBe('Nic jeszcze nie załatwione')
  })

  it('keeps the compact list row ringless — only the banner asks for one', async () => {
    mockApi(backend())

    const { container } = renderApp('/trips')
    await screen.findByText('1 z 2 załatwionych')

    expect(container.querySelector('.readiness__ring')).toBeNull()
  })
})

describe('items on the timeline', () => {
  it('renders each day’s items on its card', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1')

    expect(await screen.findByText('Batu Caves')).toBeInTheDocument()
    expect(screen.getByText('Nocleg: Memmo Alfama')).toBeInTheDocument()
  })

  it('renders a spanning item once, on its start day, with the marker', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1')

    await screen.findByText('Batu Caves')

    expect(screen.getAllByText('Nocleg: Memmo Alfama')).toHaveLength(1)
    expect(screen.getByText('→ 13.10')).toBeInTheDocument()
  })

  it('still invites the first item on the days that have none', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1')

    await screen.findByText('Batu Caves')

    // Three of the four days are empty.
    expect(screen.getAllByText('Nic jeszcze nie zaplanowano')).toHaveLength(3)
  })

  it('shows an item created in the day detail once the timeline is reopened', async () => {
    const user = userEvent.setup()
    let created = false
    mockApi((url, init) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      if (url.includes('/days/') && url.endsWith('/items') && method === 'POST') {
        created = true
        return json(201, { ...MUSEUM, id: 'item-new', title: 'Kolacja' })
      }
      if (url.includes('/days/')) {
        return json(200, created ? { ...DAY, items: [...DAY.items, { ...MUSEUM, id: 'item-new', title: 'Kolacja' }] } : DAY)
      }
      return backend()(url, init)
    })

    renderApp(DAY_PATH)
    await screen.findByText('Batu Caves')
    await user.click(screen.getByRole('button', { name: 'Dodaj element' }))
    await user.type(screen.getByLabelText('Nazwa'), 'Kolacja')
    await user.click(screen.getByRole('button', { name: 'Zapisz' }))

    expect(await screen.findByText('Kolacja')).toBeInTheDocument()
  })

  it('does not turn timeline items into buttons — the day detail is where they are edited', async () => {
    mockApi(backend())

    renderApp('/trips/trip-1')

    await screen.findByText('Batu Caves')
    const row = screen.getByText('Batu Caves').closest('.item-row')

    expect(within(row as HTMLElement).queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('the item card’s rail dot', () => {
  it('is absent unless the timeline asks for one — the day detail case', () => {
    // Rendered without `railDot`, exactly as `DayDetailPage` renders it. The
    // card is whole without the dot: the screen it is on has no rail to hang
    // one on, and the status is carried by the chip either way.
    const { container } = render(<ItemRow item={MUSEUM} dayDate="2026-10-11" />)

    expect(container.querySelector('.item-row__dot')).toBeNull()
    expect(screen.getByText('Batu Caves')).toBeInTheDocument()
    expect(screen.getByText('Do zaplanowania')).toBeInTheDocument()
  })

  it('is decoration beside the chip, never instead of it, when the timeline does', () => {
    const { container } = render(<ItemRow item={MUSEUM} dayDate="2026-10-11" railDot />)
    const dot = container.querySelector('.item-row__dot')

    expect(dot).toHaveAttribute('aria-hidden', 'true')
    expect(dot).toHaveAttribute('data-status', 'to_plan')
    expect(dot?.textContent).toBe('')
    // The colour-blindness contract: the glyph and the translated label are
    // still there, and the dot is an addition to them.
    expect(screen.getByText('Do zaplanowania')).toBeInTheDocument()
  })
})

function posted() {
  return requests.find((entry) => entry.method === 'POST' && entry.url.endsWith('/items'))?.body
}

function patched() {
  return requests.find((entry) => entry.method === 'PATCH' && entry.url.includes('/items/'))?.body
}
