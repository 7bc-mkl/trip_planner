import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

import type { Readiness } from '../../api/trips'

/**
 * The readiness counter — the number the whole product exists to show.
 *
 * When `tracked > 0` it reads "{arranged} of {tracked} arranged". When
 * `tracked = 0` — whether the trip has no items at all, or ten items all still
 * *do zaplanowania* — it reads **"nothing arranged yet"**, with no fraction, no
 * percentage and no progress bar.
 *
 * That is not a nicety. The percentage is undefined at a zero denominator, and a
 * "0%" would read as failure where the honest reading is "you have not decided
 * anything yet". Rendering a bar at zero would say the same thing in a picture.
 *
 * One component for both the timeline tile and the trip-list row, so the two
 * cannot end up saying it differently.
 */
export function ReadinessTile({
  readiness,
  compact = false,
  ring = false,
}: {
  readiness: Readiness
  compact?: boolean
  /**
   * The progress ring beside the value (Q8). The trip banner asks for it; the
   * compact list row does not, and neither does anything else.
   *
   * It is **decoration on top of the text, never instead of it**: the disc is
   * `aria-hidden`, it renders no percentage, and it is suppressed entirely at a
   * zero denominator — a 0% ring reads as failure where the percentage is
   * undefined, which is the whole reason the zero state exists.
   */
  ring?: boolean
}) {
  const { t } = useTranslation()
  const nothingTracked = readiness.tracked === 0

  return (
    <p
      className={compact ? 'readiness readiness--compact' : 'readiness'}
      data-nothing-tracked={nothingTracked ? 'true' : 'false'}
    >
      {!compact && <span className="readiness__label">{t('readiness.label')}</span>}
      {ring && !nothingTracked && (
        <span
          className="readiness__ring"
          aria-hidden="true"
          // The arc, as a fraction of a turn, handed to a two-stop
          // `conic-gradient` in `components.css`. The arithmetic is the
          // counter's own — `arranged / tracked` — and it is never rendered as
          // a number anywhere.
          style={{ '--readiness-arc': `${readiness.arranged / readiness.tracked}turn` } as CSSProperties}
        />
      )}
      <span className="readiness__value">
        {nothingTracked
          ? t('readiness.nothingArranged')
          : t('readiness.fraction', {
              arranged: readiness.arranged,
              tracked: readiness.tracked,
            })}
      </span>
    </p>
  )
}
