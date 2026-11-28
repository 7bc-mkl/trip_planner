# Final gate — every Tasks row done

- Recorded: 2026-11-28T06:53:41Z
- Head: b35e83f (code); later commits are run-folder records only

## Full validation gate (`validation.commands`, in order), on b35e83f

| Command | Result |
|---|---|
| `python3 scripts/check_locales.py` | pass |
| `python3 scripts/check_css_tokens.py` | pass |
| `python3 scripts/check_contrast.py` | pass |
| `(cd backend && uv run ruff check .)` | pass |
| `(cd backend && uv run pytest)` | pass — 1355 passed, **0 skipped** (live Postgres) |
| `(cd frontend && npm run typecheck)` | pass |
| `(cd frontend && npm run test -- --run)` | pass |
| `(cd frontend && npm run build)` | pass |

The same gate passed on 728ef21 before the review fixes (1350 passed, 0 skipped).

## Integration suite

The repository's integration coverage for this change is the live probe set against the deployed target, run twice (16/16 each, with the inbox, client-IP and 10 MiB checks on top). See `deployment-record.md`. No separate browser E2E suite exists in this repo.

## UI evidence (live site, agent-browser 0.34.0)

| Screenshot | Shows |
|---|---|
| `final-gate-artifacts/screenshot-live-login-pl.png` | `https://trips.botito.app/login`, Polish |
| `final-gate-artifacts/screenshot-live-trips-pl.png` | trips list after sign-in, served from Lambda + Neon |
| `final-gate-artifacts/screenshot-live-day-detail-pl.png` | a 4 MB upload and a pre-change 10 MB attachment side by side; hint "PDF, JPEG lub PNG, do 4 MB" |
| `final-gate-artifacts/screenshot-live-over-limit-refused-en.png` | a 4 MiB + 1 byte file refused before sending: "That file is larger than the 4 MB limit for a single attachment." |
| `final-gate-artifacts/screenshot-live-inbox-en.png` | `/inbox` with the confirmation delivered through SES, and the held-back message |

## Design-system / style pass

No new UI surface: the only frontend change is a constant and two strings. The CSS token and contrast gates above pass.
