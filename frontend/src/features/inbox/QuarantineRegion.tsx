import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import type { QuarantinedMessage } from '../../api/inbox'
import { listQuarantined, releaseMessage, trustSender } from '../../api/inbox'

/**
 * The quarantine region: **a count, and headers on request.**
 *
 * Three rules, and each of them is the control rather than a presentation
 * choice:
 *
 * - **No body, no attachment, no preview — ever.** That is what keeps
 *   quarantine a barrier rather than a delivery mechanism for content the owner
 *   never asked to see. There is no code path here that could render one: the
 *   type this component holds has no field for it.
 * - **Headers are shown on request, not by default.** A bare count would make a
 *   real loss silent — a mailbox rule that auto-forwards an airline's
 *   confirmation while preserving the airline's `From` lands here — but a list
 *   that showed every stranger's subject line by default would put unsolicited
 *   text on the screen the moment he opens the app. *Show* is the middle.
 * - **Only the action the reason permits is offered.** *Trust this sender* for
 *   an authenticated address that is merely unknown; *Release this message* for
 *   a failed authentication, once, for that message alone. Offering both would
 *   let him pick the weaker one by accident, and offering either for a failed
 *   scan would be asking him to overrule a virus verdict.
 */
export function QuarantineRegion({
  count,
  onRecovered,
}: {
  count: number
  onRecovered: () => void
}) {
  const { t } = useTranslation()
  const [shown, setShown] = useState<QuarantinedMessage[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (count === 0) {
    return null
  }

  return (
    <section className="inbox-region" aria-labelledby="inbox-quarantine-heading">
      <h2 id="inbox-quarantine-heading">{t('inbox.quarantineTitle')}</h2>
      {/* The ICU plural, which is what exercises Polish's `few`/`many` — the
          reason the project uses i18next-icu at all. */}
      <p>{t('inbox.quarantineCount', { count })}</p>

      {shown === null && (
        <button type="button" className="button-quiet" onClick={() => void show()}>
          {t('inbox.quarantineShow')}
        </button>
      )}

      {error !== null && <p role="alert">{error}</p>}

      {shown !== null && shown.length > 0 && (
        <ul className="inbox-quarantine">
          {shown.map((message) => (
            <QuarantineRow key={message.id} message={message} onRecovered={onRecovered} />
          ))}
        </ul>
      )}
    </section>
  )

  async function show() {
    setError(null)
    try {
      // Fetched only when he asks. The summary carries a count and no
      // addresses, so nothing about these senders has reached the browser
      // before this click.
      setShown(await listQuarantined())
    } catch (caught) {
      setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
    }
  }
}

function QuarantineRow({
  message,
  onRecovered,
}: {
  message: QuarantinedMessage
  onRecovered: () => void
}) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const act = (action: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    action()
      .then(() => onRecovered())
      .catch((caught: unknown) => {
        setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      })
      .finally(() => setBusy(false))
  }

  return (
    <li>
      <p className="inbox-quarantine__from">{message.from_address}</p>
      <p className="inbox-quarantine__subject">{message.subject}</p>
      {/* A translated key, never the server's string: the reason is a stable
          code precisely so no model-authored or sender-authored text can reach
          the screen through the locale layer. */}
      {message.reason !== null && (
        <p className="inbox-quarantine__reason">{t(`inbox.reason.${message.reason}`)}</p>
      )}

      {!message.recoverable && (
        <p className="inbox-quarantine__reason">{t('inbox.quarantineExpired')}</p>
      )}

      {message.recoverable && message.may_trust_sender && (
        <button
          type="button"
          className="button-quiet"
          disabled={busy}
          onClick={() => act(() => trustSender(message.id))}
        >
          {t('inbox.trustSender')}
        </button>
      )}

      {message.recoverable && message.may_release_message && (
        <button
          type="button"
          className="button-quiet"
          disabled={busy}
          onClick={() => act(() => releaseMessage(message.id))}
        >
          {t('inbox.releaseMessage')}
        </button>
      )}

      {error !== null && <p role="alert">{error}</p>}
    </li>
  )
}
