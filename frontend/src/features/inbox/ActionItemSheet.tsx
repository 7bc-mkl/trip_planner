import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../../api/client'
import type {
  ActionItem,
  ApprovableField,
  FieldValue,
  InboxMessageDetail,
  Target,
} from '../../api/inbox'
import {
  approveActionItem,
  getActionItem,
  getInboxMessage,
  rejectActionItem,
  retargetActionItem,
  undoActionItem,
} from '../../api/inbox'
import { formatCurrency, formatDate, formatTime, splitByteSize } from '../trips/format'
import { TargetPicker } from './TargetPicker'

/**
 * The review sheet — where D21 and A6 become visible.
 *
 * **One row per proposed field: what the item says now, what the message says,
 * and a checkbox.** The default ticks come from the server's pure diff and are
 * never second-guessed here: a field whose current value is empty is ticked
 * (there is nothing to lose), a non-empty one is not, and a status move is
 * ticked only when it goes forward. Nothing the owner typed is overwritten by a
 * default.
 *
 * **The source message sits beside the proposal, as plain text**, so a wrong
 * extraction is visible next to its evidence (the antidote to A08). Every value
 * is formatted through `Intl` or a translation key — never shown as a sentence a
 * model composed.
 *
 * **A conflict reloads rather than retries.** When the item changed after the
 * proposal was made, the server refuses with `action_item_conflict`, records
 * what is true now and bumps the revision; the sheet reloads, says why, and the
 * owner decides again against values he can actually see.
 *
 * Focus-trapped dialog, `Escape` closes, focus returns to the trigger — the same
 * discipline as every other dialog in the product.
 */

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href]'

export function ActionItemSheet({
  actionItemId,
  onClose,
}: {
  actionItemId: string
  /** `changed` is true when anything was decided, so the host reloads. */
  onClose: (changed: boolean) => void
}) {
  const { t, i18n } = useTranslation()
  const headingId = useId()
  const panel = useRef<HTMLDivElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const trigger = useRef<Element | null>(null)
  const [item, setItem] = useState<ActionItem | null>(null)
  const [message, setMessage] = useState<InboxMessageDetail | null>(null)
  const [ticked, setTicked] = useState<Set<ApprovableField>>(new Set())
  const [statusTicked, setStatusTicked] = useState(false)
  const [documents, setDocuments] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [changed, setChanged] = useState(false)
  const [retargetTrip, setRetargetTrip] = useState<string | null>(null)

  /** Adopt a freshly loaded proposal, and reset every tick to its default. */
  const adopt = useCallback((loaded: ActionItem) => {
    setItem(loaded)
    setTicked(new Set(loaded.fields.filter((row) => row.default_ticked).map((row) => row.name)))
    setStatusTicked(loaded.status?.default_ticked ?? false)
    // A document is ticked by default: it is the evidence, and putting it on
    // the item overwrites nothing.
    setDocuments(new Set(loaded.state === 'pending' ? loaded.attachments.map((one) => one.id) : []))
    setRetargetTrip(null)
  }, [])

  const report = useCallback(
    (caught: unknown) => {
      setError(caught instanceof ApiError ? t(caught.translationKey) : t('error.unknown'))
    },
    [t],
  )

  useEffect(() => {
    const controller = new AbortController()
    getActionItem(actionItemId, controller.signal)
      .then((loaded) => {
        adopt(loaded)
        return getInboxMessage(loaded.message_id, controller.signal).then(setMessage)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          report(caught)
        }
      })
    return () => controller.abort()
  }, [actionItemId, adopt, report])

  useEffect(() => {
    trigger.current = document.activeElement
    closeButton.current?.focus()
    return () => {
      if (trigger.current instanceof HTMLElement && document.contains(trigger.current)) {
        trigger.current.focus()
      }
    }
  }, [])

  const close = () => onClose(changed)

  // The latest `close`, for the document-level listener below, which is
  // registered once and would otherwise keep the first render's `changed`.
  const closeRef = useRef(close)
  closeRef.current = close

  // Escape is listened for on the document, not only on the overlay. A decision
  // replaces the button that had focus (Approve becomes Undo, Undo becomes
  // Approve), the browser drops focus to `<body>`, and an overlay-only handler
  // then never sees the key — the sheet stopped closing on Esc (QA, #22).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        closeRef.current()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // And focus is put back inside the sheet whenever its contents are replaced,
  // so a keyboard user is never left on `<body>` behind a modal.
  useEffect(() => {
    if (panel.current !== null && !panel.current.contains(document.activeElement)) {
      closeButton.current?.focus()
    }
  }, [item])

  function handleKeyDown(event: React.KeyboardEvent) {
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

  /** Run one decision; on a conflict, reload and explain rather than retry. */
  const decide = (action: () => Promise<ActionItem | void>) => {
    setBusy(true)
    setError(null)
    void action()
      .then((result) => {
        setChanged(true)
        if (result) {
          adopt(result)
        } else {
          onClose(true)
        }
      })
      .catch((caught: unknown) => {
        report(caught)
        if (caught instanceof ApiError && caught.code === 'action_item_conflict') {
          return getActionItem(actionItemId).then(adopt)
        }
        return undefined
      })
      .finally(() => setBusy(false))
  }

  const approve = () => {
    if (item === null) {
      return
    }
    decide(() =>
      approveActionItem(item.id, {
        target_item_id: item.target_item_id,
        target_trip_day_id: item.target_trip_day_id,
        fields: item.fields.filter((row) => ticked.has(row.name)).map((row) => row.name),
        attachment_ids: [...documents],
        set_status: statusTicked && item.status !== null ? item.status.proposed : null,
        expected_revision: item.revision,
      }),
    )
  }

  const retarget = (target: Target) => {
    if (item === null) {
      return Promise.resolve()
    }
    setError(null)
    return retargetActionItem(item.id, target, item.revision)
      .then((result) => {
        setChanged(true)
        adopt(result)
      })
      .catch((caught: unknown) => {
        report(caught)
        // A stale revision would refuse every later attempt too: reload, so the
        // next choice is made against the proposal as it now stands.
        if (caught instanceof ApiError && caught.code === 'action_item_conflict') {
          return getActionItem(actionItemId).then(adopt)
        }
        return undefined
      })
  }

  const toggle = <T,>(set: Set<T>, value: T, apply: (next: Set<T>) => void) => {
    const next = new Set(set)
    if (next.has(value)) {
      next.delete(value)
    } else {
      next.add(value)
    }
    apply(next)
  }

  const pending = item?.state === 'pending'
  const hasTarget = item !== null && (item.target_item_id ?? item.target_trip_day_id) !== null
  const anythingSelected = ticked.size > 0 || statusTicked || documents.size > 0

  return (
    <div className="dialog-overlay" onKeyDown={handleKeyDown}>
      <div
        className="dialog action-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        ref={panel}
      >
        <h2 id={headingId}>{t('inbox.sheet.title')}</h2>

        {error !== null && <p role="alert">{error}</p>}
        {item === null && error === null && <p role="status">{t('app.loading')}</p>}

        {item !== null && (
          <>
            <p className="action-sheet__subject">{item.subject}</p>
            <TargetLine item={item} />

            {item.fields.length > 0 || item.status !== null ? (
              <table className="action-sheet__table">
                <colgroup>
                  <col className="action-sheet__col-field" />
                  <col />
                  <col />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">{t('inbox.sheet.field')}</th>
                    <th scope="col">{t('inbox.sheet.now')}</th>
                    <th scope="col">{t('inbox.sheet.message')}</th>
                  </tr>
                </thead>
                <tbody>
                  {item.fields.map((row) => (
                    <tr key={row.name}>
                      <th scope="row">
                        <label className="action-sheet__choice">
                          <input
                            type="checkbox"
                            checked={ticked.has(row.name)}
                            disabled={!pending || !row.changed}
                            onChange={() => toggle(ticked, row.name, setTicked)}
                          />
                          <span className="action-sheet__label">{t(`inbox.field.${row.name}`)}</span>
                        </label>
                      </th>
                      <td>{formatValue(row.name, row.current, i18n.language, t)}</td>
                      <td>
                        {formatValue(row.name, row.proposed, i18n.language, t)}
                        <Difference
                          changed={row.changed}
                          hadValue={row.current !== null}
                          defaultTicked={row.default_ticked}
                        />
                      </td>
                    </tr>
                  ))}
                  {item.status !== null && (
                    <tr>
                      <th scope="row">
                        <label className="action-sheet__choice">
                          <input
                            type="checkbox"
                            checked={statusTicked}
                            disabled={!pending || !item.status.changed}
                            onChange={() => setStatusTicked(!statusTicked)}
                          />
                          <span className="action-sheet__label">{t('inbox.field.status')}</span>
                        </label>
                      </th>
                      <td>
                        {item.status.current === null
                          ? t('inbox.sheet.empty')
                          : t(`item.status.${item.status.current}`)}
                      </td>
                      <td>
                        {t(`item.status.${item.status.proposed}`)}
                        <Difference
                          changed={item.status.changed}
                          hadValue={item.status.current !== null}
                          defaultTicked={item.status.default_ticked}
                        />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            ) : (
              <p className="inbox-place__hint">{t('inbox.sheet.noFields')}</p>
            )}

            {item.attachments.length > 0 && (
              <fieldset className="action-sheet__documents">
                <legend>{t('inbox.sheet.documents')}</legend>
                {item.attachments.map((attachment) => {
                  const { value, unit } = splitByteSize(attachment.byte_size)
                  return (
                    <label key={attachment.id} className="action-sheet__choice">
                      <input
                        type="checkbox"
                        checked={documents.has(attachment.id)}
                        disabled={!pending}
                        onChange={() => toggle(documents, attachment.id, setDocuments)}
                      />
                      <span className="inbox-message__filename">{attachment.filename}</span>
                      <span className="inbox-message__size">
                        {t('attachment.size', { value, unit })}
                      </span>
                    </label>
                  )
                })}
              </fieldset>
            )}

            {pending && item.trip_id !== null && (
              <div className="action-sheet__retarget">
                {item.alternatives.length > 0 && (
                  <p className="inbox-place__hint">
                    {t('inbox.sheet.alternatives')}{' '}
                    {item.alternatives.map((one) => (
                      <button
                        key={one.trip_id}
                        type="button"
                        className="button-quiet"
                        onClick={() => setRetargetTrip(one.trip_id)}
                      >
                        {one.title}
                      </button>
                    ))}
                  </p>
                )}
                <TargetPicker
                  tripId={retargetTrip ?? item.trip_id}
                  label={t('inbox.sheet.retargetLabel')}
                  actionLabel={t('inbox.sheet.retarget')}
                  busyLabel={t('inbox.sheet.retargeting')}
                  onChoose={retarget}
                />
              </div>
            )}

            {item.state === 'approved' && item.applied !== null && (
              <p className="action-sheet__outcome" role="status">
                {t('inbox.sheet.approved')}{' '}
                {undoSentence(item.applied, t)}
              </p>
            )}
            {item.state === 'rejected' && (
              <p className="action-sheet__outcome" role="status">
                {t('inbox.sheet.rejected')}
              </p>
            )}

            <section className="action-sheet__source" aria-label={t('inbox.sheet.source')}>
              <h3>{t('inbox.sheet.source')}</h3>
              {message === null ? (
                <p role="status">{t('app.loading')}</p>
              ) : message.text_body === '' ? (
                <p className="inbox-message__empty">{t('inbox.noText')}</p>
              ) : (
                <p className="inbox-message__body">{message.text_body}</p>
              )}
            </section>
          </>
        )}

        <div className="dialog__actions">
          <button type="button" className="button-quiet" ref={closeButton} onClick={close}>
            {t('inbox.sheet.close')}
          </button>
          {pending && (
            <>
              <button
                type="button"
                className="button-quiet"
                disabled={busy}
                onClick={() => decide(() => rejectActionItem(item.id))}
              >
                {t('inbox.sheet.reject')}
              </button>
              <button
                type="button"
                className="button-primary"
                disabled={busy || !hasTarget || !anythingSelected}
                onClick={approve}
              >
                {t('inbox.sheet.approve')}
              </button>
            </>
          )}
          {item?.state === 'approved' && item.applied !== null && (
            <button
              type="button"
              className="button-quiet"
              disabled={busy}
              onClick={() => decide(() => undoActionItem(item.id))}
            >
              {t('inbox.sheet.undo')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * What Undo will do, naming only the halves that are not empty — "restores
 * 2 fields", "returns 1 document", or both — rather than "restores no fields".
 */
function undoSentence(applied: NonNullable<ActionItem['applied']>, t: TFunction): string {
  if (applied.created) {
    return t(applied.attachment_count > 0 ? 'inbox.sheet.undoCreated' : 'inbox.sheet.undoCreatedOnly')
  }
  const fields = applied.fields.length + (applied.status_changed ? 1 : 0)
  const documents = applied.attachment_count
  if (fields > 0 && documents > 0) {
    return t('inbox.sheet.undoBoth', { fields, documents })
  }
  if (documents > 0) {
    return t('inbox.sheet.undoDocuments', { documents })
  }
  return t('inbox.sheet.undoFields', { fields })
}

/** Where the proposal points, and why — a translated key, never prose. */
function TargetLine({ item }: { item: ActionItem }) {
  const { t, i18n } = useTranslation()
  const date = item.target_date === null ? '' : formatDate(item.target_date, i18n.language)

  let where: string
  if (item.target_item_id !== null) {
    where = t('inbox.sheet.updates', { title: item.target_item_title ?? '', date })
  } else if (item.target_trip_day_id !== null) {
    where = t('inbox.sheet.creates', { date })
  } else {
    where = t('inbox.sheet.needsTarget')
  }

  return (
    <p className="inbox-row__trip">
      {item.trip_title !== null && <>{item.trip_title} · </>}
      {where}
      <br />
      <span className="inbox-row__reason">{t(`inbox.target.${item.target_reason}`)}</span>
    </p>
  )
}

/**
 * The difference, said in words. Never colour alone: a person who cannot see
 * the difference between two greys must still be told the values differ.
 */
function Difference({
  changed,
  hadValue,
  defaultTicked,
}: {
  changed: boolean
  hadValue: boolean
  defaultTicked: boolean
}) {
  const { t } = useTranslation()
  if (!changed) {
    return <span className="action-sheet__note"> {t('inbox.sheet.same')}</span>
  }
  if (hadValue && !defaultTicked) {
    return (
      <span className="action-sheet__note action-sheet__note--differs">
        {' '}
        {t('inbox.sheet.differs')}
      </span>
    )
  }
  return null
}

function formatValue(
  name: ApprovableField,
  value: FieldValue,
  locale: string,
  t: TFunction,
): string {
  if (value === null) {
    return t('inbox.sheet.empty')
  }
  if (typeof value === 'object') {
    return formatCurrency(value.amount, value.currency, locale)
  }
  switch (name) {
    case 'end_date':
      return formatDate(value, locale)
    case 'start_time':
    case 'end_time':
      return formatTime(value, locale)
    case 'kind':
      return t(`item.kind.${value}`)
    default:
      return value
  }
}
