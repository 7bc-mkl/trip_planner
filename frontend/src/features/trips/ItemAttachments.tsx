import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Attachment } from '../../api/attachments'
import type { Item } from '../../api/items'
import { AttachmentRow } from './AttachmentRow'
import { UploadDropzone } from './UploadDropzone'

/**
 * The item-level attachment strip — hosted inside `ItemDialog`, next to the
 * fields a voucher or a ticket evidences. That is the split the design export
 * implies with its per-item ticket pills next to its separate day panel, and
 * it is the split the data model enforces: an attachment is pinned to
 * exactly one of a day or an item, never both.
 *
 * The row itself is `AttachmentRow`, shared verbatim with `DayAttachments` —
 * the same card, a different host, rather than a second copy of the same
 * markup drifting on its own.
 *
 * **The new-item case (`item === null`).** An item that has not been saved
 * yet has no id to pin a file to: `POST /trips/{tripId}/items/{itemId}/attachments`
 * needs a real `itemId`, and there is none until the first Save. Rather than
 * render a dropzone that would have nothing to upload to, this renders an
 * explanatory line instead and no upload control at all — save the item,
 * reopen it, then attach files to it. Nothing here throws; there is simply
 * nothing to click.
 *
 * **Attachments accumulate locally, across the dialog's one open session.**
 * The list starts from `item.attachments` — present because the day-detail
 * payload that opened this dialog already carries it — and a completed
 * upload is appended to it directly, the same pattern `UploadDropzone`'s own
 * rows use, so adding three files in a row does not flicker through a parent
 * refetch between each one. `onUploaded` still bubbles further up so the day
 * list's own paperclip count catches up without waiting for Save.
 *
 * **Delete follows the same local-first shape.** A row's own delete (Step
 * 2.5, on the shared `AttachmentRow`) already called the API and awaited it
 * before reporting back here, so removing the entry from local state is safe;
 * `onDeleted` then bubbles up exactly like `onUploaded` does, so the day
 * list's paperclip count catches up too.
 */
export function ItemAttachments({
  tripId,
  item,
  onUploaded,
  onDeleted,
}: {
  tripId: string
  /** The item being edited, or `null` when adding a new one — see the module doc. */
  item: Item | null
  onUploaded: (attachment: Attachment) => void
  /** Called once any row's delete succeeds, so the day list's paperclip count catches up. */
  onDeleted: () => void
}) {
  const { t } = useTranslation()
  const [attachments, setAttachments] = useState<Attachment[]>(item?.attachments ?? [])

  function handleUploaded(attachment: Attachment) {
    setAttachments((previous) => [...previous, attachment])
    onUploaded(attachment)
  }

  function handleDeleted(attachmentId: string) {
    setAttachments((previous) => previous.filter((entry) => entry.id !== attachmentId))
    onDeleted()
  }

  return (
    <section className="item-attachments">
      <h3 className="item-attachments__heading">{t('itemAttachments.heading')}</h3>

      {attachments.length === 0 ? (
        <p className="empty-state empty-state--inline">{t('itemAttachments.empty')}</p>
      ) : (
        <ul className="item-attachments__list" aria-label={t('itemAttachments.list')}>
          {attachments.map((attachment) => (
            <li key={attachment.id}>
              <AttachmentRow
                tripId={tripId}
                attachment={attachment}
                onDeleted={() => handleDeleted(attachment.id)}
              />
            </li>
          ))}
        </ul>
      )}

      {item === null ? (
        <p className="hint">{t('itemAttachments.saveFirst')}</p>
      ) : (
        <UploadDropzone
          target={{ kind: 'item', tripId, itemId: item.id }}
          onUploaded={handleUploaded}
        />
      )}
    </section>
  )
}
