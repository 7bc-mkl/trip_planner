import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import { attachmentContentUrl } from '../../api/attachments'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { DayAttachments } from './DayAttachments'

/**
 * The day-level documents panel, tested on its own: `DayDetailPage` hands it
 * plain props (the day's own `attachments`, already fetched), so this Step's
 * contract is the panel's own rendering — no router and no `fetch` stub are
 * needed to exercise it.
 */

const PDF: Attachment = {
  id: 'attachment-pdf',
  filename: 'Transfer_lotnisko_KLIA_Ekspres.pdf',
  content_type: 'application/pdf',
  byte_size: 1024,
  sha256: 'pdf-sha',
  created_at: '2026-09-06T10:11:12Z',
  item_id: null,
  trip_day_id: 'day-1',
}

const PHOTO: Attachment = {
  id: 'attachment-photo',
  filename: 'mapa_okolicy_screenshot.png',
  content_type: 'image/png',
  byte_size: 2 * 1024 * 1024,
  sha256: 'photo-sha',
  created_at: '2026-09-06T10:12:00Z',
  item_id: null,
  trip_day_id: 'day-1',
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

describe('the day documents panel', () => {
  it("renders the day's attachments", () => {
    render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[PDF, PHOTO]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(PDF.filename)).toBeInTheDocument()
    expect(screen.getByText(PHOTO.filename)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: pl.dayAttachments.list })).toBeInTheDocument()
  })

  it('renders the shipped empty-state recipe when there are none', () => {
    const { container } = render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(pl.dayAttachments.empty)).toBeInTheDocument()
    expect(container.querySelector('.empty-state')).not.toBeNull()
    // Never an empty <ul>: no list is rendered at all when there is nothing to list.
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('renders the heading, the list and the dropzone label in English too', async () => {
    await applyLocale('en')

    render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[PDF]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(en.dayAttachments.heading)).toBeInTheDocument()
    expect(screen.getByText(PDF.filename)).toBeInTheDocument()
    expect(screen.getByText(en.upload.add)).toBeInTheDocument()
  })

  it('renders the English empty state too', async () => {
    await applyLocale('en')

    render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(en.dayAttachments.empty)).toBeInTheDocument()
  })

  it('renders a lazy-loaded image preview — the original file, with the filename as alt text', () => {
    render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[PHOTO]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    const preview = screen.getByAltText(PHOTO.filename)
    expect(preview.tagName).toBe('IMG')
    expect(preview).toHaveAttribute('loading', 'lazy')
    // Never a server-generated thumbnail (A12): the same content URL a
    // download would use, scaled down by CSS alone.
    expect(preview).toHaveAttribute('src', attachmentContentUrl('trip-1', PHOTO.id))
    expect(screen.getByRole('img')).toBe(preview)
  })

  it('renders the document glyph, not a preview, for a PDF', () => {
    const { container } = render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[PDF]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    const use = container.querySelector('.attachment-row__glyph svg use')
    expect(use?.getAttribute('href')).toMatch(/icons\.svg.*#document$/u)
    expect(container.querySelector('.attachment-row__glyph svg')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
  })

  it('formats the size through a translated ICU key, never by concatenation', () => {
    render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[PDF, PHOTO]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    // 1024 bytes and 2 * 1024 * 1024 bytes: exactly one KB and one MB.
    expect(screen.getByText('1 KB')).toBeInTheDocument()
    expect(screen.getByText('2 MB')).toBeInTheDocument()
  })

  it("hosts the dropzone with the export's verbatim label, kept as-is", () => {
    render(
      <DayAttachments
        tripId="trip-1"
        date="2026-10-11"
        attachments={[]}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    expect(screen.getByText(pl.upload.add)).toBeInTheDocument()
  })
})
