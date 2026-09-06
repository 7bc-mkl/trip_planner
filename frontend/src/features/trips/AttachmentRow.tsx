import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Attachment } from '../../api/attachments'
import { attachmentContentUrl, deleteAttachment } from '../../api/attachments'
import { Icon } from '../../components/Icon'
import { ConfirmDialog } from './ConfirmDialog'
import { splitByteSize } from './format'
import { Lightbox } from './Lightbox'

/**
 * One attachment, as a card row — shared verbatim by `DayAttachments` (the
 * day-level panel) and `ItemAttachments` (the strip inside the item editor).
 * The row itself does not know or care which parent the file is pinned to,
 * so it is factored out here rather than defined twice: a second copy would
 * be the same markup drifting into two shapes of the same thing the moment
 * either host's rendering changed without the other.
 *
 * **Download** is a plain link to `attachmentContentUrl`, not a click handler
 * that fetches the bytes into memory to build a blob URL — the server already
 * answers with `Content-Disposition: attachment` on every content type, so the
 * browser's own download handling is enough. Its label is "Download"/"Pobierz",
 * deliberately never "Preview": inline PDF preview is cut (A10) because serving
 * a PDF `inline` would run its JavaScript in this origin with the session
 * cookie in scope, and promising a preview while delivering a download is the
 * kind of small lie that erodes trust in the tool.
 *
 * **Delete** is behind `ConfirmDialog`, the same shipped confirmation trip
 * delete uses, and for the same reason: there is no undo in this milestone, so
 * the dialog naming the file is the whole safety net.
 *
 * **Images open in `Lightbox`** (Step 4.2) when their preview is clicked; a
 * PDF's glyph is not a button at all, so clicking it does nothing — the PDF
 * action stays "Pobierz"/"Download", never a preview (A10).
 */
const IMAGE_CONTENT_TYPES = new Set(['image/jpeg', 'image/png'])

export function AttachmentRow({
  tripId,
  attachment,
  onDeleted,
}: {
  tripId: string
  attachment: Attachment
  /** Called once the attachment is gone server-side, so the host list can refresh. */
  onDeleted: () => void
}) {
  const { t } = useTranslation()
  const size = splitByteSize(attachment.byte_size)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const isImage = IMAGE_CONTENT_TYPES.has(attachment.content_type)
  const contentUrl = attachmentContentUrl(tripId, attachment.id)

  return (
    <div className="attachment-row">
      {isImage ? (
        // A real button, not the `<img>` itself: an image is not natively
        // interactive, and the click target has to be one for the lightbox to
        // have a trigger to focus-return to when it closes. The original
        // file, scaled by the browser in CSS — never a server-generated
        // thumbnail (A12: the server never decodes an image). Lazy-loaded
        // because a parent can carry several of these, and the filename is
        // the alt text, not a caption beside it.
        <button
          type="button"
          className="attachment-row__preview-trigger"
          onClick={() => setLightboxOpen(true)}
        >
          <img
            className="attachment-row__preview"
            src={contentUrl}
            alt={attachment.filename}
            loading="lazy"
          />
        </button>
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

      <span className="attachment-row__actions">
        {/* A real link, not a button: the server's `Content-Disposition:
            attachment` header does the downloading, so there is nothing for a
            click handler to do — and nothing here ever reads the bytes into
            memory to build a blob URL. */}
        <a className="button-quiet" href={contentUrl}>
          {t('attachment.download')}
        </a>
        <button type="button" className="button-danger" onClick={() => setConfirmingDelete(true)}>
          {t('attachment.delete')}
        </button>
      </span>

      {confirmingDelete && (
        <ConfirmDialog
          title={t('attachment.deleteTitle')}
          // Naming the file is the point: there is no undo, so the owner has
          // to be able to tell *what* is about to go.
          message={t('attachment.deleteMessage', { filename: attachment.filename })}
          confirmLabel={t('attachment.deleteConfirm')}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={async () => {
            await deleteAttachment(tripId, attachment.id)
            setConfirmingDelete(false)
            onDeleted()
          }}
        />
      )}

      {lightboxOpen && (
        <Lightbox
          src={contentUrl}
          filename={attachment.filename}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </div>
  )
}
