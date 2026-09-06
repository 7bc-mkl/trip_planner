import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useSession } from './SessionContext'

/**
 * The route guard.
 *
 * This is UX, not enforcement — the API is the fence. Its job is to send an
 * unauthenticated visitor to /login *carrying where they were going*, so signing
 * in lands them there instead of on a default screen.
 */
export function RequireSession() {
  const session = useSession()
  const location = useLocation()
  const { t } = useTranslation()

  if (session.status === 'loading') {
    // Rendering the guarded page here would flash private chrome before the
    // redirect; redirecting here would bounce an already-signed-in owner to
    // /login on every reload.
    return <p role="status">{t('app.loading')}</p>
  }

  if (session.status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return <Outlet />
}
