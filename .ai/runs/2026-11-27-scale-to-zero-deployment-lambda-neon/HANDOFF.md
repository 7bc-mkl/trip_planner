# Handoff — 2026-11-27-scale-to-zero-deployment-lambda-neon

**Last updated:** 2026-11-28T06:54:38Z
**Branch:** feat/scale-to-zero-deployment-lambda-neon
**PR:** https://github.com/7bc-mkl/trip_planner/pull/26 (ready for review; merge-queue + needs-qa)
**Current phase/step:** complete — every Tasks row done
**Last commit:** final-gate records on top of b35e83f (last code commit)

## What just happened
- Phases 0–2 implemented, reviewed (1 major + 2 minor + 3 nits fixed), and deployed: `https://trips.botito.app` runs on Lambda + Neon (stack `trip-planner`, eu-central-1; Neon project `broad-darkness-02702202`).
- Final gate green (1355 backend, 0 skipped); live probes 16/16; cold start 4.7 s page / 3.3 s first sign-in incl. Neon wake.

## Next concrete action
- Owner: manual QA per the PR's QA instructions, then merge.
- Then spec Phase 3 cutover (`deploy/lambda/README.md`, "Cutover from Hetzner") — needs the owner's go-ahead; it replaces the probe account with the real data.

## Blockers / open questions
- none for this PR. Phase 3/4 are owner-gated follow-ups.

## Environment caveats
- Live: Lambda target deployed at b35e83f; probe owner `probe@trips.botito.app` (password in SSM `/trip-planner/probe-owner-password`), plus two probe trips — replaced by the cutover's `pg_restore --clean`.
- Database/migration state: Neon at head (0009).

## Worktree
- Path: /home/mkl/cezar/projects/trip_planner/.ai/cezar/worktrees/0b6188a3-13d8-421b-b0b8-b3a9a7bfaf05
- Created this run: no
