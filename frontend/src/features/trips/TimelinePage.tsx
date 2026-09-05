import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { deleteTrip, fetchTrip } from '../../api/trips'
import type { Stage, TripDetail } from '../../api/trips'
import { AppShell } from './AppShell'
import { ConfirmDialog } from './ConfirmDialog'
import { FilterBar } from './FilterBar'
import { ItemRow } from './ItemRow'
import { ReadinessTile } from './ReadinessTile'
import { DEFAULT_FILTER, applyFilter, isFilter } from './filter'
import { formatDateRange, formatDayChip, routeSummary, stageLabel } from './format'

/**
 * `/trips/:id` — the vertical day-by-day timeline.
 *
 * Adapted from `g_wny_pulpit_i_o_czasu`. Kept: the trip header with its route
 * summary, the readiness counter in the position of the export's "STATUS
 * LOGISTYKI" tile, the filter bar where the export puts its chips, and the
 * day-by-day column with a date chip and item cards per day. Dropped, per the
 * spec: the concierge drawer and every AI card, the currency toggle and budget
 * tile, export and share, reservation codes, ticket pills and the weather strip.
 *
 * The empty state is the deliverable of Phase 2 and has to look deliberate: a
 * trip whose days are all empty shows **the days**, each inviting the first item,
 * rather than a blank page that reads as a failed load.
 */

export function TimelinePage() {
  const { t, i18n } = useTranslation()
  const { tripId } = useParams<{ tripId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [trip, setTrip] = useState<TripDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  /**
   * The filter lives in the URL, not in component state.
   *
   * That makes a filtered timeline linkable and survivable across a reload, and
   * it is the state most worth keeping when the owner comes back to the tab. An
   * unrecognised value falls back to `all` rather than showing nothing, since a
   * hand-edited URL should not be able to hide the plan.
   */
  const filterParam = searchParams.get('filter')
  const filter = isFilter(filterParam) ? filterParam : DEFAULT_FILTER

  useEffect(() => {
    if (tripId === undefined) {
      return
    }
    const controller = new AbortController()

    fetchTrip(tripId, controller.signal)
      .then(setTrip)
      .catch((caught: unknown) => {
        if (controller.signal.aborted || (caught instanceof ApiError && caught.isUnauthenticated)) {
          return
        }
        // A dead database answers 503 and lands here, which is the point: an
        // empty timeline is indistinguishable from a real empty trip and would
        // be a lie about the plan.
        setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      })

    return () => controller.abort()
  }, [tripId, t])

  if (error !== null) {
    return (
      <AppShell title={t('trips.title')}>
        <p role="alert">{error}</p>
      </AppShell>
    )
  }

  if (trip === null) {
    return (
      <AppShell title={t('trips.title')}>
        <p role="status">{t('app.loading')}</p>
      </AppShell>
    )
  }

  const stagesById = new Map(trip.stages.map((stage) => [stage.id, stage]))
  const everyItem = trip.days.flatMap((day) => day.items)
  const hasItems = everyItem.length > 0

  return (
    <AppShell
      title={trip.title}
      breadcrumb={
        <nav aria-label={t('nav.breadcrumb')} className="breadcrumb">
          <Link to="/trips">{t('trips.title')}</Link>
        </nav>
      }
      actions={
        <button
          type="button"
          className="button-danger"
          onClick={() => setConfirmingDelete(true)}
        >
          {t('trip.delete')}
        </button>
      }
    >
      <header className="trip-header">
        <p className="trip-header__dates">
          {formatDateRange(trip.start_date, trip.end_date, i18n.language)}
        </p>
        <p className="trip-header__route">{routeSummary(trip, trip.stages)}</p>
        {/* The export's "STATUS LOGISTYKI" tile. Its layout is adopted; its
            arithmetic is not — the export's denominator is the all-items count,
            which includes do zaplanowania and contradicts R02. */}
        <ReadinessTile readiness={trip.readiness} />
      </header>

      <FilterBar
        // The chips count the whole trip, and the counter above is computed
        // server-side — so neither moves when the filter changes. Only the day
        // cards below do.
        items={everyItem}
        filter={filter}
        onChange={(next) => {
          const params = new URLSearchParams(searchParams)
          if (next === DEFAULT_FILTER) {
            // The default is absence: /trips/1 and /trips/1?filter=all are the
            // same view and should not be two URLs.
            params.delete('filter')
          } else {
            params.set('filter', next)
          }
          setSearchParams(params, { replace: true })
        }}
      />

      {!hasItems && (
        <p className="empty-state empty-state--inline">{t('timeline.emptyTimeline')}</p>
      )}

      <ol className="timeline">
        {trip.days.map((day) => {
          const dayStages = day.stage_ids
            .map((id) => stagesById.get(id))
            .filter((stage): stage is Stage => stage !== undefined)
          const label = stageLabel(dayStages)

          const visible = applyFilter(day.items, filter)

          return (
            <li className="timeline__day" key={day.id}>
              <h2>
                <Link to={`/trips/${trip.id}/days/${day.date}`}>
                  <span className="timeline__chip">{formatDayChip(day.date, i18n.language)}</span>
                  {/* A day in no stage renders without a label rather than with
                      placeholder copy — it is a day in transit, not missing data. */}
                  {label !== '' && <span className="timeline__stages">{label}</span>}
                </Link>
              </h2>

              {day.items.length === 0 && (
                <p className="timeline__empty-day">{t('timeline.emptyDay')}</p>
              )}

              {/* A day whose items are all filtered out says so, rather than
                  looking like a day with nothing planned. */}
              {day.items.length > 0 && visible.length === 0 && (
                <p className="timeline__empty-day">{t('timeline.allFilteredOut')}</p>
              )}

              {visible.length > 0 && (
                <ul className="timeline__items">
                  {visible.map((item) => (
                    <li key={item.id}>
                      <ItemRow item={item} dayDate={day.date} />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ol>

      {confirmingDelete && (
        <ConfirmDialog
          title={t('trip.deleteTitle')}
          // Naming the trip is the point: "are you sure?" tells the owner
          // nothing about what is about to be destroyed, and there is no undo.
          message={t('trip.deleteMessage', { title: trip.title })}
          confirmLabel={t('trip.deleteConfirm')}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={async () => {
            await deleteTrip(trip.id)
            navigate('/trips', { replace: true })
          }}
        />
      )}
    </AppShell>
  )
}
