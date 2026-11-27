# Handoff — 2026-11-27-scale-to-zero-deployment-lambda-neon

**Last updated:** 2026-11-27T21:17:08Z
**Branch:** feat/scale-to-zero-deployment-lambda-neon
**PR:** https://github.com/7bc-mkl/trip_planner/pull/26 (draft)
**Current phase/step:** Phase 2 Step 2.5 (blocked on Neon credentials)
**Last commit:** fbe790b — docs(runs): record where the implementation corrects the spec's unverified assumptions

## What just happened
- Phase 2 IaC + docs landed: cert.yaml, template.yaml (+ inbox), deploy.sh, deploy/lambda/README.md, capability specs, spec corrections.
- Live: certificate stack trip-planner-cert created in us-east-1; SSM session-secret and origin-verify-secret generated.

## Next concrete action
- Step 2.5: once /trip-planner/database-url-pooled and /trip-planner/database-url-direct exist in SSM (eu-central-1), run `AWS_PROFILE=mkl ./deploy/lambda/deploy.sh`, then create the owner; then Step 2.6 probes.

## Blockers / open questions
- Neon project + connection strings: no Neon credentials on this machine. Owner to create the project (aws-eu-central-1) and store both URLs in SSM, or provide a Neon API key.

## Environment caveats
- Dev runtime runnable: yes (Postgres on localhost:55432)
- Browser / UI checks: none needed yet
- Database/migration state: clean

## Worktree
- Path: /home/mkl/cezar/projects/trip_planner/.ai/cezar/worktrees/0b6188a3-13d8-421b-b0b8-b3a9a7bfaf05
- Created this run: no
