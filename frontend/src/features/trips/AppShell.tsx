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
 * The header is sticky and frosted; its rules live in `styles/chrome.css` and
 * nothing here sets a height, because the sticky layers beneath it read
 * `--header-height` from the token file rather than from this component.
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
  context,
  dock,
  children,
}: {
  title: string
  breadcrumb?: ReactNode
  actions?: ReactNode
  /**
   * The trip a trip-scoped route is showing, named in the header between the
   * wordmark and the controls: the title and its date range, truncated to one
   * line.
   *
   * It is the export's trip picker without being a picker — there is one trip
   * in view and `/trips` is one click away — so it is **text, not a control**,
   * and it is optional: a screen that is not about one trip passes nothing and
   * the header is exactly what it was.
   */
  context?: ReactNode
  /**
   * The contextual dock: trip metadata promoted out of the main column — the
   * readiness figure, the stages, the route summary.
   *
   * Optional, and its absence costs nothing: a screen that passes no dock
   * renders a single centred column and the grid reserves no space for one.
   * Phase 4 fills it on `/trips/:id` and `/trips/new`; until then every screen
   * is in exactly that undocked case, which is why it is the one with a test.
   */
  dock?: ReactNode
  children: ReactNode
}) {
  const { t } = useTranslation()
  const session = useSession()

  return (
    <div className="app-shell">
      {/* The frosted sticky band. Full-bleed, with its contents on the same
          centred measure as the canvas below — see `styles/chrome.css`. */}
      <header className="app-header">
        <div className="app-header__inner">
          <Link className="app-header__brand" to="/trips">
            {t('app.name')}
          </Link>
          {context !== undefined && <p className="app-header__context">{context}</p>}
          <div className="app-header__controls">
            <LocaleSwitch
              onChange={(locale) => {
                // Signed in, the choice is stored on the owner rather than only
                // in this browser, so the language survives a new one (R01).
                if (isLocale(locale)) {
                  void session.persistLocale(locale)
                }
              }}
            />
            <button
              type="button"
              className="button-quiet"
              onClick={() => void session.signOut()}
            >
              {t('nav.signOut')}
            </button>
          </div>
        </div>
      </header>

      {/* The page grid. The dock is an `<aside>` BESIDE `<main>`, never inside
          it: `<main>` has to stay the main landmark and the canvas has to stay
          the first thing inside it, so the dock is a complementary landmark of
          its own that a screen reader can skip in one keystroke. It precedes
          `<main>` in the markup because below 1280px that is where it renders —
          a summary strip above the canvas — so the reading order and the
          visual order say the same thing. */}
      <div className={dock === undefined ? 'page' : 'page page--docked'}>
        {dock !== undefined && <aside className="page__dock">{dock}</aside>}

        <main className="page__canvas">
          {breadcrumb}
          <div className="page-heading">
            <h1>{title}</h1>
            {actions}
          </div>
          {children}
        </main>
      </div>
    </div>
  )
}
