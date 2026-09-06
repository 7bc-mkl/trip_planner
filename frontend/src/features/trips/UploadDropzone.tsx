import { useCallback, useId, useRef, useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { uploadDayAttachment, uploadItemAttachment } from '../../api/attachments'
import type { Attachment, UploadOptions } from '../../api/attachments'
import { ApiError } from '../../api/client'

/**
 * The upload drop zone.
 *
 * A real `<label>` over a real `<input type="file">` — not a `<div>` with a
 * click handler. The keyboard and file-picker path is the one that always
 * exists; drag-and-drop is an enhancement layered on this same input later, and
 * nothing here depends on it.
 *
 * Three things are contracts rather than polish:
 *
 * - **`accept` is a convenience for the picker dialog and nothing else**, and so
 *   is the client-side pre-check below it. The pre-check exists so a 60 MB video
 *   is refused instantly instead of after a wasted upload; it is never the reason
 *   a file is refused, because the server repeats every check and its answer is
 *   the only one that counts. A file the pre-check refuses issues **no request at
 *   all** — that is the point of it, and the suite asserts it.
 * - **Every file is its own row.** One file per request (see `api/attachments.ts`),
 *   so selecting five files produces five rows, five progress bars and five
 *   independent outcomes. One failure never touches the other four.
 * - **A failure shows the translated message for the server's error code**,
 *   `t(err.translationKey)` — never a hardcoded English string and never a raw
 *   code. The pre-check's own refusals reuse the *same* codes the server would
 *   have answered with, so the sentence the owner reads is identical whether the
 *   refusal cost a request or not.
 *
 * The state machine is idle (no rows) → selected → uploading → done / failed.
 * `selected` is not a decorative in-between: the request is already in flight
 * there, but no `lengthComputable` progress event has arrived yet, so there is
 * nothing honest to put in a determinate bar. The bar appears with the first
 * real byte count, which is exactly when `uploading` begins.
 *
 * Colour never carries state on its own: every pill renders a translated word
 * and a glyph beside it, the same contract `StatusChip` keeps.
 *
 * The `aria-live` region holds **facts, not a sentence**: which file, which
 * phase, how far, and — on a failure — which error code. The sentence is
 * formatted at *render* time from the current `t`, so switching the locale
 * re-renders the announcement like every other string in the app instead of
 * leaving one Polish line on an English page. Storing the formatted string was a
 * real defect (a browser walk found it; `check_locales.py` cannot, because both
 * keys exist and are in sync — what was wrong was *when* the string was made).
 * The same shape is what lets a terminal failure replace a progress claim the
 * row has moved past, rather than announcing "100 %" for an upload the server
 * refused.
 */

/** The server's per-attachment ceiling, mirrored for the pre-check only. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

/** Mirrored for the pre-check and for the picker's `accept`, in that order of importance. */
export const ACCEPTED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png'] as const

export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(',')

export type UploadTarget =
  | { kind: 'day'; tripId: string; date: string }
  | { kind: 'item'; tripId: string; itemId: string }

type RowState = 'selected' | 'uploading' | 'done' | 'failed'

type Row = {
  /** Stable across a retry — the row is the same row, not a new one. */
  key: string
  file: File
  state: RowState
  loaded: number
  total: number
  /** The i18n key of the refusal message. Non-null only while `state` is `failed`. */
  errorKey: string | null
  /** True when the pre-check refused it: no request was issued, and retrying it
      would refuse identically, so the row offers no retry. */
  refusedLocally: boolean
}

/**
 * What the live region currently has to say, as facts. Never a formatted string:
 * see the note above the component.
 */
type Announcement =
  | { kind: 'uploading'; filename: string; ratio: number }
  | { kind: 'done'; filename: string }
  | { kind: 'failed'; filename: string; errorKey: string }
  | { kind: 'cancelled'; filename: string }

const GLYPH: Record<RowState, string> = {
  selected: '•',
  uploading: '↑',
  done: '✓',
  failed: '!',
}

/**
 * The pre-check. Returns the error code the server would answer with, or `null`
 * when nothing local objects — which is not the same thing as "accepted".
 */
export function precheck(
  file: File,
): 'unsupported_file_type' | 'attachment_too_large' | 'malformed_upload' | null {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return 'unsupported_file_type'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return 'attachment_too_large'
  }
  if (file.size === 0) {
    return 'malformed_upload'
  }
  return null
}

function percentOf(row: Row): number {
  if (row.total <= 0) {
    return 0
  }
  return Math.min(100, Math.round((row.loaded / row.total) * 100))
}

/**
 * The announcement's sentence, formatted from the facts with the `t` of the
 * render that is happening now. A locale change re-renders this like any other
 * string.
 */
function announcementText(t: TFunction, announcement: Announcement | null): string {
  if (announcement === null) {
    return ''
  }
  switch (announcement.kind) {
    case 'uploading':
      return t('upload.announceUploading', {
        filename: announcement.filename,
        ratio: announcement.ratio,
      })
    case 'done':
      return t('upload.announceDone', { filename: announcement.filename })
    case 'failed':
      return t('upload.announceFailed', {
        filename: announcement.filename,
        reason: t(announcement.errorKey),
      })
    case 'cancelled':
      return t('upload.announceCancelled', { filename: announcement.filename })
  }
}

export function UploadDropzone({
  target,
  onUploaded,
  disabled = false,
}: {
  target: UploadTarget
  /** Called once per successful upload, with the attachment the server created. */
  onUploaded?: (attachment: Attachment) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const inputId = useId()
  const [rows, setRows] = useState<Row[]>([])
  const [announcement, setAnnouncement] = useState<Announcement | null>(null)

  /** One controller per in-flight row, so cancelling one cannot abort another. */
  const controllers = useRef(new Map<string, AbortController>())
  /** Monotonic, so five files picked in the same millisecond still get distinct keys. */
  const nextKey = useRef(0)
  /** The last announced quarter per row — progress is announced in steps, not per packet. */
  const announcedStep = useRef(new Map<string, number>())

  const patch = useCallback((key: string, change: Partial<Row>) => {
    setRows((previous) => previous.map((row) => (row.key === key ? { ...row, ...change } : row)))
  }, [])

  const drop = useCallback((key: string) => {
    controllers.current.delete(key)
    announcedStep.current.delete(key)
    setRows((previous) => previous.filter((row) => row.key !== key))
  }, [])

  const start = useCallback(
    (key: string, file: File) => {
      const controller = new AbortController()
      controllers.current.set(key, controller)
      announcedStep.current.set(key, -1)

      const options: UploadOptions = {
        signal: controller.signal,
        onProgress: ({ loaded, total }) => {
          patch(key, { state: 'uploading', loaded, total })

          // Four announcements over a whole upload, not one per packet: a polite
          // region read aloud on every progress event is unusable.
          const step = total > 0 ? Math.floor((loaded / total) * 4) : 0
          if (step !== announcedStep.current.get(key)) {
            announcedStep.current.set(key, step)
            setAnnouncement({
              kind: 'uploading',
              filename: file.name,
              ratio: total > 0 ? loaded / total : 0,
            })
          }
        },
      }

      const upload =
        target.kind === 'day'
          ? uploadDayAttachment(target.tripId, target.date, file, options)
          : uploadItemAttachment(target.tripId, target.itemId, file, options)

      upload.then(
        (attachment) => {
          controllers.current.delete(key)
          patch(key, { state: 'done', loaded: attachment.byte_size, total: attachment.byte_size })
          setAnnouncement({ kind: 'done', filename: file.name })
          onUploaded?.(attachment)
        },
        (caught: unknown) => {
          controllers.current.delete(key)
          if (caught instanceof DOMException && caught.name === 'AbortError') {
            return // Cancelling already removed the row and announced it.
          }
          const errorKey = caught instanceof ApiError ? caught.translationKey : 'error.unknown'
          patch(key, { state: 'failed', errorKey, refusedLocally: false })
          // The region has been claiming progress for this file — often "100 %",
          // because the bytes did arrive and the server refused them afterwards.
          // Leaving that claim standing tells a screen-reader user the upload
          // succeeded, so the terminal state replaces it.
          setAnnouncement({ kind: 'failed', filename: file.name, errorKey })
        },
      )
    },
    // `t` is deliberately absent: nothing in here formats a string any more.
    [onUploaded, patch, target],
  )

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const picked = [...(event.target.files ?? [])]

    // Reset the control, or picking the same file twice in a row fires no
    // `change` event the second time and the drop zone looks broken.
    event.target.value = ''

    const added: Row[] = picked.map((file) => {
      const refusal = precheck(file)
      return {
        key: `upload-${nextKey.current++}`,
        file,
        state: refusal === null ? 'selected' : 'failed',
        loaded: 0,
        total: file.size,
        errorKey: refusal === null ? null : `error.${refusal}`,
        refusedLocally: refusal !== null,
      }
    })

    setRows((previous) => [...previous, ...added])

    for (const row of added) {
      if (!row.refusedLocally) {
        start(row.key, row.file)
      }
    }
  }

  function retry(row: Row) {
    patch(row.key, { state: 'selected', loaded: 0, errorKey: null })
    start(row.key, row.file)
  }

  function cancel(row: Row) {
    controllers.current.get(row.key)?.abort()
    drop(row.key)
    setAnnouncement({ kind: 'cancelled', filename: row.file.name })
  }

  return (
    <div className="upload-dropzone">
      <label className="upload-dropzone__label" htmlFor={inputId}>
        <span className="upload-dropzone__title">{t('upload.add')}</span>
        <span className="upload-dropzone__hint">{t('upload.hint')}</span>
        <input
          id={inputId}
          className="upload-dropzone__input"
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          onChange={handleChange}
        />
      </label>

      {/* Always rendered, empty or not: a live region inserted at the same
          moment as its text is not announced by every screen reader. Formatted
          here, from facts, so a locale change re-renders it. */}
      <p aria-live="polite" className="upload-dropzone__announcement">
        {announcementText(t, announcement)}
      </p>

      {rows.length > 0 && (
        <ul className="upload-dropzone__list" aria-label={t('upload.list')}>
          {rows.map((row) => (
            <li className="upload-row" data-state={row.state} key={row.key}>
              <span className="upload-row__name">{row.file.name}</span>

              <span className="upload-row__pill" data-state={row.state}>
                <span aria-hidden="true" className="upload-row__glyph">
                  {GLYPH[row.state]}
                </span>
                {t(`upload.state.${row.state}`)}
              </span>

              {row.state === 'uploading' && (
                <span className="upload-row__track">
                  <span
                    className="upload-row__bar"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percentOf(row)}
                    aria-label={t('upload.progressLabel', { filename: row.file.name })}
                    style={{ '--upload-progress': `${percentOf(row)}%` } as CSSProperties}
                  />
                </span>
              )}

              {row.state === 'failed' && row.errorKey !== null && (
                <p className="upload-row__error" role="alert">
                  {t(row.errorKey)}
                </p>
              )}

              <span className="upload-row__actions">
                {(row.state === 'uploading' || row.state === 'selected') && (
                  <button className="button-quiet" onClick={() => cancel(row)} type="button">
                    {t('upload.cancel')}
                  </button>
                )}

                {row.state === 'failed' && !row.refusedLocally && (
                  <button className="button-quiet" onClick={() => retry(row)} type="button">
                    {t('upload.retry')}
                  </button>
                )}

                {(row.state === 'failed' || row.state === 'done') && (
                  <button className="button-quiet" onClick={() => drop(row.key)} type="button">
                    {t('upload.dismiss')}
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
