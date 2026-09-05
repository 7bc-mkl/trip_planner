import { Navigate, Route, Routes } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { LocaleSwitch } from './i18n/LocaleSwitch'
import { isLocale } from './i18n'
import { LoginPage } from './features/auth/LoginPage'
import { RequireSession } from './features/auth/RequireSession'
import { useSession } from './features/auth/SessionContext'

/**
 * A placeholder for the trip list, which arrives in Phase 2.
 *
 * It exists so the guarded half of the router is real: without one authenticated
 * route there is nothing for RequireSession to protect and nowhere for the
 * post-login redirect to land.
 */
function TripsPlaceholder() {
  const { t } = useTranslation()
  const session = useSession()

  return (
    <main className="app-shell">
      <header>
        <h1>{t('app.name')}</h1>
        {/* Signed in, the choice is stored on the owner rather than only in this
            browser, so the language survives a new one (R01). */}
        <LocaleSwitch
          onChange={(locale) => {
            if (isLocale(locale)) {
              void session.persistLocale(locale)
            }
          }}
        />
        <button type="button" onClick={() => void session.signOut()}>
          {t('nav.signOut')}
        </button>
      </header>
      {session.status === 'authenticated' && <p>{session.owner.email}</p>}
    </main>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireSession />}>
        <Route path="/trips" element={<TripsPlaceholder />} />
      </Route>
      <Route path="*" element={<Navigate to="/trips" replace />} />
    </Routes>
  )
}
