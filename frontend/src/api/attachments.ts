import { API_BASE, ApiError, notifyUnauthenticated, readCookie, request } from './client'
import type { ErrorCode } from './errorCodes'

/**
 * The attachment API, typed to match `backend/trip_planner/api/attachments.py`.
 *
 * Upload is the one request in this module that does not go through the shared
 * `request()` helper. `fetch` has no upload-progress event, and the spec's
 * "Uploading" section requires a determinate progress bar and a working
 * cancel — both need bytes-sent visibility `fetch` cannot give. `XMLHttpRequest`
 * can, so the upload functions below use it deliberately, re-implementing just
 * the two things `request()` otherwise gives every caller for free: the CSRF
 * double-submit header and the 401 → sign-out notification. Everything else
 * here — metadata, the content URL, delete — is an ordinary request and goes
 * through `request()` exactly like every other client module.
 */

export type Attachment = {
  id: string
  filename: string
  content_type: string
  byte_size: number
  sha256: string
  /** ISO 8601 timestamp, UTC. */
  created_at: string
  /** Exactly one of `item_id` / `trip_day_id` is non-null. */
  item_id: string | null
  trip_day_id: string | null
}

export type UploadProgress = {
  loaded: number
  total: number
}

export type UploadOptions = {
  onProgress?: (progress: UploadProgress) => void
  signal?: AbortSignal
}

const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'

/**
 * `POST multipart/form-data` with exactly one part, named `file` — the spec's
 * "one file per request" (five files means five requests, five progress bars,
 * five independent failures). Resolves with the created attachment's metadata;
 * rejects with the same `ApiError` `request()` throws, or an `AbortError`
 * `DOMException` if `options.signal` fired first.
 */
function uploadFile(path: string, file: File, options: UploadOptions = {}): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}${path}`, true)

    // The session cookie is HttpOnly, so it only travels when credentials are
    // included — the XHR equivalent of `request()`'s `credentials: 'same-origin'`.
    xhr.withCredentials = true

    // Double-submit: this is an unsafe method, so the server expects the same
    // token back that it set as a cookie — see `client.ts`.
    const csrf = readCookie(CSRF_COOKIE)
    if (csrf) {
      xhr.setRequestHeader(CSRF_HEADER, csrf)
    }

    let settled = false

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        options.onProgress?.({ loaded: event.loaded, total: event.total })
      }
    }

    // Fired by `xhr.abort()`, whether that came from `options.signal` or from
    // the browser. Either way the upload must not resolve as a success — the
    // row and the bytes are written server-side only after the whole body has
    // been read and validated, so an aborted request always leaves no row.
    xhr.onabort = () => {
      settled = true
      reject(new DOMException('The upload was aborted.', 'AbortError'))
    }

    xhr.onerror = () => {
      if (settled) return
      settled = true
      reject(new ApiError(xhr.status, 'unknown'))
    }

    xhr.onload = () => {
      if (settled) return
      settled = true

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parseJson<Attachment>(xhr.responseText))
        return
      }

      const error = toApiErrorFromXhr(xhr)
      if (error.isUnauthenticated) {
        notifyUnauthenticated()
      }
      reject(error)
    }

    // Handlers are wired up before this runs, so an already-aborted signal
    // still reaches `xhr.onabort` above rather than aborting silently.
    const onAbort = () => {
      if (settled) return
      xhr.abort()
    }

    if (options.signal) {
      if (options.signal.aborted) {
        onAbort()
      } else {
        options.signal.addEventListener('abort', onAbort)
      }
    }

    const body = new FormData()
    body.append('file', file)
    xhr.send(body)
  })
}

function parseJson<T>(text: string): T {
  return JSON.parse(text) as T
}

/** `toApiError` in `client.ts`, ported to `XMLHttpRequest`'s response shape. */
function toApiErrorFromXhr(xhr: XMLHttpRequest): ApiError {
  try {
    const body = JSON.parse(xhr.responseText) as {
      error?: { code?: string; field?: string | null }
    }
    const code = body?.error?.code
    if (code) {
      return new ApiError(xhr.status, code as ErrorCode, body.error?.field ?? null)
    }
  } catch {
    // A non-JSON body (a proxy error page, a truncated response) is still an
    // error — it just cannot tell us which one.
  }

  return new ApiError(xhr.status, 'unknown')
}

export function uploadDayAttachment(
  tripId: string,
  date: string,
  file: File,
  options?: UploadOptions,
): Promise<Attachment> {
  return uploadFile(`/trips/${tripId}/days/${date}/attachments`, file, options)
}

export function uploadItemAttachment(
  tripId: string,
  itemId: string,
  file: File,
  options?: UploadOptions,
): Promise<Attachment> {
  return uploadFile(`/trips/${tripId}/items/${itemId}/attachments`, file, options)
}

export function fetchAttachment(
  tripId: string,
  attachmentId: string,
  signal?: AbortSignal,
): Promise<Attachment> {
  return request<Attachment>(`/trips/${tripId}/attachments/${attachmentId}`, { signal })
}

/**
 * The path used for `<img src>` and the download link.
 *
 * A string, not a fetch: the bytes belong in the `<img>` tag or the browser's
 * own download handling, never read into memory here just to be handed back
 * out as a blob URL.
 */
export function attachmentContentUrl(tripId: string, attachmentId: string): string {
  return `${API_BASE}/trips/${tripId}/attachments/${attachmentId}/content`
}

export function deleteAttachment(tripId: string, attachmentId: string): Promise<void> {
  return request<void>(`/trips/${tripId}/attachments/${attachmentId}`, { method: 'DELETE' })
}
