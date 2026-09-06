import { useTranslation } from 'react-i18next'

import type { Attachment } from '../../api/attachments'
import { AttachmentRow, duplicatedSha256s } from './AttachmentRow'
import { UploadDropzone } from './UploadDropzone'

/**
 * The day-level documents panel — hosted by `DayDetailPage`, below the item
 * list, at the position the design-system spec already declared for it.
 *
 * Renders the attachments pinned to the **day itself** (the printed
 * reservation for the whole day, the ferry timetable) as opposed to the ones
 * pinned to an item, which travel with the item and render inside the item
 * editor instead (a later Step).
 *
 * **Download and delete** live on the shared `AttachmentRow` (Step 2.5). This
 * panel does not own the day's attachment list — `DayDetailPage` fetches it as
 * part of the same `DayDetail` payload — so a delete here is reported upward
 * through `onDeleted` exactly like an upload already is through `onUploaded`:
 * the host refetches the day and the panel simply re-renders with whatever
 * list comes back.
 *
 * There is no attachments-only load-error state to design for: `attachments`
 * arrives as part of the same `DayDetail` payload `DayDetailPage` already
 * fetches, so a failure there fails the whole day fetch, which
 * `DayDetailPage` already renders as an alert rather than as this panel's
 * empty state — the "never an empty list on a load error" guarantee the spec
 * asks for holds by construction, not by anything added here.
 *
 * The row itself is `AttachmentRow`, shared with the item editor's own strip
 * rather than redrawn here — see that module's doc for why.
 */

export function DayAttachments({
  tripId,
  date,
  attachments,
  onUploaded,
  onDeleted,
}: {
  tripId: string
  /** The day this panel's dropzone uploads onto — the day's own date, not an item's. */
  date: string
  attachments: Attachment[]
  onUploaded: (attachment: Attachment) => void
  /** Called once a row's own delete succeeds, so the host can refetch the day. */
  onDeleted: () => void
}) {
  const { t } = useTranslation()
  // Derived on every render from the list this panel is showing, so the
  // duplicate hint (A14) appears on the very render that first paints the
  // second copy — the same render that retires the upload queue's own row.
  const duplicated = duplicatedSha256s(attachments)

  return (
    <section className="day-attachments">
      <h2 className="day-attachments__heading">{t('dayAttachments.heading')}</h2>

      {attachments.length === 0 ? (
        <p className="empty-state empty-state--inline">{t('dayAttachments.empty')}</p>
      ) : (
        <ul className="day-attachments__list" aria-label={t('dayAttachments.list')}>
          {attachments.map((attachment) => (
            <li key={attachment.id}>
              <AttachmentRow
                tripId={tripId}
                attachment={attachment}
                duplicate={duplicated.has(attachment.sha256)}
                onDeleted={onDeleted}
              />
            </li>
          ))}
        </ul>
      )}

      {/* The list this panel is showing, handed back to the drop zone so a
          finished upload's queue row retires once the refetched list carries
          it — the file is shown once, as an attachment row, and the queue
          cannot outlive a later delete. See `UploadDropzone`'s own note. The
          hashes travel alongside for the same reason and scope: this day's
          own attachments, so the non-blocking duplicate hint (A14) only ever
          fires for a file already attached to *this* day. */}
      <UploadDropzone
        target={{ kind: 'day', tripId, date }}
        onUploaded={onUploaded}
        listedAttachmentIds={attachments.map((attachment) => attachment.id)}
        listedAttachmentHashes={attachments.map((attachment) => attachment.sha256)}
      />
    </section>
  )
}
