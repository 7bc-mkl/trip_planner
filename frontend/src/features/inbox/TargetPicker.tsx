import { useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Target } from '../../api/inbox'
import type { TripDetail } from '../../api/trips'
import { fetchTrip } from '../../api/trips'
import { formatDate } from '../trips/format'

/**
 * Where a proposal should land: an existing item of a trip, or a new item on
 * one of its days.
 *
 * One `<select>`, grouped by day, rather than a two-step day-then-item flow:
 * the owner is choosing between "this hotel" and "a new item on the 17th", and
 * seeing both side by side under the date is the comparison he is making. The
 * option values carry their kind (`item:` / `day:`) so a choice maps onto the
 * API's two target fields without a second lookup.
 */
export function TargetPicker({
  tripId,
  label,
  onChoose,
  busyLabel,
  actionLabel,
}: {
  tripId: string
  label: string
  actionLabel: string
  busyLabel: string
  onChoose: (target: Target) => Promise<void>
}) {
  const { t, i18n } = useTranslation()
  const selectId = useId()
  const [trip, setTrip] = useState<TripDetail | null>(null)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setTrip(null)
    setValue('')
    fetchTrip(tripId, controller.signal)
      .then(setTrip)
      // A trip that cannot be loaded leaves the picker empty; the sheet's own
      // error line is where failures are reported.
      .catch(() => undefined)
    return () => controller.abort()
  }, [tripId])

  if (trip === null) {
    return <p role="status">{t('app.loading')}</p>
  }

  const choose = () => {
    const [kind, id] = value.split(':')
    if (id === undefined || id === '') {
      return
    }
    setBusy(true)
    const target: Target = kind === 'item' ? { target_item_id: id } : { target_trip_day_id: id }
    void onChoose(target).finally(() => setBusy(false))
  }

  return (
    <div className="inbox-place">
      <label htmlFor={selectId}>{label}</label>
      <select id={selectId} value={value} onChange={(event) => setValue(event.target.value)}>
        <option value="">{t('inbox.sheet.chooseTarget')}</option>
        {trip.days.map((day) => {
          const date = formatDate(day.date, i18n.language)
          return (
            <optgroup key={day.id} label={date}>
              {day.items.map((item) => (
                <option key={item.id} value={`item:${item.id}`}>
                  {item.title}
                </option>
              ))}
              <option value={`day:${day.id}`}>{t('inbox.sheet.newItemOn', { date })}</option>
            </optgroup>
          )
        })}
      </select>
      <button type="button" className="button-quiet" disabled={value === '' || busy} onClick={choose}>
        {busy ? busyLabel : actionLabel}
      </button>
    </div>
  )
}
