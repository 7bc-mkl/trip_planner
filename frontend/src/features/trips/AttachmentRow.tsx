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
 *
 * **The duplicate hint (A14) rides on this row, because this row *is* the
 * file.** It is one extra muted line under the size — never a second card,
 * never a banner of its own — so it cannot become a second representation of
 * the attachment: there is nothing to render when the row is not rendered, and
 * deleting the file takes its hint with it. The verdict is not remembered from
 * the upload that produced it; it is derived on every render from the host's
 * own list (`duplicatedSha256s` below), which is why it survives the refetch
 * that retires the upload queue's row — the defect Step 4.3 shipped with — and
 * why it stops being shown the moment one of the two copies is deleted.
 */
const IMAGE_CONTENT_TYPES = new Set(['image/jpeg', 'image/png'])

/**
 * The hashes that appear **more than once** in one parent's list — i.e. the
 * same bytes attached here twice.
 *
 * Scoping falls out of the caller rather than out of anything here: each host
 * (`DayAttachments`, `ItemAttachments`) only ever passes its own parent's
 * attachments, so the same file on two different parents is two legitimate
 * attachments and matches nothing. Nothing is deduplicated and nothing is
 * refused (A14): both copies are in the list that produced this set, and both
 * keep their row, their download and their delete.
 */
export function duplicatedSha256s(attachments: readonly Attachment[]): ReadonlySet<string> {
  const seen = new Set<string>()
  const twice = new Set<string>()
  for (const attachment of attachments) {
    if (seen.has(attachment.sha256)) {
      twice.add(attachment.sha256)
    }
    seen.add(attachment.sha256)
  }
  return twice
}

export function AttachmentRow({
  tripId,
  attachment,
  duplicate = false,
  onDeleted,
}: {
  tripId: string
  attachment: Attachment
  /**
   * True when the same bytes are attached to this same parent more than once —
   * see `duplicatedSha256s`. Informational only (A14): it adds a line and
   * nothing else, no error, no undo, no dismissal.
   */
  duplicate?: boolean
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
        {/* Non-blocking (A14): no `role="alert"`, no action of its own, and no
            bearing on the row it sits in — the file exists, downloads and
            deletes exactly like any other. The same one sentence the upload
            queue uses while *it* is still the file's only representation, so
            there is one key, not two that could drift apart. */}
        {duplicate && (
          <span className="attachment-row__duplicate-hint">{t('upload.duplicateHint')}</span>
        )}
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
