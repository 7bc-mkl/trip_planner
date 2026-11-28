# Checkpoint 4 — steps 2.1..2.4, 2.7..2.9

- Steps: 2.1, 2.2, 2.3, 2.4, 2.7, 2.8, 2.9 (commits c69f9f9..fbe790b). 2.5–2.6 are waiting on Neon credentials (see HANDOFF)
- Touched areas: `deploy/lambda/` (cert.yaml, template.yaml, deploy.sh, README.md), `backend/tests/test_lambda_templates.py`, READMEs, `.ai/specs/capabilities/`, run folder
- Recorded: 2026-11-27T21:17:08Z

| Check | Result |
|---|---|
| `sam validate --lint` on template.yaml (SAM CLI 1.174.1) | pass |
| `cfn-lint` on cert.yaml | pass |
| `shellcheck deploy/lambda/deploy.sh` | pass |
| `(cd backend && uv run ruff check .)` | pass |
| `uv run pytest tests/test_lambda_templates.py tests/test_startup.py` | pass — 56 |
| Step review, diff 70408c8^..fbe790b (my own Phase 2 diff) | no blocker/major. Checked: Function URL domain extraction, conditional inbox env on both functions, roles referenced by `InboxObjectAccess`, worker readiness on 127.0.0.1, no secret on any command line in `deploy.sh` |
| Live: certificate stack `trip-planner-cert` (us-east-1) | CREATE_COMPLETE at checkpoint time |
| Live: SSM `/trip-planner/session-secret`, `/trip-planner/origin-verify-secret` | created (generated, SecureString, never printed) |
| UI verification | skipped — no UI in this window |
