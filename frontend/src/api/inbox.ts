import { request } from './client'

/**
 * The inbox API, typed to match `backend/trip_planner/api/inbox.py`.
 *
 * Two things in these types are deliberate and worth not "simplifying" later.
 *
 * **`routing_reason` and `last_error` are translation-key suffixes, never
 * prose.** The screen renders them through i18next as `inbox.reason.<value>`,
 * so an untranslated — or, from Phase 2, an *injected* — string has no path to
 * the screen through the locale layer. Rendering either of them directly would
 * be the one line that undoes that.
 *
 * **A quarantined message never appears as an `InboxMessage`.** It has its own
 * type and its own route, carrying headers and nothing else, because quarantine
 * is a barrier: a shape that could hold a body would eventually be given one.
 */

/** Every state a message in the list can be in. `quarantined` is not among them. */
export type InboxState = 'pending_ingest' | 'deferred' | 'received' | 'routed' | 'unrouted'

export type InboxAttachment = {
  id: string
  filename: string
  content_type: string
  byte_size: number
  sha256: string
  created_at: string
  /**
   * When sending this document to a model provider was attempted.
   *
   * Always `null` today: Phase 1 ships with no model and no egress. It is on
   * the type so the screen does not change contract when that changes.
   */
  sent_externally_at: string | null
}

export type InboxMessage = {
  id: string
  received_at: string
  from_address: string
  subject: string
  state: InboxState
  trip_id: string | null
  /** A translation-key suffix. See the module note. */
  routing_reason: string | null
  /** A translation-key suffix. See the module note. */
  last_error: string | null
  attachment_count: number
}

export type InboxMessageDetail = InboxMessage & {
  text_body: string
  attachments: InboxAttachment[]
}

export type QuarantinedMessage = {
  id: string
  received_at: string
  from_address: string
  subject: string
  reason: string | null
  /** Offered only for an authenticated address that is simply unknown. */
  may_trust_sender: boolean
  /** Offered only for a failed or missing authentication verdict. */
  may_release_message: boolean
  /** Both actions need the raw object; `false` once it has expired. */
  recoverable: boolean
}

/**
 * The badge's payload.
 *
 * `inbox_enabled: false` is a **normal** state, not a failure: a deployment
 * with no SES configuration shows the screen with an explanatory empty state
 * and no error. This is the one inbox call that answers on such a deployment
 * rather than `409` — otherwise the badge's absence would look like a fault.
 */
export type InboxSummary = {
  inbox_enabled: boolean
  /** The address to forward to, for the empty state. `null` when unconfigured. */
  address: string | null
  unrouted: number
  quarantined: number
  last_received_at: string | null
  last_error_at: string | null
  /** A translation-key suffix. See the module note. */
  last_error: string | null
}

const INBOX = '/inbox'

export function getInboxSummary(signal?: AbortSignal): Promise<InboxSummary> {
  return request<InboxSummary>(`${INBOX}/summary`, { signal })
}

export function listInboxMessages(signal?: AbortSignal): Promise<InboxMessage[]> {
  return request<InboxMessage[]>(`${INBOX}/messages`, { signal })
}

export function getInboxMessage(
  messageId: string,
  signal?: AbortSignal,
): Promise<InboxMessageDetail> {
  return request<InboxMessageDetail>(`${INBOX}/messages/${messageId}`, { signal })
}

/**
 * The quarantined messages, headers only.
 *
 * A separate call from `listInboxMessages` rather than a filter on it, because
 * showing quarantined mail is a separate, deliberate act — and one the summary
 * deliberately cannot serve, since it is the badge's cheap poll and putting
 * strangers' headers in it would fetch them on every page load.
 */
export function listQuarantined(signal?: AbortSignal): Promise<QuarantinedMessage[]> {
  return request<QuarantinedMessage[]>(`${INBOX}/quarantine`, { signal })
}

export function getQuarantinedMessage(
  messageId: string,
  signal?: AbortSignal,
): Promise<QuarantinedMessage> {
  return request<QuarantinedMessage>(`${INBOX}/quarantine/${messageId}`, { signal })
}

export function placeMessage(messageId: string, tripId: string): Promise<InboxMessage> {
  return request<InboxMessage>(`${INBOX}/messages/${messageId}/place`, {
    method: 'POST',
    body: { trip_id: tripId },
  })
}

export function trustSender(messageId: string): Promise<InboxMessage> {
  return request<InboxMessage>(`${INBOX}/quarantine/${messageId}/trust-sender`, {
    method: 'POST',
  })
}

export function releaseMessage(messageId: string): Promise<InboxMessage> {
  return request<InboxMessage>(`${INBOX}/quarantine/${messageId}/release`, { method: 'POST' })
}

export function deleteInboxMessage(messageId: string): Promise<void> {
  return request<void>(`${INBOX}/messages/${messageId}`, { method: 'DELETE' })
}

/**
 * The URL a document is served from while it is still in the inbox.
 *
 * A different path from the shipped trip-scoped one, because an inbox document
 * has no trip to be scoped by. Both answer with the same header set.
 */
export function inboxAttachmentUrl(messageId: string, attachmentId: string): string {
  return `/api/v1${INBOX}/messages/${messageId}/attachments/${attachmentId}/content`
}
