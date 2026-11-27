#!/usr/bin/env bash
# Release the current commit to the Lambda target.
#
#   AWS_PROFILE=mkl ./deploy/lambda/deploy.sh
#
# What it does, in order: deploy the certificate stack (us-east-1) if it is
# missing, build the image and push it to ECR, run the migrations to completion
# in that image against Neon's DIRECT endpoint, and only then `sam deploy` the
# functions onto the new image. That ordering is the spec's release step: the
# new code never takes traffic against an unmigrated database, and no function
# instance migrates on start (concurrent instances would race).
#
# Secrets live in SSM Parameter Store (SecureString) under $SSM_PREFIX and are
# read here at deploy time — see deploy/lambda/README.md for the list. They are
# handed to Docker and SAM through files created mode 0600 in a private temp
# directory, never on a command line, and the directory is removed on exit.
set -euo pipefail

STACK="${STACK:-trip-planner}"
REGION="${REGION:-eu-central-1}"
DOMAIN="${DOMAIN:-trips.botito.app}"
HOSTED_ZONE_ID="${HOSTED_ZONE_ID:-Z06147722TLSJWJZMPBG}"
SSM_PREFIX="${SSM_PREFIX:-/trip-planner}"
ENABLE_INBOX="${ENABLE_INBOX:-true}"
ALARM_EMAIL="${ALARM_EMAIL:-}"
INBOX_ALLOWED_SENDERS="${INBOX_ALLOWED_SENDERS:-}"
# Optional model routing (D24). Leave INBOX_MODEL_PROVIDER empty to run the
# inbox without it; when set, the key is read from ${SSM_PREFIX}/model-api-key.
INBOX_MODEL_PROVIDER="${INBOX_MODEL_PROVIDER:-}"
INBOX_MODEL_NAME="${INBOX_MODEL_NAME:-}"
INBOX_MODEL_MONTHLY_BUDGET="${INBOX_MODEL_MONTHLY_BUDGET:-}"
INBOX_MODEL_INPUT_PRICE="${INBOX_MODEL_INPUT_PRICE:-}"
INBOX_MODEL_OUTPUT_PRICE="${INBOX_MODEL_OUTPUT_PRICE:-}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/../.." && pwd)"
cd "$ROOT"

# A dirty tree deploys something no commit describes (same rule as deploy/deploy.sh).
if ! git diff --quiet HEAD -- || [ -n "$(git ls-files --others --exclude-standard)" ]; then
	echo "Refusing to deploy: the working tree has uncommitted changes." >&2
	exit 1
fi

for tool in aws docker sam; do
	command -v "$tool" >/dev/null || { echo "Refusing to deploy: '$tool' is not installed." >&2; exit 1; }
done

REVISION="$(git rev-parse --short HEAD)"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
REPOSITORY="${STACK}"
IMAGE="${REGISTRY}/${REPOSITORY}:${REVISION}"
echo "==> Deploying ${REVISION} to ${STACK} (${REGION}, account ${ACCOUNT})"

SECRETS_DIR="$(mktemp -d)"
chmod 700 "$SECRETS_DIR"
trap 'rm -rf "$SECRETS_DIR"' EXIT

secret() {
	aws ssm get-parameter --region "$REGION" --with-decryption \
		--name "${SSM_PREFIX}/$1" --query Parameter.Value --output text
}

echo "==> Reading secrets from SSM ${SSM_PREFIX}/"
DATABASE_URL_POOLED="$(secret database-url-pooled)"
DATABASE_URL_DIRECT="$(secret database-url-direct)"
SESSION_SECRET="$(secret session-secret)"
ORIGIN_VERIFY_SECRET="$(secret origin-verify-secret)"
MODEL_API_KEY=""
if [ -n "$INBOX_MODEL_PROVIDER" ]; then
	MODEL_API_KEY="$(secret model-api-key)"
fi

# --- 1. certificate (us-east-1, CloudFront's only region), once -------------
CERT_STACK="${STACK}-cert"
if ! aws cloudformation describe-stacks --region us-east-1 --stack-name "$CERT_STACK" >/dev/null 2>&1; then
	echo "==> Creating the certificate stack (DNS validation takes a few minutes)"
	aws cloudformation deploy --region us-east-1 --stack-name "$CERT_STACK" \
		--template-file "${HERE}/cert.yaml" \
		--parameter-overrides "DomainName=${DOMAIN}" "HostedZoneId=${HOSTED_ZONE_ID}"
fi
CERTIFICATE_ARN="$(aws cloudformation describe-stacks --region us-east-1 --stack-name "$CERT_STACK" \
	--query "Stacks[0].Outputs[?OutputKey=='CertificateArn'].OutputValue" --output text)"

# --- 2. image --------------------------------------------------------------
if ! aws ecr describe-repositories --region "$REGION" --repository-names "$REPOSITORY" >/dev/null 2>&1; then
	echo "==> Creating ECR repository ${REPOSITORY}"
	aws ecr create-repository --region "$REGION" --repository-name "$REPOSITORY" \
		--image-scanning-configuration scanOnPush=true >/dev/null
	# Untagged images are what a re-push leaves behind; keep the last ten releases.
	aws ecr put-lifecycle-policy --region "$REGION" --repository-name "$REPOSITORY" \
		--lifecycle-policy-text '{"rules":[{"rulePriority":1,"description":"keep ten","selection":{"tagStatus":"any","countType":"imageCountMoreThan","countNumber":10},"action":{"type":"expire"}}]}' >/dev/null
fi

echo "==> Building ${IMAGE}"
# --provenance=false: Lambda refuses the multi-manifest index an attestation adds.
docker build --platform linux/amd64 --provenance=false -f deploy/Dockerfile -t "$IMAGE" .

echo "==> Pushing"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
docker push "$IMAGE" >/dev/null

# --- 3. migrate, in the built image, against the direct endpoint -----------
# DDL through a transaction-mode pooler is unsafe, hence DIRECT.
echo "==> Migrating"
umask 077
cat >"${SECRETS_DIR}/migrate.env" <<EOF
DATABASE_URL=${DATABASE_URL_DIRECT}
SESSION_SECRET=${SESSION_SECRET}
APP_BASE_URL=https://${DOMAIN}
ENVIRONMENT=production
EOF
# The image's ENTRYPOINT is the Lambda-agnostic entrypoint.sh; outside Lambda
# the adapter extension is inert, so this is exactly the compose `migrate`.
docker run --rm --env-file "${SECRETS_DIR}/migrate.env" "$IMAGE" migrate

# --- 4. functions ----------------------------------------------------------
toml_string() {
	# A TOML basic string: escape backslash and double quote.
	local value="${1//\\/\\\\}"
	printf '"%s"' "${value//\"/\\\"}"
}

{
	echo 'version = 0.1'
	echo '[default.deploy.parameters]'
	echo 'parameter_overrides = ['
	for pair in \
		"ImageUri=${IMAGE}" \
		"DomainName=${DOMAIN}" \
		"HostedZoneId=${HOSTED_ZONE_ID}" \
		"CertificateArn=${CERTIFICATE_ARN}" \
		"DatabaseUrlPooled=${DATABASE_URL_POOLED}" \
		"DatabaseUrlDirect=${DATABASE_URL_DIRECT}" \
		"SessionSecret=${SESSION_SECRET}" \
		"OriginVerifySecret=${ORIGIN_VERIFY_SECRET}" \
		"EnableInbox=${ENABLE_INBOX}" \
		"AlarmEmail=${ALARM_EMAIL}" \
		"InboxAllowedSenders=${INBOX_ALLOWED_SENDERS}" \
		"InboxModelProvider=${INBOX_MODEL_PROVIDER}" \
		"InboxModelName=${INBOX_MODEL_NAME}" \
		"InboxModelApiKey=${MODEL_API_KEY}" \
		"InboxModelMonthlyBudget=${INBOX_MODEL_MONTHLY_BUDGET}" \
		"InboxModelInputPrice=${INBOX_MODEL_INPUT_PRICE}" \
		"InboxModelOutputPrice=${INBOX_MODEL_OUTPUT_PRICE}"; do
		echo "  $(toml_string "$pair"),"
	done
	echo ']'
} >"${SECRETS_DIR}/samconfig.toml"

echo "==> sam deploy"
SAM_CLI_TELEMETRY=0 sam deploy \
	--config-file "${SECRETS_DIR}/samconfig.toml" \
	--template-file "${HERE}/template.yaml" \
	--stack-name "$STACK" \
	--region "$REGION" \
	--capabilities CAPABILITY_IAM \
	--no-confirm-changeset \
	--no-fail-on-empty-changeset

# CloudFormation can create a receipt rule set but not make it the active one.
if [ "$ENABLE_INBOX" = "true" ]; then
	echo "==> Activating the inbox receipt rule set"
	aws ses set-active-receipt-rule-set --region "$REGION" --rule-set-name "${STACK}-inbox"
fi

echo "==> Deployed ${REVISION}: https://${DOMAIN}"
echo "    Probes: deploy/lambda/README.md, 'Verifying a release'."
