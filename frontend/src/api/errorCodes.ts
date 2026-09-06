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
  | 'invalid_time_span'
  | 'date_outside_trip'
  | 'days_have_items'
  | 'stages_outside_new_range'
  | 'items_outside_new_range'
  | 'attachment_too_large'
  | 'unsupported_file_type'
  | 'malformed_upload'
  | 'attachment_limit_reached'
  | 'trip_storage_quota_exceeded'
  | 'rate_limited'
  | 'invalid_cost'
  | 'invalid_reservation_field'
  | 'days_have_attachments'

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
  'invalid_time_span',
  'date_outside_trip',
  'days_have_items',
  'stages_outside_new_range',
  'items_outside_new_range',
  'attachment_too_large',
  'unsupported_file_type',
  'malformed_upload',
  'attachment_limit_reached',
  'trip_storage_quota_exceeded',
  'rate_limited',
  'invalid_cost',
  'invalid_reservation_field',
  'days_have_attachments',
] as const
