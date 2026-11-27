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
