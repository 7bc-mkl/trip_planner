import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { createTrip } from '../../api/trips'
import type { StageInput } from '../../api/trips'
import { AppShell } from './AppShell'
import { dayCount, nightCount } from './format'
import { ROUTE_MODES, returnPlaceFor } from './routeMode'
import type { RouteMode } from './routeMode'

/**
 * `/trips/new` — the multi-stop creator.
 *
 * Adapted from `kreator_podr_y_manualny_i_wieloodcinkowy`. Kept: the route-mode
 * toggle, the trip date range, the ordered stage list with optional per-stage
 * dates, the live summary panel, and the primary action this whole screen exists
 * to deliver. Dropped, per the spec: the AI mode tabs and suggestion fill, the
 * flight-number leg editor, the PNR dropzone and the budget panel.
 *
 * The client validates before sending, and the server validates again. That is
 * not redundancy for its own sake: the inline check is what lets the form point
 * at the offending stage while the owner is still typing, and the server check is
 * what makes the rule true for any other caller.
 */

type StageDraft = { key: number; place: string; startDate: string; endDate: string }

let nextStageKey = 0
const newStage = (): StageDraft => ({ key: (nextStageKey += 1), place: '', startDate: '', endDate: '' })

export function TripCreatePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [title, setTitle] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [departurePlace, setDeparturePlace] = useState('')
  const [returnPlace, setReturnPlace] = useState('')
  const [routeMode, setRouteMode] = useState<RouteMode>('roundTrip')
  const [stages, setStages] = useState<StageDraft[]>([newStage()])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const rangeIsValid = startDate !== '' && endDate !== '' && endDate >= startDate

  /**
   * The per-stage complaint, or `null`. Computed rather than stored so it cannot
   * go stale against the field it describes.
   */
  const stageErrors = useMemo(
    () =>
      stages.map((stage) => {
        if (stage.startDate !== '' && stage.endDate !== '' && stage.endDate < stage.startDate) {
          return t('error.invalid_date_range')
        }
        if (!rangeIsValid) {
          return null
        }
        const outside = [stage.startDate, stage.endDate].some(
          (boundary) => boundary !== '' && (boundary < startDate || boundary > endDate),
        )
        return outside ? t('error.stage_outside_trip') : null
      }),
    [stages, rangeIsValid, startDate, endDate, t],
  )

  const canSubmit =
    title.trim() !== '' &&
    rangeIsValid &&
    departurePlace.trim() !== '' &&
    (routeMode !== 'openJaw' || returnPlace.trim() !== '') &&
    stages.length > 0 &&
    stages.every((stage) => stage.place.trim() !== '') &&
    stageErrors.every((message) => message === null)

  function updateStage(key: number, patch: Partial<StageDraft>) {
    setStages((current) =>
      current.map((stage) => (stage.key === key ? { ...stage, ...patch } : stage)),
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit || submitting) {
      return
    }

    setSubmitting(true)
    setError(null)

    // Empty date strings become null rather than being sent as "": an undated
    // stage is a real state (R03), and "" is not a date.
    const payloadStages: StageInput[] = stages.map((stage) => ({
      place: stage.place.trim(),
      start_date: stage.startDate === '' ? null : stage.startDate,
      end_date: stage.endDate === '' ? null : stage.endDate,
    }))

    try {
      const trip = await createTrip({
        title: title.trim(),
        start_date: startDate,
        end_date: endDate,
        departure_place: departurePlace.trim(),
        return_place: returnPlaceFor(routeMode, departurePlace.trim(), returnPlace.trim()),
        stages: payloadStages,
      })
      navigate(`/trips/${trip.id}`)
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.isUnauthenticated) {
        return // The global handler is already routing to /login.
      }
      setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      setSubmitting(false)
    }
  }

  return (
    <AppShell title={t('tripCreate.title')}>
      <form className="trip-form" onSubmit={handleSubmit} noValidate>
        <label htmlFor="trip-title">{t('tripCreate.titleLabel')}</label>
        <input
          id="trip-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t('tripCreate.titlePlaceholder')}
        />

        <div className="field-row">
          <div>
            <label htmlFor="trip-start">{t('tripCreate.startDate')}</label>
            <input
              id="trip-start"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="trip-end">{t('tripCreate.endDate')}</label>
            <input
              id="trip-end"
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </div>
        </div>

        {startDate !== '' && endDate !== '' && !rangeIsValid && (
          <p role="alert">{t('error.invalid_date_range')}</p>
        )}

        {/* A real radio group, so the three modes are one control to a screen
            reader and arrow keys move between them. */}
        <fieldset className="route-mode">
          <legend>{t('tripCreate.routeMode')}</legend>
          {ROUTE_MODES.map((mode) => (
            <label key={mode}>
              <input
                type="radio"
                name="route-mode"
                value={mode}
                checked={routeMode === mode}
                onChange={() => setRouteMode(mode)}
              />
              {t(`tripCreate.routeModes.${mode}`)}
            </label>
          ))}
        </fieldset>

        <label htmlFor="trip-departure">{t('tripCreate.departurePlace')}</label>
        <input
          id="trip-departure"
          value={departurePlace}
          onChange={(event) => setDeparturePlace(event.target.value)}
        />

        {/* Only open-jaw asks for a return place: round trip mirrors the departure
            place, and one-way has none. */}
        {routeMode === 'openJaw' && (
          <>
            <label htmlFor="trip-return">{t('tripCreate.returnPlace')}</label>
            <input
              id="trip-return"
              value={returnPlace}
              onChange={(event) => setReturnPlace(event.target.value)}
            />
          </>
        )}

        <fieldset className="stages">
          <legend>{t('tripCreate.stages')}</legend>
          <p className="hint">{t('tripCreate.stagesHint')}</p>

          {stages.map((stage, index) => (
            <div className="stage-row" key={stage.key}>
              <label htmlFor={`stage-place-${stage.key}`}>
                {t('tripCreate.stagePlace', { position: index + 1 })}
              </label>
              <input
                id={`stage-place-${stage.key}`}
                value={stage.place}
                onChange={(event) => updateStage(stage.key, { place: event.target.value })}
              />

              <label htmlFor={`stage-start-${stage.key}`}>{t('tripCreate.stageStart')}</label>
              <input
                id={`stage-start-${stage.key}`}
                type="date"
                value={stage.startDate}
                onChange={(event) => updateStage(stage.key, { startDate: event.target.value })}
              />

              <label htmlFor={`stage-end-${stage.key}`}>{t('tripCreate.stageEnd')}</label>
              <input
                id={`stage-end-${stage.key}`}
                type="date"
                value={stage.endDate}
                onChange={(event) => updateStage(stage.key, { endDate: event.target.value })}
              />

              <button
                type="button"
                className="button-quiet"
                // The last stage cannot be removed: R03 requires one or more, and
                // a disabled control explains that better than a refused request.
                disabled={stages.length === 1}
                onClick={() =>
                  setStages((current) => current.filter((candidate) => candidate.key !== stage.key))
                }
              >
                {t('tripCreate.removeStage')}
              </button>

              {stageErrors[index] !== null && <p role="alert">{stageErrors[index]}</p>}
            </div>
          ))}

          <button
            type="button"
            className="button-quiet"
            onClick={() => setStages((current) => [...current, newStage()])}
          >
            {t('tripCreate.addStage')}
          </button>
        </fieldset>

        {/* The export's live summary: "15 dni / 14 n. · 3 bazy". */}
        <p className="trip-form__summary" role="status">
          {t('tripCreate.summary', {
            days: rangeIsValid ? dayCount(startDate, endDate) : 0,
            nights: rangeIsValid ? nightCount(startDate, endDate) : 0,
            stages: stages.length,
          })}
        </p>

        {error !== null && <p role="alert">{error}</p>}

        <button type="submit" className="button-primary" disabled={!canSubmit || submitting}>
          {submitting ? t('tripCreate.submitting') : t('tripCreate.submit')}
        </button>
      </form>
    </AppShell>
  )
}
