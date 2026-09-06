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
# Exit codes: 0 captured, 1 an operational failure (no environment, no browser)
# OR a capture that could not be trusted — the wrong locale applied, the expected
# element missing, the webfont not yet loaded. A caller that cannot RUN it records
# the reason and carries on — a screenshot set is evidence, not a gate — but a
# capture that runs and lies is not evidence, so those stop the script.

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

# The credentials file is DATA, PARSED — not a script, sourced. `.` would run
# whatever it contains with this shell's privileges, and it is a generated file
# holding a password; `qa-seed.py` reads the same file as plain `KEY=value` and
# this is the same parser in `awk`.
read_credential() {
  awk -v key="$1" -F= '
    /^[[:space:]]*#/ { next }
    $1 == key { sub(/^[^=]*=/, ""); gsub(/^[[:space:]]+|[[:space:]]+$/, ""); print; exit }
  ' "$CREDENTIALS"
}
TEST_OWNER_EMAIL=$(read_credential TEST_OWNER_EMAIL)
TEST_OWNER_PASSWORD=$(read_credential TEST_OWNER_PASSWORD)
if [ -z "$TEST_OWNER_EMAIL" ] || [ -z "$TEST_OWNER_PASSWORD" ]; then
  echo "$CREDENTIALS does not define TEST_OWNER_EMAIL and TEST_OWNER_PASSWORD." >&2
  exit 1
fi

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

# The value of an `eval` that returns a string, and the number of matches for a
# selector. Both read the provider's own JSON, which is how the descriptor's
# "assert" operation says to compare an observed value.
ab_eval() {
  "$AB" --session "$SESSION" eval "$1" --json | sed -n 's/.*"result":"\([^"]*\)".*/\1/p'
}

ab_count() {
  "$AB" --session "$SESSION" get count "$1" --json | sed -n 's/.*"count":\([0-9]*\).*/\1/p'
}

# `<html lang>` is set by `frontend/src/i18n/index.ts` on every locale change, so
# it is the applied locale rather than the one that was asked for. A capture
# named `-en` whose page is still Polish is worse than a missing capture: it is
# evidence for a claim nothing checked, and this run produced exactly that once.
require_locale() {
  applied=$(ab_eval "document.documentElement.lang")
  [ "$applied" = "$1" ] || {
    echo "Locale switch failed: asked for '$1', page reports '${applied:-<none>}'." >&2
    exit 1
  }
}

# Every capture asserts the screen it claims to show, then waits for the webfont.
#
# `test -s` alone passes on a blank page, an error boundary and a redirect to
# /login — a non-empty PNG is not evidence of a screen. And the headline claim of
# this PR is Plus Jakarta Sans's glyph coverage, including Polish diacritics: a
# capture raced against the font load would show the fallback face and prove the
# opposite of what the filename says.
shoot() {
  path="$OUT_DIR/$1"
  expect=$2
  count=$(ab_count "$expect")
  [ "${count:-0}" -ge 1 ] || {
    echo "Expected element '$expect' is absent — not capturing $(basename "$path")." >&2
    exit 1
  }
  status=$(ab_eval "document.fonts.ready.then(() => document.fonts.status)")
  [ "$status" = "loaded" ] || {
    echo "Webfonts are '${status:-<unknown>}', not loaded — $(basename "$path") would show the fallback face." >&2
    exit 1
  }
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
  ab eval "localStorage.setItem('locale', '$LOCALE')"
  ab open "$BASE_URL/login"
  ab select "select" "$LOCALE"
  ab wait 400
  require_locale "$LOCALE"
  shoot "01-login-${LOCALE}${SUFFIX}.png" ".login form"

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
  ab select "header select" "$LOCALE"
  ab wait 800
  require_locale "$LOCALE"
  shoot "02-trips-${LOCALE}${SUFFIX}.png" ".trip-list a"

  ab open "$BASE_URL/trips/new"
  ab wait 800
  require_locale "$LOCALE"
  shoot "03-trip-create-${LOCALE}${SUFFIX}.png" ".trip-form"

  ab open "$BASE_URL/trips/$TRIP_ID"
  ab wait 1200
  require_locale "$LOCALE"
  shoot "04-timeline-${LOCALE}${SUFFIX}.png" ".timeline__day"

  ab open "$BASE_URL/trips/$TRIP_ID/days/2026-10-11"
  ab wait 1200
  require_locale "$LOCALE"
  shoot "05-day-detail-${LOCALE}${SUFFIX}.png" ".day-nav"

  # Back to a signed-out browser so the next locale starts from /login.
  "$AB" --session "$SESSION" cookies clear --json >/dev/null 2>&1 || true
done

echo "OUT_DIR: $OUT_DIR"
ls -1 "$OUT_DIR"
