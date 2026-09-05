# AGENTS.md

Instructions for coding agents working in this repository. Every `om-*` skill reads this file before doing any work.

## Project overview

**trip_planner** is an intelligent trip planner: a web application that helps a traveller go from a rough intention ("a week somewhere warm in May, two people, moderate budget") to a concrete, bookable day-by-day itinerary. It is a Python backend serving a React single-page frontend, and it is **multilingual from day one — Polish and English are both first-class**, not an afterthought bolted on later.

> **Status: greenfield.** At the time this file was generated the repository contained no source code. The layout, commands, and conventions below are the agreed target shape, not observations of existing code. Rows marked **TODO** must be filled in by the first agent or human that establishes the convention — do not invent a rule to fill a gap; record what you actually built.

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python, managed by [`uv`](https://docs.astral.sh/uv/) | `backend/pyproject.toml` is the single source of dependency truth; `uv.lock` is committed. Never call `pip` directly. |
| Frontend | React, managed by `npm` | `frontend/package.json`; `package-lock.json` is committed. Not pnpm, not yarn, not bun. |
| Lint/format (Python) | `ruff` | Both linting and formatting; no separate black/isort. |
| Tests (Python) | `pytest` | Under `backend/tests/`. |
| Tests (frontend) | Vitest | Colocated `*.test.ts(x)` or under `frontend/src/**/__tests__/`. |
| i18n | TODO — library not yet chosen | Locale files must live where `scripts/check_locales.py` looks (see **Multilingual** below). |
| Specs & docs | English | Product-facing UI strings are translated; specs, code, comments, commit messages, and PR bodies are English. |

## Repository layout

```
backend/                 Python service (uv project; pyproject.toml + uv.lock)
  tests/                 pytest suite
frontend/                React SPA (npm; package.json + package-lock.json)
  src/locales/           en.json / pl.json (or en/ and pl/ namespace dirs)
scripts/                 Repo-level tooling run by the validation gate
  check_locales.py       Locale parity gate — no deps, plain python3
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
| Backend API endpoints, business logic | `backend/pyproject.toml`, `backend/` source tree | Dependencies go through `uv add`, never a hand-edited `pyproject.toml` or `pip install`. Every request body and query parameter is validated at the boundary — TODO: name the validation library once chosen. Every new endpoint is a contract surface: check `BACKWARD_COMPATIBILITY.md`. |
| Backend tests | `backend/tests/` | Every bug fix ships a regression test that fails before the fix. Run with `(cd backend && uv run pytest)`. |
| React components, screens, routing | `frontend/src/`, `frontend/package.json` | No user-visible string is hardcoded — every one goes through the i18n layer with a key present in **both** `en` and `pl`. TypeScript strict mode; `npm run typecheck` must pass. |
| Frontend tests | `frontend/src/**` colocated tests | Run with `(cd frontend && npm run test -- --run)`. |
| Translations / i18n / any user-visible copy | `frontend/src/locales/`, `scripts/check_locales.py` | See **Multilingual** below. Adding an English key without its Polish counterpart fails the validation gate. |
| Dependencies | `backend/pyproject.toml` + `uv.lock`, `frontend/package.json` + `package-lock.json` | Both lockfiles are committed and must be updated in the same commit as the manifest. Label the PR `dependencies`. |
| Trip-planning domain logic (itineraries, routing, scheduling, recommendations) | `.ai/specs/` | This is the product's core. Behavior changes need a spec before code — see `SDLC.md`, Definition of Ready. TODO: point at the domain module once it exists. |
| External APIs (maps, places, weather, booking, LLM providers) | TODO — integration module not yet created | Never commit API keys. Credentials come from environment variables; document each new one in the README and in `.ai/qa/test-env.env` (gitignored) for QA. Every external call needs a timeout and a defined failure mode — a dead third party must not take down a page. |
| CI | `.github/workflows/` | TODO — no workflows yet. When added, they must run the same commands as the validation gate below, in the same order. |
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
- `(cd backend && uv run ruff check .)`
- `(cd backend && uv run pytest)`
- `(cd frontend && npm run typecheck)`
- `(cd frontend && npm run test -- --run)`
- `(cd frontend && npm run build)`

The authoritative list is `validation.commands` in `.ai/agentic.config.json`. When it changes, update it there, in `SDLC.md`, and here — together.

Until the backend and frontend are scaffolded, most of these commands will fail because the directories do not exist. That is expected: the first scaffolding PR's job is to make the whole gate green.

## Pointers

- `SDLC.md` — the ticket lifecycle, label state machine, QA gate, and claim protocol.
- `CODE_REVIEW.md` — the review rules `om-code-review` applies automatically.
- `BACKWARD_COMPATIBILITY.md` — what counts as a protected contract surface and how to change one.
- `.ai/agentic.config.json` — the machine-readable pipeline configuration.
- `.ai/trackers/github.md` — how every tracker operation executes; edit to override.
- `.ai/browsers/agent-browser.md` — how browser automation executes for QA and E2E.
