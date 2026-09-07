import { useTranslation } from 'react-i18next'

import type { Item, ItemKind } from '../../api/items'
import { Icon } from '../../components/Icon'
import type { IconName } from '../../components/Icon'
import { StatusChip } from './StatusChip'
import { formatShortDate, formatTime } from './format'

/**
 * Kind → sprite symbol. The ids happen to match the kind names, but the map is
 * written out rather than interpolated so that a sixth kind added to
 * `ITEM_KINDS` is a typecheck failure here — pointing at the missing glyph —
 * instead of an empty tile nobody notices.
 */
const KIND_ICONS: Record<ItemKind, IconName> = {
  accommodation: 'accommodation',
  transport: 'transport',
  activity: 'activity',
  meal: 'meal',
  other: 'other',
}

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
 *
 * **No price, per the spec** — costs never appear on the timeline or the day
 * detail. **The paperclip is different**: it is `attachmentCount`, an
 * **optional** prop rather than a field this component reads off `item`
 * itself, so a caller that has not wired it up yet (until the timeline's own
 * Step does) renders exactly as before. It appears only when the count is
 * given and greater than zero — never a bare "0" paperclip.
 */
export function ItemRow({
  item,
  dayDate,
  onOpen,
  railDot = false,
  attachmentCount,
}: {
  item: Item
  /** The day this row is being rendered on — the item's start day. */
  dayDate: string
  /** Given on the day detail, where a row opens the editor. Absent on the timeline. */
  onOpen?: () => void
  /**
   * The status dot on the timeline's rail. The timeline passes it; the day
   * detail, which has no rail to hang it on, does not.
   *
   * It is `aria-hidden` decoration beside the status chip, never instead of it:
   * the chip keeps the glyph and the translated label that carry the status for
   * a reader who cannot see the colour.
   */
  railDot?: boolean
  /**
   * How many files are pinned to this item. Optional and opt-in per caller:
   * the day detail passes `item.attachment_count`; a caller that passes
   * nothing renders with no paperclip at all, unchanged from before this prop
   * existed.
   */
  attachmentCount?: number
}) {
  const { t, i18n } = useTranslation()

  // Both formatted through the active locale; only the en dash joining them is
  // punctuation rather than locale data.
  const start = formatTime(item.start_time, i18n.language)
  const end = formatTime(item.end_time, i18n.language)
  const time = start === '' ? t('item.allDay') : end === '' ? start : `${start}–${end}`
  const spansOn = item.end_date !== null && item.end_date !== dayDate ? item.end_date : null

  const body = (
    <>
      {railDot && <span className="item-row__dot" data-status={item.status} aria-hidden="true" />}
      <span className="item-row__time">{time}</span>
      {/* The type: a rounded icon tile plus its translated label. The glyph
          inside the tile is decoration — the translated label beside it is what
          carries the kind, and it is never replaced by the glyph. */}
      <span className="item-row__type">
        <span className="item-row__icon" aria-hidden="true">
          <Icon name={KIND_ICONS[item.kind]} />
        </span>
        <span className="item-row__kind">{t(`item.kind.${item.kind}`)}</span>
      </span>
      <span className="item-row__title">{item.title}</span>
      {spansOn !== null && (
        <span className="item-row__spans">
          {t('item.spansUntil', { date: formatShortDate(spansOn, i18n.language) })}
        </span>
      )}
      <StatusChip status={item.status} />
      {/* The paperclip: an ADDITION to a translated word beside it, never the
          glyph alone — same contract as the kind tile above. Present only
          when there is at least one file, per the spec's "and only then". */}
      {attachmentCount !== undefined && attachmentCount > 0 && (
        <span className="item-row__attachments">
          <span className="item-row__attachments-icon" aria-hidden="true">
            <Icon name="paperclip" />
          </span>
          {t('item.attachmentCount', { count: attachmentCount })}
        </span>
      )}
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
