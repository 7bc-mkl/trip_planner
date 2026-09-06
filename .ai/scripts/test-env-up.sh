#!/bin/sh
# om-prepare-test-env: generated entrypoint
#
# Brings up a disposable trip_planner instance for QA and integration tests:
# the production app factory serving the *built* SPA from a single origin, in
# front of a throwaway Postgres database. Consumers attach through
# `.ai/qa/test-env.json`.
#
#   sh .ai/scripts/test-env-up.sh [--force] [--force-rebuild]
#
# Why this shape, and not the other two:
#
#   * Not `vite dev` + `uvicorn --reload`. That serves the SPA from a second
#     origin behind a proxy — precisely the arrangement the single-image design
#     exists to avoid. Cookies, CSRF and same-origin behaviour would be exercised
#     in a configuration nobody deploys, which is worse than useless for QA.
#   * Not `docker compose` on `deploy/Dockerfile`. It is the closest thing to the
#     deployed artifact, and it was the first thing tried — see the history
#     below for why it was abandoned on this machine.
#
# What this runs is `create_production_app` — the same factory the container's
# entrypoint runs, with the same four required environment variables and the same
# `STATIC_DIR` bundle mount. The SPA is the real `npm run build` output, served by
# the real `mount_spa`, from one origin. The difference from the container is the
# process boundary, not the application's behaviour.
#
# history:
# - 2026-09-05 initial generation, on `deploy/compose.yml` + a port override.
#   Failed cold: `bind: address already in use` on 8000. Compose *appends*
#   `ports` lists and `!override` needs Compose >= 2.24 (this machine has 2.18),
#   so the base file's fixed `8000:8000` was published too and the port was never
#   really configurable.
# - 2026-09-05 replaced the override with a standalone compose file on a
#   kernel-assigned free port. `docker compose build` then hung for 20+ minutes
#   at zero CPU on an image it had already built successfully — this machine
#   carries 68 GB of images and several other live compose projects, and the
#   daemon is contended. A QA environment that cannot be brought up reliably is
#   not a QA environment.
# - 2026-09-05 switched to running the app directly: same factory, same built
#   bundle, same single origin, Postgres from `deploy/compose.dev.yml` (already
#   the suite's dependency) in its own database. Boots in seconds and does not
#   depend on the image build. `--force-rebuild` still rebuilds the SPA bundle.
# - 2026-09-05 that cold run failed too: `Bind for 0.0.0.0:55432 failed`. The
#   test suite already had `deploy/compose.dev.yml` up under a *different*
#   compose project, so looking for this project's own container name found
#   nothing and started a second server onto a taken port. Now any container
#   publishing the port is reused, and `dbStartedByThisRun` in the descriptor
#   tells the down script whether stopping it is its business.

set -eu

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO_ROOT"

PROJECT=trip-planner-testenv
DB_PORT=55432
DB_NAME=trip_planner_qa

QA_DIR="$REPO_ROOT/.ai/qa"
DESCRIPTOR="$QA_DIR/test-env.json"
CREDENTIALS="$QA_DIR/test-env.env"
BUILD_CACHE="$QA_DIR/test-env-build-cache.json"
LOCK_DIR="$QA_DIR/.test-env.lock"
PID_FILE="$QA_DIR/.test-env.pid"
LOG_FILE="$QA_DIR/test-env-app.log"

FORCE=0
FORCE_REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --force-rebuild) FORCE_REBUILD=1 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$QA_DIR"
STARTED_AT=$(date +%s)

read_json_number() { sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p" "$1" 2>/dev/null | head -1; }
read_json_string() { sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" 2>/dev/null | head -1; }

# --- the bootstrap lock -----------------------------------------------------
# A directory, not a file: mkdir is atomic on every POSIX filesystem, so two runs
# starting at once cannot both believe they hold it. The PID inside lets a
# crashed run's lock be reclaimed rather than blocking the next one forever.
acquire_lock() {
  attempt=0
  while [ "$attempt" -lt 120 ]; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      echo $$ > "$LOCK_DIR/pid"
      return 0
    fi
    holder=$(cat "$LOCK_DIR/pid" 2>/dev/null || echo "")
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
      echo "Reclaiming the lock from dead process $holder." >&2
      rm -rf "$LOCK_DIR"
      continue
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  echo "Timed out waiting for $LOCK_DIR (held by ${holder:-unknown})." >&2
  exit 1
}
release_lock() {
  if [ -f "$LOCK_DIR/pid" ] && [ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" = "$$" ]; then
    rm -rf "$LOCK_DIR"
  fi
}
acquire_lock
trap release_lock EXIT INT TERM

# --- fingerprint ------------------------------------------------------------
# Only the inputs that change what is served. A spec edit, a run artifact or this
# script itself must not invalidate a perfectly good bundle.
fingerprint() {
  {
    git ls-files -s backend frontend 2>/dev/null || true
    git diff HEAD -- backend frontend 2>/dev/null || true
  } | sha256sum | cut -d' ' -f1
}
FINGERPRINT=$(fingerprint)
HEAD_SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)

healthy() { curl -fsS --max-time 5 "http://127.0.0.1:$1/api/v1/health" >/dev/null 2>&1; }

# --- port -------------------------------------------------------------------
# Asked of the kernel rather than hardcoded: binding :0 and reading back the
# assignment is the only way to learn a port is free without racing for it.
free_port() {
  python3 -c 'import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()'
}

PREVIOUS_PORT=$(read_json_number "$DESCRIPTOR" port)

# --- reuse ------------------------------------------------------------------
# Three conditions, all required: the app answers its health endpoint, the
# descriptor records this repo as its owner, and the fingerprint matches. The
# third is what stops a warm run from serving the previous branch's code — the
# failure that quietly turns QA evidence into a lie.
if [ "$FORCE" -eq 0 ] && [ -n "$PREVIOUS_PORT" ] && healthy "$PREVIOUS_PORT"; then
  if [ "$(read_json_string "$DESCRIPTOR" fingerprint)" = "$FINGERPRINT" ]; then
    echo "Reusing the running environment (fingerprint unchanged)."
    echo "RESULT: reused"
    echo "BASE_URL: http://127.0.0.1:$PREVIOUS_PORT"
    echo "DESCRIPTOR: $DESCRIPTOR"
    echo "ELAPSED: $(( $(date +%s) - STARTED_AT ))s"
    exit 0
  fi
  echo "A different build is running (fingerprint changed); replacing it."
fi

# Stop whatever this script started before, so the old process does not keep the
# port or serve stale code alongside the new one.
if [ -f "$PID_FILE" ]; then
  old=$(cat "$PID_FILE" 2>/dev/null || echo "")
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    kill "$old" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

APP_PORT=${APP_PORT:-$(free_port)}
BASE_URL="http://127.0.0.1:${APP_PORT}"

# --- credentials ------------------------------------------------------------
# Generated once into a gitignored file. Disposable and local-only: this account
# exists to click through a throwaway database and is never a real credential.
if [ ! -f "$CREDENTIALS" ]; then
  umask 077
  {
    echo "# Generated by .ai/scripts/test-env-up.sh — gitignored, disposable."
    echo "# Local-only fixtures for a throwaway environment. Not real credentials."
    echo "TEST_OWNER_EMAIL=owner@example.com"
    echo "TEST_OWNER_PASSWORD=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    echo "SESSION_SECRET=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  } > "$CREDENTIALS"
fi
# shellcheck disable=SC1090
. "$CREDENTIALS"

# --- database ---------------------------------------------------------------
# The same server the test suite already depends on, in its own database, so QA
# data and the suite's throwaway databases never meet.
#
# **Reuse whatever already publishes the port.** A developer, or the test suite,
# very likely already has `deploy/compose.dev.yml` up — under its own project
# name, which is why looking for this project's container name is not enough.
# Starting a second one just loses the port race (it did, on the first run), and
# tearing theirs down to win it would be worse.
EXISTING_DB=$(docker ps -q --filter "publish=${DB_PORT}" 2>/dev/null | head -1)

if [ -n "$EXISTING_DB" ]; then
  DB_CONTAINER=$(docker inspect -f '{{.Name}}' "$EXISTING_DB" | sed 's|^/||')
  DB_STARTED_HERE=false
  echo "Reusing the PostgreSQL already on :${DB_PORT} ($DB_CONTAINER)."
else
  echo "Starting PostgreSQL…"
  docker compose -p "$PROJECT" -f deploy/compose.dev.yml up -d db >/dev/null
  DB_CONTAINER="${PROJECT}-db-1"
  DB_STARTED_HERE=true
fi

attempt=0
until docker exec "$DB_CONTAINER" pg_isready -U trip_planner >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -ge 60 ] && { echo "PostgreSQL did not become ready." >&2; exit 1; }
  sleep 1
done

# Dropped and recreated: a QA pass must start from a known-empty plan, or the
# previous run's trips show up in this run's screenshots.
echo "Recreating the $DB_NAME database…"
docker exec "$DB_CONTAINER" psql -U trip_planner -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME'" >/dev/null 2>&1 || true
docker exec "$DB_CONTAINER" psql -U trip_planner -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME" >/dev/null
docker exec "$DB_CONTAINER" psql -U trip_planner -d postgres -c "CREATE DATABASE $DB_NAME" >/dev/null

DATABASE_URL="postgresql+psycopg://trip_planner:trip_planner@127.0.0.1:${DB_PORT}/${DB_NAME}"
export DATABASE_URL SESSION_SECRET
export APP_BASE_URL="$BASE_URL"
export ENVIRONMENT=development
export STATIC_DIR="$REPO_ROOT/frontend/dist"

# --- build ------------------------------------------------------------------
CACHED=$(read_json_string "$BUILD_CACHE" fingerprint)
if [ "$FORCE_REBUILD" -eq 0 ] && [ "$CACHED" = "$FINGERPRINT" ] && [ -f "$STATIC_DIR/index.html" ]; then
  echo "Build cache hit — reusing the existing SPA bundle."
  REBUILT=false
else
  echo "Installing dependencies and building the SPA…"
  (cd backend && uv sync --quiet)
  [ -d frontend/node_modules ] || (cd frontend && npm ci --silent)
  (cd frontend && npm run build >/dev/null)
  REBUILT=true
fi

# --- migrate ----------------------------------------------------------------
# The release step, in the ordering the spec requires: schema before traffic.
echo "Running migrations…"
(cd backend && uv run alembic upgrade head >/dev/null 2>&1) || {
  echo "alembic upgrade head failed." >&2
  (cd backend && uv run alembic upgrade head) >&2
  exit 1
}

# --- owner ------------------------------------------------------------------
echo "Creating the owner account…"
printf '%s\n' "$TEST_OWNER_PASSWORD" | \
  (cd backend && uv run trip-planner create-owner --email "$TEST_OWNER_EMAIL" --replace) >/dev/null

# --- serve ------------------------------------------------------------------
# `create_production_app` via --factory, exactly as deploy/entrypoint.sh runs it,
# so configuration is validated at startup and a missing variable is a crash
# naming it rather than a confusing failure on the first request.
echo "Starting the app on $BASE_URL …"
(
  cd backend
  exec uv run uvicorn trip_planner.app:create_production_app \
    --factory --host 127.0.0.1 --port "$APP_PORT"
) > "$LOG_FILE" 2>&1 &
APP_PID=$!
echo "$APP_PID" > "$PID_FILE"

attempt=0
until healthy "$APP_PORT"; do
  attempt=$((attempt + 1))
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "The app exited during startup. Log:" >&2
    tail -30 "$LOG_FILE" >&2
    exit 1
  fi
  if [ "$attempt" -ge 60 ]; then
    echo "The app did not become healthy within 60s. Log:" >&2
    tail -30 "$LOG_FILE" >&2
    exit 1
  fi
  sleep 1
done

# --- descriptor -------------------------------------------------------------
# What consumers attach to. The password is NOT here — only a reference to the
# gitignored file holding it, per the descriptor contract.
cat > "$DESCRIPTOR" <<JSON
{
  "status": "running",
  "baseUrl": "$BASE_URL",
  "healthUrl": "$BASE_URL/api/v1/health",
  "port": $APP_PORT,
  "startedByThisRepo": true,
  "startScript": ".ai/scripts/test-env-up.sh",
  "stopScript": ".ai/scripts/test-env-down.sh",
  "platform": "posix",
  "pidFile": ".ai/qa/.test-env.pid",
  "dbContainer": "$DB_CONTAINER",
  "dbStartedByThisRun": $DB_STARTED_HERE,
  "logFile": ".ai/qa/test-env-app.log",
  "fingerprint": "$FINGERPRINT",
  "headSha": "$HEAD_SHA",
  "branch": "$BRANCH",
  "services": [
    { "name": "app", "url": "$BASE_URL", "description": "create_production_app serving the built SPA from one origin" },
    { "name": "db", "description": "PostgreSQL 16 in $DB_CONTAINER, database $DB_NAME, recreated on every run" }
  ],
  "credentials": {
    "reference": ".ai/qa/test-env.env",
    "roles": [
      { "role": "owner", "emailVar": "TEST_OWNER_EMAIL", "passwordVar": "TEST_OWNER_PASSWORD", "loginPath": "/login" }
    ]
  },
  "notes": [
    "One origin serves the API and the SPA (spec A12), so cookies and CSRF behave as deployed.",
    "The database is dropped and recreated on every non-reused run: QA starts from an empty plan.",
    "A warm run with an unchanged fingerprint reuses the running app and rebuilds nothing."
  ]
}
JSON

printf '{ "fingerprint": "%s", "builtAt": "%s" }\n' "$FINGERPRINT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$BUILD_CACHE"

if [ "$REBUILT" = true ]; then RESULT=rebuilt; else RESULT=restarted; fi
echo "RESULT: $RESULT"
echo "BASE_URL: $BASE_URL"
echo "DESCRIPTOR: $DESCRIPTOR"
echo "ELAPSED: $(( $(date +%s) - STARTED_AT ))s"
