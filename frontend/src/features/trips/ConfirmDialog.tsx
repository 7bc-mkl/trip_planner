import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * A confirmation dialog for an action that cannot be undone.
 *
 * There is no undo anywhere in this milestone, so deleting a trip takes its
 * stages, every one of its days and every item on them with it. That is the
 * whole reason this exists — and why `message` names the trip rather than asking
 * "are you sure?", which tells the owner nothing about what is about to go.
 *
 * The same focus discipline as the item editor: focus moves in on open, is
 * trapped while open, and returns to the trigger on unmount. It opens focused on
 * the **cancel** button rather than the destructive one, so a stray Return on a
 * dialog that appeared unexpectedly does not delete a trip.
 *
 * **A failed confirmation is reported here, inside the dialog.** `onConfirm`
 * can reject — a `503`, a dropped connection, a `404` for a row a second tab
 * already deleted — and when it does, the dialog stays open with `busy`
 * cleared. That is the only place the owner is still looking, and it is where
 * the retry (the same confirm button) is, so the host passes the translated
 * message back down through `error` rather than putting it somewhere the
 * dialog is covering. The host owns the string: it is the one that caught the
 * failure and knows its `translationKey`.
 */

const FOCUSABLE = 'button:not([disabled])'

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  error = null,
  onConfirm,
  onCancel,
}: {
  title: string
  message: string
  confirmLabel: string
  /**
   * The translated message for a confirmation that failed — already through
   * `t(...)` by the host, never a code and never an English fallback. `null`
   * while nothing has failed, which is every render until one does.
   */
  error?: string | null
  onConfirm: () => Promise<void> | void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const headingId = useId()
  const panel = useRef<HTMLDivElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const trigger = useRef<Element | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    trigger.current = document.activeElement
    cancel.current?.focus()

    return () => {
      if (trigger.current instanceof HTMLElement && document.contains(trigger.current)) {
        trigger.current.focus()
      }
    }
  }, [])

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      // Escape cancels. On a destructive dialog the safe action is the one that
      // needs no deliberation.
      event.stopPropagation()
      onCancel()
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
        className="dialog dialog--confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        ref={panel}
      >
        <h2 id={headingId}>{title}</h2>
        <p>{message}</p>

        {/* `role="alert"`, so it is announced when it appears rather than
            waiting for the owner to go looking: the action they asked for did
            not happen, and the dialog is still standing. */}
        {error !== null && <p role="alert">{error}</p>}

        <div className="dialog__actions">
          <button type="button" className="button-quiet" ref={cancel} onClick={onCancel}>
            {t('item.cancel')}
          </button>
          <button
            type="button"
            className="button-danger button-danger--solid"
            disabled={busy}
            onClick={() => {
              setBusy(true)
              void Promise.resolve(onConfirm()).finally(() => setBusy(false))
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
