import { request } from './client'

/** The owner as `/auth/me` returns them. `password_hash` is absent by construction. */
export type Owner = {
  id: string
  email: string
  locale: 'pl' | 'en'
}

export function login(email: string, password: string): Promise<void> {
  return request<void>('/auth/login', { method: 'POST', body: { email, password } })
}

export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}

export function fetchMe(signal?: AbortSignal): Promise<Owner> {
  return request<Owner>('/auth/me', { signal })
}

export function updateLocale(locale: Owner['locale']): Promise<Owner> {
  return request<Owner>('/auth/me', { method: 'PATCH', body: { locale } })
}
