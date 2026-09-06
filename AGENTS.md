# AGENTS.md

Instructions for coding agents working in this repository. Every `om-*` skill reads this file before doing any work.

## Project overview

**trip_planner** is an intelligent trip planner: a web application that helps a traveller go from a rough intention ("a week somewhere warm in May, two people, moderate budget") to a concrete, bookable day-by-day itinerary. It is a Python backend serving a React single-page frontend, and it is **multilingual from day one — Polish and English are both first-class**, not an afterthought bolted on later.

> **Status: walking skeleton complete.** All four phases of `.ai/specs/2026-09-05-walking-skeleton.md` have landed: the validation gate is green, owner authentication is in place, and a trip can be created with multiple stages, filled in day by day with items carrying the three statuses, read through the readiness counter, and filtered to what is outstanding. What is deliberately **not** built — chat and the AI assistant, sharing, attachments and reservation documents, cost data — was cut from this milestone by assumption A05, not abandoned; the specs for the last two are in flight. Rows still marked **TODO** must be filled in by the first agent or human that establishes the convention — do not invent a rule to fill a gap; record what you actually built.

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python, managed by [`uv`](https://docs.astral.sh/uv/) | `backend/pyproject.toml` is the single source of dependency truth; `uv.lock` is committed. Never call `pip` directly. |
| Frontend | React, managed by `npm` | `frontend/package.json`; `package-lock.json` is committed. Not pnpm, not yarn, not bun. |
| Lint/format (Python) | `ruff` | Both linting and formatting; no separate black/isort. |
| Tests (Python) | `pytest` | Under `backend/tests/`. |
| Tests (frontend) | Vitest | Colocated `*.test.ts(x)` or under `frontend/src/**/__tests__/`. |
| i18n | `react-i18next` + `i18next` + `i18next-icu` | ICU message formatting, so a counted noun is one key whose value carries every plural category. i18next's default suffix pluralisation would put four keys in `pl.json` against English's two and fail `scripts/check_locales.py`. Locale files live where that gate looks (see **Multilingual** below). |
| Specs & docs | English | Product-facing UI strings are translated; specs, code, comments, commit messages, and PR bodies are English. |

## Repository layout

```
backend/                 Python service (uv project; pyproject.toml + uv.lock)
  trip_planner/
    api/                 FastAPI routers, request/response models
    domain/              Pure business rules — no database, no HTTP
    db/                  SQLAlchemy models and session handling
    security/            Passwords, sessions, CSRF, rate limiting
  migrations/            Alembic revisions, one per phase
  tests/                 pytest suite
frontend/                React SPA (npm; package.json + package-lock.json)
  src/locales/           en.json / pl.json (or en/ and pl/ namespace dirs)
scripts/                 Repo-level tooling run by the validation gate
  check_locales.py       Locale parity gate — no deps, plain python3
  check_css_tokens.py    CSS token completeness gate — no deps, plain python3
  check_contrast.py      WCAG contrast gate over tokens.css — no deps, plain python3
.ai/                     Agent pipeline configuration (see below)
  agentic.config.json    The config every om-* skill reads
  specs/                 Feature specifications (English)
  trackers/github.md     How tracker operations execute
  browsers/agent-browser.md  How browser automation executes
  runs/  analysis/  qa/  Generated run artifacts
SDLC.md                  How work flows from ticket to merged PR
CODE_REVIEW.md           Review rules, auto-applied by om-code-review
BACKWARD_COMPATIBILITY.md  Protected contract surfaces
```

## Task-routing table

| When the task involves… | Read first | Key rules |
|---|---|---|
| Backend API endpoints, business logic | `backend/pyproject.toml`, `backend/` source tree | Dependencies go through `uv add`, never a hand-edited `pyproject.toml` or `pip install`. Every request body and query parameter is validated at the boundary by **Pydantic v2** models, which reject unknown fields. Every new endpoint is a contract surface: check `BACKWARD_COMPATIBILITY.md`. |
| Backend tests | `backend/tests/` | Every bug fix ships a regression test that fails before the fix. Run with `(cd backend && uv run pytest)`. |
| React components, screens, routing | `frontend/src/`, `frontend/package.json` | No user-visible string is hardcoded — every one goes through the i18n layer with a key present in **both** `en` and `pl`. TypeScript strict mode; `npm run typecheck` must pass. |
| Frontend tests | `frontend/src/**` colocated tests | Run with `(cd frontend && npm run test -- --run)`. |
| Translations / i18n / any user-visible copy | `frontend/src/locales/`, `scripts/check_locales.py` | See **Multilingual** below. Adding an English key without its Polish counterpart fails the validation gate. |
| Dependencies | `backend/pyproject.toml` + `uv.lock`, `frontend/package.json` + `package-lock.json` | Both lockfiles are committed and must be updated in the same commit as the manifest. Label the PR `dependencies`. |
| Trip-planning domain logic (itineraries, routing, scheduling, recommendations) | `backend/trip_planner/domain/`, then `.ai/specs/` | This is the product's core. The rules that are not CRUD live in `domain/` as pure functions with their own unit tests — day generation (`days.py`), the day-to-stage derivation (`stages.py`), item span validation and ordering (`items.py`), and the readiness arithmetic (`readiness.py`). Put a new rule there rather than in a request handler, so it is testable without a database. Behavior changes need a spec before code — see `SDLC.md`, Definition of Ready. |
| External APIs (maps, places, weather, booking, LLM providers) | TODO — integration module not yet created | Never commit API keys. Credentials come from environment variables; document each new one in the README and in `.ai/qa/test-env.env` (gitignored) for QA. Every external call needs a timeout and a defined failure mode — a dead third party must not take down a page. |
| CI | `.github/workflows/validation-gate.yml` | Runs the same eight commands as the validation gate below, in the same order. When the gate changes, change the workflow in the same PR. |
| The agent pipeline itself (labels, review flow, QA gate) | `SDLC.md`, `.ai/agentic.config.json` | Change the config and `SDLC.md` together. Per-skill repo overrides go in `.ai/skills/<skill-name>/SKILL.md`. |

## Multilingual (PL + EN)

This is a product requirement, and it is enforced by the validation gate rather than by review vigilance.

- **English is the reference locale.** Polish must have a non-empty value for every English key, and no keys English does not define.
- Locale files live in `frontend/src/locales/` as either `en.json` + `pl.json`, or `en/` + `pl/` directories of namespaced JSON. Backend-originated user-facing strings (emails, error messages surfaced to users) go in `backend/trip_planner/locales/` with the same structure.
- `scripts/check_locales.py` is the gate. It runs first in the validation sequence, has no dependencies, and passes vacuously while no locale directory exists yet. When you add a new locale root or a third language, edit `LOCALE_ROOTS` / `REQUIRED_LOCALES` at the top of that file.
- User-facing text also includes: dates, times, numbers, currencies, and distances. Format them through the locale, never with hand-rolled string concatenation.

## Validation gate

Run these in order before opening or updating a PR. Any non-zero exit blocks the PR.

- `python3 scripts/check_locales.py`
- `python3 scripts/check_css_tokens.py`
- `python3 scripts/check_contrast.py`
- `(cd backend && uv run ruff check .)`
- `(cd backend && uv run pytest)`
- `(cd frontend && npm run typecheck)`
- `(cd frontend && npm run test -- --run)`
- `(cd frontend && npm run build)`

The authoritative list is `validation.commands` in `.ai/agentic.config.json`. When it changes, update it there, in `SDLC.md`, and here — together.

All eight commands are expected to pass. `(cd backend && uv run pytest)` needs a reachable PostgreSQL server — start one with `docker compose -f deploy/compose.dev.yml up -d db`, or point `TEST_DATABASE_URL` at your own. Without a server those tests **skip** rather than fail, so read the summary: a run reporting skips has not verified the database layer.

## Pointers

- `SDLC.md` — the ticket lifecycle, label state machine, QA gate, and claim protocol.
- `CODE_REVIEW.md` — the review rules `om-code-review` applies automatically.
- `BACKWARD_COMPATIBILITY.md` — what counts as a protected contract surface and how to change one.
- `.ai/agentic.config.json` — the machine-readable pipeline configuration.
- `.ai/trackers/github.md` — how every tracker operation executes; edit to override.
- `.ai/browsers/agent-browser.md` — how browser automation executes for QA and E2E.
