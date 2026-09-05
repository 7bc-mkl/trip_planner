#!/bin/sh
# om-prepare-test-env: generated entrypoint
#
# Stops exactly what `test-env-up.sh` started, and nothing else.
#
#   sh .ai/scripts/test-env-down.sh [--keep-db]
#
# Two safety mechanisms. The app is stopped by the PID this repo's own descriptor
# recorded, so another uvicorn on the machine is never in scope. The database is
# stopped only when that descriptor's `dbStartedByThisRun` says this environment
# started it — the up script reuses a PostgreSQL that is already listening, and
# something merely borrowed must not be torn down here.
#
# history:
# - 2026-09-05 initial generation.
# - 2026-09-05 rewritten alongside test-env-up.sh when the environment moved off
#   the Docker image build; see that script's history for why.
# - 2026-09-05 the database is stopped only when the descriptor records this run
#   as having started it, since the up script now reuses a PostgreSQL that is
#   already listening.

set -eu

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO_ROOT"

PROJECT=trip-planner-testenv
QA_DIR="$REPO_ROOT/.ai/qa"
DESCRIPTOR="$QA_DIR/test-env.json"
PID_FILE="$QA_DIR/.test-env.pid"

KEEP_DB=0
for arg in "$@"; do
  case "$arg" in
    --keep-db) KEEP_DB=1 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

if [ -f "$DESCRIPTOR" ] && ! grep -q '"startedByThisRepo": true' "$DESCRIPTOR"; then
  echo "The descriptor does not record this repo as having started the environment; leaving it alone."
  exit 0
fi

if [ -f "$PID_FILE" ]; then
  pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "Stopping the app (pid $pid)…"
    kill "$pid" 2>/dev/null || true
    attempt=0
    while kill -0 "$pid" 2>/dev/null && [ "$attempt" -lt 10 ]; do
      attempt=$((attempt + 1))
      sleep 1
    done
    # SIGKILL only after SIGTERM was given a fair chance to shut down cleanly.
    if kill -0 "$pid" 2>/dev/null; then kill -9 "$pid" 2>/dev/null || true; fi
  fi
  rm -f "$PID_FILE"
fi

# Only when this repo started it. When the up script reused a PostgreSQL that
# was already running — the test suite's, or a developer's — stopping it here
# would take down something this environment merely borrowed.
if [ "$KEEP_DB" -eq 0 ] && grep -q '"dbStartedByThisRun": true' "$DESCRIPTOR" 2>/dev/null; then
  echo "Stopping the database this run started…"
  docker compose -p "$PROJECT" -f deploy/compose.dev.yml down --remove-orphans --volumes >/dev/null 2>&1 || true
else
  echo "Leaving PostgreSQL alone — this run did not start it."
fi

if [ -f "$DESCRIPTOR" ]; then
  # Rewritten rather than deleted: a consumer reading it should learn the
  # environment is stopped, not that it never existed.
  tmp="$DESCRIPTOR.tmp"
  sed 's/"status": "running"/"status": "stopped"/' "$DESCRIPTOR" > "$tmp" && mv "$tmp" "$DESCRIPTOR"
fi

echo "RESULT: stopped"
