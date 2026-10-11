import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import type { InboxMessage } from '../../api/inbox'
import { placeMessage } from '../../api/inbox'
import type { TripSummary } from '../../api/trips'

/**
 * Hand placement for a message the router could not place.
 *
 * A `<select>` of the owner's trips and one button, deliberately — this is the
 * smallest thing that clears the unrouted queue, and D20 puts the queue behind
 * the routing the model will do from Phase 2. Anything more elaborate would be
 * building a workflow around a state that is meant to be rare.
 *
 * **Placing a message writes nothing to the plan.** It records which trip the
 * mail belongs to and no more: the document stays in the inbox, no item is
 * touched, and nothing is created. That is why this can ship before the
 * approval path exists — the owner is classifying his own mail, not approving a
 * change to a trip, and D21 still governs every later write. The copy says so,
 * because a control that looked like it filed the document into the trip would
 * be promising something it does not do.
 */
export function PlaceMessage({
  message,
  trips,
  onPlaced,
}: {
  message: InboxMessage
  trips: TripSummary[]
  onPlaced: (placed: InboxMessage) => void
}) {
  const { t } = useTranslation()
  const [tripId, setTripId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (trips.length === 0) {
    // No trip to place it on. D03 is deliberate here: a message never creates a
    // trip, so the honest answer is to say what is missing rather than to offer
    // a shortcut the product has decided against.
    return <p className="inbox-place__hint">{t('inbox.placeNoTrips')}</p>
  }

  const submit = () => {
    if (tripId === '' || busy) {
      return
    }
    setBusy(true)
    setError(null)

    placeMessage(message.id, tripId)
      .then(onPlaced)
      .catch((caught: unknown) => {
        setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      })
      .finally(() => setBusy(false))
  }

  const selectId = `place-${message.id}`

  return (
    <div className="inbox-place">
      <label htmlFor={selectId}>{t('inbox.placeLabel')}</label>
      <select
        id={selectId}
        value={tripId}
        disabled={busy}
        onChange={(event) => setTripId(event.target.value)}
      >
        <option value="">{t('inbox.placeChoose')}</option>
        {trips.map((trip) => (
          <option key={trip.id} value={trip.id}>
            {trip.title}
          </option>
        ))}
      </select>
      <button type="button" className="button-primary" disabled={tripId === '' || busy} onClick={submit}>
        {busy ? t('inbox.placing') : t('inbox.place')}
      </button>
      <p className="inbox-place__hint">{t('inbox.placeHint')}</p>
      {error !== null && <p role="alert">{error}</p>}
    </div>
  )
}
