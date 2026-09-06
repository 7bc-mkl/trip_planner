import spriteUrl from '../assets/icons.svg?no-inline'

/**
 * The application's only icon primitive: one `<use>` into the bundled sprite at
 * `src/assets/icons.svg`.
 *
 * The sprite is imported rather than referenced from `public/`, so the bundler
 * content-hashes it and it is cacheable instead of being served unversioned.
 *
 * `?no-inline` is load-bearing, not decoration. The sprite is under Vite's
 * `assetsInlineLimit`, so without it the build would hand back a
 * `data:image/svg+xml;base64,…` string — and browsers refuse a `data:` URL as
 * an external `<use href>` target, which would leave every glyph silently
 * blank. The suffix forces a real, hashed file on disk.
 *
 * Two invariants live here rather than at each call site, so they cannot be
 * forgotten one control at a time:
 *
 * - **`aria-hidden` and `focusable="false"` on every instance.** Every icon in
 *   this application sits beside a translated text label — the icon is an
 *   addition to the label, never a replacement — so announcing it would say the
 *   same thing twice, and `focusable="false"` keeps the old IE-era focus stop
 *   out of the tab order.
 * - **`name` is typed against the sprite's ids**, so a typo is a typecheck
 *   failure rather than an invisible glyph.
 */
// Not exported: the sprite's ids are an implementation detail, and `IconName`
// is the whole surface a call site needs.
const ICON_NAMES = [
  // The five item kinds, ids identical to `ITEM_KINDS` in `src/api/items.ts`.
  'accommodation',
  'transport',
  'activity',
  'meal',
  'other',
  // Day navigation.
  'chevron-left',
  'chevron-right',
  // A PDF attachment's glyph — see `DayAttachments.tsx`. An image attachment
  // renders its own preview instead, never this glyph.
  'document',
  // The attachment-count badge on an item's card — see `ItemRow.tsx`.
  'paperclip',
] as const

export type IconName = (typeof ICON_NAMES)[number]

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      className={className === undefined ? 'icon' : `icon ${className}`}
      aria-hidden="true"
      focusable="false"
    >
      <use href={`${spriteUrl}#${name}`} />
    </svg>
  )
}
