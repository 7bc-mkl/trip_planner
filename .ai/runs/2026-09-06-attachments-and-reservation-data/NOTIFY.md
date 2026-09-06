# Notify — 2026-09-06-attachments-and-reservation-data

> Append-only log. Every entry is UTC-timestamped. Never rewrite prior entries.

## 2026-09-06T16:27:06Z — run started
- Brief: implement `.ai/specs/2026-09-05-attachments-and-reservation-data.md` — attachments on days
  and items, plus reservation data (confirmation number and cost) on the item.
- External skill URLs: none.
- Engine decision: `Engine: om-auto-create-pr-loop (steps: 28, --loop: no)` — the spec's
  Implementation Plan drafts 28 Steps across 4 phases, over the configured threshold of 20.
- Slot check: free — no `feat/attachments-and-reservation-data` branch, no run folder for the slug,
  and no open PRs in the repository at all.
- Decision: `python-multipart` will be added as a backend dependency in Step 1.6. FastAPI needs it
  for `multipart/form-data`, and it is not in `backend/pyproject.toml` today. It is the only
  dependency this run adds; the spec's "no image library" rule is asserted by a test in Step 1.2.

## 2026-09-06T17:05:00Z — checkpoint 1
- Steps covered: 1.1..1.5 (`f6360f9..da84350`). Backend vocabulary complete; no endpoint wired yet.
- Outcome: PASS. `check_locales` / `check_css_tokens` / `check_contrast` green, `ruff` clean,
  `pytest` **520 passed / 0 skipped**, frontend typecheck and 149 tests green. `npm run build` is
  deferred to the final gate because no application source changed in this window.
- UI verification skipped, with reason: no Step in the window touched a page, component or
  stylesheet — the frontend diff is a generated type union and nine locale keys.
- Step review (checkpoint mode): no blocker and no major findings. Two nits recorded and deferred
  to the final review — `normalise_filename` strips after truncating, and `INSTALLATION_LOCK_KEY`
  shares an advisory keyspace with `hashtext(trip_id)` (harmless extra serialisation at worst).
- Decision — Tasks-table SHA reconciliation. The per-Step "commit, read SHA, edit PLAN.md, amend"
  procedure can only ever record the *pre-amend* SHA, because amending changes the SHA it just
  recorded. Executors therefore record the pre-amend value and the main session rewrites the whole
  `Commit` column to the real post-amend SHAs at every checkpoint. All five rows were reconciled
  here (1.1 `a76361d`, 1.2 `223399b`, 1.3 `17215fb`, 1.4 `8cc3dc2`, 1.5 `da84350`), so
  `om-auto-continue-pr-loop` resumes against SHAs that actually exist on the branch.
- Environment note: `frontend/node_modules` was absent in this worktree and `npm ci` was run. The
  first typecheck failure was that absence, not the diff.

## 2026-09-06T18:12:00Z — Step 1.8 scope decision: the reservation fields moved to Step 3.1
- Situation: Step 1.8 was drafted to add both the attachment counts/lists **and** the three
  reservation fields (`confirmation_number`, `cost_amount`, `cost_currency`) to `ItemRead` and
  `ItemUpdate`. Those three are `item` **columns**, and Step 3.1 adds them on its own Alembic
  revision precisely so Phase 3 rolls back alone (assumption A1). At 1.8 the columns do not exist.
- Decision: **resolution (ii)** — the attachment half landed in Step 1.8; the reservation half moves
  into Step 3.1's commit, alongside the migration and the model columns it reads and writes.
- Why: the split holds cleanly. Nothing in the attachment work needs the reservation columns, and
  nothing in the reservation contract can be written without them — a serialiser field for a column
  that does not exist is not a half-landed contract, it is a broken one, and `ItemUpdate` would have
  had to accept fields it could not persist. Pulling `0006_item_reservation` forward into Phase 1
  (resolution (i)) would have bought nothing and would have destroyed the property the phase split
  exists for: Phase 3 rolling back on its own.
- Effect on the plan: PLAN.md's Step 1.8 text now describes the attachment half only and records
  this decision; Step 3.1's text now carries the API half verbatim — the `Decimal` on the wire, the
  `model_fields_set` clear-vs-omit rule, `422 invalid_cost` for one half alone through
  `domain/money.py`, `422 invalid_reservation_field` past 500 characters, `""` meaning clear, and no
  second copy of the reservation's dates. The cost/confirmation tests move with it.
- Step ids, `Exec` cells and the Tasks table's shape are unchanged; only the two Step descriptions
  and row 1.8's `Status`/`Commit` were touched.

## 2026-09-06T19:40:00Z — Step 1.10 contract decision: a day with BOTH items and attachments answers `days_have_items`
- Situation: `PATCH /trips/{tripId}` gains `409 days_have_attachments` for a dropped day carrying
  documents. A day can carry items *and* documents, and the spec leaves the code for that case open.
- Decision: **`days_have_items` wins.** `_refuse_if_attachments_would_be_lost` runs immediately
  *after* `_refuse_if_days_would_be_lost`, so a day with both answers the older code; only a day
  with documents and no items answers `days_have_attachments`.
- Why: both codes are truthful and both lead the owner to the same fix (clear that day), so the tie
  is broken on compatibility. A client shipped before this feature already branches on
  `days_have_items`; keeping it means no existing client meets an unknown code for a case it already
  handles, and the new code appears only for a case that previously did not exist as a refusal at
  all. Reversing the order would re-label a refusal an existing client understands —
  `BACKWARD_COMPATIBILITY.md` §1's "changing an error code for an existing condition".
- Scope note: this Step **narrows** shipped behaviour — a shortening that used to succeed can now be
  refused. That direction is the point: the behaviour it removes is silent deletion of a voucher by
  a date edit (foundation A10). No path that preserved data changes. The whole `days_have_items`
  suite passes unmodified as the regression guard; the backend suite is 600 passed / 0 skipped.
- The guard also covers attachments pinned to an *item* on a dropped day, in one `UNION`ed statement
  for the whole edit (no query per day), so it does not depend on the sibling's ordering to be safe.

## 2026-09-06T19:45:00Z — checkpoint 2 (Phase 1 closes)
- Steps covered: 1.6..1.10 (`26941d8..2ab94c6`). **Phase 1 is complete and independently shippable.**
- Outcome: PASS. Three script gates green, `ruff` clean, `pytest` **600 passed / 0 skipped**,
  frontend typecheck and 149 tests green. `npm run build` still deferred — no frontend source has
  changed yet.
- UI verification skipped, with reason: Phase 1 is backend-only by design ("Nothing in the UI
  changes yet, and the phase is verifiable entirely by tests"), so there is nothing to photograph.
- Dependency: `python-multipart` 0.0.32 added via `uv add`, `uv.lock` committed with the manifest.
  The only dependency this run adds; the no-image-library rule stays asserted by a test.
- Step review (checkpoint mode): no blocker, no major. The `UploadFile`-avoidance and the check
  order are proved by test, not asserted in a comment — the temp-file test patches
  `starlette.formparsers.SpooledTemporaryFile` as well as `tempfile`, which is the patch that
  actually matters, and the ordering test demands `429` rather than `413` on an oversized body.
- Nits carried to the final review: the parent lookup runs before `check_rate` (deliberate — a bad
  path answers 404 without consuming quota — but a deviation from the spec's literal order), plus
  the two nits from checkpoint 1.
- Tasks-table SHAs for rows 1.6..1.10 reconciled to their post-amend values.

## 2026-09-06T20:14:41Z — Step 2.4 scope decisions
- New-item case (`item === null`): `ItemAttachments` renders its heading, its shipped empty state
  and a translated "save the item first" line, but **no dropzone at all** — there is no `itemId` yet
  for `POST /trips/{tripId}/items/{itemId}/attachments` to target, so nothing is rendered that could
  throw or silently no-op on the first drop. Pinned down by `itemAttachments.test.tsx`'s "the
  new-item case" block.
- `ItemRow` gains `attachmentCount?: number` as an **opt-in prop**, not a direct read of
  `item.attachment_count` off the item it already receives (which would have painted the paperclip
  on the timeline too, ahead of Step 2.7). Only `DayDetailPage` passes it (`attachmentCount=
  {item.attachment_count}`); `TimelinePage` is untouched, matching 2.7's own plan text ("ItemRow's
  existing callers that pass no count render exactly as before").
- The `paperclip` glyph was added to the icon sprite here rather than in 2.7: `icons.svg`'s header
  comment had pencilled it in for "the timeline's per-item badge", but the task brief for this Step
  explicitly assigns "the paperclip and count on the item row" to 2.4, and the glyph needed a first
  consumer regardless of which host reaches it first. The sprite's comment is updated accordingly.
- `AttachmentRow` (the per-attachment card) was factored out of `DayAttachments.tsx` into its own
  module and imported by both it and the new `ItemAttachments.tsx`, per this Step's explicit
  instruction not to re-implement the same row twice.
- The count text (`item.attachmentCount`, "Attachments ({count, number})" / "Załączniki ({count,
  number})") deliberately does **not** pluralise the noun — that ICU plural key is Step 2.6's own
  named deliverable. This Step's key can be swapped for 2.6's once it lands without changing where
  it is called from.

## 2026-09-06T18:25:51Z — Step 2.5 scope decisions
- `AttachmentRow` owns the whole delete flow, not just the trigger: it renders the download `<a>`,
  the delete `.button-danger`, and (behind `confirmingDelete` state) the `ConfirmDialog` itself,
  which calls `deleteAttachment(tripId, attachment.id)` directly. A host never touches the API for
  delete — it only receives the new required `onDeleted: () => void` prop, fired after the awaited
  delete resolves, exactly mirroring how upload already bubbles through `onUploaded`.
- Both hosts gained a same-shaped `onDeleted` prop and forward it unchanged to every row.
  `DayAttachments` is purely presentational (no local list state), so its `onDeleted` is a straight
  pass-through; `ItemAttachments` still owns its local `attachments` array, so its `onDeleted` prop
  wraps a `handleDeleted(attachmentId)` that filters the row out locally *and* bubbles up, the same
  local-first/bubble-up shape `handleUploaded` already uses.
- `ItemDialog` gained `onAttachmentDeleted: () => void` — a name deliberately distinct from its
  existing `onDelete` (which deletes the whole item) — wired by `DayDetailPage` to `() => void
  load()`, the same refetch `onUploaded` already triggers on both hosts.
- Download is a real `<a href={attachmentContentUrl(...)}>` wearing `.button-quiet`; a new
  `.attachment-row__actions a { text-decoration: none }` rule undoes the link underline, the same
  pattern `.day-nav__link` already uses for its own anchors.
- Whoever builds Step 4.2's lightbox on top of this row should know: `AttachmentRow`'s own delete
  button and `ConfirmDialog` stay mounted in the row regardless of what a host does with `onDeleted`
  (confirmed by `attachmentRow.test.tsx`'s focus-return-on-confirm test), so a lightbox trigger on
  the image preview can coexist without fighting this row's own confirm-dialog lifecycle.

## 2026-09-06T20:45:00Z — checkpoint 3 (first real browser walk)
- Steps covered: 2.1..2.5 (`59ff245..d83e6eb`). The whole attachment UI now exists.
- Gate outcome: PASS — **all eight commands green**, including `npm run build` and 213 frontend
  tests (up from 149). Backend unchanged at 600 passed / 0 skipped.
- UI verification: **RAN**, against `.ai/scripts/test-env-up.sh` (production app factory, built SPA,
  one origin, fresh database), driven with `agent-browser` v0.34.0 in **both locales**.
  Verdict **PARTIAL** — everything Steps 2.1–2.5 were asked to build works end to end, and the walk
  still found four major defects plus one nit that **no gate command could see**. That gap is the
  argument for doing the walk at all, and it is why this entry exists.
- Defects → two fix Steps appended to the Tasks table (blocker/major fix now, minor/nit defer):
  - `2.2-review-fix-1` — the `aria-live` announcement is formatted at event time and never
    re-renders, so Polish leaks into the English UI (R01/R09) and a rejected upload still announces
    "100%" to a screen reader. `check_locales.py` cannot catch this: both keys exist and are in
    sync; what is wrong is *when* the string was formatted.
  - `2.2-review-fix-2` — a completed upload stays in the dropzone queue while also appearing as a
    real attachment row, so every file shows twice and the queue goes stale after a delete.
  - Deferred nit: a long filename wraps mid-word in the narrow item modal.
- Process deviation recorded: Step 2.4 produced a second, docs-only commit (`96fa3a7`) against the
  one-Step-one-commit rule. Not force-fixed — it changes no code, so bisect-by-Step is unaffected,
  and rewriting pushed history to tidy a docs commit would cost more than the deviation. Later
  executor prompts carry an explicit instruction not to repeat it; Step 2.5 produced exactly one.
- Environment: `agent-browser` is not on `PATH` (cached binary used), and Chrome will not launch
  unless `TMPDIR` is `/tmp` — this worktree path exceeds Chromium's singleton-socket length limit.
- Tasks-table SHAs for rows 2.1..2.5 reconciled to their post-amend values.

## 2026-09-06T21:35:00Z — Step 2.8 is a no-op, and is recorded as one
- Checked, at the moment the Step ran: `frontend/src/features/preview/` **does not exist**; a
  repository-wide grep for `data-preview` and `PreviewNotice` returns **nothing**; there is no
  census test. Only `features/auth/` and `features/trips/` exist under `features/`.
- Therefore this feature had no inert preview surfaces to delete and no census number to update, and
  Step 2.8 lands no code.
- **Recorded rather than deleted, deliberately**, because the spec asks for exactly that: "If the
  folder does not exist, this step is a no-op and is recorded as one — rather than deleted, so a
  later reader knows the interaction was considered." The interaction was considered.
- The background, for that later reader: the design-system spec's workstream B specified two of this
  feature's surfaces as inert previews — the day-documents panel with a disabled file input, and the
  collapsed reservation disclosure with three disabled fields — and its Phase 5 was cut by the owner
  mid-run (PR #11). So this feature's UI is a **first build, not an activation**, and every surface
  Phase 2 and Phase 3 create is new markup. Had workstream B shipped first, this Step would have
  deleted those two `<PreviewNotice>` blocks, removed the `disabled` attributes and the
  `data-preview` markers, and lowered that spec's census from four surfaces to two.

## 2026-09-06T22:10:00Z — Step 2.3-review-fix-1: a stale day response could unshow a fresh upload
- **The defect, from the browser walk.** On `/trips/:id/days/:date`, uploading a ~4.3 MB PNG
  announced "Dodano big3.png" and then showed the file **nowhere** — neither as an attachment row
  nor as a queue row. A reload proved the file was on the server all along. 75 B and 594 KB files
  appeared instantly; the same 4.3 MB file uploaded through the *item* strip appeared instantly.
  To the owner it looked exactly like silent data loss.
- **Root cause — confirmed, not the drop zone.** `DayDetailPage.load()` let **whichever day response
  arrived last win**, regardless of which request was newest. Several loads are in flight routinely
  (the mount's, one per item save or delete, one per upload or attachment delete), and nothing
  orders the answers. The losing ordering: an unrelated refetch is issued while the upload is still
  in flight → the upload finishes and its own refetch renders the list *with* the new attachment →
  `UploadDropzone` correctly retires the queue row against that list, **permanently**, as
  `2.2-review-fix-2` designed it → the older request finally answers with the pre-upload list and
  overwrites the fresh one. The attachment row is gone and the queue row is never coming back. A
  slow upload widens that window, which is exactly why only large files showed it, and why the item
  strip — which appends the created attachment to its own local list — never did.
- **The fix.** `DayDetailPage` now tags every day request with a monotonic counter and drops any
  response, success *or* failure, that is no longer the newest. That is the same discipline the file
  already used on the other axis (state tagged with the date it was loaded for, so another day's
  answer cannot render) extended to the request axis rather than a parallel mechanism. Alongside it,
  a finished day upload is now appended to the day's own attachment list from the upload's own
  answer before the refetch replies — the local-first shape `ItemAttachments` already had, so the
  two hosts behave the same and the panel no longer depends on a round trip for a fact the server
  has already confirmed. Queue retirement is untouched: the duplicate rows `2.2-review-fix-2` fixed
  stay fixed, and both properties now hold at once — a file is shown exactly once, never zero times.
- **Failing-first, on purpose.** `frontend/src/features/trips/dayAttachmentsRace.test.tsx` drives the
  ordering through the real screen with the day responses held open by hand. It **fails on the
  pre-fix code** ("expected `[]` to deeply equal `['rezerwacja.pdf']`" at the post-stale-response
  assertion) and passes after. Verified a second time that the counter alone carries the fix, so it
  is not the optimistic append masking the race. Three cases: the out-of-order refetch; the upload's
  own answer rendering without waiting for a round trip; and an unrelated refresh landing *while*
  the upload is in flight, which must not retire the queue row that is the file's only
  representation at that moment.
- **Deferred, still open.** The `aria-live` region keeps its previous message after an unrelated
  action (a rejection message survives a later successful delete, item creation and locale
  switches). Clearing it is not a consequence of this change — the announcement lives in
  `UploadDropzone` and the actions that ought to supersede it happen outside it — so per this Step's
  own scope note it is left as a deferred minor rather than widening the Step.
- Gate: `typecheck`, `test --run` (**232 passed**, up from 229), `build`, `check_locales.py`,
  `check_css_tokens.py`, `check_contrast.py` — all green.

## 2026-09-06T21:55:00Z — checkpoint 4 (Phase 2 closes; run pauses at the safety checkpoint)
- Steps covered: `2.2-review-fix-1`, `2.2-review-fix-2`, `2.6`, `2.7`, `2.8`, and the
  `2.3-review-fix-1` this checkpoint produced (`bdcfa5b..02339d2`).
- Gate: all eight commands green — 600 backend / 0 skips, **232** frontend tests, build clean.
- UI re-verification: **all four checkpoint-3 defects confirmed FIXED in the running application**,
  in both locales, rather than inferred from the suite.
- **A fifth, worse defect was found by the same walk, and fixed.** A ~4.3 MB upload to the day panel
  announced success and **never appeared in the list** (35 s DOM poll, reproduced 4/4) — the file was
  on the server, so to a user this is indistinguishable from silent data loss. Root cause:
  `DayDetailPage.load()` let whichever day response arrived last win; a refetch issued before the
  upload answered after it and overwrote the fresh list, while the queue row had already retired
  against the good render. Zero representations. Size-dependent because a long upload widens the
  window; the item strip was immune because it appends from its own answer.
  **This is precisely the "appears in neither" failure mode `2.2-review-fix-2` was warned to avoid,
  and it happened anyway** — the strongest argument this run has produced for walking the UI at
  every checkpoint instead of trusting a green suite.
- Fix `2.3-review-fix-1`: a monotonic request tag; a superseded response is dropped on success and
  on failure alike. Failing-first verified, and the executor reverted its optimistic append to prove
  the tag alone carries the fix. Confirmed by **8 large uploads, 0 failures**, including a 4.3 MB
  upload concurrent with an item save (network trace shows the two overlapping day GETs) and a
  9.3 MB worst case.
- 2.6 verified in the browser: Polish `few` (2 pliki) and `many` (5 plików) both render. 2.7's
  "no money on the timeline" is currently *trivially* true — Phase 3 has not run — and must be
  re-checked afterwards.
- Environment: **the main checkout's `.ai/qa/test-env.env` holds a stale password**; the worktree
  copy is the live one. Cost the confirmation walk ~10 minutes of 401s. Also: `agent-browser`'s
  `fill`/`type` do not work on `input[type=date]` segment spinbuttons.
- **Run paused here for user review**, per the executor-dispatch safety checkpoint (~20 consecutive
  successful Steps). 21 of 31 Steps are done; Phases 1 and 2 are complete and independently
  shippable. Nothing is blocked and nothing awaits an answer.
