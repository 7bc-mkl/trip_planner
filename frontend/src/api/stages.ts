import { request } from './client'
import type { Stage, StageInput } from './trips'

/**
 * The stage API, typed to match `backend/trip_planner/api/stages.py`.
 *
 * A module of its own rather than three more functions in `trips.ts`, mirroring
 * the split the server already makes: stages are a collection under a trip with
 * their own router, their own dense `position` rule and their own refusals.
 *
 * **`StagePatch` is not `Partial<StageInput>`, and the difference is the whole
 * point.** `StageUpdate` on the server reads `model_fields_set`, so for the two
 * dates *omitting* a key and sending `null` are different requests: omitting
 * leaves the date alone, `null` clears it back to "undecided", which R03 says
 * is a real state for a base whose days have not been settled. A caller that
 * sent every field on every edit could never express "leave this one as it is",
 * so this type makes both sayable and the caller says which it means.
 *
 * There is no bulk endpoint here, and this module does not invent one: a
 * "save all the stages" helper looping over three requests would be a save with
 * no rollback, reporting success after it had already half-applied.
 */

export type StagePatch = {
  place?: string
  /** `null` clears the date; omit the key to leave it untouched. */
  start_date?: string | null
  end_date?: string | null
}

export function createStage(tripId: string, input: StageInput): Promise<Stage> {
  return request<Stage>(`/trips/${tripId}/stages`, { method: 'POST', body: input })
}

export function updateStage(
  tripId: string,
  stageId: string,
  patch: StagePatch,
): Promise<Stage> {
  return request<Stage>(`/trips/${tripId}/stages/${stageId}`, { method: 'PATCH', body: patch })
}

export function deleteStage(tripId: string, stageId: string): Promise<void> {
  return request<void>(`/trips/${tripId}/stages/${stageId}`, { method: 'DELETE' })
}
