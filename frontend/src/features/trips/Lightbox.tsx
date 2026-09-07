import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Step 4.2: an image attachment opens larger, in a focus-trapped dialog.
 *
 * Only images ever reach this component — `AttachmentRow` never wires a PDF's
 * preview to it, because inline PDF preview is cut outright (A10: serving a
 * PDF `inline` would run its JavaScript in this origin with the session cookie
 * in scope). The PDF action stays a download link; there is nothing here for
 * it to open.
 *
 * `src` is `attachmentContentUrl` — the same bytes the row's own `<img>`
 * already requests, never a server-generated thumbnail (A12: the server never
 * decodes an image). `filename` is the accessible name: it is the `<img>`'s
 * `alt`, and nothing else in the dialog repeats it as a caption.
 *
 * The focus discipline is copied verbatim from `ConfirmDialog`, not
 * reinvented: focus moves onto the close button on open, is trapped inside
 * the panel while it is open (`Tab`/`Shift+Tab` cycle only through the
 * elements here), `Escape` closes it, and closing — by any path — returns
 * focus to whatever triggered it. A `<dialog>` element's `showModal()` is
 * deliberately not used, for the same reason `ItemDialog` gives: its native
 * focus behaviour is not implemented consistently enough in jsdom for the
 * trap itself to be verified.
 */

const FOCUSABLE = 'button:not([disabled])'

export function Lightbox({
  src,
  filename,
  onClose,
}: {
  src: string
  filename: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const panel = useRef<HTMLDivElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const trigger = useRef<Element | null>(null)

  useEffect(() => {
    trigger.current = document.activeElement
    closeButton.current?.focus()

    return () => {
      if (trigger.current instanceof HTMLElement && document.contains(trigger.current)) {
        trigger.current.focus()
      }
    }
  }, [])

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      onClose()
      return
    }

    if (event.key !== 'Tab' || panel.current === null) {
      return
    }

    const focusable = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (first === undefined || last === undefined) {
      return
    }

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="dialog-overlay" onKeyDown={handleKeyDown}>
      <div
        className="dialog dialog--lightbox"
        role="dialog"
        aria-modal="true"
        aria-label={filename}
        ref={panel}
      >
        <button
          type="button"
          className="button-quiet dialog--lightbox__close"
          ref={closeButton}
          onClick={onClose}
        >
          {t('attachment.lightboxClose')}
        </button>
        {/* The original file — the same URL the row's own preview requests,
            never a server-generated thumbnail (A12). The filename is the
            accessible name; nothing beside it repeats it as a caption. */}
        <img className="dialog--lightbox__image" src={src} alt={filename} />
      </div>
    </div>
  )
}
