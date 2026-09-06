# Final gate — spec completion

- Run: `2026-09-06-attachments-and-reservation-data`
- Fired: 2026-09-07T01:30Z, when every row in the Tasks table reached `done`.
- Final commit at gate close: `5c4acb6`. Base: `main` at `4ef73d9`.
- **35 Steps** landed: the spec's 28, plus 7 fix Steps appended from browser findings.

## The headline

**The gate ran twice.** It passed all eight commands on the first attempt — and the UI walk that
runs beside it found a **critical** defect that would have shipped: two concurrent uploads to one
trip permanently hung the whole server. So the first pass is recorded as a **FAIL**, three fixes
landed, and the gate was re-run. That sequence is the honest account and it is the single most
important thing in this file.

## Full validation gate — `validation.commands`, in order

| # | Command | First pass | After fixes |
|---|---|---|---|
| 1 | `python3 scripts/check_locales.py` | ✅ | ✅ |
| 2 | `python3 scripts/check_css_tokens.py` | ✅ | ✅ |
| 3 | `python3 scripts/check_contrast.py` | ✅ | ✅ — still 16 declared pairs; this feature introduced **no** new text-on-colour pair, so no row was ever added to the script |
| 4 | `(cd backend && uv run ruff check .)` | ✅ | ✅ |
| 5 | `(cd backend && uv run pytest)` | ✅ 635 passed, **0 skipped** | ✅ **637 passed, 0 skipped** |
| 6 | `(cd frontend && npm run typecheck)` | ✅ | ✅ |
| 7 | `(cd frontend && npm run test -- --run)` | ✅ 293 | ✅ **336 tests, 22 files** |
| 8 | `(cd frontend && npm run build)` | ✅ | ✅ |

The **zero skips** matter and are checked every time: this suite skips the entire database layer
silently when PostgreSQL is unreachable, so a green exit code alone would prove nothing about the
migrations, the `CHECK` constraints, the advisory lock or the cascades.

## Integration suite

The repository has **no separate integration or E2E runner** — no Playwright, no Cypress, no
`om-integration-tests` harness — and this run deliberately added none: it has added exactly one
dependency (`python-multipart`, for `multipart/form-data`) and a browser runner is not a dependency
the spec asked for. The repository's integration-level coverage lives **inside the vitest suite** as
full-app tests that drive real `App`/`MemoryRouter` with a state-storing fetch stub and a shared
`FakeXhr` — `arrangingOneItem.test.tsx` (Step 3.7), `statusPathIndependence.test.tsx`,
`dayAttachmentsRace.test.tsx`, `duplicateHint.test.tsx` — and it ran in full at command 7 above.
That is recorded as what it is: **a full-app integration suite, not browser E2E.** The browser
coverage this feature has is the five walks below, not an automated suite.

## Design-system / style compliance pass

The repository's design-system compliance tooling **is** `check_css_tokens.py` and
`check_contrast.py`, both green (commands 2 and 3). There is no `.uxproof/` and no repo-local style
skill. `check_css_tokens.py` is the load-bearing one: an undefined `var()` drops its property
silently with no error anywhere, so a component referencing an invented token would ship as an
unstyled div and pass every other check. This feature invents **no colour, no radius and no border
style** — it uses the three tokens the design system annotated for a dropzone before this feature
had any code (`--surface-sunken`, `--hairline-strong`, `--radius-lg`), the shipped `.empty-state`,
`.dialog--confirm`, field and button recipes, and the existing status-chip triple for the upload
pills.

`npm run lint` (oxlint) is **not** one of the eight gate commands, but was run as part of this pass.
It reports warnings only, no errors. Two are in this feature's code and both are **deliberate,
documented patterns rather than oversights**, so they were surfaced for the reviewer rather than
rewritten at the last minute:

- `UploadDropzone.tsx` — `react(refs): Cannot access refs during render`. This is the "latest value"
  ref idiom: `hashesRef.current` is assigned during render and read only in an event handler, never
  for render output. It carries a comment explaining why the assignment must happen during the
  committing render.
- `UploadDropzone.tsx` — `react(set-state-in-effect)`. This is the retirement effect from
  `2.2-review-fix-2`; it returns the previous array unchanged when nothing needs removing, so it
  cannot cascade.

The remaining warnings are the pre-existing `only-export-components` fast-refresh class, including
one in `SessionContext.tsx` that this run did not touch.

## UI verification — five browser walks, six major defects

Every walk ran against `.ai/scripts/test-env-up.sh`: `create_production_app` serving the real
`npm run build` bundle from **one origin** in front of a freshly recreated PostgreSQL database, so
cookies and CSRF behave as deployed.

**Every one of the six defects below passed the full eight-command gate.** They were found only by
driving the application. That is this run's clearest finding and it is worth stating plainly rather
than burying in a checkpoint file.

| # | Defect | Found at | Fixed by |
|---|---|---|---|
| 1 | Polish copy frozen into the English UI — the `aria-live` string was formatted at event time and never re-rendered | checkpoint 3 | `2.2-review-fix-1` |
| 2 | A rejected upload still announced "100%" to screen readers | checkpoint 3 | `2.2-review-fix-1` |
| 3 | Every successful upload was shown **twice** — once as a queue row, once as an attachment row | checkpoint 3 | `2.2-review-fix-2` |
| 4 | The queue asserted a deleted file still existed | checkpoint 3 | `2.2-review-fix-2` |
| 5 | A ~4.3 MB upload announced success and **never appeared** — a stale day refetch overwrote the fresh list after the queue row had already retired. Reproduced 4/4; indistinguishable from silent data loss | checkpoint 4 | `2.3-review-fix-1` |
| 6 | **Two concurrent uploads to one trip permanently hung the entire server** | **final gate** | `1.6-review-fix-1` |

Plus two more the final walk caught: Step 4.3's duplicate hint was **dead code** that never rendered
anywhere (`4.3-review-fix-1`), and typing `249,50` — the Polish decimal separator, in the Polish UI —
rendered a literal `NaN €` and then failed to save with "check the marked fields" while nothing was
marked (`3.4-review-fix-2`).

### Defect 6 in full, because it is the one that mattered

Two concurrent uploads to the same trip hung the whole process permanently: one returned `201`, the
other never returned, and `/api/v1/health` then timed out **for every client** until the database
backend was killed. PostgreSQL showed one backend `active / wait_event=advisory` on
`pg_advisory_xact_lock(hashtext(trip_id))` and another `idle in transaction / ClientRead`.

The cause was a mismatch this run introduced. The upload handlers are `async def` — they have to be,
because Step 1.6 drives `request.stream()` itself to check the rate window and `Content-Length`
before the body is read and to keep every byte off the filesystem — but they then did **synchronous
psycopg work on the event loop**. FastAPI runs a sync `def` endpoint in a threadpool and an
`async def` endpoint on the loop, so the request waiting on the advisory lock froze the loop and the
request *holding* it could never be served to commit. The advisory lock was never the problem and is
untouched; running it on the event loop was. The fix awaits the blocking database work through
`run_in_threadpool`, leaving only the streaming on the loop.

**The regression test is worth reading.** Its author found that simply `gather`ing two uploads does
**not** reproduce the hang — under `ASGITransport` the first upload commits before the second is
scheduled, and that test passes with the bug present. So the test holds the trip's advisory lock on
a third connection and asks whether `/api/v1/health` still answers while an upload waits on it, with
the deadline enforced from another thread because a timeout scheduled *on* a frozen loop never
fires. Reverting the fix makes it fail at the deadline; with the fix, health answers `200`.

### Re-verification after the fixes

| Push | Result |
|---|---|
| 2 concurrent 2.3 MB uploads, same day | both `201` in 0.12 / 0.19 s |
| 8 concurrent (5 to a day, 3 to an item of the same trip) | all `201`, slowest 0.67 s |
| 16 concurrent, one client holding its request open 7.9 s | all `201` |
| UI multi-file drop, 5 files | all 5 stored |
| 8 concurrent throttled to ~26 s each, day and item mixed | all `201` |

`/api/v1/health` was polled continuously throughout: **18 153 polls, 100 % `200`, zero timeouts.**
Byte integrity was checked — md5 of stored content matched the source on 10/10 sampled uploads —
and the final tally of 40 attachments accounted for every upload. The application log for the whole
walk shows 0× 5xx and no tracebacks.

The duplicate hint now renders on exactly the duplicated rows with all copies stored (nothing
refused, nothing deduplicated — assumption A14), and no hint appears for the same bytes on a
different parent. `249,50` renders `249,50 €` and stores `249.50`; `NaN` appears nowhere in the DOM
for any malformed input, and a refused save marks `#item-cost-amount` with `aria-invalid="true"`
and `aria-describedby` pointing at a visible translated message.

### R04, verified end to end

The product brief's own flow was walked in the running application in both locales (Step 3.7):
open a day → open an item → attach a voucher PDF → save the confirmation number and cost → move the
status to *gotowe* → **the readiness counter changed from `0 z 1 załatwionych` to `1 z 1`.** A full
reload returned every value, the disclosure never opened itself, and moving to *gotowe* stayed one
click with no prompt.

## Residual findings — surfaced for the reviewer, not fixed

Recorded here and in the PR summary so the reviewer decides rather than discovers:

1. The `aria-live` region keeps its previous message after an unrelated action — after a delete it
   still shows an earlier rejection. Stale text, not a false claim about the current operation.
2. After a multi-file drop the live region announces only the last filename, not the batch.
3. On re-edit, the Polish UI re-populates the cost **input** as `249.50` (dot) while the summary
   beside it renders `249,50 €`. The round trip is correct; it is a locale inconsistency on re-edit.
4. Manually clearing the pre-filled `PLN` while an amount is present drops both halves silently.
   Outside ordinary use, but real.
5. A long filename wraps mid-word in the narrow item modal; large PNG previews show a placeholder
   before the original loads (expected for a lazy-loaded original, but worth an eye).
6. Backend nits: `normalise_filename` strips after truncating; `INSTALLATION_LOCK_KEY` shares an
   advisory keyspace with `hashtext(trip_id)` (at worst a brief unrelated serialisation); the parent
   lookup runs before `check_rate` (deliberate — a bad path answers `404` without consuming quota —
   but a deviation from the spec's literal check order).
7. One report of a `201` returned for a file later absent from the database, observed **after** the
   tester killed a deadlocked backend by hand. Confounded by that intervention and not reproduced in
   the 40-upload re-verification, but recorded rather than dismissed.

## Process deviations, recorded

- Step 2.4's executor produced a second, docs-only commit against the one-Step-one-commit rule. Not
  force-fixed: it changes no code, so bisect-by-Step is unaffected, and rewriting pushed history to
  tidy a docs commit would cost more than the deviation.
- Checkpoint 5 covered eight Steps rather than five, because Step 3.7 *is* a full UI walk with
  screenshots and checkpointing at 3.5 would have paid for the same browser work twice. The gate
  commands still ran at the 3.6 boundary and were green.
- Tasks-table `Commit` cells are reconciled at each checkpoint: the per-Step commit-then-amend
  procedure can only ever record a pre-amend SHA.

## Environment findings (not application defects)

`agent-browser` is not on `PATH`; `TMPDIR` must be `/tmp` or Chrome will not launch from this
worktree path; `agent-browser` cannot drive `input[type=date]` or `input[type=time]` at all, so
walks created their trip through the REST API and did the flow under test through the UI; and
`find role button "<label>" click` silently no-ops on this app's dialog buttons. Separately, the
**main checkout's `.ai/qa/test-env.env` holds a stale password** — the worktree copy is the live one.

## Artifacts

`final-gate-artifacts/` — `gate.log`, 11 screenshots from the two final walks (including the
deadlock before, and health answering `200` during concurrent uploads after), and two session
transcripts. No credential reached any artifact, filename or log.
