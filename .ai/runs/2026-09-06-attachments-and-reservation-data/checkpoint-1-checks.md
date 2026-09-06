# Checkpoint 1 — Steps 1.1..1.5

- Fired: 2026-09-06T17:00Z, after 5 consecutive Steps landed.
- Commit range: `f6360f9..da84350` (run-folder commit exclusive, Step 1.5 inclusive).
- Steps covered: 1.1, 1.2, 1.3, 1.4, 1.5.
- Touched areas: `backend/trip_planner/db/models.py`, `backend/migrations/versions/`,
  `backend/trip_planner/domain/`, `backend/trip_planner/security/`, `backend/trip_planner/errors.py`,
  `backend/tests/`, `frontend/src/locales/`, `frontend/src/api/errorCodes.ts` (generated).
  **No component, screen or stylesheet was touched in this window.**

## Checks run

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ PASS | `en`, `pl` in sync across `frontend/src/locales` — the nine new `error.*` keys landed in both. |
| `python3 scripts/check_css_tokens.py` | ✅ PASS | 500 `var()` references across 45 files all resolve. Run despite no CSS change, because it is cheap and the window touched the frontend tree. |
| `python3 scripts/check_contrast.py` | ✅ PASS | 16 declared pairs, all meeting WCAG AA. No new pair was introduced in this window. |
| `(cd backend && uv run ruff check .)` | ✅ PASS | All checks passed. |
| `(cd backend && uv run pytest)` | ✅ PASS | **520 passed, 0 skipped** in 37.92s. The zero-skip count is the load-bearing part: without a reachable PostgreSQL the database layer skips silently, so a green exit code alone would not prove the migration, the CHECK constraints or the advisory-lock test actually ran. PostgreSQL was reachable on `localhost:55432`. |
| `(cd frontend && npm run typecheck)` | ✅ PASS | Clean after `npm ci` — this worktree had no `node_modules` on first run, which is an environment fact rather than a code failure. |
| `(cd frontend && npm run test -- --run)` | ✅ PASS | 149 tests across 7 files. |
| `(cd frontend && npm run build)` | ⏭️ DEFERRED | Not run at this checkpoint: no application source changed, only a generated type union and two locale files, both already covered by typecheck and the locale gate. It runs in full at the final gate. |

## UI verification

⏭️ **Skipped, with reason.** No Step in this window touched a page, component, widget or navigation
surface — the frontend diff is `errorCodes.ts` (generated from the backend enum) and nine key/value
pairs in each locale file. There is nothing rendered to photograph that did not render identically
before. UI verification begins at the Phase 2 checkpoint and runs again as Step 3.7's end-to-end
walk, both with screenshots posted to PR #12.

## Step review (`engine.stepReview: checkpoint`)

The diff `f6360f9..da84350` was reviewed against the `om-code-review` checklist. **No blocker and no
major findings.** The security-critical modules were read in full rather than skimmed:

- `domain/uploads.py` holds the line the spec drew: the client's `Content-Type` and the filename
  extension are never consulted, no image library is imported (and a test asserts none is declared),
  the PNG path reads two integers out of a CRC-verified `IHDR` without touching `IDAT`, and the JPEG
  path walks the marker chain with length arithmetic and stops at `SOS` rather than reading scan
  data. Both truncation checks (`%%EOF`, trailing `FF D9`) are commented as integrity heuristics
  that resist no attacker — which is exactly the honesty the spec asked for.
- `security/quota.py` takes `pg_advisory_xact_lock` **before** summing, in a fixed order (trip key,
  then installation key) so two uploads cannot deadlock against each other, and its pre-read check
  takes only the owner and the session — never a payload — which is what makes the memory control
  real rather than decorative. The executor mutation-tested this: with the trip lock removed, the
  concurrency test fails; with it, it passes.
- `0005_attachment` omits the `item` reservation columns deliberately, and its `downgrade` drops in
  FK-safe order (`upload_event`, then `attachment_blob`, then `attachment`), so Phase 3 will roll
  back independently as A1 requires.

Two **nits**, both recorded and deferred to the final `om-auto-review-pr` pass rather than fixed
mid-run (fixing minors mid-run inflates the Step count without moving the plan):

1. `normalise_filename` applies `.strip()` *after* truncating to 200 characters, so a name that is
   200 characters ending in spaces yields fewer than 200. Harmless; the bound is an upper bound.
2. `INSTALLATION_LOCK_KEY` shares one advisory-lock keyspace with `hashtext(trip_id)`. A collision
   would only cause an unrelated upload to serialise briefly, never a wrong answer, and the constant
   already carries a comment saying so.

## Artifacts

None. No browser session ran and no command output was worth retaining beyond the counts above, so
no `checkpoint-1-artifacts/` folder was created.
