#!/bin/sh
# Capture the five routes in both locales against the running QA environment.
#
#   sh .ai/scripts/qa-screenshots.sh <output-dir> [width] [height] [suffix]
#
# The design-system adoption spec makes a screenshot set the review artifact for
# every phase — "no command in the validation gate can see". This is that capture,
# scripted rather than driven by hand, so each phase's set is comparable with the
# last and a reviewer can diff two directories instead of trusting a description.
#
# It drives the browser through the provider contract in `.ai/browsers/agent-browser.md`
# and attaches to the environment `.ai/scripts/test-env-up.sh` describes in
# `.ai/qa/test-env.json`; `.ai/scripts/qa-seed.py` supplies the plan being
# photographed. Nothing here writes to the repository outside the output directory.
#
# Exit codes: 0 captured, 1 an operational failure (no environment, no browser).
# A caller that cannot run it records the reason and carries on — a screenshot
# set is evidence, not a gate.

set -eu

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO_ROOT"

OUT_DIR=${1:?usage: qa-screenshots.sh <output-dir> [width] [height] [suffix]}
WIDTH=${2:-1440}
HEIGHT=${3:-1000}
SUFFIX=${4:-}

mkdir -p "$OUT_DIR"
OUT_DIR=$(cd "$OUT_DIR" && pwd)

DESCRIPTOR="$REPO_ROOT/.ai/qa/test-env.json"
CREDENTIALS="$REPO_ROOT/.ai/qa/test-env.env"
[ -f "$DESCRIPTOR" ] || { echo "No $DESCRIPTOR — run .ai/scripts/test-env-up.sh first." >&2; exit 1; }
[ -f "$CREDENTIALS" ] || { echo "No $CREDENTIALS — run .ai/scripts/test-env-up.sh first." >&2; exit 1; }

BASE_URL=$(sed -n 's/.*"baseUrl"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$DESCRIPTOR" | head -1)
# shellcheck disable=SC1090
. "$CREDENTIALS"

# The seed is idempotent: a warm environment already holding the trip is a no-op.
SEED_OUT=$(python3 "$REPO_ROOT/.ai/scripts/qa-seed.py")
TRIP_ID=$(printf '%s\n' "$SEED_OUT" | sed -n 's/^TRIP_ID: //p')
[ -n "$TRIP_ID" ] || { echo "qa-seed.py did not report a trip id." >&2; exit 1; }

if command -v agent-browser >/dev/null 2>&1; then
  AB=$(command -v agent-browser)
else
  AB="$HOME/.cache/agent-tools/agent-browser/v0.34.0/agent-browser-linux-x64"
fi
[ -x "$AB" ] || { echo "agent-browser is not installed — see .ai/browsers/agent-browser.md." >&2; exit 1; }

# Chrome refuses to start when its singleton socket path is long, and an agent
# worktree under `.ai/cezar/tmp/<uuid>/` makes TMPDIR exactly that. Point it at a
# short directory for the browser only.
TMPDIR=${AGENT_BROWSER_TMPDIR:-/tmp}
export TMPDIR

SESSION="qa-dsa-$$"
cleanup() { "$AB" --session "$SESSION" close --json >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

ab() { "$AB" --session "$SESSION" "$@" --json >/dev/null; }

shoot() {
  path="$OUT_DIR/$1"
  "$AB" --session "$SESSION" screenshot --full "$path" --json >/dev/null
  test -s "$path" || { echo "Empty screenshot: $path" >&2; exit 1; }
  echo "  captured $(basename "$path")"
}

ab open "$BASE_URL/login"
ab set viewport "$WIDTH" "$HEIGHT"

for LOCALE in pl en; do
  echo "locale $LOCALE at ${WIDTH}x${HEIGHT}"

  # Signed out, and on the login screen, so the locale switch is the one on /login.
  ab open "$BASE_URL/login"
  "$AB" --session "$SESSION" eval "localStorage.setItem('locale', '$LOCALE')" --json >/dev/null 2>&1 || true
  ab open "$BASE_URL/login"
  "$AB" --session "$SESSION" select "select" "$LOCALE" --json >/dev/null 2>&1 || true
  ab wait 400
  shoot "01-login-${LOCALE}${SUFFIX}.png"

  "$AB" --session "$SESSION" fill "input[type=email]" "$TEST_OWNER_EMAIL" --json >/dev/null
  "$AB" --session "$SESSION" fill "input[type=password]" "$TEST_OWNER_PASSWORD" --json >/dev/null
  "$AB" --session "$SESSION" press Enter --json >/dev/null
  ab wait 1500

  # Signed in, the owner's stored locale wins over the one chosen on /login (R01:
  # the choice follows the owner, not the browser). So set it again here, through
  # the header's own switch — the first capture pass proved a locale set only on
  # /login leaves every authenticated screen in the persisted language.
  ab open "$BASE_URL/trips"
  ab wait 800
  "$AB" --session "$SESSION" select "header select" "$LOCALE" --json >/dev/null 2>&1 || true
  ab wait 800
  shoot "02-trips-${LOCALE}${SUFFIX}.png"

  ab open "$BASE_URL/trips/new"
  ab wait 800
  shoot "03-trip-create-${LOCALE}${SUFFIX}.png"

  ab open "$BASE_URL/trips/$TRIP_ID"
  ab wait 1200
  shoot "04-timeline-${LOCALE}${SUFFIX}.png"

  ab open "$BASE_URL/trips/$TRIP_ID/days/2026-10-11"
  ab wait 1200
  shoot "05-day-detail-${LOCALE}${SUFFIX}.png"

  # Back to a signed-out browser so the next locale starts from /login.
  "$AB" --session "$SESSION" cookies clear --json >/dev/null 2>&1 || true
done

echo "OUT_DIR: $OUT_DIR"
ls -1 "$OUT_DIR"
