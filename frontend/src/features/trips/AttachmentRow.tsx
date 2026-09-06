import { useTranslation } from 'react-i18next'

import type { Attachment } from '../../api/attachments'
import { attachmentContentUrl } from '../../api/attachments'
import { Icon } from '../../components/Icon'
import { splitByteSize } from './format'

/**
 * One attachment, as a card row — shared verbatim by `DayAttachments` (the
 * day-level panel) and `ItemAttachments` (the strip inside the item editor).
 * The row itself does not know or care which parent the file is pinned to,
 * so it is factored out here rather than defined twice: a second copy would
 * be the same markup drifting into two shapes of the same thing the moment
 * either host's rendering changed without the other.
 *
 * **Download and delete are Step 2.5's, not this one's.** A row is readable
 * without them — a preview or glyph, a filename and a size already say what
 * the file is — so none is stubbed in here; adding either action extends
 * this same markup rather than redesigning it.
 */
const IMAGE_CONTENT_TYPES = new Set(['image/jpeg', 'image/png'])

export function AttachmentRow({ tripId, attachment }: { tripId: string; attachment: Attachment }) {
  const { t } = useTranslation()
  const size = splitByteSize(attachment.byte_size)

  return (
    <div className="attachment-row">
      {IMAGE_CONTENT_TYPES.has(attachment.content_type) ? (
        // The original file, scaled by the browser in CSS — never a
        // server-generated thumbnail (A12: the server never decodes an
        // image). Lazy-loaded because a parent can carry several of these, and
        // the filename is the alt text, not a caption beside it.
        <img
          className="attachment-row__preview"
          src={attachmentContentUrl(tripId, attachment.id)}
          alt={attachment.filename}
          loading="lazy"
        />
      ) : (
        <span className="attachment-row__glyph" aria-hidden="true">
          <Icon name="document" />
        </span>
      )}

      <span className="attachment-row__meta">
        <span className="attachment-row__name">{attachment.filename}</span>
        <span className="attachment-row__size">
          {t('attachment.size', { value: size.value, unit: size.unit })}
        </span>
      </span>
    </div>
  )
}
