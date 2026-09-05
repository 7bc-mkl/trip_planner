# Execution plan — Walking skeleton, Phases 0 and 1

- Date: 2026-09-05 · Engine: `om-auto-create-pr` · Slug: `walking-skeleton-phase-0-1`
- Branch: `feat/walking-skeleton-phase-0-1` · Base: `main`
- Source doc: `.ai/specs/2026-09-05-walking-skeleton.md` (in flight on spec PR #1, `spec/walking-skeleton`)

`Engine: om-auto-create-pr (steps: 15, --loop: no)`

## 🎯 Goal

Ship the first two phases of the walking skeleton: a repository that builds, lints
and tests itself in both locales (Phase 0), and an owner-authenticated FastAPI +
React application with nothing showing a plan reachable without a session, packaged
as a single deployable container image (Phase 1).

## 📋 Scope

In scope — exactly Phase 0 steps 1-6 and Phase 1 steps 1-9 of the spec's
Implementation Plan, no more:

- `backend/` as a `uv` project (FastAPI, SQLAlchemy 2.0, Alembic, pytest, ruff).
- `frontend/` as a Vite + React + TypeScript SPA with Vitest and react-i18next + ICU.
- Real `en.json` / `pl.json` carrying every string this milestone renders, with the
  stage-count ICU plural as the proving key.
- `owner`, `session` and `login_attempt` tables; Argon2id hashing; opaque server-side
  sessions; CSRF double-submit; database-backed login rate limiting with a fixed
  response floor.
- The `ErrorCode` enum and its generated TypeScript union, with the test that every
  member resolves to a non-empty key in both locales.
- The auth-by-default route dependency and the route-enumeration test that keeps R08
  true as routes are added.
- The `create-owner` management command.
- The `/login` screen, session context, route guard, redirect-with-return-path and
  the module-scoped draft store.
- `deploy/Dockerfile`, the compose file, the fatal missing-env-var startup check, and
  the `alembic upgrade head` release step.
- The GitHub Actions workflow running the six validation-gate commands in config order.

## 🚫 Non-goals

- **Phases 2, 3 and 4 of the spec** — trips, stages, days, items, statuses, the
  readiness counter, the filter and the trip-management tail. They ship on a later PR.
  No `trip`, `trip_stage`, `trip_day` or `item` table is created here.
- Re-opening spec assumptions **A2** (the multi-stop shape) or **A4** (the item time
  span). The owner confirmed both on 2026-09-05; the data model is settled and this run
  raises no confirmation guard on them.
- Chat, sharing, attachments and cost data — cut from this milestone under A05, still
  in scope for the first version.
- **Provisioning a deployment host.** Phase 1 step 9 builds every deployment artifact,
  but the actual deploy is gated on the owner authorizing a host (see Risks).

## 📋 Implementation Plan

### Phase 0 — Foundation and a green gate

1. `backend/` as a `uv` project: `pyproject.toml`, `uv.lock`, ruff config, pytest with a
   smoke test, FastAPI app exposing `GET /api/v1/health`.
2. `frontend/` as Vite + React + TypeScript strict, Vitest, one smoke test.
3. react-i18next + i18next-icu; real `en.json` / `pl.json`; provider, `<html lang>`
   binding, locale switch; the stage-count ICU plural proving key with a test asserting
   the Polish `few` (2 etapy) and `many` (5 etapów) forms render.
4. PostgreSQL + SQLAlchemy 2.0 + Alembic with an empty baseline revision, and a pytest
   fixture that migrates a throwaway database per session.
5. Replace the resolved TODOs in `AGENTS.md` and `BACKWARD_COMPATIBILITY.md`, with a
   test asserting the exact TODO strings are absent.
6. The GitHub Actions workflow running the six gate commands in `.ai/agentic.config.json`
   order.

### Phase 1 — Owner authentication and deployment

1. Migration and models for `owner`, `session`, `login_attempt`, including the
   `lower(email)` unique index.
2. `security/`: Argon2id hash/verify, opaque 256-bit tokens, constant-time comparison.
3. `errors.py` with the `ErrorCode` enum and its generated TypeScript union, plus the
   both-locales resolution test.
4. `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/me` with cookie
   and CSRF handling.
5. Database-backed login rate limiting plus the fixed response floor, tested through an
   injected clock.
6. `get_current_session` applied by default to every non-auth route, `get_owned_trip` for
   trip-scoped routes, and the route-enumeration test.
7. `trip-planner create-owner` reading the password from stdin.
8. The `/login` screen, session context, route guard, redirect-with-return-path and the
   module-scoped draft store.
9. `deploy/Dockerfile`, the compose file, the fatal missing-env-var startup check and the
   `alembic upgrade head` release step — **artifacts only**; the deployment itself is
   gated on host authorization.

## ⚠️ Risks

- **The deployment sub-step is the run's one open item.** A05's test is "deployed", and
  the spec is explicit that a plan ending at a passing test suite has not met it. This run
  builds every deployment artifact but does not provision a host: standing up a public
  service and a billed Postgres requires the owner to name an account. Recon found the
  local `gcloud` authenticated against project `cosmic-bonfire-318907` (Cloud Run,
  Artifact Registry, Cloud Build and Cloud SQL Admin all enabled, no existing Cloud Run
  services), but that project hosts an unrelated product, so it is offered as a candidate
  rather than assumed. **A local run is not a substitute** and none is recorded as one.
- **`get_owned_trip` has no trip-scoped routes to guard yet**, because trips arrive in
  Phase 2. It ships here with its enumeration test written so that the assertion becomes
  load-bearing the moment the first `/trips/…` route appears, rather than being added
  after the routes it is meant to protect.
- **The locale gate can pass vacuously.** `check_locales.py` returns 0 when no locale root
  exists. Phase 0 step 3 therefore ships real content in both files, and the ICU plural
  proving key exists specifically because Polish's four CLDR plural categories are what
  would break key parity under i18next's default suffix pluralisation.
- **Postgres is required for the test suite.** The Alembic round-trip and the rate-limiter
  tests need a real server; a SQLite fallback would not exercise the deferrable constraint,
  the functional index or `INET`. CI provisions a Postgres service container.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 0: Foundation and a green gate

- [x] 0.1 Scaffold backend as a uv project with ruff, pytest and GET /api/v1/health — cd7b4ca
- [x] 0.2 Scaffold frontend as Vite + React + TypeScript strict with Vitest — 0c4b71a
- [x] 0.3 Add react-i18next + i18next-icu, real en/pl locales and the ICU plural proving key — 7e061a9
- [x] 0.4 Add SQLAlchemy 2.0 + Alembic empty baseline and the throwaway-database fixture — 3e02e4c
- [x] 0.5 Replace the resolved TODOs in AGENTS.md and BACKWARD_COMPATIBILITY.md — 7256ac8
- [x] 0.6 Add the GitHub Actions workflow running the six gate commands in config order — 4d72c34

### Phase 1: Owner authentication and deployment

- [ ] 1.1 Migration and models for owner, session and login_attempt
- [ ] 1.2 security/: Argon2id hashing, opaque tokens, constant-time comparison
- [ ] 1.3 errors.py ErrorCode enum, generated TypeScript union, both-locales test
- [ ] 1.4 Auth endpoints with cookie and CSRF handling
- [ ] 1.5 Database-backed login rate limiting and the fixed response floor
- [ ] 1.6 Auth-by-default route dependency, get_owned_trip, route-enumeration test
- [ ] 1.7 create-owner command reading the password from stdin
- [ ] 1.8 /login screen, session context, route guard and the draft store
- [ ] 1.9 Deployment artifacts: Dockerfile, compose, fatal env check, release step
- [ ] 1.9d Deployment itself — a real TLS URL where /api/v1/trips answers 401 and /login answers 200 (BLOCKED: awaiting owner authorization of a host)
