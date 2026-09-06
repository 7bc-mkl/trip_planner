import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import { attachmentContentUrl } from '../../api/attachments'
import { applyLocale, initI18n } from '../../i18n'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { AttachmentRow } from './AttachmentRow'

/**
 * Step 2.5: download and delete, on the row shared by both hosts. Tested
 * directly on `AttachmentRow` rather than through `DayAttachments` or
 * `ItemAttachments` — both actions and the confirmation live here once, and a
 * host only ever forwards `onDeleted` (see `dayAttachments.test.tsx` and
 * `itemAttachments.test.tsx` for the hosts' own wiring).
 */

const ATTACHMENT: Attachment = {
  id: 'attachment-1',
  filename: 'Voucher_The_Chow_Kit.pdf',
  content_type: 'application/pdf',
  byte_size: 1024,
  sha256: 'attachment-sha',
  created_at: '2026-09-06T10:11:12Z',
  item_id: 'item-1',
  trip_day_id: null,
}

let requests: { method: string }[] = []

function mockApi(onDelete?: () => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase()
      requests.push({ method })
      if (method === 'DELETE') {
        return Promise.resolve(onDelete?.() ?? new Response(null, { status: 204 }))
      }
      return Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )
}

beforeEach(async () => {
  requests = []
  initI18n('pl')
  await applyLocale('pl')
  document.cookie = 'csrf_token=test-csrf-token; path=/'
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the download action', () => {
  it('is a link to the content URL, never a click handler', () => {
    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={vi.fn()} />)

    const link = screen.getByRole('link', { name: pl.attachment.download })
    expect(link.tagName).toBe('A')
    expect(link).toHaveAttribute('href', attachmentContentUrl('trip-1', ATTACHMENT.id))
  })

  it('renders no fetch call at all — the server\'s Content-Disposition header does the downloading', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={vi.fn()} />)

    // A plain <a href>, not a click handler that reads the bytes into memory
    // to build a blob URL: rendering the row alone must never call fetch.
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('says "Pobierz", never a preview word (A10: inline PDF preview is cut)', () => {
    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={vi.fn()} />)

    expect(screen.getByRole('link', { name: 'Pobierz' })).toBeInTheDocument()
    expect(pl.attachment.download).toBe('Pobierz')
    expect(screen.queryByText(/podgląd/iu)).not.toBeInTheDocument()
  })

  it('says "Download" in English, never "Preview"', async () => {
    await applyLocale('en')

    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={vi.fn()} />)

    expect(screen.getByRole('link', { name: en.attachment.download })).toBeInTheDocument()
    expect(en.attachment.download).toBe('Download')
    expect(screen.queryByText(/preview/iu)).not.toBeInTheDocument()
  })
})

describe('the delete action', () => {
  async function openConfirmation(deleteLabel: string = pl.attachment.delete) {
    const user = userEvent.setup()
    mockApi()
    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: deleteLabel }))
    return user
  }

  it('asks for confirmation instead of deleting straight away', async () => {
    await openConfirmation()

    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(requests.some((entry) => entry.method === 'DELETE')).toBe(false)
  })

  it('names the file rather than saying "this item", in Polish', async () => {
    await openConfirmation()

    expect(screen.getByRole('dialog')).toHaveTextContent(ATTACHMENT.filename)
  })

  it('names the file in English too', async () => {
    await applyLocale('en')
    await openConfirmation(en.attachment.delete)

    expect(screen.getByRole('dialog')).toHaveTextContent(ATTACHMENT.filename)
  })

  it('cancelling deletes nothing and closes the dialog', async () => {
    const user = await openConfirmation()

    await user.click(screen.getByRole('button', { name: pl.item.cancel }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(requests.some((entry) => entry.method === 'DELETE')).toBe(false)
  })

  it('a cancelled delete calls neither the API nor the host refresh', async () => {
    const onDeleted = vi.fn()
    const user = userEvent.setup()
    mockApi()
    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={onDeleted} />)

    await user.click(screen.getByRole('button', { name: pl.attachment.delete }))
    await user.click(screen.getByRole('button', { name: pl.item.cancel }))

    expect(requests.some((entry) => entry.method === 'DELETE')).toBe(false)
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('returns focus to the trigger when the dialog closes on cancel', async () => {
    const user = userEvent.setup()
    mockApi()
    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={vi.fn()} />)

    const trigger = screen.getByRole('button', { name: pl.attachment.delete })
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: pl.item.cancel }))

    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('confirming calls the delete API and refreshes the host list', async () => {
    const user = userEvent.setup()
    mockApi()
    const onDeleted = vi.fn()
    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={onDeleted} />)

    await user.click(screen.getByRole('button', { name: pl.attachment.delete }))
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: pl.attachment.deleteConfirm }),
    )

    await waitFor(() => expect(requests.some((entry) => entry.method === 'DELETE')).toBe(true))
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('returns focus to the trigger when the dialog closes on confirm', async () => {
    const user = userEvent.setup()
    mockApi()
    render(<AttachmentRow tripId="trip-1" attachment={ATTACHMENT} onDeleted={vi.fn()} />)

    const trigger = screen.getByRole('button', { name: pl.attachment.delete })
    await user.click(trigger)
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: pl.attachment.deleteConfirm }),
    )

    await waitFor(() => expect(trigger).toHaveFocus())
  })
})
