import type { ItemStatus } from '../../api/items'

/**
 * One distinct shape per status — distinguishable without colour.
 *
 * Its own module, beside `format.ts` and `filter.ts`, because two components
 * need it: the chip that reports a status and the editor's segmented control
 * that sets one. The pill a person picks and the chip they read back have to be
 * recognisably the same thing, and two copies of this map would eventually
 * disagree.
 *
 * Text characters rather than an icon font or a sprite: they need no asset,
 * they survive with styles disabled, and they are `aria-hidden` wherever they
 * render because the translated label beside them already says the same thing.
 */
export const STATUS_GLYPH: Record<ItemStatus, string> = {
  to_plan: '○',
  to_book: '◐',
  done: '●',
}
