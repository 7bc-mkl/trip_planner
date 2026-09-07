import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  attachmentContentUrl,
  uploadDayAttachment,
  uploadItemAttachment,
  type Attachment,
} from './attachments'
import { setUnauthenticatedHandler } from './client'

/**
 * `uploadDayAttachment` / `uploadItemAttachment` are the one client function
 * that drives `XMLHttpRequest` instead of `fetch`, so `fetch` cannot be
 * stubbed the way the rest of the suite stubs it (see `deleteTrip.test.tsx`).
 * This fakes just enough of `XMLHttpRequest` to drive the three events the
 * client listens for — `upload.onprogress`, `onload`, `onabort` — and to
 * inspect what was sent.
 */

type Listener = () => void

class FakeXhr {
  static instances: FakeXhr[] = []

  method = ''
  url = ''
  status = 0
  responseText = ''
  withCredentials = false
  requestHeaders: Record<string, string> = {}
  sentBody: FormData | null = null
  aborted = false

  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
  onload: Listener | null = null
  onerror: Listener | null = null
  onabort: Listener | null = null

  constructor() {
    FakeXhr.instances.push(this)
  }

  open(method: string, url: string): void {
    this.method = method
    this.url = url
  }

  setRequestHeader(name: string, value: string): void {
    this.requestHeaders[name] = value
  }

  send(body: FormData): void {
    this.sentBody = body
  }

  abort(): void {
    this.aborted = true
    this.onabort?.()
  }

  /** Test helper: the server answering. */
  respond(status: number, body: unknown): void {
    this.status = status
    this.responseText = JSON.stringify(body)
    this.onload?.()
  }

  /** Test helper: an upload-progress tick. */
  progress(loaded: number, total: number): void {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total } as ProgressEvent)
  }
}

const ATTACHMENT: Attachment = {
  id: 'attachment-1',
  filename: 'Voucher.pdf',
  content_type: 'application/pdf',
  byte_size: 1024,
  sha256: 'abc',
  created_at: '2026-09-05T10:11:12Z',
  item_id: 'item-1',
  trip_day_id: null,
}

function file(): File {
  return new File(['%PDF-1.4 …'], 'voucher.pdf', { type: 'application/pdf' })
}

beforeEach(() => {
  FakeXhr.instances = []
  vi.stubGlobal('XMLHttpRequest', FakeXhr as unknown as typeof XMLHttpRequest)
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
  document.cookie = 'csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

describe('uploadDayAttachment / uploadItemAttachment', () => {
  it('sends exactly one multipart part named "file" to the day endpoint', () => {
    void uploadDayAttachment('trip-1', '2026-10-10', file())

    const xhr = FakeXhr.instances[0]!
    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('/api/v1/trips/trip-1/days/2026-10-10/attachments')
    expect(xhr.withCredentials).toBe(true)

    const keys = Array.from(xhr.sentBody!.keys())
    expect(keys).toEqual(['file'])
  })

  it('posts to the item endpoint', () => {
    void uploadItemAttachment('trip-1', 'item-1', file())

    expect(FakeXhr.instances[0]!.url).toBe('/api/v1/trips/trip-1/items/item-1/attachments')
  })

  it('sends the CSRF header read from the cookie, because this is an unsafe method', () => {
    void uploadDayAttachment('trip-1', '2026-10-10', file())

    expect(FakeXhr.instances[0]!.requestHeaders['X-CSRF-Token']).toBe('test-csrf-token')
  })

  it('reports upload progress with the bytes loaded and the total', () => {
    const onProgress = vi.fn()
    void uploadDayAttachment('trip-1', '2026-10-10', file(), { onProgress })

    const xhr = FakeXhr.instances[0]!
    xhr.progress(512, 1024)

    expect(onProgress).toHaveBeenCalledWith({ loaded: 512, total: 1024 })
  })

  it('resolves with the created attachment on a 201', async () => {
    const promise = uploadDayAttachment('trip-1', '2026-10-10', file())

    FakeXhr.instances[0]!.respond(201, ATTACHMENT)

    await expect(promise).resolves.toEqual(ATTACHMENT)
  })

  it('rejects with an ApiError carrying the server error code', async () => {
    const promise = uploadDayAttachment('trip-1', '2026-10-10', file())

    FakeXhr.instances[0]!.respond(413, { error: { code: 'attachment_too_large', field: 'file' } })

    await expect(promise).rejects.toMatchObject({
      name: 'ApiError',
      status: 413,
      code: 'attachment_too_large',
      field: 'file',
    })
  })

  it('notifies the shared unauthenticated handler on a 401', async () => {
    const onUnauthenticated = vi.fn()
    setUnauthenticatedHandler(onUnauthenticated)

    const promise = uploadDayAttachment('trip-1', '2026-10-10', file())
    FakeXhr.instances[0]!.respond(401, { error: { code: 'not_authenticated' } })

    await expect(promise).rejects.toMatchObject({ status: 401 })
    expect(onUnauthenticated).toHaveBeenCalledTimes(1)
  })

  it('aborting produces no success and no row', async () => {
    const controller = new AbortController()
    const promise = uploadDayAttachment('trip-1', '2026-10-10', file(), {
      signal: controller.signal,
    })

    controller.abort()

    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
    expect(FakeXhr.instances[0]!.aborted).toBe(true)

    // A late, out-of-order server answer must not flip an aborted upload into
    // a success — the abort already settled the promise.
    FakeXhr.instances[0]!.respond(201, ATTACHMENT)
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('an already-aborted signal aborts before the request is sent anything back', async () => {
    const controller = new AbortController()
    controller.abort()

    const promise = uploadDayAttachment('trip-1', '2026-10-10', file(), {
      signal: controller.signal,
    })

    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('attachmentContentUrl', () => {
  it('is a path, not a fetch — used directly as an <img src> and download href', () => {
    expect(attachmentContentUrl('trip-1', 'attachment-1')).toBe(
      '/api/v1/trips/trip-1/attachments/attachment-1/content',
    )
  })
})
