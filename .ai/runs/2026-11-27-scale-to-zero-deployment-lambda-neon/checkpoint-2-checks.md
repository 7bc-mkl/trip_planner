# Checkpoint 2 — steps 1.6..1.10 (+ 1.7-review-fix)

- Steps: 1.6, 1.7, 1.8, 1.9, 1.10, 1.7-review-fix (commits a8d71c7..8e1a29a)
- Touched areas: `db/session.py`, `security/rate_limit.py`, `api/auth.py`, `config.py`, `deploy/entrypoint.sh`, attachments (domain, API, frontend pre-check), locales, product brief (D26)
- Recorded: 2026-11-27T20:46:04Z

| Check | Result |
|---|---|
| `python3 scripts/check_locales.py` | pass |
| `(cd backend && uv run ruff check .)` | pass |
| `uv run pytest` on test_db_session, test_rate_limit, test_config, test_auth, test_startup, test_attachments_api, test_domain_uploads, test_models_attachment, test_domain_inbound, test_upload_concurrency, test_quota, test_security, test_spa | pass — 403 passed, 0 skipped; test_startup re-run after the fix: 33 passed |
| `(cd frontend && npm run typecheck)` | pass |
| `(cd frontend && npm run test -- --run)` | pass — 478 tests |
| Step review, diff f1443dd..b62651d | **1 major, fixed:** `entrypoint.sh` dropped `--proxy-headers --forwarded-allow-ips '*'` for `CLIENT_IP_SOURCE=cloudfront`, but uvicorn enables proxy headers by default and trusts 127.0.0.1 — where LWA connects from — so `request.client` stayed spoofable. Fixed in 1.7-review-fix (`--no-proxy-headers`, with a test pinning uvicorn's default). Nit, deferred: two comments in `api/attachments.py` still quote a "10 MB body" memory measurement |
| UI verification | skipped — the only UI change is the pre-check constant and two strings, covered by Vitest; browser evidence comes from `om-auto-qa-pr` after the final gate |
