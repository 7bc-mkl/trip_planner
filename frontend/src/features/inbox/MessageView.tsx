import { useTranslation } from 'react-i18next'

import type { InboxMessageDetail } from '../../api/inbox'
import { inboxAttachmentUrl } from '../../api/inbox'
import { Icon } from '../../components/Icon'
import { splitByteSize } from '../trips/format'

/**
 * One message, opened: its text and its documents.
 *
 * **The body is rendered as text and only as text.** It is in a `<p>` with
 * `white-space: pre-wrap`, never `dangerouslySetInnerHTML` and never a
 * sanitiser's output — the server already reduced any HTML to text and threw
 * the markup away, so there is nothing here to render and nothing to sanitise.
 * That is also what makes "remote content is never fetched" true on this side
 * of the wire: there is no `<img>`, no stylesheet and no link for a tracking
 * pixel to hide in, because there is no markup at all.
 *
 * **Documents are downloads, never previews**, exactly as on the day panel and
 * for the same reason (A10): serving a PDF `inline` would run its JavaScript in
 * this origin with the session cookie in scope. The link goes straight to the
 * content route, whose `Content-Disposition: attachment` does the rest.
 */
export function MessageView({ message }: { message: InboxMessageDetail }) {
  const { t } = useTranslation()

  return (
    <div className="inbox-message">
      {message.text_body === '' ? (
        <p className="inbox-message__empty">{t('inbox.noText')}</p>
      ) : (
        // `pre-wrap` in the stylesheet, so the sender's line breaks survive
        // without a single tag being introduced to carry them.
        <p className="inbox-message__body">{message.text_body}</p>
      )}

      {message.attachments.length > 0 && (
        <ul className="inbox-message__documents">
          {message.attachments.map((attachment) => {
            const { value, unit } = splitByteSize(attachment.byte_size)
            return (
              <li key={attachment.id}>
                <Icon name="paperclip" />
                <span className="inbox-message__filename">{attachment.filename}</span>
                {/* The shipped `attachment.size` key, whose ICU value formats
                    the number itself — so the size reads the same here as it
                    does on the day panel, in whichever locale is active. */}
                <span className="inbox-message__size">
                  {t('attachment.size', { value, unit })}
                </span>
                <a
                  className="button-quiet"
                  href={inboxAttachmentUrl(message.id, attachment.id)}
                  download={attachment.filename}
                >
                  {t('attachment.download')}
                </a>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
