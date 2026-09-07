import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import type { Item } from '../../api/items'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { FakeXhr } from '../../test/fakeXhr'
import { ItemAttachments } from './ItemAttachments'

/**
 * The item-level attachment strip, tested on its own: `ItemDialog` hands it
 * plain props (the item being edited, or `null`), so this Step's contract is
 * the strip's own rendering — none, one, several, and the unsaved-new-item
 * case — no dialog and no `fetch` stub are needed to exercise it.
 */

const VOUCHER: Attachment = {
  id: 'attachment-voucher',
  filename: 'Voucher_The_Chow_Kit.pdf',
  content_type: 'application/pdf',
  byte_size: 840 * 1024,
  sha256: 'voucher-sha',
  created_at: '2026-09-06T10:11:12Z',
  item_id: 'item-1',
  trip_day_id: null,
}

const TICKET: Attachment = {
  id: 'attachment-ticket',
  filename: 'e_bilet_klia_ekspres.png',
  content_type: 'image/png',
  byte_size: 512 * 1024,
  sha256: 'ticket-sha',
  created_at: '2026-09-06T10:12:00Z',
  item_id: 'item-1',
  trip_day_id: null,
}

function item(overrides: Partial<Item> = {}): Item {
  return {
    id: 'item-1',
    position: 0,
    kind: 'accommodation',
    status: 'to_book',
    start_time: null,
    end_time: null,
    end_date: null,
    title: 'Stay: The Chow Kit',
    notes: null,
    attachment_count: 0,
    attachments: [],
    confirmation_number: null,
    cost_amount: null,
    cost_currency: null,
    ...overrides,
  }
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the item attachment strip', () => {
  it('renders the empty state when the item has no attachments', () => {
    render(
      <ItemAttachments
        tripId="trip-1"
        item={item({ attachments: [] })}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(pl.itemAttachments.empty)).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('renders a single attachment', () => {
    render(
      <ItemAttachments
        tripId="trip-1"
        item={item({ attachments: [VOUCHER] })}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(VOUCHER.filename)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: pl.itemAttachments.list })).toBeInTheDocument()
  })

  it('renders several attachments', () => {
    render(
      <ItemAttachments
        tripId="trip-1"
        item={item({ attachments: [VOUCHER, TICKET] })}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(VOUCHER.filename)).toBeInTheDocument()
    expect(screen.getByText(TICKET.filename)).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('hosts the upload dropzone for a saved item', () => {
    render(
      <ItemAttachments
        tripId="trip-1"
        item={item({ attachments: [] })}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(pl.upload.add)).toBeInTheDocument()
  })

  describe('the new-item case', () => {
    it('renders no upload control and an explanatory line instead, for a new (unsaved) item', () => {
      render(
        <ItemAttachments tripId="trip-1" item={null} onUploaded={vi.fn()} onDeleted={vi.fn()} />,
      )

      expect(screen.getByText(pl.itemAttachments.saveFirst)).toBeInTheDocument()
      // No dropzone: there is no `itemId` yet to upload against.
      expect(screen.queryByText(pl.upload.add)).not.toBeInTheDocument()
      expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument()
    })

    it('still renders the empty state and the heading for a new item', () => {
      render(
        <ItemAttachments tripId="trip-1" item={null} onUploaded={vi.fn()} onDeleted={vi.fn()} />,
      )

      expect(screen.getByText(pl.itemAttachments.heading)).toBeInTheDocument()
      expect(screen.getByText(pl.itemAttachments.empty)).toBeInTheDocument()
    })
  })

  it('renders the heading, the list and the dropzone label in English too', async () => {
    await applyLocale('en')

    render(
      <ItemAttachments
        tripId="trip-1"
        item={item({ attachments: [VOUCHER] })}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(en.itemAttachments.heading)).toBeInTheDocument()
    expect(screen.getByText(VOUCHER.filename)).toBeInTheDocument()
    expect(screen.getByText(en.upload.add)).toBeInTheDocument()
  })

  describe('the upload queue against the strip it sits under', () => {
    /**
     * The strip is the host that appends locally, so the attachment row and
     * the finished upload settle in the same commit. That is the window where
     * showing the file twice would be a bug, and it is the window the browser
     * walk found: "✓ Dodany" under a dropzone whose file was already listed
     * above it. Counts, not presence — presence passes with the bug.
     */
    const UPLOADED: Attachment = { ...VOUCHER, id: 'attachment-fresh', filename: 'nowy.pdf' }

    function uploadable(): File {
      const file = new File(['%PDF-1.4 …'], 'nowy.pdf', { type: 'application/pdf' })
      Object.defineProperty(file, 'size', { value: 2048 })
      return file
    }

    beforeEach(() => {
      FakeXhr.reset()
      vi.stubGlobal('XMLHttpRequest', FakeXhr as unknown as typeof XMLHttpRequest)
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))),
      )
      document.cookie = 'csrf_token=test-csrf-token; path=/'
    })

    it('shows an uploaded file exactly once — as an attachment row, not also as a queue entry', async () => {
      const user = userEvent.setup()
      render(
        <ItemAttachments
          tripId="trip-1"
          item={item({ attachments: [] })}
          onUploaded={vi.fn()}
          onDeleted={vi.fn()}
        />,
      )

      await user.upload(screen.getByLabelText(new RegExp(pl.upload.add)), uploadable())
      FakeXhr.instances[0]!.respond(201, UPLOADED)

      await waitFor(() => expect(screen.getAllByText('nowy.pdf')).toHaveLength(1))
      expect(screen.queryByRole('list', { name: pl.upload.list })).not.toBeInTheDocument()
      expect(screen.queryByText(pl.upload.state.done)).not.toBeInTheDocument()
    })

    it('leaves no queue entry behind once the uploaded file is deleted', async () => {
      const user = userEvent.setup()
      render(
        <ItemAttachments
          tripId="trip-1"
          item={item({ attachments: [] })}
          onUploaded={vi.fn()}
          onDeleted={vi.fn()}
        />,
      )

      await user.upload(screen.getByLabelText(new RegExp(pl.upload.add)), uploadable())
      FakeXhr.instances[0]!.respond(201, UPLOADED)
      await waitFor(() => expect(screen.getAllByText('nowy.pdf')).toHaveLength(1))

      await user.click(screen.getByRole('button', { name: pl.attachment.delete }))
      // The confirm button carries the same word as the trigger, so it is
      // reached through the dialog rather than by name alone.
      const dialog = within(screen.getByRole('dialog'))
      await user.click(dialog.getByRole('button', { name: pl.attachment.deleteConfirm }))

      // The row goes, and nothing in the queue is left asserting a file that
      // no longer exists.
      await waitFor(() => expect(screen.queryByText('nowy.pdf')).not.toBeInTheDocument())
      expect(screen.getByText(pl.itemAttachments.empty)).toBeInTheDocument()
      expect(screen.queryByRole('list', { name: pl.upload.list })).not.toBeInTheDocument()
    })
  })

  it('renders the English empty state and the new-item message too', async () => {
    await applyLocale('en')

    render(
      <ItemAttachments tripId="trip-1" item={null} onUploaded={vi.fn()} onDeleted={vi.fn()} />,
    )

    expect(screen.getByText(en.itemAttachments.saveFirst)).toBeInTheDocument()
  })
})
