import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { fetchTrip } from '../../api/trips'
import type { Stage, TripDetail } from '../../api/trips'
import { AppShell } from './AppShell'
import { ItemRow } from './ItemRow'
import { ReadinessTile } from './ReadinessTile'
import { formatDateRange, formatDayChip, routeSummary, stageLabel } from './format'

/**
 * `/trips/:id` — the vertical day-by-day timeline.
 *
 * Adapted from `g_wny_pulpit_i_o_czasu`. Kept: the trip header with its route
 * summary, the day-by-day column with a date chip per day, and the position the
 * export gives the readiness counter and the filter bar (both arrive in Phases 3
 * and 4). Dropped, per the spec: the concierge drawer and every AI card, the
 * currency toggle and budget tile, export and share, reservation codes, ticket
 * pills and the weather strip.
 *
 * The empty state is the deliverable of Phase 2 and has to look deliberate: a
 * trip whose days are all empty shows **the days**, each inviting the first item,
 * rather than a blank page that reads as a failed load.
 */

export function TimelinePage() {
  const { t, i18n } = useTranslation()
  const { tripId } = useParams<{ tripId: string }>()
  const [trip, setTrip] = useState<TripDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

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
  const hasItems = trip.days.some((day) => day.items.length > 0)

  return (
    <AppShell
      title={trip.title}
      breadcrumb={
        <nav aria-label={t('nav.breadcrumb')} className="breadcrumb">
          <Link to="/trips">{t('trips.title')}</Link>
        </nav>
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

      {!hasItems && (
        <p className="empty-state empty-state--inline">{t('timeline.emptyTimeline')}</p>
      )}

      <ol className="timeline">
        {trip.days.map((day) => {
          const dayStages = day.stage_ids
            .map((id) => stagesById.get(id))
            .filter((stage): stage is Stage => stage !== undefined)
          const label = stageLabel(dayStages)

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

              {day.items.length === 0 ? (
                <p className="timeline__empty-day">{t('timeline.emptyDay')}</p>
              ) : (
                <ul className="timeline__items">
                  {day.items.map((item) => (
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
    </AppShell>
  )
}
