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
