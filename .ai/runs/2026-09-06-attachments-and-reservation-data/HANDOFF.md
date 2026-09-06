# Handoff — 2026-09-06-attachments-and-reservation-data

**Last updated:** 2026-09-07T00:25:00Z
**Branch:** feat/attachments-and-reservation-data
**PR:** https://github.com/7bc-mkl/trip_planner/pull/12 (draft, claimed by @7bc-mkl)
**Current phase/step:** Phase 4 Step 4.1
**Last commit:** 8d21299 — feat(reservations): show the saved cost formatted through Intl

## What just happened
- **Phase 3 is complete.** 29 of 32 Steps done. The user reviewed at the safety checkpoint and chose
  to finish the whole spec, so the run resumed through Phase 3 and continues into Phase 4.
- **R04 is met**, proved by walking the brief\'s own flow in the running app: open a day → open an
  item → attach a voucher → save the confirmation number and cost → move to *gotowe* → the counter
  went `0 z 1` to `1 z 1`. A full reload returned every value; the disclosure never opened itself;
  moving to *gotowe* stayed one click with no prompt.
- That walk also found `formatCurrency` had **no call site** — a green Step-3.4 test over
  unreachable code. Fixed as `3.4-review-fix-1`: the collapsed disclosure now shows a *saved* cost
  formatted through `Intl`, and only when one exists, so it cannot become a nag.
- Gate: **635 backend / 0 skips, 270 frontend**, build clean.

## Next concrete action
- **Step 4.1** — drag-and-drop layered on the existing file input. Phase 4 is the spec\'s own
  slippable tail; the user asked for all of it.

## Blockers / open questions
- none.

## Remaining after Phase 4
The final gate (full `validation.commands` + the integration suite + a design-system pass), the
authoritative `om-auto-review-pr {12} --autofix` pass, the summary comment, and the draft→ready flip.

## Deferred to the final `om-auto-review-pr` pass
- The `aria-live` announcement keeps its previous message after an unrelated action.
- Manually clearing the pre-filled `PLN` currency while an amount is present drops both halves
  silently (outside ordinary use, but real).
- A long filename wraps mid-word in the narrow item modal; large PNG previews show a placeholder.
- Three backend nits: `normalise_filename` strips after truncating; `INSTALLATION_LOCK_KEY` shares
  an advisory keyspace with `hashtext(trip_id)`; the parent lookup runs before `check_rate`.

## Environment caveats
- PostgreSQL on `localhost:55432`. Every backend run reports **0 skips** — keep checking that.
- QA env: `sh .ai/scripts/test-env-up.sh [--force-rebuild]`; descriptor `.ai/qa/test-env.json`; left
  running. **Use this worktree\'s `.ai/qa/test-env.env`** — the main checkout\'s password is stale.
- Browser: `agent-browser` v0.34.0, **not on `PATH`**; **`TMPDIR` must be `/tmp`** or Chrome will not
  launch from this worktree path. It **cannot drive `input[type=date]` or `input[type=time]`** at
  all — create trips through the REST API and do the flow under test through the UI. Also
  `find role button "<label>" click` silently no-ops on this app\'s dialog buttons; use
  `click \'button[type=submit]\'`.
- Frontend deps installed here via `npm ci`.
- Database/migration state: clean. Head is `0006_item_reservation`.

## Worktree
- Path: /home/mkl/cezar/projects/trip_planner/.ai/cezar/worktrees/2223e7fe-07b0-43b2-962a-a6d3db36f6f0
- Created this run: no — the invoking linked worktree, reused per the worktree contract.
