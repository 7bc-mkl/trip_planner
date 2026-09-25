#!/usr/bin/env bash
# Release the current commit to the deployment host.
#
#   ./deploy/deploy.sh root@167.235.52.206
#   DEPLOY_TARGET=root@host ./deploy/deploy.sh
#
# What it does, in order: ship the committed tree, build the image, run the
# migrations to completion, then start the app against the migrated database.
# The ordering is not incidental — it is the spec's release-step requirement, and
# compose enforces it through `service_completed_successfully`.
#
# What it deliberately does not do: create or edit the env file. Secrets are
# written on the host once, by a human, and never travel through this script or
# this repository. See deploy/README.md.
set -euo pipefail

TARGET="${1:-${DEPLOY_TARGET:-}}"
REMOTE_ROOT="${DEPLOY_ROOT:-/srv/trip-planner}"
REMOTE_APP="${REMOTE_ROOT}/app"
ENV_FILE="${REMOTE_ROOT}/.env"

if [ -z "$TARGET" ]; then
	echo "usage: $0 <user@host>   (or set DEPLOY_TARGET)" >&2
	exit 64
fi

# A dirty tree deploys something no commit describes, and the first question
# after an incident is always "which commit is running".
if ! git diff --quiet HEAD -- || [ -n "$(git ls-files --others --exclude-standard)" ]; then
	echo "Refusing to deploy: the working tree has uncommitted changes." >&2
	echo "Commit them (or stash them) so the running code has a sha." >&2
	exit 1
fi

REVISION="$(git rev-parse --short HEAD)"
echo "==> Deploying ${REVISION} to ${TARGET}:${REMOTE_APP}"

ssh "$TARGET" "test -f '${ENV_FILE}'" || {
	echo "Refusing to deploy: ${ENV_FILE} does not exist on ${TARGET}." >&2
	echo "Create it first — deploy/README.md, 'First release', step 2." >&2
	exit 1
}

# git archive rather than rsync: it ships exactly what is committed, honours
# .gitattributes, and needs nothing installed on the host but tar.
echo "==> Shipping the tree"
ssh "$TARGET" "rm -rf '${REMOTE_APP}.incoming' && mkdir -p '${REMOTE_APP}.incoming'"
git archive --format=tar HEAD | ssh "$TARGET" "tar -x -C '${REMOTE_APP}.incoming'"
ssh "$TARGET" "rm -rf '${REMOTE_APP}' && mv '${REMOTE_APP}.incoming' '${REMOTE_APP}'"
ssh "$TARGET" "printf '%s\n' '${REVISION}' > '${REMOTE_ROOT}/REVISION'"

COMPOSE="docker compose -f deploy/compose.prod.yml --env-file '${ENV_FILE}'"

echo "==> Building the image"
ssh "$TARGET" "cd '${REMOTE_APP}' && ${COMPOSE} build"

# `up -d` starts db, waits for it to be healthy, runs migrate to completion, and
# only then starts the app. A failed migration therefore leaves the previous
# container serving rather than pointing a new image at a half-migrated database.
echo "==> Migrating and starting"
ssh "$TARGET" "cd '${REMOTE_APP}' && ${COMPOSE} up -d --remove-orphans"

echo "==> Waiting for the app to answer"
ssh "$TARGET" "cd '${REMOTE_APP}' && for i in \$(seq 1 30); do
	if ${COMPOSE} exec -T app python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')\" 2>/dev/null; then
		echo 'app is healthy'; exit 0
	fi
	sleep 2
done
echo 'app did not become healthy; last logs:' >&2
${COMPOSE} logs --tail 50 app >&2
exit 1"

echo "==> Deployed ${REVISION}"
echo "    Verify the public URL with deploy/README.md, 'Verifying a release'."
