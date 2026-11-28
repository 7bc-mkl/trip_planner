# Notify — 2026-11-27-scale-to-zero-deployment-lambda-neon

> Append-only log. Every entry is UTC-timestamped. Never rewrite prior entries.

## 2026-11-27T21:00:00Z — run started
- Brief: implement `.ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md` Phases 0–2 for issue #24.
- External skill URLs: none
- Decision: Phases 3–4 (cutover, decommission) are out of this PR — the spec gates cutover on Phases 1–2 being merged.
- Decision: PR claim uses the comment-election fallback; `.ai/trackers/github.md` has no `acquire-lock` operation.
- Delegation: Phase 0 step 1 documentation research delegated to one research subagent (read-only).

## 2026-11-27T20:32:57Z — checkpoint 1 (steps 0.1..1.5)
- Targeted validation green (159 tests, ruff). Step review: no blocker/major; one nit deferred (routing batch per pass).
- Decision: region eu-central-1 (Neon has no eu-west-1; SES receiving exists in eu-central-1). Production has no inbox, so cutover cannot lose mail.
- Delegations: steps 1.1, 1.2, 1.4 → standard-tier executors; 1.3, 1.5 → capable-tier executors.

## 2026-11-27T20:46:04Z — checkpoint 2 (steps 1.6..1.10)
- Targeted validation green (403 backend, 478 frontend, locales, ruff).
- Step review: 1 major (uvicorn proxy headers default-on, trusting 127.0.0.1) fixed as 1.7-review-fix (8e1a29a); 1 nit deferred (stale "10 MB body" comments in api/attachments.py).
- Delegations: 1.6, 1.8, 1.10 → standard-tier executors; 1.7, 1.9 → capable-tier executors.

## 2026-11-27T21:08:13Z — checkpoint 3 (steps 1.11..1.13, Phase 1 closed)
- Full validation gate green: 8/8 commands, 1328 backend tests with 0 skipped; image builds with the adapter.
- Step review clean. New error code `forbidden_origin` (additive).
- Delegations: 1.11, 1.13 → standard-tier executors; 1.12 → capable-tier executor.

## 2026-11-27T21:17:08Z — checkpoint 4 (steps 2.1..2.4, 2.7..2.9)
- SAM validate --lint, cfn-lint, shellcheck, 56 targeted tests green. Self-review clean.
- Decision: secrets reach Lambda as NoEcho parameters read from SSM by deploy.sh (CloudFormation cannot resolve ssm-secure into Lambda env).
- Decision: step 2.9 records spec corrections in the run folder + PR body instead of editing the merged spec (delta-archive rule).
- Live AWS: trip-planner-cert stack (us-east-1) created; two generated secrets put into SSM.
- **Blocker:** step 2.5 needs Neon credentials (no Neon account access here). Steps 2.7–2.9 were done ahead of 2.5–2.6 so the blocker costs no idle time.

## 2026-11-28T06:10:00Z — blocker cleared
- Owner supplied a Neon API key; `neon init` / `neon deploy` linked project broad-darkness-02702202 (aws-eu-central-1, Postgres 18). URLs stored in SSM.
- First real deploy surfaced three `deploy.sh` defects (Docker 20.10 `--provenance`, empty SAM overrides, `--image-repository`), each fixed as a review-fix Step.

## 2026-11-28T06:54:38Z — run complete
- Final gate green on b35e83f (8/8, 1355 backend, 0 skipped); live probes 16/16 twice; cold start recorded.
- Review: independent reviewer found 1 major (drain spun on no-progress passes), 2 minor, 3 nits — all fixed (dee968e, b35e83f); re-review approved.
- Decision: Phase 3 cutover left for the owner's go-ahead after merge.
- PR: https://github.com/7bc-mkl/trip_planner/pull/26
