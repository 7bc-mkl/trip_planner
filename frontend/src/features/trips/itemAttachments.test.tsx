import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import type { Item } from '../../api/items'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
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
    ...overrides,
  }
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
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

  it('renders the English empty state and the new-item message too', async () => {
    await applyLocale('en')

    render(
      <ItemAttachments tripId="trip-1" item={null} onUploaded={vi.fn()} onDeleted={vi.fn()} />,
    )

    expect(screen.getByText(en.itemAttachments.saveFirst)).toBeInTheDocument()
  })
})
