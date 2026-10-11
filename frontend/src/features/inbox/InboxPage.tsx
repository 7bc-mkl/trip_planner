import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import type { InboxMessage, InboxMessageDetail, InboxSummary } from '../../api/inbox'
import { getInboxMessage, getInboxSummary, listInboxMessages } from '../../api/inbox'
import type { TripSummary } from '../../api/trips'
import { listTrips } from '../../api/trips'
import { AppShell } from '../trips/AppShell'
import { MessageView } from './MessageView'
import { PlaceMessage } from './PlaceMessage'
import { QuarantineRegion } from './QuarantineRegion'

/**
 * `/inbox` — what the account's forwarding address has taken delivery of.
 *
 * **Three regions, in the order his attention should go.** The spec's first
 * region is *action items awaiting you*, and it is deliberately absent here:
 * action items arrive with the extraction phase, and an always-empty region
 * would promise a feature this build does not have. Its place is taken by the
 * mail that has been placed or is ready to be read, which is what Phase 1
 * actually produces. The other two — *unrouted* and *quarantined* — are the
 * spec's, unchanged.
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
          return Promise.all([listInboxMessages(signal), listTrips(signal)]).then(
            ([loadedMessages, loadedTrips]) => {
              setMessages(loadedMessages)
              setTrips(loadedTrips)
            },
          )
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
                  />
                ))}
              </ul>
            </section>
          )}

          <QuarantineRegion count={summary.quarantined} onRecovered={() => load()} />
        </>
      )}
    </AppShell>
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
}: {
  message: InboxMessage
  trips: TripSummary[]
  onChanged: () => void
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
        <p className="inbox-row__reason">{t(`inbox.reason.${message.routing_reason}`)}</p>
      )}

      <button type="button" className="button-quiet" onClick={toggle} aria-expanded={open}>
        {open ? t('inbox.hide') : t('inbox.open')}
      </button>

      {error !== null && <p role="alert">{error}</p>}

      {open && detail === null && error === null && <p role="status">{t('app.loading')}</p>}
      {open && detail !== null && <MessageView message={detail} />}

      {message.state === 'unrouted' && (
        <PlaceMessage message={message} trips={trips} onPlaced={onChanged} />
      )}
    </li>
  )
}
