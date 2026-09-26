import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import type { InboxSummary } from '../../api/inbox'
import { getInboxSummary } from '../../api/inbox'

/**
 * The header's inbox link, with what is waiting on it.
 *
 * Self-fetching rather than fed from above, because the screens that show it
 * have nothing to do with the inbox and threading a summary through them would
 * make every one of them import an inbox type. `GET /inbox/summary` is a single
 * cheap row precisely so this can be its own concern.
 *
 * **It renders nothing at all when there is nothing to say** — an unconfigured
 * deployment, or a quiet inbox. An absent badge is the honest rendering of
 * "the inbox is off", and a zero would invite the question of what it counts.
 *
 * The count is announced through `aria-live`, so a message arriving while he is
 * on another screen reaches a screen-reader user rather than only a sighted one.
 */
export function InboxBadge() {
  const { t } = useTranslation()
  const [summary, setSummary] = useState<InboxSummary | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getInboxSummary(controller.signal)
      .then(setSummary)
      // Silent on purpose. The badge is chrome on screens that are about
      // something else; a failed poll must not put an error on a trip page.
      .catch(() => undefined)
    return () => controller.abort()
  }, [])

  if (summary === null || !summary.inbox_enabled) {
    return null
  }

  const waiting = summary.unrouted + summary.quarantined

  return (
    <Link className="button-quiet inbox-badge" to="/inbox">
      {t('nav.inbox')}
      {waiting > 0 && (
        <span className="inbox-badge__count" aria-live="polite">
          {t('inbox.waitingCount', { count: waiting })}
        </span>
      )}
    </Link>
  )
}
