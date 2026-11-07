import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { ApiError } from '../../api/client'
import type {
  ActionItem,
  InboxMessage,
  InboxMessageDetail,
  InboxSummary,
  Target,
} from '../../api/inbox'
import {
  getInboxMessage,
  getInboxSummary,
  listActionItems,
  listInboxMessages,
  proposeForMessage,
} from '../../api/inbox'
import type { TripSummary } from '../../api/trips'
import { listTrips } from '../../api/trips'
import { AppShell } from '../trips/AppShell'
import { formatDate, parseIsoDate } from '../trips/format'
import { ActionItemSheet } from './ActionItemSheet'
import { MessageView } from './MessageView'
import { PlaceMessage } from './PlaceMessage'
import { QuarantineRegion } from './QuarantineRegion'
import { TargetPicker } from './TargetPicker'

/**
 * `/inbox` — what the account's forwarding address has taken delivery of.
 *
 * **The regions, in the order his attention should go**: *action items
 * awaiting you* first — proposals the owner approves field by field (D21) — then
 * the *unrouted* queue, the rest of his mail, and the *quarantined* count.
 *
 * **Honest freshness, and it is load-bearing.** The screen says when SES last
 * delivered and when ingestion last failed, because an empty inbox and a broken
 * inbox must not look the same: without this, a dead SNS subscription renders
 * identically to a quiet week, and he would find out when a confirmation he was
 * sure he forwarded never turned up.
 *
 * **An unconfigured deployment is a normal state**, not a fault. The screen
 * explains itself and shows no error; the nav badge is simply absent.
 */
export function InboxPage() {
  const { t, i18n } = useTranslation()
  const [summary, setSummary] = useState<InboxSummary | null>(null)
  const [messages, setMessages] = useState<InboxMessage[] | null>(null)
  const [actionItems, setActionItems] = useState<ActionItem[]>([])
  const [reviewing, setReviewing] = useState<string | null>(null)
  /**
   * Set when a decided sheet closes. The button that opened it belongs to a
   * proposal the reload is about to remove, so the sheet's own focus return
   * would land on a node that then vanishes and leave focus on `<body>`. Once
   * the list has re-rendered, focus moves to the page heading instead.
   */
  const refocus = useRef(false)
  const [trips, setTrips] = useState<TripSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    (signal?: AbortSignal) => {
      setError(null)
      getInboxSummary(signal)
        .then((loaded) => {
          setSummary(loaded)
          if (!loaded.inbox_enabled) {
            // Nothing else to ask for: every other inbox route answers
            // `inbox_not_configured`, and asking anyway would paint an error
            // over a screen whose whole job here is to explain calmly.
            setMessages([])
            return
          }
          return Promise.all([
            listInboxMessages(signal),
            listTrips(signal),
            listActionItems(signal),
          ]).then(([loadedMessages, loadedTrips, loadedActionItems]) => {
            setMessages(loadedMessages)
            setTrips(loadedTrips)
            setActionItems(loadedActionItems)
          })
        })
        .catch((caught: unknown) => {
          if (signal?.aborted) {
            return
          }
          if (caught instanceof ApiError && caught.isUnauthenticated) {
            return
          }
          setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
        })
    },
    [t],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  useEffect(() => {
    if (!refocus.current) {
      return
    }
    refocus.current = false
    const heading =
      document.getElementById('inbox-actions-heading') ?? document.querySelector('main h1')
    if (heading instanceof HTMLElement) {
      heading.setAttribute('tabindex', '-1')
      heading.focus()
    }
  }, [actionItems])

  const unrouted = (messages ?? []).filter((one) => one.state === 'unrouted')
  const rest = (messages ?? []).filter((one) => one.state !== 'unrouted')

  return (
    <AppShell title={t('inbox.title')}>
      {error !== null && <p role="alert">{error}</p>}

      {error === null && summary === null && <p role="status">{t('app.loading')}</p>}

      {summary !== null && !summary.inbox_enabled && (
        <section className="empty-state">
          <h2>{t('inbox.disabledTitle')}</h2>
          <p>{t('inbox.disabledBody')}</p>
        </section>
      )}

      {summary !== null && summary.inbox_enabled && (
        <>
          <DeliveryStatus summary={summary} locale={i18n.language} />

          {actionItems.length > 0 && (
            <section className="inbox-region" aria-labelledby="inbox-actions-heading">
              <h2 id="inbox-actions-heading">{t('inbox.actionsTitle')}</h2>
              <ul className="inbox-list">
                {actionItems.map((actionItem) => (
                  <ActionItemCard
                    key={actionItem.id}
                    actionItem={actionItem}
                    onReview={() => setReviewing(actionItem.id)}
                  />
                ))}
              </ul>
            </section>
          )}

          {messages !== null && messages.length === 0 && summary.quarantined === 0 && (
            <section className="empty-state">
              <h2>{t('inbox.emptyTitle')}</h2>
              {/* The address, because the empty state's whole job is to tell
                  him the one thing he needs in order to make it non-empty. */}
              <p>{t('inbox.emptyBody', { address: summary.address })}</p>
              <p className="inbox-address">{summary.address}</p>
            </section>
          )}

          {unrouted.length > 0 && (
            <section className="inbox-region" aria-labelledby="inbox-unrouted-heading">
              <h2 id="inbox-unrouted-heading">{t('inbox.unroutedTitle')}</h2>
              <ul className="inbox-list">
                {unrouted.map((message) => (
                  <MessageRow
                    key={message.id}
                    message={message}
                    trips={trips}
                    onChanged={() => load()}
                    onReview={setReviewing}
                  />
                ))}
              </ul>
            </section>
          )}

          {rest.length > 0 && (
            <section className="inbox-region" aria-labelledby="inbox-mail-heading">
              <h2 id="inbox-mail-heading">{t('inbox.mailTitle')}</h2>
              <ul className="inbox-list">
                {rest.map((message) => (
                  <MessageRow
                    key={message.id}
                    message={message}
                    trips={trips}
                    onChanged={() => load()}
                    onReview={setReviewing}
                  />
                ))}
              </ul>
            </section>
          )}

          <QuarantineRegion count={summary.quarantined} onRecovered={() => load()} />
        </>
      )}

      {reviewing !== null && (
        <ActionItemSheet
          actionItemId={reviewing}
          onClose={(changed) => {
            setReviewing(null)
            if (changed) {
              refocus.current = true
              load()
            }
          }}
        />
      )}
    </AppShell>
  )
}

/**
 * A reason's arguments, with its dates turned into real `Date`s.
 *
 * The server sends `{from: '2026-10-04'}` — a string, because that is what
 * crosses JSON honestly — and the ICU message formats it as
 * `{from, date, medium}`. Converting here is what makes "no trip covers
 * 4–11 October" read correctly in Polish and English from one key, rather than
 * the server shipping a formatted date in one language and the screen
 * displaying it in the other.
 *
 * `parseIsoDate` rather than `new Date(iso)`: the latter parses as UTC midnight
 * and renders as the day before for anyone west of Greenwich, which the trip
 * screens already learned.
 */
function reasonArguments(message: InboxMessage): Record<string, unknown> {
  const args = message.routing_reason_args ?? {}

  return Object.fromEntries(
    Object.entries(args).map(([key, value]) => [
      key,
      /^\d{4}-\d{2}-\d{2}$/u.test(value) ? parseIsoDate(value) : value,
    ]),
  )
}

/**
 * When SES last delivered, and when ingestion last failed.
 *
 * Shown always, not only on failure. "Nothing has arrived" and "nothing has
 * arrived *and the last five attempts failed*" are different facts, and the
 * screen that only mentioned the second when it was bad would still be silent
 * in the case that matters most: a subscription that stopped delivering weeks
 * ago and has therefore had nothing to fail at.
 */
function DeliveryStatus({ summary, locale }: { summary: InboxSummary; locale: string }) {
  const { t } = useTranslation()
  const when = (iso: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
      new Date(iso),
    )

  return (
    <p className="inbox-status">
      {summary.last_received_at === null
        ? t('inbox.neverReceived')
        : t('inbox.lastReceived', { when: when(summary.last_received_at) })}
      {summary.last_error_at !== null && (
        <>
          {' '}
          <span className="inbox-status__error">
            {t('inbox.lastError', {
              when: when(summary.last_error_at),
              // A translated code, never the server's string.
              reason: t(`inbox.reason.${summary.last_error ?? 'ingest_failed'}`),
            })}
          </span>
        </>
      )}
    </p>
  )
}

/**
 * One message: its headers, an expander for its text and documents, and — when
 * it is unrouted — the control that places it on a trip.
 *
 * The detail is fetched on expand rather than with the list, because the list
 * deliberately carries no bodies: a page of twenty messages would otherwise
 * pull twenty full texts nobody has asked to read.
 */
function MessageRow({
  message,
  trips,
  onChanged,
  onReview,
}: {
  message: InboxMessage
  trips: TripSummary[]
  onChanged: () => void
  onReview: (actionItemId: string) => void
}) {
  const { t, i18n } = useTranslation()
  const [detail, setDetail] = useState<InboxMessageDetail | null>(null)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = () => {
    if (open) {
      setOpen(false)
      return
    }
    setOpen(true)
    if (detail !== null) {
      return
    }
    getInboxMessage(message.id)
      .then(setDetail)
      .catch((caught: unknown) => {
        setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      })
  }

  const received = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(message.received_at))

  const placedOn = trips.find((trip) => trip.id === message.trip_id)

  return (
    <li className="inbox-row">
      <p className="inbox-row__from">{message.from_address}</p>
      <p className="inbox-row__subject">{message.subject}</p>
      <p className="inbox-row__meta">
        {received}
        {message.attachment_count > 0 && (
          <> · {t('inbox.documentCount', { count: message.attachment_count })}</>
        )}
      </p>

      {/* Every reason the owner reads is a translated key with arguments, never
          a string the server composed — which is what stops an untranslated or
          injected sentence reaching the screen through the locale layer. */}
      {message.routing_reason !== null && (
        <p className="inbox-row__reason">
          {t(`inbox.reason.${message.routing_reason}`, reasonArguments(message))}
        </p>
      )}

      {/* The trip's **current** name, read from the loaded list rather than
          from the reason's stored arguments: renaming a trip should rename it
          here too. The stored argument stays in the database as a record of
          what it matched at the time, which is a different question. */}
      {placedOn !== undefined && (
        <p className="inbox-row__trip">
          {t('inbox.routedTo')} <Link to={`/trips/${placedOn.id}`}>{placedOn.title}</Link>
        </p>
      )}

      <button type="button" className="button-quiet" onClick={toggle} aria-expanded={open}>
        {open ? t('inbox.hide') : t('inbox.open')}
      </button>

      {error !== null && <p role="alert">{error}</p>}

      {open && detail === null && error === null && <p role="status">{t('app.loading')}</p>}
      {open && detail !== null && <MessageView message={detail} />}

      {/* A proposal already exists: open it. Otherwise, for a message on a
          trip, the owner may propose a placement himself — documents onto an
          item, still approved like any other write (D21). */}
      {open && detail !== null && detail.action_item_ids.length > 0 && (
        <button
          type="button"
          className="button-quiet"
          onClick={() => onReview(detail.action_item_ids[0] ?? '')}
        >
          {t('inbox.review')}
        </button>
      )}
      {open &&
        detail !== null &&
        detail.action_item_ids.length === 0 &&
        detail.trip_id !== null &&
        detail.attachments.length > 0 && (
          <TargetPicker
            tripId={detail.trip_id}
            label={t('inbox.proposeLabel')}
            actionLabel={t('inbox.propose')}
            busyLabel={t('inbox.proposing')}
            onChoose={(target: Target) =>
              proposeForMessage(message.id, target)
                .then((created) => onReview(created.id))
                .catch((caught: unknown) => {
                  setError(
                    caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'),
                  )
                })
            }
          />
        )}

      {(message.state === 'unrouted' || message.state === 'received') && (
        <PlaceMessage message={message} trips={trips} onPlaced={onChanged} />
      )}

      {/* Re-placement. Offered on a message that already has a trip because the
          match may simply be wrong — and correcting it is the same request and
          the same single column, so it is the same control under a different
          label rather than a second flow. */}
      {message.state === 'routed' && (
        <PlaceMessage
          message={message}
          trips={trips}
          onPlaced={onChanged}
          label={t('inbox.changeTrip')}
        />
      )}
    </li>
  )
}

/**
 * One proposal awaiting the owner: where it points, how many fields it claims,
 * and whether a document came with it. The sheet is where it is decided.
 */
function ActionItemCard({
  actionItem,
  onReview,
}: {
  actionItem: ActionItem
  onReview: () => void
}) {
  const { t, i18n } = useTranslation()
  const date =
    actionItem.target_date === null ? '' : formatDate(actionItem.target_date, i18n.language)
  const changes =
    actionItem.fields.filter((row) => row.changed).length + (actionItem.status?.changed ? 1 : 0)

  let where: string
  if (actionItem.target_item_id !== null) {
    where = t('inbox.sheet.updates', { title: actionItem.target_item_title ?? '', date })
  } else if (actionItem.target_trip_day_id !== null) {
    where = t('inbox.sheet.creates', { date })
  } else {
    where = t('inbox.sheet.needsTarget')
  }

  return (
    <li className="inbox-row">
      <p className="inbox-row__from">{actionItem.from_address}</p>
      <p className="inbox-row__subject">{actionItem.subject}</p>
      <p className="inbox-row__trip">
        {actionItem.trip_title !== null && <>{actionItem.trip_title} · </>}
        {where}
      </p>
      <p className="inbox-row__meta">
        {/* Only what would change: a duplicate forward claims five fields the
            item already holds, and "5 fields" on its card promised work the
            sheet then showed did not exist (QA, #22). */}
        {changes === 0 && actionItem.attachments.length === 0
          ? t('inbox.upToDate')
          : t('inbox.claimCount', { count: changes })}
        {actionItem.attachments.length > 0 && (
          <> · {t('inbox.documentCount', { count: actionItem.attachments.length })}</>
        )}
      </p>
      <button type="button" className="button-primary" onClick={onReview}>
        {t('inbox.review')}
      </button>
    </li>
  )
}
