# Checkpoint 4 — Steps 2.2-review-fix-1 .. 2.3-review-fix-1 (Phase 2 closes)

- Fired: 2026-09-06T21:10Z, on both triggers — 5 Steps since checkpoint 3, and Phase 2 closed.
- Commit range: `bdcfa5b..02339d2`.
- Steps covered: `2.2-review-fix-1`, `2.2-review-fix-2`, `2.6`, `2.7`, `2.8`, plus the
  `2.3-review-fix-1` this checkpoint itself produced.
- Touched areas: `UploadDropzone.tsx`, `DayAttachments.tsx`, `ItemAttachments.tsx`,
  `DayDetailPage.tsx`, `TimelinePage.tsx`, both locale files, `src/test/fakeXhr.ts` (new).

## Checks run

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ PASS | |
| `python3 scripts/check_css_tokens.py` | ✅ PASS | |
| `python3 scripts/check_contrast.py` | ✅ PASS | Still 16 declared pairs; no new pair introduced. |
| `(cd backend && uv run ruff check .)` | ✅ PASS | |
| `(cd backend && uv run pytest)` | ✅ PASS | 600 passed, 0 skipped — backend untouched this window. |
| `(cd frontend && npm run typecheck)` | ✅ PASS | |
| `(cd frontend && npm run test -- --run)` | ✅ PASS | **232 tests** (213 → 216 → 226 → 229 → 232 across the window). |
| `(cd frontend && npm run build)` | ✅ PASS | |

## UI re-verification — the four checkpoint-3 defects

The QA environment was rebuilt from the fixed branch (`--force-rebuild`) and walked again in both
locales. **All four are fixed, confirmed in the running application rather than inferred from the
suite:**

1. **Polish no longer leaks into the English UI.** Uploading `alpha.png` in Polish announces
   "Dodano alpha.png"; switching to English re-renders it as "alpha.png was added". Verified in both
   directions, and the refusal message follows the locale too.
2. **A rejected upload no longer announces completion.** HTML bytes named `bad.jpg` announce "Nie
   dodano bad.jpg. Można załączać tylko pliki PDF, JPEG i PNG." with no "100%" anywhere. A
   structurally broken PDF got a *distinct* message, which is incidental evidence that the checks
   are genuinely content-based rather than extension-based.
3. **A successful upload appears exactly once.** Two uploads produced two list rows and no queue
   element at all.
4. **No stale queue entry after a delete.**

## The new major bug this checkpoint found, and fixed

The same walk turned up a defect the previous one had not reached: **a large upload succeeded but
never appeared in the day documents panel.** Announced "Dodano big3.png"; the list never grew under a
35-second DOM poll; the file was in neither the queue nor the list. Reproduced **4/4** with ~4.3 MB
files. To a user this is indistinguishable from silent data loss — the file *was* on the server, and
a reload revealed it.

Three diagnostics narrowed it sharply: 75 B and 594 KB files appeared instantly, so it was
size-dependent; the same file through the **item** strip appeared immediately, so it was not the
shared dropzone; only the day panel was affected.

**Root cause (confirmed by the fix's executor, not merely hypothesised):** `DayDetailPage.load()`
let whichever day response arrived *last* win, and several loads are routinely in flight (mount,
item save, item delete, upload, attachment delete). A refetch issued *before* the upload could answer
*after* it, overwriting the fresh list — and the queue row had already retired against the good
render, exactly as `2.2-review-fix-2` designed. Zero representations. A long upload widens that
window, which is precisely why only big files showed it. `ItemAttachments` was immune because it
appends the created attachment to its own local state and is never fed by the racing refetch.

**This is the exact "appears in neither" failure mode `2.2-review-fix-2` was warned to avoid**, and
it still happened — which is the strongest argument in this run for walking the UI at every
checkpoint rather than trusting a green suite.

**Fix (`2.3-review-fix-1`):** a monotonic request tag in `DayDetailPage`; a response that is no
longer the newest is dropped, on success *and* on failure (a superseded failure wiping a loaded day
was the same bug wearing a different hat). That extends the file's existing date-tagging discipline
to the request axis rather than adding a parallel mechanism. Queue retirement is untouched, so both
properties now hold at once: shown exactly once, and never shown zero times.

**Failing-first was verified.** Pre-fix the regression test fails with
`expected [] to deeply equal [ 'rezerwacja.pdf' ]`; post-fix it passes. The executor also reverted
its optimistic append to confirm the request tag alone carries the fix rather than masking it.

**Browser confirmation: 8 large uploads, 0 failures**, including the interleaving that actually opens
the race — a 4.3 MB upload concurrent with an item save, where the network trace shows the two
overlapping `GET …/days/…` requests and the attachment still renders and stays. A 9.3 MB upload
batched with an item save also held. Exactly-one-representation still holds: 8 attachment rows,
8 distinct names, 0 leftover queue rows.

## Steps 2.6, 2.7, 2.8

- **2.6** — the count is now a real ICU plural. Verified in the browser: Polish **2 → "2 pliki"**
  (`few`) and **5 → "5 plików"** (`many`). That split is the reason this project chose ICU over
  i18next's suffix pluralisation, so seeing both forms render was worth doing.
- **2.7** — the timeline badge appears only on cards whose item has attachments, and no cost,
  currency or confirmation number appears on the timeline. Note honestly that the second half is
  *trivially* true right now: Phase 3 has not run, so there is no reservation UI to leak. It must be
  re-checked after Phase 3.
- **2.8** — a verified **no-op**, recorded rather than deleted, exactly as the spec asks:
  `frontend/src/features/preview/` does not exist, a repo-wide grep for `data-preview` and
  `PreviewNotice` returns nothing, and there is no census test.

## Deferred to the final review

- The `aria-live` announcement retains its previous message after an unrelated action — after a
  successful delete it still shows an earlier rejection, which then sits on screen indefinitely.
  Minor: it is stale text, not a false claim about the current operation. Left out of
  `2.3-review-fix-1` deliberately because the superseding actions live outside `UploadDropzone`.
- A long filename wraps mid-word in the narrow item modal (from checkpoint 3).
- Large PNGs show a grey placeholder thumbnail while a small one renders immediately — expected for
  a lazy-loaded 4.3 MB original, but worth a reviewer's eye.
- The three backend nits from checkpoints 1 and 2.

## Environment findings (not application defects)

- **The main checkout's `.ai/qa/test-env.env` holds a stale password**; the live one is this
  worktree's copy. It cost the confirmation walk about ten minutes of 401s. Worth fixing before the
  next QA run from another worktree.
- `agent-browser` is not on `PATH`; `TMPDIR` must be `/tmp` or Chrome will not launch from this
  worktree path.
- `agent-browser`'s `fill`/`type` do not work on `input[type=date]` segment spinbuttons, so the
  confirmation walk created its trip through the REST API. Possibly an automation gap, possibly an
  accessibility one — flagged, not investigated.

## Artifacts

`checkpoint-4-artifacts/` — 11 screenshots plus two session transcripts, including the "before"
screenshot of the large-upload bug and the "after" confirmation. No credential ever reached an
artifact, filename or log.
