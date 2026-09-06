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
 * Step 4.2: the image lightbox.
 *
 * Exercised through `AttachmentRow` rather than mounting `Lightbox` bare with
 * an invented trigger — the row's preview button is the only trigger it has
 * in the real app, and the focus-return assertions below are only meaningful
 * against the element a user actually clicked.
 */

const IMAGE_ATTACHMENT: Attachment = {
  id: 'attachment-2',
  filename: 'Bilet_lotniczy.jpg',
  content_type: 'image/jpeg',
  byte_size: 2048,
  sha256: 'image-sha',
  created_at: '2026-09-06T10:11:12Z',
  item_id: 'item-1',
  trip_day_id: null,
}

const PDF_ATTACHMENT: Attachment = {
  id: 'attachment-1',
  filename: 'Voucher.pdf',
  content_type: 'application/pdf',
  byte_size: 1024,
  sha256: 'pdf-sha',
  created_at: '2026-09-06T10:11:12Z',
  item_id: 'item-1',
  trip_day_id: null,
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function openLightbox() {
  const user = userEvent.setup()
  render(<AttachmentRow tripId="trip-1" attachment={IMAGE_ATTACHMENT} onDeleted={vi.fn()} />)
  const trigger = screen.getByRole('button', { name: IMAGE_ATTACHMENT.filename })
  await user.click(trigger)
  return { user, trigger }
}

describe('the image lightbox', () => {
  it('opens on the preview, showing the original file — never a thumbnail (A12)', async () => {
    await openLightbox()

    // Scoped to the dialog: the row's own preview behind it carries the same
    // alt text, and is correctly still in the document underneath.
    const image = within(screen.getByRole('dialog')).getByRole('img', {
      name: IMAGE_ATTACHMENT.filename,
    })
    // The same URL the row's own preview already requested — not a second,
    // server-generated asset.
    expect(image).toHaveAttribute(
      'src',
      attachmentContentUrl('trip-1', IMAGE_ATTACHMENT.id),
    )
  })

  it('carries the filename as its accessible name', async () => {
    await openLightbox()

    expect(
      within(screen.getByRole('dialog')).getByRole('img', { name: IMAGE_ATTACHMENT.filename }),
    ).toBeInTheDocument()
  })

  it('moves focus into the dialog on open', async () => {
    await openLightbox()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: pl.attachment.lightboxClose })).toHaveFocus(),
    )
  })

  it('traps focus: Tab does not walk out to the page behind', async () => {
    const { user } = await openLightbox()
    const close = screen.getByRole('button', { name: pl.attachment.lightboxClose })

    await user.tab()

    expect(close).toHaveFocus()
  })

  it('traps focus: Shift+Tab does not walk out to the page behind either', async () => {
    const { user } = await openLightbox()
    const close = screen.getByRole('button', { name: pl.attachment.lightboxClose })

    await user.tab({ shift: true })

    expect(close).toHaveFocus()
  })

  it('closes on Escape', async () => {
    const { user } = await openLightbox()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('returns focus to the trigger when closed via Escape', async () => {
    const { user, trigger } = await openLightbox()

    await user.keyboard('{Escape}')

    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('returns focus to the trigger when closed via the close button', async () => {
    const { user, trigger } = await openLightbox()

    await user.click(screen.getByRole('button', { name: pl.attachment.lightboxClose }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('the close button says "Zamknij" in Polish', async () => {
    await openLightbox()

    expect(screen.getByRole('button', { name: 'Zamknij' })).toBeInTheDocument()
    expect(pl.attachment.lightboxClose).toBe('Zamknij')
  })

  it('the close button says "Close" in English', async () => {
    await applyLocale('en')

    await openLightbox()

    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
    expect(en.attachment.lightboxClose).toBe('Close')
  })
})

describe('a PDF attachment', () => {
  it('never opens a lightbox — the split is that there is no preview button to click', () => {
    render(<AttachmentRow tripId="trip-1" attachment={PDF_ATTACHMENT} onDeleted={vi.fn()} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
