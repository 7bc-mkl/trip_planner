import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { fetchMe, login as loginRequest, logout as logoutRequest } from '../../api/auth'
import type { Owner } from '../../api/auth'
import { ApiError, setUnauthenticatedHandler } from '../../api/client'
import { applyLocale, isLocale } from '../../i18n'
import { clearAllDrafts } from './draftStore'

type SessionState =
  /** The initial /auth/me call has not finished; we do not yet know either way. */
  | { status: 'loading' }
  | { status: 'authenticated'; owner: Owner }
  | { status: 'anonymous' }

type SessionValue = SessionState & {
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  /** Called when any request answers 401, so an expired session is noticed everywhere. */
  handleUnauthenticated: () => void
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

  const handleUnauthenticated = useCallback(() => {
    setState((current) =>
      // Only a session we believed in can expire. Collapsing 'loading' here would
      // race the initial /auth/me call and flash the login screen.
      current.status === 'authenticated' ? { status: 'anonymous' } : current,
    )
  }, [])

  useEffect(() => {
    setUnauthenticatedHandler(handleUnauthenticated)
    return () => setUnauthenticatedHandler(null)
  }, [handleUnauthenticated])

  const value = useMemo<SessionValue>(
    () => ({ ...state, signIn, signOut, handleUnauthenticated }),
    [state, signIn, signOut, handleUnauthenticated],
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
