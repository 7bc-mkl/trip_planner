# Handoff — 2026-09-06-attachments-and-reservation-data

**Last updated:** 2026-09-06T20:45:00Z
**Branch:** feat/attachments-and-reservation-data
**PR:** https://github.com/7bc-mkl/trip_planner/pull/12 (draft, claimed by @7bc-mkl)
**Current phase/step:** Phase 2 Step 2.2-review-fix-1
**Last commit:** d83e6eb — feat(attachments): add download and delete with confirmation

## What just happened
- Steps 2.1–2.5 landed the whole attachment UI, and checkpoint 3 ran the **first real browser walk**
  of this feature against the QA environment, in both locales.
- **All eight gate commands are green and the feature is still defective.** The walk found four
  major defects no gate could see, plus one nit. Two fix Steps were appended to the Tasks table.
- Everything the five Steps were asked to build does work end to end: upload, preview, refusals in
  both locales, the paperclip badge, and a delete confirmation naming the file.

## Next concrete action
- **2.2-review-fix-1** — `UploadDropzone`'s `aria-live` announcement is formatted at event time and
  never re-renders, so it leaks Polish into the English UI and tells a screen-reader user that a
  rejected upload reached 100%. Derive it from state at render time; make a terminal failure
  announce the failure.
- Then **2.2-review-fix-2** — a completed upload stays in the dropzone queue while also appearing as
  a real attachment row, so every file shows twice and the queue goes stale after a delete.

## Blockers / open questions
- none. The defects are understood and scoped into the two fix Steps.

## Scope decisions taken so far (all recorded in NOTIFY.md)
- Reservation fields moved from Step 1.8 to Step 3.1, so they ship with the columns they need and
  assumption A1 holds (Phase 3 rolls back alone).
- A day with both items and attachments answers the older `days_have_items`, not the new code.
- Tasks-table SHAs are reconciled to their real post-amend values at every checkpoint.
- Step 2.4 produced an extra docs-only commit against the one-commit rule; not force-fixed, because
  it changes no code and bisect-by-Step is unaffected.

## Environment caveats
- Dev runtime runnable: yes. PostgreSQL on `localhost:55432`; every backend gate run reports
  **0 skips**, which is the part to keep checking — this suite skips the database layer silently.
- QA environment: `sh .ai/scripts/test-env-up.sh` brings up the production app factory serving the
  built SPA from one origin. Descriptor at `.ai/qa/test-env.json`; it was left **running**.
- Browser: `agent-browser` v0.34.0, not on `PATH` — use the cached binary. **Chrome will not launch
  unless `TMPDIR` is overridden to `/tmp`**: this worktree path is too long for Chromium's singleton
  socket. Step 3.7 will hit the same thing.
- Frontend deps installed here via `npm ci`.
- Database/migration state: clean. Head `0005_attachment`; Phase 3 adds `0006_item_reservation`.

## Worktree
- Path: /home/mkl/cezar/projects/trip_planner/.ai/cezar/worktrees/2223e7fe-07b0-43b2-962a-a6d3db36f6f0
- Created this run: no — the invoking linked worktree, reused per the worktree contract.
