# Smart Trip Planner

A web application that turns a rough travel intention into a concrete, day-by-day
itinerary — and, above all, answers the one question a plan in your head, your mailbox
and "a bit in Excel" cannot: **what is still not arranged?**

That answer is the readiness counter, and it is the main object of the product rather
than a badge in a corner. The app is **multilingual from day one** — Polish and English
are both first-class, enforced by the validation gate, not by review vigilance.

- Product brief: `.ai/specs/product-brief.md`
- Current milestone spec: `.ai/specs/2026-09-05-walking-skeleton.md`
- Conventions for humans and agents: [`AGENTS.md`](AGENTS.md), [`SDLC.md`](SDLC.md)

## Status — walking skeleton complete

All four phases of the walking-skeleton spec have landed. What works today:

| Capability | Where |
|---|---|
| Owner sign-in with e-mail and password; no plan screen is reachable without a session | `/login` |
| Trip list, and creating a trip with a title, a date range, a departure point, an optional return point and one or more stages | `/trips`, `/trips/new` |
| A timeline of days generated from the trip's date range, each day derived to its stage | `/trips/:tripId` |
| Items on a day — kind (`accommodation`, `transport`, `activity`, `meal`, `other`), an optional time span that may cross midnight, a title and free-text notes | `/trips/:tripId/days/:date` |
| Exactly three statuses: `to_plan`, `to_book`, `done` | every item |
| The readiness counter, and a filter down to what is still outstanding | the timeline |
| Polish and English UI, switchable at runtime, with ICU plural formatting | the locale switch |

What is **not** built yet — chat and the AI assistant, the read-only sharing link,
file and image attachments, cost and reservation data — was **cut from this milestone
by assumption A05, not abandoned**. Those capabilities remain in scope for the first
version and are covered by later specs. See the spec's "Out of scope — and the honest
authority for each cut" table before assuming anything there is a product decision.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python ≥3.11, FastAPI, SQLAlchemy 2.0, Alembic, managed by [`uv`](https://docs.astral.sh/uv/) |
| Database | PostgreSQL 16 (the schema uses a functional unique index, a `DEFERRABLE` unique constraint and an `INET` column — SQLite cannot express them) |
| Frontend | React 19 + TypeScript (strict) + Vite, managed by `npm` |
| i18n | `react-i18next` + `i18next-icu` |
| Auth | Opaque server-side session in an `HttpOnly` cookie, plus a CSRF token; Argon2 password hashing |
| Deployment | One container image serving both the API and the built SPA from a single origin |

Never call `pip` directly, and do not swap `npm` for pnpm/yarn/bun — both lockfiles are
committed and are the source of dependency truth.

## Repository layout

```
backend/                 Python service (uv project)
  trip_planner/
    api/                 FastAPI routers, Pydantic request/response models
    domain/              Pure business rules — no database, no HTTP
    db/                  SQLAlchemy models and session handling
    security/            Passwords, sessions, CSRF, rate limiting
  migrations/            Alembic revisions, one per phase
  tests/                 pytest suite (414 tests)
frontend/                React SPA
  src/features/          auth/ and trips/ screens, with colocated tests
  src/locales/           en.json / pl.json — kept in sync by the gate
deploy/                  Dockerfile, entrypoint, compose files
scripts/check_locales.py Locale parity gate (plain python3, no deps)
scripts/check_css_tokens.py  CSS token completeness gate (plain python3, no deps)
scripts/check_contrast.py    WCAG contrast gate over tokens.css (plain python3, no deps)
.ai/                     Specs, agent pipeline config, generated run artifacts
```

## Prerequisites

- **Python 3.11+** and **`uv`** — <https://docs.astral.sh/uv/getting-started/installation/>
- **Node.js 20+** and **npm**
- **Docker** with Compose v2, for the local PostgreSQL server (or your own Postgres 16
  reachable over TCP)

## Configuration

Four environment variables are **required**; the app refuses to start without them and
the crash names the ones that are missing (`backend/trip_planner/config.py`).

| Variable | What it is |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string. `postgres://` and `postgresql://` are rewritten to the pinned psycopg 3 driver automatically. |
| `SESSION_SECRET` | Random secret, **at least 32 characters**. Keys the session-token hash and the CSRF token; rotating it signs every session out. |
| `APP_BASE_URL` | Absolute public URL of the installation. With `ENVIRONMENT=production` it **must** be `https://` — the session cookie is `Secure`, so an http production URL would hand out a cookie the browser then refuses to send back. |
| `ENVIRONMENT` | `development` or `production`. Only `production` marks cookies `Secure`. |

Optional:

| Variable | Default | What it is |
|---|---|---|
| `STATIC_DIR` | `/srv/static` | Directory holding the built SPA. When it contains no `index.html` the API starts without serving a frontend — which is what you want when Vite is serving it. |
| `PORT` | `8000` | Port the container's `serve` command listens on. |
| `TEST_DATABASE_URL` | `postgresql+psycopg://trip_planner:trip_planner@127.0.0.1:55432/trip_planner_test` | Database the pytest suite uses. |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the Vite dev server proxies `/api`. |

Generate a secret with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

## Local deployment

Three shapes, in increasing fidelity to production. Start with the first for
development; use the third when you need to exercise the deployed artifact.

### 1. Development — Vite dev server + `uvicorn --reload`

Best for day-to-day work: hot module reload on the frontend, auto-reload on the
backend. The SPA and the API stay on one origin because Vite proxies `/api`, so the
cookie and CSRF behaviour matches production.

**Start PostgreSQL** (published on host port `55432`):

```bash
docker compose -f deploy/compose.dev.yml up -d db
```

That container's database is `trip_planner_test`, used by the test suite. Create a
separate one for your development data so a test run cannot wipe it:

```bash
docker compose -f deploy/compose.dev.yml exec db \
  psql -U trip_planner -d postgres -c 'CREATE DATABASE trip_planner_dev'
```

**Set up the backend environment** (from `backend/`):

```bash
cd backend
export DATABASE_URL='postgresql+psycopg://trip_planner:trip_planner@127.0.0.1:55432/trip_planner_dev'
export SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export APP_BASE_URL='http://localhost:5173'
export ENVIRONMENT=development
```

**Apply the migrations and create the owner account:**

```bash
uv run alembic upgrade head
uv run trip-planner create-owner --email you@example.com --locale pl
```

There is no sign-up form — D15 says one user, and a public registration endpoint on an
internet-facing app is attack surface serving nobody. `create-owner` reads the password
interactively (or from a pipe), never from `argv`, and requires at least 12 characters.
Re-run it with `--replace` to set a new password; that is also the password-recovery
path.

**Run the API:**

```bash
uv run uvicorn trip_planner.app:create_production_app --factory --reload --port 8000
```

**Run the frontend** (in a second terminal, from `frontend/`):

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173> and sign in. Requests to `/api` are proxied to port 8000.

### 2. Single origin, no container — the production app factory over a built bundle

Same process boundary as development, but the real `npm run build` output served by the
real `mount_spa` from one origin. This is what the QA environment uses, and the right
shape for verifying static serving, the SPA deep-link fallback and anything
cookie- or CSRF-adjacent.

```bash
(cd frontend && npm ci && npm run build)

cd backend
export DATABASE_URL='postgresql+psycopg://trip_planner:trip_planner@127.0.0.1:55432/trip_planner_dev'
export SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export APP_BASE_URL='http://localhost:8000'
export ENVIRONMENT=development
export STATIC_DIR="$(cd ../frontend/dist && pwd)"

uv run alembic upgrade head
uv run uvicorn trip_planner.app:create_production_app --factory --port 8000
```

Everything is on <http://localhost:8000> — the SPA at `/`, the API under `/api/v1`.

A scripted version of this, with its own throwaway database and a JSON descriptor other
tooling attaches to, is `.ai/scripts/test-env-up.sh` (torn down by
`.ai/scripts/test-env-down.sh`). Read the header comment in that script before reaching
for Docker — it records why the container route was abandoned on the development machine.

### 3. The deployed shape — Docker Compose

The single image serving both the API and the SPA, in front of Postgres, with
migrations running to completion **before** the app starts:

```bash
SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  docker compose -f deploy/compose.yml up --build
```

The app is on <http://localhost:8000>. Create the owner account inside the running
container:

```bash
docker compose -f deploy/compose.yml exec app \
  sh -c 'printf "%s\n" "your-password-here" | trip-planner create-owner --email you@example.com'
```

This is **not** the production deployment: production terminates TLS at the platform's
proxy and uses a managed Postgres. It exists so the image can be exercised the way it
will actually run.

The image's entrypoint takes three commands — `migrate` (the release step),
`serve` (takes traffic), and `migrate-and-serve` (both in order, correct only for a
single instance; the day a second replica appears, every replica would race to migrate).

## Validation gate

Run these eight commands, in this order, before opening or updating a PR. Any non-zero
exit blocks the PR. The authoritative list is `validation.commands` in
`.ai/agentic.config.json`; `.github/workflows/validation-gate.yml` runs the same eight.

```bash
python3 scripts/check_locales.py
python3 scripts/check_css_tokens.py
python3 scripts/check_contrast.py
(cd backend && uv run ruff check .)
(cd backend && uv run pytest)
(cd frontend && npm run typecheck)
(cd frontend && npm run test -- --run)
(cd frontend && npm run build)
```

`uv run pytest` needs a reachable PostgreSQL server — `docker compose -f
deploy/compose.dev.yml up -d db`, or point `TEST_DATABASE_URL` at your own. **Without a
server those tests skip rather than fail**, so read the summary: a run reporting skips
has not verified the database layer. A full green run is 414 backend and 127 frontend
tests.

## The API

Everything lives under `/api/v1` — a URL version prefix, additive-only within a
version. `docs_url` and `redoc_url` are disabled, so there is no interactive schema
browser on a deployed installation.

Authentication is applied **by default**: every router other than the public allow-list
in `backend/trip_planner/app.py` is included with a session dependency, so a new
endpoint is authenticated the moment it is written, and a route enumeration test
(`tests/test_route_protection.py`) fails if one is not.

| Method | Path | |
|---|---|---|
| `GET` | `/api/v1/health` | public |
| `POST` | `/api/v1/auth/login` | public |
| `POST` | `/api/v1/auth/logout` | public |
| `GET` `PATCH` | `/api/v1/auth/me` | the owner's profile and locale |
| `GET` `POST` | `/api/v1/trips` | list, create |
| `GET` `PATCH` `DELETE` | `/api/v1/trips/{trip_id}` | a trip; `PATCH` regenerates days on a date-range change |
| `POST` | `/api/v1/trips/{trip_id}/stages` | add a stage |
| `PATCH` `DELETE` | `/api/v1/trips/{trip_id}/stages/{stage_id}` | |
| `GET` | `/api/v1/trips/{trip_id}/days/{day_date}` | a day and its items |
| `POST` | `/api/v1/trips/{trip_id}/days/{day_date}/items` | add an item |
| `PATCH` `DELETE` | `/api/v1/trips/{trip_id}/items/{item_id}` | `PATCH` can move an item to another day |

Every request body and query parameter is validated at the boundary by Pydantic v2
models that reject unknown fields. Errors come back in one shape — `{"error": {...}}`
with a stable code — including validation failures, which are translated out of
FastAPI's default format on purpose. Frontend codes live in
`frontend/src/api/errorCodes.ts`.

Non-`GET` requests need the double-submit CSRF token: send the value of the
`csrf_token` cookie in the `X-CSRF-Token` header. `frontend/src/api/client.ts` does
this for you.

## Contributing

- Read [`AGENTS.md`](AGENTS.md) first — it carries the task-routing table, the
  multilingual rules and the stack constraints.
- Behaviour changes need a spec before code; see the Definition of Ready in
  [`SDLC.md`](SDLC.md).
- Every bug fix ships a regression test that fails before the fix.
- No user-visible string is hardcoded. Every one goes through the i18n layer with a key
  present in **both** `en` and `pl`, and dates, times, numbers and currencies are
  formatted through the locale.
- Business rules that are not CRUD go in `backend/trip_planner/domain/` as pure
  functions with their own unit tests, not in a request handler.
- Every new endpoint is a contract surface — check
  [`BACKWARD_COMPATIBILITY.md`](BACKWARD_COMPATIBILITY.md).
- Review rules are in [`CODE_REVIEW.md`](CODE_REVIEW.md).
- Never commit secrets or API keys. Credentials come from the environment, and each new
  variable is documented in this README's **Configuration** section.
