import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { createItem, deleteItem, fetchDay, updateItem } from '../../api/items'
import type { DayDetail, Item, ItemInput } from '../../api/items'
import { fetchTrip } from '../../api/trips'
import type { TripSummary } from '../../api/trips'
import { AppShell } from './AppShell'
import { ItemDialog } from './ItemDialog'
import { ItemRow } from './ItemRow'
import { formatDate, formatDateRange, stageLabel } from './format'

/**
 * `/trips/:tripId/days/:date` — the day detail.
 *
 * Adapted from `szczeg_y_dnia_i_aktywno_ci`. Kept: the breadcrumb, the day
 * heading with its derived stages, prev/next navigation, the ordered item list
 * and the editor dialog. Dropped, per the spec: the route map and GPS, the
 * attachments panel, the tasks panel, the AI day assistant and its optimisation
 * suggestions, the calendar export, and per-item photos, ratings and prices.
 *
 * **The status control is the point of this screen.** Moving an item to *done*
 * here is the action the timeline's counter reacts to.
 */

/** Which dialog is open: none, a new item, or an existing one. */
type Editing = { mode: 'closed' } | { mode: 'new' } | { mode: 'edit'; item: Item }

export function DayDetailPage() {
  const { t, i18n } = useTranslation()
  const { tripId, date } = useParams<{ tripId: string; date: string }>()

  /**
   * What has been loaded, tagged with the date it was loaded for.
   *
   * Tagged rather than cleared in an effect: navigating from day to day must not
   * show the previous day's items under the new day's heading, and resetting the
   * state inside the effect would render the stale pair once before the reset
   * lands. Comparing during render makes the stale state unrenderable instead of
   * merely short-lived.
   */
  const [loaded, setLoaded] = useState<{ date: string; day: DayDetail | null; error: string | null }>(
    { date: '', day: null, error: null },
  )
  const [editing, setEditing] = useState<Editing>({ mode: 'closed' })

  const load = useCallback(
    (signal?: AbortSignal) => {
      if (tripId === undefined || date === undefined) {
        return Promise.resolve()
      }
      return fetchDay(tripId, date, signal)
        .then((fresh) => setLoaded({ date, day: fresh, error: null }))
        .catch((caught: unknown) => {
          if (signal?.aborted || (caught instanceof ApiError && caught.isUnauthenticated)) {
            return
          }
          setLoaded({
            date,
            day: null,
            error: caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'),
          })
        })
    },
    [tripId, date, t],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  /**
   * The trip this day belongs to, for the header's context line only.
   *
   * The day endpoint answers with `trip_id` and nothing else about the trip, so
   * the title and the date range have to be read separately. Deliberately
   * best-effort: a failure here leaves the context line absent and changes
   * nothing else on the screen, because naming the trip in the header must
   * never be a reason a day fails to render.
   */
  const [tripSummary, setTripSummary] = useState<TripSummary | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    if (tripId !== undefined) {
      fetchTrip(tripId, controller.signal)
        .then((fresh) => setTripSummary(fresh))
        .catch(() => setTripSummary(null))
    }
    return () => controller.abort()
  }, [tripId])

  // Anything loaded for another date is not this screen's data.
  const current = loaded.date === date ? loaded : null
  const day = current?.day ?? null
  const error = current?.error ?? null

  // Narrowed once, so the handlers below close over plain strings rather than
  // repeating a non-null assertion the router already guarantees.
  if (tripId === undefined || date === undefined) {
    return null
  }
  const trip = tripId
  const dayDate = date

  async function handleSave(input: ItemInput) {
    if (editing.mode === 'edit') {
      await updateItem(trip, editing.item.id, input)
    } else {
      await createItem(trip, dayDate, input)
    }
    await load()
  }

  async function handleDelete(item: Item) {
    await deleteItem(trip, item.id)
    setEditing({ mode: 'closed' })
    await load()
  }

  if (error !== null) {
    return (
      <AppShell title={t('day.title')}>
        <p role="alert">{error}</p>
      </AppShell>
    )
  }

  if (day === null) {
    return (
      <AppShell title={t('day.title')}>
        <p role="status">{t('app.loading')}</p>
      </AppShell>
    )
  }

  const stages = stageLabel(day.stages)

  return (
    <AppShell
      title={formatDate(day.date, i18n.language)}
      context={
        tripSummary === null
          ? undefined
          : t('trip.headerContext', {
              title: tripSummary.title,
              dates: formatDateRange(
                tripSummary.start_date,
                tripSummary.end_date,
                i18n.language,
              ),
            })
      }
      /*
       * BOTH lines above the heading go through the shell's one existing slot,
       * as siblings: the breadcrumb first, then the derived stage as the
       * eyebrow. This screen is the only one that needs two of them, and a
       * second prop on a component four screens share would be a new API bought
       * for one caller — the spec's Scope names `dock`, `context` and `drawer`
       * as the additive props and nothing else.
       *
       * The `<h1>` is untouched by the arrangement: it stays the single heading
       * with the formatted date as its single accessible name, and neither the
       * `<nav>` nor the eyebrow paragraph is part of it.
       */
      breadcrumb={
        <>
          <nav aria-label={t('nav.breadcrumb')} className="breadcrumb">
            <Link to="/trips">{t('trips.title')}</Link>
            {' / '}
            <Link to={`/trips/${tripId}`}>{t('day.backToTimeline')}</Link>
          </nav>
          {stages !== '' && <p className="day-stages">{stages}</p>}
        </>
      }
      actions={
        <button
          type="button"
          className="button-primary"
          onClick={() => setEditing({ mode: 'new' })}
        >
          {t('item.add')}
        </button>
      }
    >
      {/* Real prev/next links, disabled at the trip's boundaries — the server
          sends null there rather than making the SPA guess where the trip ends.
          They wear the ghost recipe now, and each carries an empty, `aria-hidden`
          glyph slot the chevron lands in at step 6.1 — no sprite is invented
          here. The slot is decoration in both cases: the control's name is the
          VISIBLE word beside it, which is why the disabled boundary still reads
          "previous day" rather than a greyed-out arrow. */}
      <nav className="day-nav" aria-label={t('day.navLabel')}>
        {day.previous_date === null ? (
          <span className="day-nav__link day-nav__disabled">
            <span className="day-nav__icon" aria-hidden="true" />
            {t('day.previous')}
          </span>
        ) : (
          <Link
            className="button-quiet day-nav__link"
            to={`/trips/${tripId}/days/${day.previous_date}`}
          >
            <span className="day-nav__icon" aria-hidden="true" />
            {t('day.previous')}
          </Link>
        )}
        {day.next_date === null ? (
          <span className="day-nav__link day-nav__disabled">
            {t('day.next')}
            <span className="day-nav__icon" aria-hidden="true" />
          </span>
        ) : (
          <Link
            className="button-quiet day-nav__link"
            to={`/trips/${tripId}/days/${day.next_date}`}
          >
            {t('day.next')}
            <span className="day-nav__icon" aria-hidden="true" />
          </Link>
        )}
      </nav>

      {day.items.length === 0 ? (
        <p className="empty-state empty-state--inline">{t('day.empty')}</p>
      ) : (
        <ol className="item-list">
          {day.items.map((item) => (
            <li key={item.id}>
              <ItemRow
                item={item}
                dayDate={day.date}
                onOpen={() => setEditing({ mode: 'edit', item })}
              />
            </li>
          ))}
        </ol>
      )}

      {editing.mode !== 'closed' && (
        <ItemDialog
          item={editing.mode === 'edit' ? editing.item : null}
          onSave={handleSave}
          onDelete={
            editing.mode === 'edit' ? () => handleDelete(editing.item) : undefined
          }
          onClose={() => setEditing({ mode: 'closed' })}
        />
      )}
    </AppShell>
  )
}
