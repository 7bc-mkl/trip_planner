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
  /**
   * The values that key renders with — `{from: '2026-10-04', to: '2026-10-11'}`.
   *
   * Data rather than a formatted sentence, which is what lets the screen say
   * "no trip covers 4–11 October" in either language without the server
   * owning a word of it.
   */
  routing_reason_args: Record<string, string> | null
  /** A translation-key suffix. See the module note. */
  last_error: string | null
  attachment_count: number
}

export type InboxMessageDetail = InboxMessage & {
  text_body: string
  attachments: InboxAttachment[]
  /** This message's proposals, newest first — ids only; the sheet loads one. */
  action_item_ids: string[]
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
  /** Proposals awaiting the owner's decision (D21). */
  pending_action_items: number
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

/* ------------------------------------------------------------------------ *
 * Action items — Phase 3 (D21)
 * ------------------------------------------------------------------------ */

/** What an approval may name. `cost` is one field: an amount and its currency. */
export type ApprovableField =
  | 'title'
  | 'kind'
  | 'confirmation_number'
  | 'cost'
  | 'start_time'
  | 'end_time'
  | 'end_date'

export type CostValue = { amount: string; currency: string }

/**
 * A typed value on the wire: an ISO date, an `HH:MM` time, a cost pair, or a
 * plain string. **Never prose a model composed** — the sheet formats every one
 * of these through `Intl` or a translation key.
 */
export type FieldValue = string | CostValue | null

export type FieldRow = {
  name: ApprovableField
  current: FieldValue
  proposed: FieldValue
  changed: boolean
  /** True only when the item's value is empty — nothing to lose (A6). */
  default_ticked: boolean
}

export type StatusRow = {
  current: string | null
  proposed: string
  changed: boolean
  /** True only for a forward move; a backwards one is offered, never ticked. */
  default_ticked: boolean
}

export type ActionItem = {
  id: string
  message_id: string
  subject: string
  from_address: string
  received_at: string
  kind: 'update_item' | 'create_item'
  state: 'pending' | 'approved' | 'rejected' | 'superseded'
  /** Sent back as `expected_revision`. */
  revision: number
  source: 'model' | 'owner'
  trip_id: string | null
  trip_title: string | null
  target_item_id: string | null
  target_item_title: string | null
  target_trip_day_id: string | null
  target_date: string | null
  /** A translation-key suffix under `inbox.target.` — never prose. */
  target_reason: string
  fields: FieldRow[]
  status: StatusRow | null
  attachments: InboxAttachment[]
  alternatives: { trip_id: string; title: string }[]
  applied: {
    item_id: string
    created: boolean
    fields: ApprovableField[]
    status_changed: boolean
    attachment_count: number
  } | null
  decided_at: string | null
  created_at: string
}

export type ApprovalSelection = {
  target_item_id?: string | null
  target_trip_day_id?: string | null
  fields: ApprovableField[]
  attachment_ids: string[]
  set_status: string | null
  expected_revision: number
}

export type Target = { target_item_id: string } | { target_trip_day_id: string }

export function listActionItems(signal?: AbortSignal): Promise<ActionItem[]> {
  return request<ActionItem[]>(`${INBOX}/action-items`, { signal })
}

export function getActionItem(id: string, signal?: AbortSignal): Promise<ActionItem> {
  return request<ActionItem>(`${INBOX}/action-items/${id}`, { signal })
}

export function approveActionItem(id: string, selection: ApprovalSelection): Promise<ActionItem> {
  return request<ActionItem>(`${INBOX}/action-items/${id}/approve`, {
    method: 'POST',
    body: selection,
  })
}

export function rejectActionItem(id: string): Promise<void> {
  return request<void>(`${INBOX}/action-items/${id}/reject`, { method: 'POST' })
}

export function undoActionItem(id: string): Promise<ActionItem> {
  return request<ActionItem>(`${INBOX}/action-items/${id}/undo`, { method: 'POST' })
}

export function retargetActionItem(
  id: string,
  target: Target,
  expectedRevision: number,
): Promise<ActionItem> {
  return request<ActionItem>(`${INBOX}/action-items/${id}/retarget`, {
    method: 'POST',
    body: { ...target, expected_revision: expectedRevision },
  })
}

export function proposeForMessage(messageId: string, target: Target): Promise<ActionItem> {
  return request<ActionItem>(`${INBOX}/messages/${messageId}/action-items`, {
    method: 'POST',
    body: target,
  })
}
