// Generated from backend/trip_planner/errors.py — do not edit by hand.
// Regenerate with: (cd backend && uv run python -m trip_planner.errors)

export type ErrorCode =
  | 'invalid_credentials'
  | 'not_authenticated'
  | 'csrf_token_invalid'
  | 'validation_error'
  | 'not_found'
  | 'service_unavailable'

export const ERROR_CODES: readonly ErrorCode[] = [
  'invalid_credentials',
  'not_authenticated',
  'csrf_token_invalid',
  'validation_error',
  'not_found',
  'service_unavailable',
] as const
