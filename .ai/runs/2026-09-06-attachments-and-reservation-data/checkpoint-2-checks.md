# Checkpoint 2 — Steps 1.6..1.10 (Phase 1 closes)

- Fired: 2026-09-06T19:40Z, on both triggers at once — 5 Steps landed since checkpoint 1, and
  Phase 1 (10 Steps) closed.
- Commit range: `26941d8..2ab94c6`.
- Steps covered: 1.6, 1.7, 1.8, 1.9, 1.10.
- Touched areas: `backend/trip_planner/api/attachments.py` (new, 506 lines), `api/items.py`,
  `api/trips.py`, `api/schemas.py`, `app.py`, `backend/pyproject.toml` + `uv.lock`, and four test
  modules. **No frontend source was touched in this window** — Phase 1 is backend-only by design,
  and the spec says so: "Nothing in the UI changes yet, and the phase is verifiable entirely by
  tests."

## Checks run

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ PASS | Unchanged since checkpoint 1; run because the gate is ordered and cheap. |
| `python3 scripts/check_css_tokens.py` | ✅ PASS | |
| `python3 scripts/check_contrast.py` | ✅ PASS | No new pair — this window rendered nothing. |
| `(cd backend && uv run ruff check .)` | ✅ PASS | All checks passed. |
| `(cd backend && uv run pytest)` | ✅ PASS | **600 passed, 0 skipped** in 57.15s — up from 520 at checkpoint 1. Zero skips again confirms the PostgreSQL layer genuinely ran; the upload, header, cascade and advisory-lock tests are meaningless if they skip. |
| `(cd frontend && npm run typecheck)` | ✅ PASS | |
| `(cd frontend && npm run test -- --run)` | ✅ PASS | 149 tests, unchanged — nothing in the frontend moved. |
| `(cd frontend && npm run build)` | ⏭️ DEFERRED | Still no frontend source change. Runs in full at the final gate. |

## Dependency added

`python-multipart` 0.0.32, via `(cd backend && uv add python-multipart)`, with `uv.lock` committed in
the same commit as `pyproject.toml` (AGENTS.md, Dependencies row). It is the **only** dependency this
run adds. The spec's countervailing rule — that no *image* library may be added — is asserted by a
test from Step 1.2 that reads `pyproject.toml` and fails if pillow, wand, opencv or pyvips appears.

## UI verification

⏭️ **Skipped, with reason.** Phase 1 is backend-only; no page, component, stylesheet or user-visible
string changed. There is nothing to photograph that did not look identical before. The first real UI
verification is the Phase 2 checkpoint, and the full flow walk is Step 3.7 — both with screenshots
posted to PR #12.

## Step review (`engine.stepReview: checkpoint`)

`26941d8..2ab94c6` reviewed against the `om-code-review` checklist. **No blocker, no major.**
`api/attachments.py` was read in full, as the run's highest-risk module.

- **The two constraints that ruled out FastAPI's `UploadFile` are genuinely satisfied, and proved by
  test rather than asserted in a comment.** No `UploadFile`/`Form` parameter is declared and
  `request.form()` is never called; the body is a `bytearray` handed to the driver as a bind
  parameter, and the multipart is parsed in memory by `python-multipart`'s low-level callback
  parser. The executor's test replaces `tempfile.SpooledTemporaryFile`/`NamedTemporaryFile`/
  `TemporaryFile`/`mkstemp` **and** `starlette.formparsers.SpooledTemporaryFile` with a raising stub
  and uploads 2 MiB — well past Starlette's ~1 MB spool threshold — and still gets a `201`. Patching
  both names is the right call: Starlette binds its own reference at import time, so patching
  `tempfile` alone would miss the only path that matters.
- **The order is real.** `check_rate` runs against the owner alone before `read_body`, which refuses
  on `Content-Length` before touching `request.stream()`. The test that proves it shrinks the quota
  to zero and posts an oversized body: it must answer `429`, not `413` — a `413` would prove the
  length or the bytes were consulted first. A sibling test posts the same body **chunked** (with
  `content-length` asserted absent) and gets `413` from the in-loop counter.
- **The part's own `Content-Type` is dropped unread at the parser**, which makes "the client is never
  asked what the file is" structural rather than a rule someone has to remember.
- `_refuse` maps rejections with `ErrorCode(rejection.value)` — an identity lookup, so a member added
  to either rejection enum is answered correctly without this function changing. That is better than
  the `if` ladder the plan would have tolerated.
- `find_attachment` outer-joins **both** parent chains through separate `trip_day` aliases in one
  query, and never joins `attachment_blob`. Step 1.7 added a statement-recording test asserting the
  metadata request never mentions `attachment_blob`, so a future `joinedload` cannot silently make a
  listing read sixty megabytes.
- **Step 1.10, the only edit to shipped code, is correctly conservative.** A day with *both* items
  and attachments still answers the older `days_have_items`, because an existing client already
  branches on it and re-labelling a refusal it understands would be `BACKWARD_COMPATIBILITY.md` §1's
  "changing an error code for an existing condition". The new code appears only for a case that was
  previously not a refusal at all. Every pre-existing `days_have_items` test passes **unmodified** —
  the regression guard the spec's Risks section names.
- Step 1.8's phase-split decision was taken correctly: the reservation request/response fields moved
  into Step 3.1's commit alongside the columns they need, rather than pulling migration
  `0006_item_reservation` forward into Phase 1. That preserves assumption **A1** — Phase 3 rolls back
  alone — which was an explicit spec decision, not an accident. PLAN.md's 1.8 and 3.1 texts were
  updated to say so honestly.

**Nits** recorded and deferred to the final review (never fixed mid-run — a minor would inflate the
Step count without moving the plan):

3. The parent lookup (`get_day` / `find_item`) runs *before* `check_rate`. This is a cheap indexed
   query and it means a request for a nonexistent day answers `404` without consuming quota, which
   is the better behaviour — but it is a deviation from the spec's literal check order and is worth
   a reviewer's eye.
4. Carried forward from checkpoint 1, still open: `normalise_filename` strips after truncating, and
   `INSTALLATION_LOCK_KEY` shares an advisory keyspace with `hashtext(trip_id)`.

## Phase 1 outcome

The spec's Phase 1 exit condition is met: "Files can be uploaded, listed, downloaded and deleted
through the API, with every security control in place. Nothing in the UI changes yet, and the phase
is verifiable entirely by tests." All of it is, and the phase is independently shippable.

## Artifacts

None — no browser session ran and no retained command output beyond the counts above.
