import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import { ITEM_KINDS, ITEM_STATUSES, fromTimeInput } from '../../api/items'
import type { Item, ItemInput } from '../../api/items'
import { clearDraft, readDraft, saveDraft } from '../auth/draftStore'
import { draftKey, draftOf } from './itemDraft'
import type { ItemDraft } from './itemDraft'

/**
 * The item editor.
 *
 * A modal dialog, opened from an item or from "Add item". Three things about it
 * are requirements rather than polish:
 *
 * - **Focus returns to the trigger when it closes.** Otherwise focus falls back
 *   to `<body>` and a keyboard user is dropped at the top of the page every time
 *   they save an item.
 * - **Focus is trapped while it is open**, so Tab cannot walk into the page
 *   behind the overlay — content a sighted user cannot even see.
 * - **The draft survives a session expiry.** When a 401 arrives while this is
 *   open the router navigates to /login and React unmounts the dialog; the draft
 *   goes to the module-scoped store on the way out and is restored on return.
 *   Component state does not survive an unmount, so this needs a real mechanism
 *   or the promise should not be made.
 *
 * `<dialog>` is deliberately not used: its `showModal()` focus behaviour is not
 * implemented consistently enough in jsdom to test, and the trap below is the
 * part that actually has to be verified.
 */

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function ItemDialog({
  item,
  onSave,
  onDelete,
  onClose,
}: {
  /** The item being edited, or `null` when adding a new one. */
  item: Item | null
  onSave: (input: ItemInput) => Promise<void>
  onDelete?: () => Promise<void>
  onClose: () => void
}) {
  const { t } = useTranslation()
  const headingId = useId()
  const panel = useRef<HTMLDivElement>(null)
  /** The element that had focus when the dialog opened — where focus goes back to. */
  const trigger = useRef<Element | null>(null)

  const key = draftKey(item?.id ?? null)
  const [draft, setDraft] = useState<ItemDraft>(() => readDraft<ItemDraft>(key) ?? draftOf(item))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Keep the store in step with what is typed, so an unmount at any moment — a
  // 401 mid-keystroke — loses nothing.
  useEffect(() => {
    saveDraft(key, draft)
  }, [key, draft])

  useEffect(() => {
    trigger.current = document.activeElement
    panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus()

    return () => {
      // Restoring on unmount rather than in the close handler covers *every* way
      // the dialog can go away, including the route change a 401 causes.
      if (trigger.current instanceof HTMLElement && document.contains(trigger.current)) {
        trigger.current.focus()
      }
    }
  }, [])

  /**
   * Close the dialog, discarding what was typed.
   *
   * Cancel and Escape are the owner explicitly throwing the edit away, so the
   * draft goes with it — otherwise reopening the item shows the discarded text
   * as if it had been saved. The session-expiry path deliberately does *not*
   * come through here: it returns early without closing, so its draft survives,
   * which is the whole point of the store.
   */
  function dismiss() {
    clearDraft(key)
    onClose()
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      dismiss()
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

    // Wrap at both ends: without this, Tab from the last control lands on
    // browser chrome and then on the page behind the overlay.
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (draft.title.trim() === '' || saving) {
      return
    }

    setSaving(true)
    setError(null)

    try {
      await onSave({
        kind: draft.kind,
        status: draft.status,
        start_time: fromTimeInput(draft.startTime),
        end_time: fromTimeInput(draft.endTime),
        end_date: draft.endDate === '' ? null : draft.endDate,
        title: draft.title.trim(),
        notes: draft.notes.trim() === '' ? null : draft.notes.trim(),
      })
      // Cleared only on success: a failed save must leave the draft to retry.
      clearDraft(key)
      onClose()
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.isUnauthenticated) {
        return // The draft stays; the global handler is routing to /login.
      }
      setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
      setSaving(false)
    }
  }

  return (
    <div className="dialog-overlay" onKeyDown={handleKeyDown}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        ref={panel}
      >
        <h2 id={headingId}>{item === null ? t('item.addTitle') : t('item.editTitle')}</h2>

        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor="item-title">{t('item.titleLabel')}</label>
          <input
            id="item-title"
            value={draft.title}
            onChange={(event) => setDraft({ ...draft, title: event.target.value })}
          />

          <label htmlFor="item-kind">{t('item.kindLabel')}</label>
          <select
            id="item-kind"
            value={draft.kind}
            onChange={(event) =>
              setDraft({ ...draft, kind: event.target.value as ItemDraft['kind'] })
            }
          >
            {ITEM_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {t(`item.kind.${kind}`)}
              </option>
            ))}
          </select>

          <div className="field-row">
            <div>
              <label htmlFor="item-start-time">{t('item.startTime')}</label>
              <input
                id="item-start-time"
                type="time"
                value={draft.startTime}
                onChange={(event) => setDraft({ ...draft, startTime: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="item-end-time">{t('item.endTime')}</label>
              <input
                id="item-end-time"
                type="time"
                value={draft.endTime}
                onChange={(event) => setDraft({ ...draft, endTime: event.target.value })}
              />
            </div>
          </div>

          <label htmlFor="item-end-date">{t('item.endDate')}</label>
          <input
            id="item-end-date"
            type="date"
            value={draft.endDate}
            onChange={(event) => setDraft({ ...draft, endDate: event.target.value })}
          />
          <p className="hint">{t('item.endDateHint')}</p>

          {/* The control this screen exists for: moving an item to `done` is what
              the timeline's counter reacts to. */}
          <label htmlFor="item-status">{t('item.statusLabel')}</label>
          <select
            id="item-status"
            value={draft.status}
            onChange={(event) =>
              setDraft({ ...draft, status: event.target.value as ItemDraft['status'] })
            }
          >
            {ITEM_STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(`item.status.${status}`)}
              </option>
            ))}
          </select>

          <label htmlFor="item-notes">{t('item.notesLabel')}</label>
          <textarea
            id="item-notes"
            rows={3}
            value={draft.notes}
            onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
          />

          {error !== null && <p role="alert">{error}</p>}

          <div className="dialog__actions">
            {onDelete !== undefined && (
              <button
                type="button"
                className="button-danger"
                onClick={() => {
                  clearDraft(key)
                  void onDelete()
                }}
              >
                {t('item.delete')}
              </button>
            )}
            <button type="button" className="button-quiet" onClick={dismiss}>
              {t('item.cancel')}
            </button>
            <button
              type="submit"
              className="button-primary"
              disabled={draft.title.trim() === '' || saving}
            >
              {saving ? t('item.saving') : t('item.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
