import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { UploadDropzone, precheck } from './UploadDropzone'

/**
 * The drop zone's own contract, asserted without a screen around it.
 *
 * Uploads run on `XMLHttpRequest` (see `api/attachments.ts`), so `fetch` cannot
 * be stubbed the way the screen suites stub it. This is the same fake
 * `api/attachments.test.ts` uses, kept deliberately minimal: open/send, the
 * three events the client listens for, and enough inspection to prove *which*
 * requests were issued — and, for the pre-check, that none was.
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

const DAY = { kind: 'day', tripId: 'trip-1', date: '2026-10-11' } as const

const ATTACHMENT: Attachment = {
  id: 'attachment-1',
  filename: 'voucher.pdf',
  content_type: 'application/pdf',
  byte_size: 1024,
  sha256: 'abc',
  created_at: '2026-09-06T10:11:12Z',
  item_id: null,
  trip_day_id: 'day-1',
}

function pdf(name = 'voucher.pdf', bytes = 1024): File {
  const file = new File(['%PDF-1.4 …'], name, { type: 'application/pdf' })
  Object.defineProperty(file, 'size', { value: bytes })
  return file
}

/** The file input, addressed the way a user reaches it: by its label. */
function dropzone(locale: 'pl' | 'en' = 'pl'): HTMLInputElement {
  const label = locale === 'pl' ? pl.upload.add : en.upload.add
  return screen.getByLabelText(new RegExp(label)) as HTMLInputElement
}

/** The one row for one file — the unit per-file independence is asserted on. */
function row(filename: string): HTMLElement {
  return screen.getByText(filename).closest('li')!
}

beforeEach(async () => {
  FakeXhr.instances = []
  vi.stubGlobal('XMLHttpRequest', FakeXhr as unknown as typeof XMLHttpRequest)
  initI18n('pl')
  await applyLocale('pl')
})

afterEach(async () => {
  vi.unstubAllGlobals()
  await applyLocale('pl')
})

describe('the upload drop zone', () => {
  it('is a real label over a real file input, with `accept` as a picker convenience', () => {
    render(<UploadDropzone target={DAY} />)

    const input = dropzone()
    expect(input.tagName).toBe('INPUT')
    expect(input.type).toBe('file')
    expect(input.accept).toBe('.pdf,.jpg,.jpeg,.png')
    // Idle: no rows at all.
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows the selected state while the request is in flight but has reported no bytes yet', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), pdf())

    expect(within(row('voucher.pdf')).getByText(pl.upload.state.selected)).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(FakeXhr.instances).toHaveLength(1)
  })

  it('shows a determinate progress bar once real byte counts arrive', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), pdf())
    FakeXhr.instances[0]!.progress(512, 1024)

    const bar = await screen.findByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '50')
    expect(within(row('voucher.pdf')).getByText(pl.upload.state.uploading)).toBeInTheDocument()
  })

  it('announces progress and completion through the polite live region', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    const live = document.querySelector('[aria-live="polite"]')!
    expect(live).toBeInTheDocument()

    await user.upload(dropzone(), pdf())
    FakeXhr.instances[0]!.progress(512, 1024)
    await waitFor(() => expect(live.textContent).toContain('voucher.pdf'))
    expect(live.textContent).toMatch(/50\s*%/)

    FakeXhr.instances[0]!.respond(201, ATTACHMENT)
    await waitFor(() => expect(live.textContent).toBe('Dodano voucher.pdf'))
  })

  it('reaches done and hands the attachment to its caller', async () => {
    const user = userEvent.setup()
    const onUploaded = vi.fn()
    render(<UploadDropzone target={DAY} onUploaded={onUploaded} />)

    await user.upload(dropzone(), pdf())
    FakeXhr.instances[0]!.respond(201, ATTACHMENT)

    await waitFor(() =>
      expect(within(row('voucher.pdf')).getByText(pl.upload.state.done)).toBeInTheDocument(),
    )
    expect(onUploaded).toHaveBeenCalledWith(ATTACHMENT)
  })

  it('posts to the item endpoint when the target is an item', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={{ kind: 'item', tripId: 'trip-1', itemId: 'item-1' }} />)

    await user.upload(dropzone(), pdf())

    expect(FakeXhr.instances[0]!.url).toBe('/api/v1/trips/trip-1/items/item-1/attachments')
  })
})

describe('the client-side pre-check', () => {
  it('refuses on extension and on size, and decides nothing the server does not', () => {
    expect(precheck(pdf('ticket.pdf'))).toBeNull()
    expect(precheck(pdf('photo.jpg'))).toBeNull()
    expect(precheck(pdf('archive.zip'))).toBe('unsupported_file_type')
    expect(precheck(pdf('huge.pdf', 10 * 1024 * 1024 + 1))).toBe('attachment_too_large')
    expect(precheck(pdf('empty.pdf', 0))).toBe('malformed_upload')
    // Exactly at the ceiling is the server's to accept, not the client's to refuse.
    expect(precheck(pdf('atlimit.pdf', 10 * 1024 * 1024))).toBeNull()
  })

  it('issues NO request for a file it refuses, and says why in the reader’s language', async () => {
    // `applyAccept: false` is the point of this test rather than a workaround
    // around it: `user-event` emulates the picker's own `accept` filter, and
    // `accept` is a convenience the real world walks straight past — "All files"
    // in the picker, or a drop. The pre-check is what has to catch this.
    const user = userEvent.setup({ applyAccept: false })
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), pdf('archive.zip'))

    expect(FakeXhr.instances).toHaveLength(0)
    expect(screen.getByRole('alert')).toHaveTextContent(pl.error.unsupported_file_type)
    // Nothing to retry: the same file would be refused identically.
    expect(screen.queryByRole('button', { name: pl.upload.retry })).not.toBeInTheDocument()
  })

  it('refuses an oversized file with the same message the server would have sent', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), pdf('huge.pdf', 12 * 1024 * 1024))

    expect(FakeXhr.instances).toHaveLength(0)
    expect(screen.getByRole('alert')).toHaveTextContent(pl.error.attachment_too_large)
  })
})

describe('failure', () => {
  const CODES = [
    'attachment_too_large',
    'unsupported_file_type',
    'malformed_upload',
    'attachment_limit_reached',
    'trip_storage_quota_exceeded',
    'rate_limited',
  ] as const

  for (const code of CODES) {
    it(`renders the translated message for ${code}, never the code`, async () => {
      const user = userEvent.setup()
      render(<UploadDropzone target={DAY} />)

      await user.upload(dropzone(), pdf())
      FakeXhr.instances[0]!.respond(400, { error: { code } })

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(pl.error[code])
      expect(alert).not.toHaveTextContent(code)
      expect(within(row('voucher.pdf')).getByText(pl.upload.state.failed)).toBeInTheDocument()
    })
  }

  it('renders the same refusal in English when the locale is English', async () => {
    await applyLocale('en')
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone('en'), pdf())
    FakeXhr.instances[0]!.respond(429, { error: { code: 'rate_limited' } })

    expect(await screen.findByRole('alert')).toHaveTextContent(en.error.rate_limited)
  })

  it('falls back to the unknown message when the server names no code', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), pdf())
    FakeXhr.instances[0]!.respond(500, 'not json at all')

    expect(await screen.findByRole('alert')).toHaveTextContent(pl.error.unknown)
  })

  it('retries a failed upload, and the retry can succeed', async () => {
    const user = userEvent.setup()
    const onUploaded = vi.fn()
    render(<UploadDropzone target={DAY} onUploaded={onUploaded} />)

    await user.upload(dropzone(), pdf())
    FakeXhr.instances[0]!.respond(429, { error: { code: 'rate_limited' } })

    await user.click(await screen.findByRole('button', { name: pl.upload.retry }))
    expect(FakeXhr.instances).toHaveLength(2)

    FakeXhr.instances[1]!.respond(201, ATTACHMENT)

    await waitFor(() =>
      expect(within(row('voucher.pdf')).getByText(pl.upload.state.done)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(onUploaded).toHaveBeenCalledWith(ATTACHMENT)
  })

  it('aborts the request when an upload is cancelled', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), pdf())
    FakeXhr.instances[0]!.progress(100, 1024)

    await user.click(await screen.findByRole('button', { name: pl.upload.cancel }))

    expect(FakeXhr.instances[0]!.aborted).toBe(true)
    expect(screen.queryByText('voucher.pdf')).not.toBeInTheDocument()
  })
})

describe('per-file independence', () => {
  it('gives every selected file its own row, its own request and its own outcome', async () => {
    const user = userEvent.setup()
    const onUploaded = vi.fn()
    render(<UploadDropzone target={DAY} onUploaded={onUploaded} />)

    await user.upload(dropzone(), [
      pdf('a.pdf'),
      pdf('b.pdf'),
      pdf('c.pdf'),
      pdf('d.pdf'),
      pdf('e.pdf'),
    ])

    expect(screen.getAllByRole('listitem')).toHaveLength(5)
    expect(FakeXhr.instances).toHaveLength(5)

    // The middle one fails; the other four are untouched by it.
    FakeXhr.instances[2]!.respond(429, { error: { code: 'rate_limited' } })
    for (const index of [0, 1, 3, 4]) {
      FakeXhr.instances[index]!.respond(201, { ...ATTACHMENT, filename: `${index}.pdf` })
    }

    await waitFor(() =>
      expect(within(row('c.pdf')).getByText(pl.upload.state.failed)).toBeInTheDocument(),
    )
    for (const name of ['a.pdf', 'b.pdf', 'd.pdf', 'e.pdf']) {
      expect(within(row(name)).getByText(pl.upload.state.done)).toBeInTheDocument()
    }
    expect(onUploaded).toHaveBeenCalledTimes(4)
    expect(screen.getAllByRole('alert')).toHaveLength(1)
  })

  it('a locally refused file does not stop the acceptable ones beside it', async () => {
    const user = userEvent.setup({ applyAccept: false })
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), [pdf('ok.pdf'), pdf('nope.zip')])

    expect(FakeXhr.instances).toHaveLength(1)
    expect(within(row('ok.pdf')).getByText(pl.upload.state.selected)).toBeInTheDocument()
    expect(within(row('nope.zip')).getByText(pl.upload.state.failed)).toBeInTheDocument()
  })
})

describe('no state by colour alone', () => {
  it('every state renders a translated word beside its glyph', async () => {
    const user = userEvent.setup()
    render(<UploadDropzone target={DAY} />)

    await user.upload(dropzone(), pdf())
    const pill = row('voucher.pdf').querySelector('.upload-row__pill')!
    expect(pill).toHaveTextContent(pl.upload.state.selected)
    expect(pill.querySelector('[aria-hidden="true"]')).toBeInTheDocument()

    FakeXhr.instances[0]!.respond(201, ATTACHMENT)
    await waitFor(() => expect(pill).toHaveTextContent(pl.upload.state.done))
  })
})
