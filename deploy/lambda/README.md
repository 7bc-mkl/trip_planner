# Deploying to AWS Lambda + Neon (scale to zero)

The same image as the compose deployment, run by AWS Lambda through the
[Lambda Web Adapter], with [Neon] serverless Postgres. With no traffic there is
**no compute running**, and Neon suspends its own compute five minutes after
the last query. The compose target (`deploy/README.md`) is unchanged and stays
supported. Spec: `.ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md`.

```
browser ──HTTPS──▶ trips.botito.app ──▶ CloudFront ─┬─ /assets/*  cached at the edge
                    (Route 53 alias)   (ACM, us-east-1) └─ the rest, uncached, + X-Origin-Verify
                                                         ──▶ Function URL ──▶ web function ──▶ Neon (pooled)
SES ──▶ S3 + SNS ──HTTPS──▶ (same path) ──▶ web function ──async invoke──▶ worker function ──▶ Neon (direct)
                         EventBridge Scheduler, every 6 h ──────────────────▶ worker function
```

| File | What it is |
|---|---|
| `cert.yaml` | The ACM certificate for the hostname, in us-east-1 (CloudFront reads certificates only from there). |
| `template.yaml` | AWS SAM: the web and worker functions, the Function URL, the schedule, CloudFront, DNS, and (optionally) the inbox. |
| `deploy.sh` | The release: certificate if missing → build and push → migrate → `sam deploy`. |

[Lambda Web Adapter]: https://github.com/aws/aws-lambda-web-adapter
[Neon]: https://neon.tech

## How the app behaves on Lambda

Nothing about what the user sees changes, apart from the 4 MB upload limit
(D26). Under the hood:

- **The web function** runs `serve`. The adapter (`/opt/extensions/lambda-adapter`
  in the image, inert outside Lambda) turns each invocation into HTTP to
  uvicorn on `localhost:8000`. Responses stream (`AWS_LWA_INVOKE_MODE=response_stream`),
  so an attachment stored under the old 10 MB limit still downloads.
- **The worker function** runs `worker`: a separate app serving only `POST /events`
  and health. It has no URL. It is invoked asynchronously after each inbox
  receipt commits (the "kick"), and every 6 hours by EventBridge Scheduler for
  retries, deferred mail and the S3 cleanup. One event drains for up to four
  minutes. No in-process thread runs on this target.
- **The origin is locked.** CloudFront sends `X-Origin-Verify`; the web function
  answers `403 forbidden_origin` to anything without it, except `GET /api/v1/health`
  (the adapter's readiness probe). The login rate limit reads the client address
  from `CloudFront-Viewer-Address`, and only on verified requests.
- **Database connections**: the web function uses Neon's *pooled* endpoint with no
  client-side pool (`DB_POOL=null`). The worker and the migrations use the
  *direct* endpoint: the worker's session-level advisory lock would leak behind
  a transaction-mode pooler.

## Variables

The four required variables and the `INBOX_*` / model blocks mean what they mean
on compose (root `README.md`). These are new, all optional, and their defaults
reproduce the compose behaviour exactly (`BACKWARD_COMPATIBILITY.md` §5):

| Variable | Default | Lambda value | Meaning |
|---|---|---|---|
| `INBOX_WORKER_MODE` | `thread` | `lambda` | `lambda`: no in-process worker; the receipt commits, then kicks the worker function. |
| `INBOX_WORKER_FUNCTION` | unset | `trip-planner-worker` | The function the kick invokes. Required in `lambda` mode when the inbox is configured. |
| `DB_POOL` | unset (QueuePool) | `null` (web only) | `null` opens one connection per use and keeps none. |
| `CLIENT_IP_SOURCE` | `x-forwarded-for` | `cloudfront` | Where the login rate limit reads the client address. `cloudfront` requires `ORIGIN_VERIFY_SECRET`. |
| `ORIGIN_VERIFY_SECRET` | unset (no check) | from SSM | The value CloudFront sends as `X-Origin-Verify`; 32+ characters. |
| `INBOX_WORKER_SCHEDULE` | — | `rate(6 hours)` | A template parameter (`WorkerSchedule`), not an app variable. |

`template.yaml` sets all of them; you do not set them by hand.

## Provisioning, once

Everything below runs with the owner's AWS profile (`AWS_PROFILE=mkl`) in
**eu-central-1**: the one region where both Neon and SES email receiving exist.

**1. Tools.** AWS CLI v2, Docker, and the SAM CLI (`uv tool install aws-sam-cli`).

**2. Neon.** Create a project in **AWS Europe Central 1 (Frankfurt)**, Postgres 16,
with a database `trip_planner`. From *Connect*, copy two connection strings for
the same role: **pooled** (host contains `-pooler`) and **direct**. Both need
`sslmode=require`. The Free plan holds 1 GB per project (the database was 8 MB at
cutover) and suspends compute after 5 minutes idle.

**3. Secrets into SSM**, as SecureString. Type each value at a prompt, so none
reaches the shell history:

```bash
export AWS_PROFILE=mkl AWS_REGION=eu-central-1
put() { read -rsp "$1: " v; echo; aws ssm put-parameter --overwrite --type SecureString --name "/trip-planner/$1" --value "$v" >/dev/null; }
put database-url-pooled      # postgresql://…@ep-…-pooler.eu-central-1.aws.neon.tech/trip_planner?sslmode=require
put database-url-direct      # the same without -pooler
put session-secret           # python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
put origin-verify-secret     # python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
put model-api-key            # only if INBOX_MODEL_PROVIDER is set
```

CloudFormation cannot put an `ssm-secure` value into a Lambda environment
variable, so `deploy.sh` reads them and passes them as `NoEcho` parameters,
through a 0600 file rather than a command line. Rotating one is `put` + a
release. Rotating `session-secret` signs everyone out.

**4. DNS.** The `botito.app` zone is in Route 53 in this account
(`Z06147722TLSJWJZMPBG`). The stacks create the `trips.botito.app` aliases,
the certificate's validation record and, with the inbox, its MX and DKIM records.

## Release

```bash
git checkout main && git pull
AWS_PROFILE=mkl ./deploy/lambda/deploy.sh
```

`deploy.sh` refuses a dirty tree. It tags the image with the short commit SHA,
runs `migrate` in that image against the direct endpoint, and only then moves
both functions onto it with `sam deploy`. A failed migration leaves the
previous version serving. Overrides: `STACK`, `REGION`, `DOMAIN`,
`HOSTED_ZONE_ID`, `SSM_PREFIX`, `ENABLE_INBOX` (default `true`), `ALARM_EMAIL`,
`INBOX_ALLOWED_SENDERS`, and the `INBOX_MODEL_*` block.

**The first release** also creates the certificate stack (DNS validation takes
a few minutes) and the CloudFront distribution (about five minutes more). Then
create the owner, from the built image, against the direct endpoint:

```bash
docker run --rm -it \
  -e DATABASE_URL="$(aws ssm get-parameter --with-decryption --name /trip-planner/database-url-direct --query Parameter.Value --output text)" \
  -e SESSION_SECRET=unused-by-this-command-but-required-000000 \
  -e APP_BASE_URL=https://trips.botito.app -e ENVIRONMENT=production \
  <account>.dkr.ecr.eu-central-1.amazonaws.com/trip-planner:<sha> \
  trip-planner create-owner --email you@example.com
```

## The inbox

With `ENABLE_INBOX=true` (the default) the stack creates the SES domain identity
for `trips.botito.app` with its DKIM and MX records, the receipt rule for
`inbox@trips.botito.app` (spam and virus scanning on, S3 action with an SNS
notification), the private encrypted bucket (`inbound/` prefix, 30-day expiry),
the topic, the HTTPS subscription with an SQS dead-letter queue, and an alarm
on that queue (`ALARM_EMAIL` to receive it). `deploy.sh` makes the rule set the
active one, which CloudFormation cannot. The app confirms the SNS subscription
itself, so the owner account must exist before the first message arrives. A
message sent before that gets a `503`, which SNS retries.

## Verifying a release

```bash
U=https://trips.botito.app
curl -sS -o /dev/null -w '%{http_code}\n' "$U/login"            # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$U/api/v1/trips"     # 401
curl -sS -o /dev/null -w '%{http_code}\n' "http://trips.botito.app/login"   # 301 to https
F=$(aws cloudformation describe-stacks --stack-name trip-planner --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" --output text)
curl -sS -o /dev/null -w '%{http_code}\n' "${F}login"           # 403 — CloudFront is the only way in
curl -sS -o /dev/null -w '%{http_code}\n' "${F}api/v1/health"   # 200 — the readiness probe's exemption
curl -sSI "$U/login" | grep -iE 'strict-transport|x-frame|nosniff|referrer'   # all four
```

The recorded probes for the first deployment, including the cold-start timing,
are in `.ai/runs/2026-11-27-scale-to-zero-deployment-lambda-neon/`.

## Rollback

- **A bad release:** check out the previous commit and run `deploy.sh` again. The
  image for each released SHA stays in ECR (the last ten are kept). Migrations
  only roll forward, so a release whose migration must be undone needs a new
  migration.
- **Back to the Hetzner host** (during the 14 days after cutover): the compose
  deployment is stopped with its database intact. Start it with
  `docker compose -f deploy/compose.prod.yml --env-file /srv/trip-planner/.env up -d`
  on the host. It keeps its sslip.io hostname, and `trips.botito.app` is not
  repointed. Writes made on Lambda after cutover need a reverse dump (Neon →
  compose), the cutover below run in the other direction.

## Cutover from Hetzner (spec Phase 3)

Run this after this target is deployed and its probes pass. The order matters:
no write and no receipt may land on the old host after its dump.

1. **Stop the compose app**, keep its database:
   `ssh root@HOST 'cd /srv/trip-planner/app && docker compose -f deploy/compose.prod.yml --env-file ../.env stop app caddy'`.
   The old host had no inbox configured, so no mail is in flight.
2. **Dump** from the compose database:
   `ssh root@HOST 'cd /srv/trip-planner/app && docker compose -f deploy/compose.prod.yml --env-file ../.env exec -T db pg_dump -U trip_planner -d trip_planner -Fc' > trip-planner.dump`
3. **Restore** into Neon through the **direct** endpoint, replacing what the
   empty deployment created:
   `pg_restore --clean --if-exists --no-owner --no-acl -d "$DATABASE_URL_DIRECT" trip-planner.dump`
4. **Release** (`deploy.sh`): its `migrate` brings the restored schema to head.
5. **Probe** as above, sign in as the owner, and check that the trips are there.
   Forward a confirmation to `inbox@trips.botito.app` and watch it reach `/inbox`.
6. Keep the host, stopped, for 14 days. Then archive a final dump and the owner
   decommissions it (spec Phase 4).

## Cost

Idle cost is close to zero: no Lambda instances, no CloudFront minimum, no NAT
or load balancer. What remains is Neon storage (free under 1 GB), the inbox
bucket, ECR storage for ten images, and the worker's six-hourly wake-ups (each
wakes Neon for about five minutes). Under traffic you pay per request. Reserved
concurrency (web 10, worker 1) caps both the bill and the number of Neon
connections. The first month's bill is compared with the Hetzner invoice on
issue #24 (spec Phase 4).
