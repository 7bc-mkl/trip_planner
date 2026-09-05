import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { listTrips } from '../../api/trips'
import type { TripSummary } from '../../api/trips'
import { ApiError } from '../../api/client'
import { AppShell } from './AppShell'
import { formatDateRange, routeSummary } from './format'

/**
 * `/trips` — the owner's trips.
 *
 * Not in the design export: it is the smallest thing that makes more than one
 * trip navigable, and otherwise standard CRUD. The parts that are not standard
 * are the empty state (a first-time account is a normal state, not an error) and
 * the readiness counter per row, which Phase 3 adds here.
 */
export function TripListPage() {
  const { t, i18n } = useTranslation()
  const [trips, setTrips] = useState<TripSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    listTrips(controller.signal)
      .then(setTrips)
      .catch((caught: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        // A 401 is already handled globally by the client's unauthenticated
        // handler, which routes to /login; showing an error here as well would
        // flash a failure on the way out.
        if (caught instanceof ApiError && caught.isUnauthenticated) {
          return
        }
        setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      })

    return () => controller.abort()
  }, [t])

  return (
    <AppShell
      title={t('trips.title')}
      actions={
        <Link className="button-primary" to="/trips/new">
          {t('trips.new')}
        </Link>
      }
    >
      {error !== null && <p role="alert">{error}</p>}

      {error === null && trips === null && <p role="status">{t('app.loading')}</p>}

      {trips !== null && trips.length === 0 && (
        <section className="empty-state">
          <h2>{t('trips.emptyTitle')}</h2>
          <p>{t('trips.emptyBody')}</p>
          <Link className="button-primary" to="/trips/new">
            {t('trips.new')}
          </Link>
        </section>
      )}

      {trips !== null && trips.length > 0 && (
        <ul className="trip-list">
          {trips.map((trip) => (
            <li key={trip.id}>
              <Link to={`/trips/${trip.id}`}>
                <h2>{trip.title}</h2>
                <p className="trip-list__dates">
                  {formatDateRange(trip.start_date, trip.end_date, i18n.language)}
                </p>
                <p className="trip-list__route">{routeSummary(trip)}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  )
}
