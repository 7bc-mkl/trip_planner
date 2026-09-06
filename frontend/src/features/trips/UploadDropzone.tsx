import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, CSSProperties, DragEvent } from 'react'
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
 * exists; drag-and-drop is an enhancement layered on this same input, and
 * nothing here depends on it — a drop calls exactly the same `addFiles` the
 * picker's `onChange` calls, so the two paths cannot drift apart. Dragging over
 * the zone fills it to `--surface-sunken` (declared for exactly this before the
 * feature had code) and swaps the hint line to a "drop it" sentence, because a
 * background tint is not read by everyone and the state is meaningful enough
 * that colour alone must not be the only way to notice it. The dashed
 * `--hairline-strong` outline never changes; only the fill and the hint do.
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
 *
 * **The queue is about work in flight, never about files that exist.** The
 * attachment row in the host panel is a file's one representation; a queue row
 * that outlives the upload is a second one. A successful row therefore
 * *retires* the moment the host's list is observed to contain the attachment
 * the server created — `listedAttachmentIds` is that observation, and it is the
 * host's already-existing refresh, not a second notification path.
 *
 * The retirement is timed so that neither bad window exists:
 *
 * - **Never twice.** The hiding happens during *render*, from
 *   `listedAttachmentIds` as it is on that render. The commit that first paints
 *   the attachment row is the same commit that stops painting the queue row —
 *   there is no in-between frame showing both, not even one.
 * - **Never invisible.** Nothing retires on completion alone. A row that has
 *   finished but is not in the host's list yet — a day panel refetching, a host
 *   that keeps no list at all — keeps showing its "done" row, so the file is on
 *   screen continuously.
 *
 * Retirement is also *permanent*: the effect below prunes retired rows out of
 * state, so deleting the attachment afterwards (its id leaves the list) cannot
 * resurrect a queue row asserting a file that no longer exists.
 *
 * **Nothing survives the panel.** Every in-flight upload is aborted when this
 * component unmounts — closing the item dialog mid-upload cancels the request
 * rather than leaving it to finish into a tree that is gone — and the two
 * per-row maps below are pruned wherever a row leaves state, by cancellation,
 * dismissal or retirement alike, so neither grows for the panel's lifetime.
 *
 * **Only successful rows retire.** A failed or cancelled row is the only record
 * of what went wrong and it carries the retry action, so it stays until the
 * owner dismisses it.
 *
 * **The duplicate hint (A14) is informational, never a gate.** When a
 * successful upload's `sha256` matches one already in `listedAttachmentHashes`
 * — the host's own list, scoped to this same parent — the done row grows one
 * extra line saying so. Nothing is deduplicated and nothing is refused: both
 * copies are stored, the attachment row still appears, and the hint requires
 * no dismissal and offers no undo. It is decided entirely client-side from
 * data the `201` response and the host's existing list already carry, so it
 * costs no new request. Two identical files on two different parents are two
 * legitimate attachments, not a duplicate — each host only ever lists its own
 * parent's hashes, so the scoping falls out of that rather than needing its
 * own check here.
 *
 * **The hint lives wherever the file's one representation currently is.** In a
 * composed host the queue row retires on the very commit that paints the
 * attachment row, so the hint below is not the surface the owner normally
 * reads — `AttachmentRow` carries it there, derived from the host's list (see
 * `duplicatedSha256s`). This one stays for the window where the queue row *is*
 * the file's only representation: a host that lists nothing, or one whose
 * refetch has not caught up yet. The two are mutually exclusive by exactly the
 * retirement rule above, which is why the hint can be in both places without
 * ever being in both at once, and why both read the same key.
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
  /** The attachment the server created. Non-null only once `state` is `done`,
      and the handle the row retires by once the host's list carries it. */
  attachmentId: string | null
  /**
   * True when this upload's `sha256`, at the moment it succeeded, matched a
   * hash already in `listedAttachmentHashes` — i.e. the same bytes are
   * already attached to this same parent. Decided once, at success, from the
   * hashes the host was listing *before* this attachment joined them: reading
   * it reactively off the current list later would have the file match
   * itself the instant the host's own refresh caught up. Never blocks, never
   * offers undo, never affects storage (A14) — it is a hint, not a gate.
   */
  duplicate: boolean
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
  listedAttachmentIds = [],
  listedAttachmentHashes = [],
  disabled = false,
}: {
  target: UploadTarget
  /** Called once per successful upload, with the attachment the server created. */
  onUploaded?: (attachment: Attachment) => void
  /**
   * The ids the host panel is listing right now — its own refreshed list, not a
   * second notification channel. A successful row whose attachment appears here
   * retires, because the attachment row above is already showing that file. A
   * host that lists nothing (the drop zone rendered on its own) passes nothing
   * and no row ever retires, which is right: there is nowhere else the file
   * would be shown.
   */
  listedAttachmentIds?: readonly string[]
  /**
   * The `sha256` of every attachment `listedAttachmentIds` names — the same
   * host list, one column over. Scoped to this same parent by construction:
   * each host (`DayAttachments`, `ItemAttachments`) only ever passes its own
   * parent's attachments, so a match here means "already attached here", never
   * "attached somewhere in the trip". Used only for the non-blocking duplicate
   * hint (A14); a host that passes nothing simply never shows the hint.
   */
  listedAttachmentHashes?: readonly string[]
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const inputId = useId()
  const [rows, setRows] = useState<Row[]>([])
  const [announcement, setAnnouncement] = useState<Announcement | null>(null)
  /** Purely presentational — which files are selected never depends on this. */
  const [isDragOver, setIsDragOver] = useState(false)

  // Keyed by content, not by array identity: hosts build this list inline, so a
  // fresh array arrives on every render and only a *changed* one should re-run
  // the prune below. Attachment ids are UUIDs, so the separator is unambiguous.
  const listedKey = listedAttachmentIds.join(',')
  const listed = useMemo(
    () => new Set(listedKey === '' ? [] : listedKey.split(',')),
    [listedKey],
  )

  // The latest hashes the host is listing, read at the moment an upload
  // succeeds rather than through the closure `start` was created with — a
  // ref kept current every render, exactly like `listed` above but read
  // imperatively instead of during render. Assigning during render (rather
  // than in an effect) is deliberate: the value must reflect the render that
  // is committing *now*, before this success's own `patch` and `onUploaded`
  // run, or a host that appends synchronously could make the file match
  // itself.
  const hashesRef = useRef<readonly string[]>(listedAttachmentHashes)
  hashesRef.current = listedAttachmentHashes

  /** One controller per in-flight row, so cancelling one cannot abort another. */
  const controllers = useRef(new Map<string, AbortController>())
  /** Monotonic, so five files picked in the same millisecond still get distinct keys. */
  const nextKey = useRef(0)
  /** The last announced quarter per row — progress is announced in steps, not per packet. */
  const announcedStep = useRef(new Map<string, number>())
  /** Enters minus leaves for the drag-over highlight — see `handleDragLeave`. */
  const dragDepth = useRef(0)

  const patch = useCallback((key: string, change: Partial<Row>) => {
    setRows((previous) => previous.map((row) => (row.key === key ? { ...row, ...change } : row)))
  }, [])

  const drop = useCallback((key: string) => {
    controllers.current.delete(key)
    announcedStep.current.delete(key)
    setRows((previous) => previous.filter((row) => row.key !== key))
  }, [])

  /**
   * A row whose attachment the host is now listing is *hidden* by this, during
   * the very render that first shows the attachment row — so the file is never
   * on screen twice.
   */
  const retired = useCallback(
    (row: Row) => row.attachmentId !== null && listed.has(row.attachmentId),
    [listed],
  )

  // …and dropped from state right after, so it stays retired. Without this, the
  // id leaving the list on a delete would bring the queue row back, asserting a
  // file that no longer exists.
  //
  // The two per-row maps are pruned *with* the row, the same pair `drop` above
  // deletes. A row can leave state by either route, and only one of them used
  // to clean up after itself: every successful upload left its `announcedStep`
  // entry — and, on any path that does not settle through `start`, its
  // controller — behind for the panel's whole lifetime.
  //
  // `rows` is a dependency rather than something read inside an updater, so the
  // deletes happen here, when the effect runs, instead of whenever React next
  // gets round to invoking a lazy updater. Re-running on every `rows` change
  // cannot loop: the early return covers the render this effect's own
  // `setRows` causes.
  useEffect(() => {
    const retiredRows = rows.filter((row) => retired(row))
    if (retiredRows.length === 0) {
      return
    }
    for (const row of retiredRows) {
      controllers.current.delete(row.key)
      announcedStep.current.delete(row.key)
    }
    setRows((previous) => previous.filter((row) => !retired(row)))
  }, [rows, retired])

  // Nothing outlives the panel. Closing the item dialog mid-upload used to
  // leave the request running: its `.then` then called `patch` and
  // `setAnnouncement` into a tree that no longer exists and `onUploaded` on a
  // host that had gone, and the bytes kept flowing for a file nobody could see
  // the outcome of. Aborting rejects each upload with an `AbortError`, which
  // the handler in `start` already returns early on, so the unmount is silent.
  useEffect(() => {
    const inFlight = controllers.current
    const steps = announcedStep.current
    return () => {
      for (const controller of inFlight.values()) {
        controller.abort()
      }
      inFlight.clear()
      steps.clear()
    }
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
          // Decided now, from the hashes the host was listing the instant
          // before this attachment joined them (see `hashesRef` above) — the
          // upload still succeeds and the row still reaches `done` either way;
          // this only adds a line, never a gate (A14).
          const duplicate = hashesRef.current.includes(attachment.sha256)
          patch(key, {
            state: 'done',
            loaded: attachment.byte_size,
            total: attachment.byte_size,
            attachmentId: attachment.id,
            duplicate,
          })
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

  /**
   * The one funnel both entry points call. `handleChange` (the picker) and
   * `handleDrop` (the drag-and-drop enhancement) differ only in how they get a
   * `File[]` out of the browser event — everything after that, both share:
   * the same per-file pre-check, the same row shape, the same `start` call.
   * There is no second upload path to drift out of sync with this one.
   */
  const addFiles = useCallback(
    (files: readonly File[]) => {
      const added: Row[] = files.map((file) => {
        const refusal = precheck(file)
        return {
          key: `upload-${nextKey.current++}`,
          file,
          state: refusal === null ? 'selected' : 'failed',
          loaded: 0,
          total: file.size,
          errorKey: refusal === null ? null : `error.${refusal}`,
          refusedLocally: refusal !== null,
          attachmentId: null,
          duplicate: false,
        }
      })

      setRows((previous) => [...previous, ...added])

      for (const row of added) {
        if (!row.refusedLocally) {
          start(row.key, row.file)
        }
      }
    },
    [start],
  )

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const picked = [...(event.target.files ?? [])]

    // Reset the control, or picking the same file twice in a row fires no
    // `change` event the second time and the drop zone looks broken.
    event.target.value = ''

    addFiles(picked)
  }

  // `dragover` must be prevented on every event for the browser to treat the
  // zone as a valid drop target at all — without it, `drop` never fires and
  // the browser navigates to the file instead.
  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
  }

  // Children of the label (its title, its hint, the clipped input) fire their
  // own `dragenter`/`dragleave` as the pointer crosses them, and those bubble
  // here too — so the pointer moving from the label's own padding onto the
  // title text is a `dragleave` immediately followed by a `dragenter`, not a
  // single clean exit. A plain "leave clears it" would flicker the fill off
  // and back on for every such crossing. `dragDepth` counts enters minus
  // leaves instead: it only reaches zero, clearing the highlight, once every
  // nested enter has been matched by a leave — i.e. the pointer has actually
  // left the zone, whether onto a sibling of the page or out of the window
  // altogether (the classic "stuck highlight" bug this guards against).
  function handleDragEnter(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    if (disabled) return
    dragDepth.current += 1
    setIsDragOver(true)
  }

  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    if (disabled) return
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) {
      setIsDragOver(false)
    }
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    dragDepth.current = 0
    setIsDragOver(false)
    if (disabled) return
    addFiles([...(event.dataTransfer?.files ?? [])])
  }

  function retry(row: Row) {
    patch(row.key, {
      state: 'selected',
      loaded: 0,
      errorKey: null,
      attachmentId: null,
      duplicate: false,
    })
    start(row.key, row.file)
  }

  function cancel(row: Row) {
    controllers.current.get(row.key)?.abort()
    drop(row.key)
    setAnnouncement({ kind: 'cancelled', filename: row.file.name })
  }

  // The rows still worth showing: everything except the successes the host list
  // has taken over. Computed here rather than in the effect above so that the
  // takeover is seamless — see the note on the component.
  const visibleRows = rows.filter((row) => !retired(row))

  return (
    <div className="upload-dropzone">
      <label
        className="upload-dropzone__label"
        htmlFor={inputId}
        data-drag-over={isDragOver ? 'true' : undefined}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <span className="upload-dropzone__title">{t('upload.add')}</span>
        {/* The fill is the primary cue, but colour is never the only one: the
            hint's own words change too, so the state does not depend on being
            able to see the tint. */}
        <span className="upload-dropzone__hint">
          {isDragOver ? t('upload.dropHint') : t('upload.hint')}
        </span>
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

      {visibleRows.length > 0 && (
        <ul className="upload-dropzone__list" aria-label={t('upload.list')}>
          {visibleRows.map((row) => (
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

              {/* Non-blocking (A14): no `role="alert"`, no dismiss action of its
                  own, and no bearing on the row above it — the upload already
                  succeeded and the attachment already exists either way. */}
              {row.state === 'done' && row.duplicate && (
                <p className="upload-row__duplicate-hint">{t('upload.duplicateHint')}</p>
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
