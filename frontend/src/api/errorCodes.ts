// Generated from backend/trip_planner/errors.py — do not edit by hand.
// Regenerate with: (cd backend && uv run python -m trip_planner.errors)

export type ErrorCode =
  | 'invalid_credentials'
  | 'not_authenticated'
  | 'csrf_token_invalid'
  | 'validation_error'
  | 'not_found'
  | 'service_unavailable'
  | 'invalid_date_range'
  | 'trip_too_long'
  | 'stages_required'
  | 'stage_outside_trip'

export const ERROR_CODES: readonly ErrorCode[] = [
  'invalid_credentials',
  'not_authenticated',
  'csrf_token_invalid',
  'validation_error',
  'not_found',
  'service_unavailable',
  'invalid_date_range',
  'trip_too_long',
  'stages_required',
  'stage_outside_trip',
] as const
