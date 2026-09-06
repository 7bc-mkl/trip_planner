import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { isLocale } from '../../i18n'
import { LocaleSwitch } from '../../i18n/LocaleSwitch'
import { useSession } from '../auth/SessionContext'

/**
 * The chrome every authenticated screen shares: the product name, the locale
 * switch, sign-out, and a slot for the screen's own primary action.
 *
 * One component rather than a copy per screen so the locale switch (R01, present
 * on every screen) and the sign-out control cannot go missing from one of them.
 * `<main>` and the heading are real landmarks, which is what makes the page
 * navigable by landmark as the spec's keyboard rules require.
 */
export function AppShell({
  title,
  breadcrumb,
  actions,
  children,
}: {
  title: string
  breadcrumb?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  const { t } = useTranslation()
  const session = useSession()

  return (
    <div className="app-shell">
      <header>
        <Link className="app-shell__brand" to="/trips">
          {t('app.name')}
        </Link>
        <LocaleSwitch
          onChange={(locale) => {
            // Signed in, the choice is stored on the owner rather than only in
            // this browser, so the language survives a new one (R01).
            if (isLocale(locale)) {
              void session.persistLocale(locale)
            }
          }}
        />
        <button type="button" onClick={() => void session.signOut()}>
          {t('nav.signOut')}
        </button>
      </header>

      <main>
        {breadcrumb}
        <div className="page-heading">
          <h1>{title}</h1>
          {actions}
        </div>
        {children}
      </main>
    </div>
  )
}
