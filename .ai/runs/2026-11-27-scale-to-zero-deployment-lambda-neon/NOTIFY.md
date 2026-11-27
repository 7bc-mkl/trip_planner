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
