import { Navigate, Route, Routes } from 'react-router-dom'

import { LoginPage } from './features/auth/LoginPage'
import { RequireSession } from './features/auth/RequireSession'
import { DayDetailPage } from './features/trips/DayDetailPage'
import { TimelinePage } from './features/trips/TimelinePage'
import { TripCreatePage } from './features/trips/TripCreatePage'
import { TripListPage } from './features/trips/TripListPage'

/**
 * The four routes of the milestone.
 *
 * `/trips/new` is declared before `/trips/:tripId` so "new" is never read as a
 * trip id. React Router 7 ranks static segments above dynamic ones regardless of
 * order, but relying on that leaves the file's correctness dependent on a
 * matching rule a reader has to know.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireSession />}>
        <Route path="/trips" element={<TripListPage />} />
        <Route path="/trips/new" element={<TripCreatePage />} />
        <Route path="/trips/:tripId" element={<TimelinePage />} />
        <Route path="/trips/:tripId/days/:date" element={<DayDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/trips" replace />} />
    </Routes>
  )
}
