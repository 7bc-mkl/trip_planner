import { useTranslation } from 'react-i18next'

import type { Attachment } from '../../api/attachments'
import { AttachmentRow } from './AttachmentRow'
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
 * **Download and delete are a later Step's, not this one's.** A row is
 * readable without them — a preview or glyph, a filename and a size already
 * say what the file is — so none is stubbed in here; adding either action is
 * exactly the same markup this component's callers will extend, not a
 * redesign of it.
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
}: {
  tripId: string
  /** The day this panel's dropzone uploads onto — the day's own date, not an item's. */
  date: string
  attachments: Attachment[]
  onUploaded: (attachment: Attachment) => void
}) {
  const { t } = useTranslation()

  return (
    <section className="day-attachments">
      <h2 className="day-attachments__heading">{t('dayAttachments.heading')}</h2>

      {attachments.length === 0 ? (
        <p className="empty-state empty-state--inline">{t('dayAttachments.empty')}</p>
      ) : (
        <ul className="day-attachments__list" aria-label={t('dayAttachments.list')}>
          {attachments.map((attachment) => (
            <li key={attachment.id}>
              <AttachmentRow tripId={tripId} attachment={attachment} />
            </li>
          ))}
        </ul>
      )}

      <UploadDropzone target={{ kind: 'day', tripId, date }} onUploaded={onUploaded} />
    </section>
  )
}
