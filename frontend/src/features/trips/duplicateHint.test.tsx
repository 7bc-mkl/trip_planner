import { useState } from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Attachment } from '../../api/attachments'
import type { Item } from '../../api/items'
import en from '../../locales/en.json'
import pl from '../../locales/pl.json'
import { applyLocale, initI18n } from '../../i18n'
import { FakeXhr } from '../../test/fakeXhr'
import { DayAttachments } from './DayAttachments'
import { ItemAttachments } from './ItemAttachments'

/**
 * The duplicate hint (A14), asserted **against the composed host** — which is
 * the whole point of this file.
 *
 * Step 4.3 shipped the hint on the upload queue's own row, and every test it
 * came with passed while the feature was dead in the real app: a host appends
 * the new attachment in the same React batch that moves the row to `done`, so
 * the row retires before it is ever painted and the hint had no surface left.
 * Testing the drop zone in isolation could not see that, because in isolation
 * nothing ever retires.
 *
 * So every test here renders a host whose list actually updates, the way
 * `DayDetailPage` and `ItemDialog` do, and asserts on what the owner ends up
 * looking at: the attachment row.
 */

const EXISTING_DAY_PDF: Attachment = {
  id: 'attachment-existing',
  filename: 'Voucher_hotel.pdf',
  content_type: 'application/pdf',
  byte_size: 1024,
  sha256: 'same-bytes',
  created_at: '2026-09-06T10:11:12Z',
  item_id: null,
  trip_day_id: 'day-1',
}

const EXISTING_ITEM_PDF: Attachment = {
  ...EXISTING_DAY_PDF,
  id: 'attachment-existing-item',
  item_id: 'item-1',
  trip_day_id: null,
}

function pdf(name: string): File {
  const file = new File(['%PDF-1.4 …'], name, { type: 'application/pdf' })
  Object.defineProperty(file, 'size', { value: 1024 })
  return file
}

function item(attachments: Attachment[]): Item {
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
    attachment_count: attachments.length,
    attachments,
    confirmation_number: null,
    cost_amount: null,
    cost_currency: null,
  }
}

/** `DayDetailPage` at its smallest: it refetches, and the panel re-renders with the new list. */
function HostedDay({ initial = [] as Attachment[] }: { initial?: Attachment[] }) {
  const [attachments, setAttachments] = useState<Attachment[]>(initial)
  return (
    <DayAttachments
      tripId="trip-1"
      date="2026-10-11"
      attachments={attachments}
      onUploaded={(attachment) => setAttachments((previous) => [...previous, attachment])}
      onDeleted={vi.fn()}
    />
  )
}

function dropzoneIn(panel: HTMLElement, locale: 'pl' | 'en' = 'pl'): HTMLInputElement {
  const label = locale === 'pl' ? pl.upload.add : en.upload.add
  return within(panel).getByLabelText(new RegExp(label)) as HTMLInputElement
}

beforeEach(async () => {
  initI18n('pl')
  await applyLocale('pl')
  FakeXhr.reset()
  vi.stubGlobal('XMLHttpRequest', FakeXhr as unknown as typeof XMLHttpRequest)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the duplicate hint on the day panel', () => {
  it('renders on the attachment row once the same bytes land on the same day, and both copies survive', async () => {
    const user = userEvent.setup()
    const { container } = render(<HostedDay initial={[EXISTING_DAY_PDF]} />)

    await user.upload(dropzoneIn(container.querySelector('.day-attachments')!), pdf('kopia.pdf'))
    FakeXhr.instances[0]!.respond(201, {
      ...EXISTING_DAY_PDF,
      id: 'attachment-fresh',
      filename: 'kopia.pdf',
    })

    // The hint is on screen at all — the assertion Step 4.3 never actually made.
    await waitFor(() =>
      expect(screen.getAllByText(pl.upload.duplicateHint).length).toBeGreaterThan(0),
    )

    // Nothing was deduplicated and nothing was refused (A14): both copies are
    // listed, each with its own row, and the upload plainly succeeded.
    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(screen.getByText('kopia.pdf')).toBeInTheDocument()
    expect(screen.getByText(EXISTING_DAY_PDF.filename)).toBeInTheDocument()

    // The hint rides on the rows themselves, so it is the file's one
    // representation carrying it — never a second card or banner beside them.
    for (const row of rows) {
      expect(within(row).getByText(pl.upload.duplicateHint)).toBeInTheDocument()
    }

    // Informational, not an error: no alert, and the queue is gone as before.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: pl.upload.list })).not.toBeInTheDocument()
  })

  it('renders it in English too', async () => {
    await applyLocale('en')
    const user = userEvent.setup()
    const { container } = render(<HostedDay initial={[EXISTING_DAY_PDF]} />)

    await user.upload(
      dropzoneIn(container.querySelector('.day-attachments')!, 'en'),
      pdf('kopia.pdf'),
    )
    FakeXhr.instances[0]!.respond(201, {
      ...EXISTING_DAY_PDF,
      id: 'attachment-fresh',
      filename: 'kopia.pdf',
    })

    expect((await screen.findAllByText(en.upload.duplicateHint)).length).toBeGreaterThan(0)
  })

  it('shows no hint when the uploaded bytes are new to the day', async () => {
    const user = userEvent.setup()
    const { container } = render(<HostedDay initial={[EXISTING_DAY_PDF]} />)

    await user.upload(dropzoneIn(container.querySelector('.day-attachments')!), pdf('inny.pdf'))
    FakeXhr.instances[0]!.respond(201, {
      ...EXISTING_DAY_PDF,
      id: 'attachment-fresh',
      filename: 'inny.pdf',
      sha256: 'other-bytes',
    })

    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
    expect(screen.queryByText(pl.upload.duplicateHint)).not.toBeInTheDocument()
  })

  it('drops the hint again when one of the two copies is deleted', async () => {
    // Derived from the list rather than remembered from the upload, so the
    // sentence stops being shown the moment it stops being true.
    function Shrinking() {
      const [attachments, setAttachments] = useState<Attachment[]>([
        EXISTING_DAY_PDF,
        { ...EXISTING_DAY_PDF, id: 'attachment-copy', filename: 'kopia.pdf' },
      ])
      return (
        <>
          <button type="button" onClick={() => setAttachments([EXISTING_DAY_PDF])}>
            forget the copy
          </button>
          <DayAttachments
            tripId="trip-1"
            date="2026-10-11"
            attachments={attachments}
            onUploaded={vi.fn()}
            onDeleted={vi.fn()}
          />
        </>
      )
    }

    const user = userEvent.setup()
    render(<Shrinking />)
    expect(screen.getAllByText(pl.upload.duplicateHint)).toHaveLength(2)

    await user.click(screen.getByRole('button', { name: 'forget the copy' }))
    expect(screen.queryByText(pl.upload.duplicateHint)).not.toBeInTheDocument()
  })
})

describe('the duplicate hint on the item strip', () => {
  it('renders on the attachment row once the same bytes land on the same item', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <ItemAttachments
        tripId="trip-1"
        item={item([EXISTING_ITEM_PDF])}
        onUploaded={vi.fn()}
        onDeleted={vi.fn()}
      />,
    )

    await user.upload(dropzoneIn(container.querySelector('.item-attachments')!), pdf('kopia.pdf'))
    FakeXhr.instances[0]!.respond(201, {
      ...EXISTING_ITEM_PDF,
      id: 'attachment-fresh',
      filename: 'kopia.pdf',
    })

    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
    expect(screen.getAllByText(pl.upload.duplicateHint)).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('the same bytes on a different parent are not a duplicate', () => {
  /**
   * Deliberately one test with both halves in it. The previous Step's version
   * of this passed vacuously — no hint rendered anywhere, so of course none
   * rendered on the other parent. Here the *same render* proves the mechanism
   * is live: the day panel already holds these bytes and shows the hint, while
   * the item strip receiving the identical file shows nothing.
   */
  it('shows the hint on the parent that holds both copies and nowhere else', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <>
        <HostedDay initial={[EXISTING_DAY_PDF]} />
        <ItemAttachments
          tripId="trip-1"
          item={item([])}
          onUploaded={vi.fn()}
          onDeleted={vi.fn()}
        />
      </>,
    )

    const dayPanel = container.querySelector<HTMLElement>('.day-attachments')!
    const itemStrip = container.querySelector<HTMLElement>('.item-attachments')!

    // The same bytes, onto the *item* — a legitimate second attachment.
    await user.upload(dropzoneIn(itemStrip), pdf('kopia.pdf'))
    FakeXhr.instances[0]!.respond(201, {
      ...EXISTING_ITEM_PDF,
      id: 'attachment-on-item',
      filename: 'kopia.pdf',
    })

    await waitFor(() => expect(within(itemStrip).getAllByRole('listitem')).toHaveLength(1))
    expect(screen.queryByText(pl.upload.duplicateHint)).not.toBeInTheDocument()

    // …and the same bytes onto the day that already has them, in the same
    // render tree. If this stops showing the hint, the assertion above became
    // vacuous and this test fails rather than passing quietly.
    await user.upload(dropzoneIn(dayPanel), pdf('kopia.pdf'))
    FakeXhr.instances[1]!.respond(201, {
      ...EXISTING_DAY_PDF,
      id: 'attachment-on-day',
      filename: 'kopia.pdf',
    })

    await waitFor(() => expect(within(dayPanel).getAllByRole('listitem')).toHaveLength(2))
    expect(within(dayPanel).getAllByText(pl.upload.duplicateHint)).toHaveLength(2)
    expect(within(itemStrip).queryByText(pl.upload.duplicateHint)).not.toBeInTheDocument()
  })
})
