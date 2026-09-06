import { useTranslation } from 'react-i18next'

import { ITEM_KINDS } from '../../api/items'
import type { Item, ItemKind } from '../../api/items'
import { FILTERS, countByKind } from './filter'
import type { Filter } from './filter'

/**
 * The timeline's filter bar, in the position the design export gives
 * "Wszystko (11) · Noclegi (3) · Transport (4) · …".
 *
 * The two-way filter is a **real radio group** — a `<fieldset>` with a `<legend>`
 * and `<input type="radio">` — so a screen reader announces it as one control
 * with two options, and arrow keys move between them. A pair of styled buttons
 * would look identical and be neither.
 *
 * The per-type chips are **counts, not filters**. The spec's filter is *All* /
 * *Only outstanding*; the chips answer "what is this trip made of", and the
 * export's own numbers show why they are not a second filter — its chips sum to
 * the all-items count while its counter uses a different denominator. Presenting
 * them as clickable would promise a filter this milestone does not have.
 */
export function FilterBar({
  items,
  filter,
  onChange,
}: {
  /** Every item of the trip, unfiltered — the chips count the whole trip. */
  items: readonly Item[]
  filter: Filter
  onChange: (filter: Filter) => void
}) {
  const { t } = useTranslation()
  const counts = countByKind(items)

  return (
    <div className="filter-bar">
      <fieldset className="filter-bar__filters">
        <legend>{t('filter.legend')}</legend>
        {FILTERS.map((candidate) => (
          <label key={candidate}>
            <input
              type="radio"
              name="timeline-filter"
              value={candidate}
              checked={filter === candidate}
              onChange={() => onChange(candidate)}
            />
            {t(`filter.${candidate}`)}
          </label>
        ))}
      </fieldset>

      <ul className="filter-bar__chips">
        {ITEM_KINDS.filter((kind: ItemKind) => counts[kind] > 0).map((kind) => (
          <li key={kind} className="kind-chip" data-kind={kind}>
            {t('filter.kindCount', { kind: t(`item.kind.${kind}`), count: counts[kind] })}
          </li>
        ))}
      </ul>
    </div>
  )
}
