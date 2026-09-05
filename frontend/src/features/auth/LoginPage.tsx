import { useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useLocation } from 'react-router-dom'

import { ApiError } from '../../api/client'
import { LocaleSwitch } from '../../i18n/LocaleSwitch'
import { useSession } from './SessionContext'

type LocationState = { from?: string } | null

export function LoginPage() {
  const { t } = useTranslation()
  const session = useSession()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as LocationState)?.from

  if (session.status === 'authenticated') {
    return <Navigate to={from && from !== '/login' ? from : '/trips'} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await session.signIn(email, password)
    } catch (caught: unknown) {
      // One generic message whatever went wrong. Distinguishing "no such
      // account" from "wrong password" here would undo the work the API does to
      // keep them indistinguishable.
      setError(
        caught instanceof ApiError && caught.status !== 401
          ? t(caught.translationKey)
          : t('login.failed'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login">
      <header>
        <h1>{t('app.name')}</h1>
        <LocaleSwitch />
      </header>

      <form onSubmit={handleSubmit} noValidate>
        <h2>{t('login.title')}</h2>
        <p>{t('login.subtitle')}</p>

        <label htmlFor="email">{t('login.emailLabel')}</label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />

        <label htmlFor="password">{t('login.passwordLabel')}</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />

        {/* Why the owner is suddenly back here. Shown only until they try again,
            at which point the sign-in result is the more useful message. */}
        {error === null && session.sessionExpired && (
          <p role="status">{t('login.sessionExpired')}</p>
        )}

        {/* role="alert" so the failure is announced, not only shown. */}
        {error !== null && <p role="alert">{error}</p>}

        <button type="submit" disabled={submitting}>
          {submitting ? t('login.submitting') : t('login.submit')}
        </button>
      </form>
    </main>
  )
}
