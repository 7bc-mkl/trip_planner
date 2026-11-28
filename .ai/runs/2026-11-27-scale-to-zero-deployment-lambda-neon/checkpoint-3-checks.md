# Checkpoint 3 — steps 1.11..1.13 (Phase 1 close, spec step 14)

- Steps: 1.11, 1.12, 1.13 (commits 42f9b93..a56aa48)
- Touched areas: `security/headers.py`, `security/origin.py`, `spa.py`, `app.py`, `config.py`, `errors.py` (+ `forbidden_origin`), `rate_limit.py`, `deploy/Dockerfile`, `deploy/entrypoint.sh`, locales, `frontend/src/api/errorCodes.ts`
- Recorded: 2026-11-27T21:08:13Z

Full validation gate (`validation.commands`, in order) — this is spec Phase 1 step 14:

| Command | Result |
|---|---|
| `python3 scripts/check_locales.py` | pass |
| `python3 scripts/check_css_tokens.py` | pass |
| `python3 scripts/check_contrast.py` | pass — 16 pairs |
| `(cd backend && uv run ruff check .)` | pass |
| `(cd backend && uv run pytest)` | pass — 1328 passed, **0 skipped** (live Postgres) |
| `(cd frontend && npm run typecheck)` | pass |
| `(cd frontend && npm run test -- --run)` | pass |
| `(cd frontend && npm run build)` | pass |
| `docker build -f deploy/Dockerfile .` (executor, step 1.13) | pass — `/opt/extensions/lambda-adapter` present, root-owned, executable |

| Review | Result |
|---|---|
| Step review, diff 8e1a29a..a56aa48 | no blocker/major. Middleware order verified: origin lock inside the security headers, so a 403 carries them; viewer address read only on origin-verified scopes; constant-time compare; single-header requirement |
| UI verification | skipped — the only UI-visible addition is the `forbidden_origin` message, which a browser reaches only by bypassing CloudFront; covered by locale parity |
