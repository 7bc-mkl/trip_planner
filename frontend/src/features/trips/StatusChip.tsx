import { useTranslation } from 'react-i18next'

import type { ItemStatus } from '../../api/items'

/**
 * The status chip.
 *
 * Two rules from the spec's cross-cutting UI section, and both are testable:
 *
 * 1. **Status is never colour alone.** The chip renders its translated label as a
 *    real text node and carries a `data-status` attribute that drives a distinct
 *    glyph. A colour-blind reader gets the word; a screen-reader user gets the
 *    word; a test can assert both. A chip that expressed status only through a
 *    CSS class would pass a visual review and fail every one of those readers.
 * 2. **The label is translated**, never the stored value. `to_plan` is the wire
 *    format; *do zaplanowania* and *to plan* are what a person reads.
 *
 * The glyph is a text character rather than an icon font or an SVG sprite: it
 * needs no asset, survives with styles disabled, and is `aria-hidden` because the
 * label beside it already says the same thing.
 *
 * The dot is the design's own (`DESIGN.md`, "Status Chips & Badges": a 6px solid
 * dot beside the label). It is decoration and nothing else — pure paint, no text
 * node, `aria-hidden`, and deliberately a *sibling* of the glyph rather than a
 * replacement for it. Strip every stylesheet and the dot vanishes while the
 * glyph and the translated word both stay, which is the whole contract.
 */

/** One distinct shape per status — distinguishable without colour. */
const GLYPH: Record<ItemStatus, string> = {
  to_plan: '○',
  to_book: '◐',
  done: '●',
}

export function StatusChip({ status }: { status: ItemStatus }) {
  const { t } = useTranslation()

  return (
    <span className="status-chip" data-status={status}>
      <span aria-hidden="true" className="status-chip__dot" />
      <span aria-hidden="true" className="status-chip__glyph">
        {GLYPH[status]}
      </span>
      {t(`item.status.${status}`)}
    </span>
  )
}
