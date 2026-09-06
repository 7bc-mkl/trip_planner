/**
 * A minimal `XMLHttpRequest` stand-in for the upload path.
 *
 * Uploads run on `XMLHttpRequest` (see `api/attachments.ts`) because `fetch`
 * has no upload-progress event, so `fetch` cannot be stubbed the way the screen
 * suites stub it. This is that stub, shared by every suite that drives an
 * upload rather than copied into each: open/send, the three events the client
 * listens for, and enough inspection to prove *which* requests were issued —
 * and, for the pre-check, that none was.
 */

type Listener = () => void

export class FakeXhr {
  static instances: FakeXhr[] = []

  /** Call in `beforeEach`, before stubbing the global. */
  static reset(): void {
    FakeXhr.instances = []
  }

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
