import { useTranslation } from 'react-i18next'

import type { Item } from '../../api/items'
import { toTimeInput } from '../../api/items'
import { StatusChip } from './StatusChip'
import { formatShortDate } from './format'

/**
 * One item, as it renders on the day detail and on a timeline day card.
 *
 * One component for both so an item cannot look like two different things
 * depending on which screen you reached it from.
 *
 * The time reads as a range when there is one, as a single time when only a
 * start is set, and as "all day" when there is none — because "sometime that
 * day" is a real plan and rendering an empty gap would look like missing data.
 * An item spanning into a later day carries a "→ dd.MM" marker, and is rendered
 * **once**, on its start day: it is one item and is counted once.
 */
export function ItemRow({
  item,
  dayDate,
  onOpen,
}: {
  item: Item
  /** The day this row is being rendered on — the item's start day. */
  dayDate: string
  /** Given on the day detail, where a row opens the editor. Absent on the timeline. */
  onOpen?: () => void
}) {
  const { t, i18n } = useTranslation()

  const start = toTimeInput(item.start_time)
  const end = toTimeInput(item.end_time)
  const time = start === '' ? t('item.allDay') : end === '' ? start : `${start}–${end}`
  const spansOn = item.end_date !== null && item.end_date !== dayDate ? item.end_date : null

  const body = (
    <>
      <span className="item-row__time">{time}</span>
      <span className="item-row__kind">{t(`item.kind.${item.kind}`)}</span>
      <span className="item-row__title">{item.title}</span>
      {spansOn !== null && (
        <span className="item-row__spans">
          {t('item.spansUntil', { date: formatShortDate(spansOn, i18n.language) })}
        </span>
      )}
      <StatusChip status={item.status} />
      {item.notes !== null && <span className="item-row__notes">{item.notes}</span>}
    </>
  )

  if (onOpen === undefined) {
    return <div className="item-row">{body}</div>
  }

  return (
    <button type="button" className="item-row item-row--button" onClick={onOpen}>
      {body}
    </button>
  )
}
