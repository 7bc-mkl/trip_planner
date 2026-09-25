import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { fetchTrip, updateTrip } from '../../api/trips'
import type { TripDetail } from '../../api/trips'
import { AppShell } from './AppShell'
import { detailedErrorMessage, refusalAnchor } from './errorDetail'
import type { RefusalAnchor } from './errorDetail'
import { dayCount, formatDateRange, nightCount } from './format'
import { ROUTE_MODES, returnPlaceFor, routeModeOf } from './routeMode'
import type { RouteMode } from './routeMode'

/**
 * `/trips/:tripId/edit` — correcting a trip after it was created.
 *
 * Until this screen existed the only way to change a wrong date was to delete
 * the trip, which cascades away every stage, day, item and attachment on it —
 * exactly the loss `PATCH /trips/{id}` was written to refuse. The endpoint has
 * been able to do this safely since the walking skeleton; nothing called it.
 *
 * **One `PATCH`, all five fields, always.** The screen holds every field the
 * endpoint takes, so there is nothing it does not know; and sending
 * `return_place` explicitly on every save is what keeps the server's
 * mode-stability rewrite from firing. That rule rewrites `return_place` to
 * follow `departure_place` when a round trip's departure changes *without* an
 * explicit return place — correct for a caller that sends a partial body, and
 * wrong for this one, where the radio group is the owner saying which mode the
 * trip is in. An explicit value always wins, which is what the server's own
 * comment promises.
 *
 * **A refusal changes nothing and resets nothing.** The four `409`s are the
 * point of the screen: the server names the offending days or places in
 * `error.field`, `errorDetail` turns that into a sentence, and the typed values
 * stay exactly as they were so the edit can be corrected rather than retyped.
 * Focus moves to the alert, because a keyboard user left at the foot of a form
 * that silently did nothing has no way to know it refused.
 *
 * The field labels come from the `tripCreate.*` keys rather than from a
 * duplicate set: they name the same five fields of the same object, and two
 * translations of "Departing from" that could drift apart would be worse than
 * one key whose name mentions the other screen.
 */

type Draft = {
  title: string
  startDate: string
  endDate: string
  departurePlace: string
  returnPlace: string
  routeMode: RouteMode
}

function draftOf(trip: TripDetail): Draft {
  const mode = routeModeOf(trip)

  return {
    title: trip.title,
    startDate: trip.start_date,
    endDate: trip.end_date,
    departurePlace: trip.departure_place,
    // Only open-jaw shows this field; the other two modes derive it, so the
    // box starts empty for them rather than pre-filled with a value the mode
    // will overwrite anyway.
    returnPlace: mode === 'openJaw' ? (trip.return_place ?? '') : '',
    routeMode: mode,
  }
}

export function TripEditPage() {
  const { t, i18n } = useTranslation()
  const { tripId } = useParams<{ tripId: string }>()
  const navigate = useNavigate()

  const [trip, setTrip] = useState<TripDetail | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<{ message: string; anchor: RefusalAnchor } | null>(null)
  const [saving, setSaving] = useState(false)

  /** Focused when a save is refused — see the note about silent failure above. */
  const alertRef = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    if (tripId === undefined) {
      return
    }
    const controller = new AbortController()

    fetchTrip(tripId, controller.signal)
      .then((loaded) => {
        setTrip(loaded)
        setDraft(draftOf(loaded))
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || (caught instanceof ApiError && caught.isUnauthenticated)) {
          return
        }
        // An empty form would be a lie about the trip, the same reason the
        // timeline refuses to render a blank page on a failed load.
        setLoadError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      })

    return () => controller.abort()
  }, [tripId, t])

  useEffect(() => {
    if (refusal !== null) {
      alertRef.current?.focus()
    }
  }, [refusal])

  const rangeIsValid =
    draft !== null && draft.startDate !== '' && draft.endDate !== '' && draft.endDate >= draft.startDate

  /**
   * Whether the form differs from what the server holds. Computed rather than
   * tracked with a flag, so undoing an edit by hand disables Save again.
   */
  const dirty = useMemo(() => {
    if (trip === null || draft === null) {
      return false
    }
    const current = draftOf(trip)
    return (
      draft.title !== current.title ||
      draft.startDate !== current.startDate ||
      draft.endDate !== current.endDate ||
      draft.departurePlace !== current.departurePlace ||
      draft.routeMode !== current.routeMode ||
      (draft.routeMode === 'openJaw' && draft.returnPlace !== current.returnPlace)
    )
  }, [trip, draft])

  const canSave =
    draft !== null &&
    dirty &&
    rangeIsValid &&
    draft.title.trim() !== '' &&
    draft.departurePlace.trim() !== '' &&
    (draft.routeMode !== 'openJaw' || draft.returnPlace.trim() !== '') &&
    !saving

  function update(patch: Partial<Draft>) {
    setDraft((current) => (current === null ? current : { ...current, ...patch }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSave || draft === null || tripId === undefined) {
      return
    }

    setSaving(true)
    setRefusal(null)

    try {
      await updateTrip(tripId, {
        title: draft.title.trim(),
        start_date: draft.startDate,
        end_date: draft.endDate,
        departure_place: draft.departurePlace.trim(),
        return_place: returnPlaceFor(
          draft.routeMode,
          draft.departurePlace.trim(),
          draft.returnPlace.trim(),
        ),
      })
      navigate(`/trips/${tripId}`)
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.isUnauthenticated) {
        return // The global handler is already routing to /login.
      }
      setRefusal({
        message: detailedErrorMessage(caught, t, i18n.language),
        anchor: refusalAnchor(caught),
      })
      setSaving(false)
    }
  }

  if (loadError !== null) {
    return (
      <AppShell title={t('tripEdit.title')}>
        <p role="alert">{loadError}</p>
      </AppShell>
    )
  }

  if (trip === null || draft === null) {
    return (
      <AppShell title={t('tripEdit.title')}>
        <p role="status">{t('app.loading')}</p>
      </AppShell>
    )
  }

  return (
    <AppShell
      title={t('tripEdit.title')}
      context={t('trip.headerContext', {
        title: trip.title,
        dates: formatDateRange(trip.start_date, trip.end_date, i18n.language),
      })}
      breadcrumb={
        <nav aria-label={t('nav.breadcrumb')} className="breadcrumb">
          <Link to="/trips">{t('trips.title')}</Link>
          <Link to={`/trips/${trip.id}`}>{trip.title}</Link>
        </nav>
      }
      dock={
        <div className="trip-dock">
          <section className="trip-dock__block">
            <h2>{t('tripCreate.dockTitle')}</h2>
            {/* The same live summary the creator shows, so the consequence of a
                date edit is visible before it is saved rather than after. */}
            <p className="trip-form__summary" role="status">
              {t('tripCreate.summary', {
                days: rangeIsValid ? dayCount(draft.startDate, draft.endDate) : 0,
                nights: rangeIsValid ? nightCount(draft.startDate, draft.endDate) : 0,
                stages: trip.stages.length,
              })}
            </p>
          </section>
        </div>
      }
    >
      <p className="trip-form__subtitle">{t('tripEdit.subtitle')}</p>

      <form className="trip-form" onSubmit={handleSubmit} noValidate>
        {refusal !== null && (
          <p className="trip-form__refusal" role="alert" tabIndex={-1} ref={alertRef}>
            {refusal.message}
          </p>
        )}

        <section className="field-card">
          <div className="field-card__row">
            <label htmlFor="trip-title">{t('tripCreate.titleLabel')}</label>
            <input
              id="trip-title"
              value={draft.title}
              onChange={(event) => update({ title: event.target.value })}
            />
          </div>

          <div className="field-card__row field-row">
            <div>
              <label htmlFor="trip-start">{t('tripCreate.startDate')}</label>
              <input
                id="trip-start"
                type="date"
                value={draft.startDate}
                aria-invalid={refusal?.anchor === 'dates' ? true : undefined}
                onChange={(event) => update({ startDate: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="trip-end">{t('tripCreate.endDate')}</label>
              <input
                id="trip-end"
                type="date"
                value={draft.endDate}
                aria-invalid={refusal?.anchor === 'dates' ? true : undefined}
                onChange={(event) => update({ endDate: event.target.value })}
              />
            </div>
          </div>

          {draft.startDate !== '' && draft.endDate !== '' && !rangeIsValid && (
            <p role="alert">{t('error.invalid_date_range')}</p>
          )}
        </section>

        <fieldset className="field-card route-mode">
          <legend>{t('tripCreate.routeMode')}</legend>

          <div className="route-mode__options">
            {ROUTE_MODES.map((mode) => (
              <label key={mode}>
                <input
                  type="radio"
                  name="route-mode"
                  value={mode}
                  checked={draft.routeMode === mode}
                  onChange={() => update({ routeMode: mode })}
                />
                <span>{t(`tripCreate.routeModes.${mode}`)}</span>
              </label>
            ))}
          </div>

          <div className="field-card__row">
            <label htmlFor="trip-departure">{t('tripCreate.departurePlace')}</label>
            <input
              id="trip-departure"
              value={draft.departurePlace}
              onChange={(event) => update({ departurePlace: event.target.value })}
            />
          </div>

          {draft.routeMode === 'openJaw' && (
            <div className="field-card__row">
              <label htmlFor="trip-return">{t('tripCreate.returnPlace')}</label>
              <input
                id="trip-return"
                value={draft.returnPlace}
                onChange={(event) => update({ returnPlace: event.target.value })}
              />
            </div>
          )}
        </fieldset>

        {/* Phase 1 shows the bases without editing them, rather than pretending
            the screen can already change them. Phase 2 replaces this block with
            the editable cards. */}
        <section
          className="field-card stages"
          aria-invalid={refusal?.anchor === 'stages' ? true : undefined}
        >
          <h2>{t('tripCreate.stages')}</h2>
          <dl className="trip-dock__list">
            {trip.stages.map((stage) => (
              <div className="trip-dock__entry" key={stage.id}>
                <dt>{stage.place}</dt>
                <dd>
                  {stage.start_date !== null && stage.end_date !== null
                    ? formatDateRange(stage.start_date, stage.end_date, i18n.language)
                    : t('trip.dockUndated')}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <div className="trip-form__actions">
          <button
            type="submit"
            className="button-primary button-primary--deep trip-form__submit"
            disabled={!canSave}
          >
            {saving ? t('tripEdit.saving') : t('tripEdit.save')}
          </button>
          <Link className="button-quiet" to={`/trips/${trip.id}`}>
            {t('tripEdit.cancel')}
          </Link>
        </div>
      </form>
    </AppShell>
  )
}
