import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import { createStage, deleteStage, updateStage } from '../../api/stages'
import type { StagePatch } from '../../api/stages'
import type { Stage } from '../../api/trips'
import { ConfirmDialog } from './ConfirmDialog'

/**
 * The trip editor's destination list: add, edit and remove a trip's bases.
 *
 * **Each card saves on its own, immediately.** The server has no bulk stage
 * endpoint — `POST`, `PATCH` and `DELETE` are one stage each — so a single
 * "save all" button would be three requests with no rollback, which reports
 * success after it has already half-applied. One card, one request, one
 * outcome reported on the card that caused it.
 *
 * **Every success refetches the whole trip** through `onChanged`. `position` is
 * renumbered densely by the server after a delete, and which stage a day
 * belongs to is *derived* from the stage dates — so keeping a local copy in
 * step would mean re-implementing `stages_for_day` in the browser. One extra
 * `GET` per change is the cheaper correctness.
 *
 * **The last stage cannot be removed** (R03: a trip has one or more bases). The
 * button is disabled rather than the request being refused, because a disabled
 * control explains the rule where a `409 stages_required` only reports it —
 * the same choice the creator makes for the same rule. The server enforces it
 * regardless, and if a second tab gets there first the refusal renders on the
 * card.
 */

type StageDraft = {
  /** Stable across a refetch: the server id, or a local key for an unsaved card. */
  key: string
  /** `null` until the card has been saved once — that is what picks POST or PATCH. */
  id: string | null
  place: string
  startDate: string
  endDate: string
}

let nextLocalKey = 0

const blankDraft = (): StageDraft => ({
  key: `new-${(nextLocalKey += 1)}`,
  id: null,
  place: '',
  startDate: '',
  endDate: '',
})

const draftOf = (stage: Stage): StageDraft => ({
  key: stage.id,
  id: stage.id,
  place: stage.place,
  startDate: stage.start_date ?? '',
  endDate: stage.end_date ?? '',
})

/** `''` is not a date: an empty box means "undecided" (R03), which is `null`. */
const dateOrNull = (value: string): string | null => (value === '' ? null : value)

export function StageEditor({
  tripId,
  stages,
  tripStart,
  tripEnd,
  disabled,
  onChanged,
  onBusyChange,
}: {
  tripId: string
  /** The stages as the server holds them — the truth every card is compared to. */
  stages: readonly Stage[]
  tripStart: string
  tripEnd: string
  /** True while the trip-level save is in flight, so a stage edit cannot race it. */
  disabled: boolean
  /** Refetch the trip. Awaited, so the card stays busy until the list is fresh. */
  onChanged: () => Promise<void>
  /** Mirrors the lock the other way: the trip's Save waits for these requests. */
  onBusyChange: (busy: boolean) => void
}) {
  const { t } = useTranslation()

  const [drafts, setDrafts] = useState<StageDraft[]>(() => stages.map(draftOf))
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [removing, setRemoving] = useState<StageDraft | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)

  // Rebuild from the server after every refetch, but keep any card that has
  // never been saved: adding a base and then saving a different one must not
  // silently discard what was typed into the new card.
  useEffect(() => {
    setDrafts((current) => [...stages.map(draftOf), ...current.filter((one) => one.id === null)])
  }, [stages])

  useEffect(() => {
    onBusyChange(busyKey !== null)
  }, [busyKey, onBusyChange])

  const saved = useMemo(() => new Map(stages.map((stage) => [stage.id, stage])), [stages])

  /** The client-side complaint for a card, or `null` — the creator's two rules. */
  function complaintFor(draft: StageDraft): string | null {
    if (draft.startDate !== '' && draft.endDate !== '' && draft.endDate < draft.startDate) {
      return t('error.invalid_date_range')
    }
    const outside = [draft.startDate, draft.endDate].some(
      (boundary) => boundary !== '' && (boundary < tripStart || boundary > tripEnd),
    )
    return outside ? t('error.stage_outside_trip') : null
  }

  function isDirty(draft: StageDraft): boolean {
    const stage = draft.id === null ? undefined : saved.get(draft.id)
    if (stage === undefined) {
      // An unsaved card is worth saving as soon as it names a place.
      return draft.place.trim() !== ''
    }
    return (
      draft.place !== stage.place ||
      draft.startDate !== (stage.start_date ?? '') ||
      draft.endDate !== (stage.end_date ?? '')
    )
  }

  function update(key: string, patch: Partial<StageDraft>) {
    setDrafts((current) => current.map((one) => (one.key === key ? { ...one, ...patch } : one)))
  }

  function clearError(key: string) {
    setErrors((current) => {
      const { [key]: _removed, ...rest } = current
      return rest
    })
  }

  async function save(draft: StageDraft) {
    setBusyKey(draft.key)
    clearError(draft.key)

    try {
      if (draft.id === null) {
        await createStage(tripId, {
          place: draft.place.trim(),
          start_date: dateOrNull(draft.startDate),
          end_date: dateOrNull(draft.endDate),
        })
        // The refetch below brings it back with its server id; dropping the
        // local card here is what stops it appearing twice.
        setDrafts((current) => current.filter((one) => one.key !== draft.key))
      } else {
        await updateStage(tripId, draft.id, patchFor(draft, saved.get(draft.id)))
      }
      await onChanged()
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.isUnauthenticated) {
        return // The global handler is already routing to /login.
      }
      setErrors((current) => ({
        ...current,
        [draft.key]: caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'),
      }))
    } finally {
      setBusyKey(null)
    }
  }

  /**
   * Only what changed. The dates are tri-state on the wire — a date, `null` for
   * undecided, or absent for "leave it alone" — so an unchanged one is omitted
   * rather than echoed back.
   */
  function patchFor(draft: StageDraft, stage: Stage | undefined): StagePatch {
    const patch: StagePatch = {}
    if (stage === undefined || draft.place !== stage.place) {
      patch.place = draft.place.trim()
    }
    if (draft.startDate !== (stage?.start_date ?? '')) {
      patch.start_date = dateOrNull(draft.startDate)
    }
    if (draft.endDate !== (stage?.end_date ?? '')) {
      patch.end_date = dateOrNull(draft.endDate)
    }
    return patch
  }

  async function remove(draft: StageDraft) {
    if (draft.id === null) {
      // Never saved: there is nothing on the server to delete.
      setDrafts((current) => current.filter((one) => one.key !== draft.key))
      setRemoving(null)
      return
    }

    setBusyKey(draft.key)
    setRemoveError(null)

    try {
      await deleteStage(tripId, draft.id)
      await onChanged()
      setRemoving(null)
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.isUnauthenticated) {
        return
      }
      // Reported inside the dialog, which is the only place still being looked
      // at and where the retry button is.
      setRemoveError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <fieldset className="field-card stages" disabled={disabled}>
      <legend>{t('tripCreate.stages')}</legend>
      <p className="hint">{t('tripEdit.stagesHint')}</p>

      {drafts.map((draft, index) => {
        const complaint = complaintFor(draft)
        const busy = busyKey === draft.key
        const error = errors[draft.key]

        return (
          <div className="stage-card" key={draft.key}>
            <div className="stage-card__head">
              <span className="stage-card__number" aria-hidden="true">
                {index + 1}
              </span>

              <span className="stage-card__actions">
                <button
                  type="button"
                  className="button-quiet"
                  disabled={
                    busy || !isDirty(draft) || complaint !== null || draft.place.trim() === ''
                  }
                  onClick={() => void save(draft)}
                >
                  {busy ? t('tripEdit.saving') : t('tripEdit.saveStage')}
                </button>

                <button
                  type="button"
                  className="button-quiet stage-card__remove"
                  // R03 again: the trip's last *saved* base stays. An unsaved
                  // card is always removable — nothing is lost by discarding it.
                  disabled={busy || (draft.id !== null && stages.length === 1)}
                  onClick={() => {
                    setRemoveError(null)
                    setRemoving(draft)
                  }}
                >
                  {t('tripCreate.removeStage')}
                </button>
              </span>
            </div>

            <div className="stage-card__fields">
              <div>
                <label htmlFor={`stage-place-${draft.key}`}>
                  {t('tripCreate.stagePlace', { position: index + 1 })}
                </label>
                <input
                  id={`stage-place-${draft.key}`}
                  value={draft.place}
                  onChange={(event) => update(draft.key, { place: event.target.value })}
                />
              </div>

              <div>
                <label htmlFor={`stage-start-${draft.key}`}>{t('tripCreate.stageStart')}</label>
                <input
                  id={`stage-start-${draft.key}`}
                  type="date"
                  value={draft.startDate}
                  onChange={(event) => update(draft.key, { startDate: event.target.value })}
                />
              </div>

              <div>
                <label htmlFor={`stage-end-${draft.key}`}>{t('tripCreate.stageEnd')}</label>
                <input
                  id={`stage-end-${draft.key}`}
                  type="date"
                  value={draft.endDate}
                  onChange={(event) => update(draft.key, { endDate: event.target.value })}
                />
              </div>
            </div>

            {/* The client's complaint first — it is about what is on screen
                right now — then whatever the server said about the last save. */}
            {complaint !== null && <p role="alert">{complaint}</p>}
            {complaint === null && error !== undefined && <p role="alert">{error}</p>}
          </div>
        )
      })}

      <button
        type="button"
        className="button-quiet stages__add"
        onClick={() => setDrafts((current) => [...current, blankDraft()])}
      >
        {t('tripCreate.addStage')}
      </button>

      {removing !== null && (
        <ConfirmDialog
          title={t('tripEdit.removeStageTitle')}
          // Naming the base is the point: a destination is a decision, and
          // there is no undo for removing one.
          message={t('tripEdit.removeStageMessage', { place: removing.place })}
          confirmLabel={t('tripCreate.removeStage')}
          error={removeError}
          onCancel={() => {
            setRemoveError(null)
            setRemoving(null)
          }}
          onConfirm={() => remove(removing)}
        />
      )}
    </fieldset>
  )
}
