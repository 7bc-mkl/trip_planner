import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import {
  fetchMe,
  login as loginRequest,
  logout as logoutRequest,
  updateLocale,
} from '../../api/auth'
import type { Owner } from '../../api/auth'
import { ApiError, setUnauthenticatedHandler } from '../../api/client'
import { applyLocale, isLocale } from '../../i18n'
import type { Locale } from '../../i18n'
import { clearAllDrafts } from './draftStore'

type SessionState =
  /** The initial /auth/me call has not finished; we do not yet know either way. */
  | { status: 'loading' }
  | { status: 'authenticated'; owner: Owner }
  /** `expired` distinguishes "was signed in and got thrown out" from "never was". */
  | { status: 'anonymous'; expired?: boolean }

type SessionValue = SessionState & {
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  /** Called when any request answers 401, so an expired session is noticed everywhere. */
  handleUnauthenticated: () => void
  /**
   * Store the owner's language choice on the server.
   *
   * The locale lives in the `owner` row rather than only in localStorage so it
   * survives a new browser (R01) — which it only does if something actually
   * writes it. A no-op while signed out: there is no owner to store it against,
   * and the local preference already carries the login screen.
   */
  persistLocale: (locale: Locale) => Promise<void>
  /**
   * True when a session we believed in was rejected, so the login screen can say
   * why the owner is suddenly back on it rather than looking like a random bounce.
   */
  sessionExpired: boolean
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: 'loading' })

  const adopt = useCallback((owner: Owner) => {
    setState({ status: 'authenticated', owner })
    // The server-side locale is the source of truth once signed in: it is what
    // makes the language survive a new browser (R01).
    if (isLocale(owner.locale)) {
      void applyLocale(owner.locale)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    fetchMe(controller.signal)
      .then(adopt)
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        // A 401 here is the ordinary "not signed in yet" case, not a failure.
        if (error instanceof ApiError && error.isUnauthenticated) {
          setState({ status: 'anonymous' })
          return
        }
        // Any other failure still leaves the app usable at the login screen
        // rather than stuck on a spinner forever.
        setState({ status: 'anonymous' })
      })

    return () => controller.abort()
  }, [adopt])

  const signIn = useCallback(
    async (email: string, password: string) => {
      await loginRequest(email, password)
      adopt(await fetchMe())
    },
    [adopt],
  )

  const signOut = useCallback(async () => {
    try {
      await logoutRequest()
    } catch {
      // Swallowed deliberately, not ignored: the request can fail precisely
      // because the session already expired, and the local outcome is the same
      // either way. Rethrowing would surface an unhandled rejection from every
      // sign-out button for a request whose failure changes nothing.
    } finally {
      // Local state is cleared even if the request failed: the owner asked to be
      // signed out, and leaving the UI signed in would be a lie.
      clearAllDrafts()
      setState({ status: 'anonymous' })
    }
  }, [])

  const persistLocale = useCallback(
    async (locale: Locale) => {
      if (state.status !== 'authenticated') {
        return
      }

      try {
        adopt(await updateLocale(locale))
      } catch {
        // The language already changed locally. Failing to store the preference
        // is worth nothing to shout about — refusing to switch would be worse.
      }
    },
    [adopt, state.status],
  )

  const handleUnauthenticated = useCallback(() => {
    setState((current) =>
      // Only a session we believed in can expire. Collapsing 'loading' here would
      // race the initial /auth/me call and flash the login screen.
      current.status === 'authenticated' ? { status: 'anonymous', expired: true } : current,
    )
  }, [])

  useEffect(() => {
    setUnauthenticatedHandler(handleUnauthenticated)
    return () => setUnauthenticatedHandler(null)
  }, [handleUnauthenticated])

  const value = useMemo<SessionValue>(
    () => ({
      ...state,
      signIn,
      signOut,
      handleUnauthenticated,
      persistLocale,
      sessionExpired: state.status === 'anonymous' && state.expired === true,
    }),
    [state, signIn, signOut, handleUnauthenticated, persistLocale],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (value === null) {
    throw new Error('useSession must be used inside a <SessionProvider>')
  }
  return value
}
