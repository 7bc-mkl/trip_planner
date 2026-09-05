import type { ErrorCode } from './errorCodes'

/**
 * The typed fetch client.
 *
 * Two things live here rather than in each caller: the CSRF header, which the
 * server requires on every unsafe method, and the translation of the API's error
 * envelope into a thrown `ApiError`. A caller that had to remember either would
 * eventually forget.
 */

export const API_BASE = '/api/v1'

const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export class ApiError extends Error {
  readonly status: number
  readonly code: ErrorCode | 'unknown'
  readonly field: string | null

  constructor(status: number, code: ErrorCode | 'unknown', field: string | null = null) {
    super(`API error ${status}: ${code}`)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.field = field
  }

  /** The i18n key for this error. Codes are stable; the copy is translated. */
  get translationKey(): string {
    return `error.${this.code}`
  }

  get isUnauthenticated(): boolean {
    return this.status === 401
  }
}

export function readCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null
  }

  const match = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`))

  return match ? decodeURIComponent(match.slice(name.length + 1)) : null
}

type RequestOptions = {
  method?: string
  body?: unknown
  signal?: AbortSignal
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = { Accept: 'application/json' }

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  if (!SAFE_METHODS.has(method)) {
    // Double-submit: the server compares this against the cookie it set.
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) {
      headers[CSRF_HEADER] = csrf
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    // The session cookie is HttpOnly, so it only travels when credentials are included.
    credentials: 'same-origin',
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  })

  if (!response.ok) {
    throw await toApiError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: string; field?: string | null }
    }
    const code = body?.error?.code
    if (code) {
      return new ApiError(response.status, code as ErrorCode, body.error?.field ?? null)
    }
  } catch {
    // A non-JSON body (a proxy error page, a truncated response) is still an
    // error — it just cannot tell us which one.
  }

  return new ApiError(response.status, 'unknown')
}
