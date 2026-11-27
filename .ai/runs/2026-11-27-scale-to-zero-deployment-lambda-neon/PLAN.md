# Execution plan — scale-to-zero deployment on AWS Lambda + Neon

- Date: 2026-11-27
- Slug: `scale-to-zero-deployment-lambda-neon`
- Branch: `feat/scale-to-zero-deployment-lambda-neon`
- Base: `main`
- Engine: `om-auto-create-pr-loop` (steps: 24, `--loop`: no — the plan exceeds `engine.loopStepThreshold` = 20)
- Source spec: `.ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md` (merged to `main` as PR #25)
- Tracking issue: #24
- Invoked by: `om-auto-fix-issue` → `om-auto-implement-spec` → `om-auto-create-pr`
- Claim run id: `40ee8c42-6489-4cbe-84bc-854f202cb9d8`
- Deployment credentials: AWS CLI profile `mkl` (account 919747048193), per the owner's instruction on the task.

## Tasks

> Authoritative status table. `Status` is one of `todo` or `done`. On landing a Step, flip `Status` to `done` and fill the `Commit` column with the short SHA. The first row whose `Status` is not `done` is the resume point for `om-auto-continue-pr-loop`. Step ids and `Exec` cells are immutable once the plan is committed — per-Step commits touch only `Status` and `Commit`.

| Phase | Step | Title | Exec | Status | Commit |
|-------|------|-------|------|--------|--------|
| 0 | 0.1 | Record verified platform facts (spec Phase 0 step 1) | inline | done | 3fac4d9 |
| 0 | 0.2 | Record the AWS account and production measurements (spec Phase 0 steps 2–4) | inline | done | b694c17 |
| 1 | 1.1 | Characterize the receipt path (spec step 1) | dispatch | done | 01e9201 |
| 1 | 1.2 | `INBOX_WORKER_MODE`, `INBOX_WORKER_FUNCTION`, `DB_POOL` settings (spec step 2) | dispatch | done | 2c1427a |
| 1 | 1.3 | `WorkerKick` port and commit-then-kick in the receipt endpoint (spec step 3) | dispatch:capable | todo | — |
| 1 | 1.4 | Lifespan skips the worker thread in `lambda` mode (spec step 4) | dispatch:cheap | todo | — |
| 1 | 1.5 | `worker_app.py` — `POST /events` drains under a 4-minute budget (spec step 5) | dispatch:capable | todo | — |
| 1 | 1.6 | `DB_POOL=null` → `NullPool`, and worker keepalives (spec step 6) | dispatch | todo | — |
| 1 | 1.7 | Client-IP hop rule behind a setting (spec step 7) | dispatch:capable | todo | — |
| 1 | 1.8 | Characterize the upload limit and the stored 10 MiB row (spec step 8) | dispatch | todo | — |
| 1 | 1.9 | Upload limit 4 MiB; stored bound stays 10 MiB; frontend and copy (spec step 9) | dispatch:capable | todo | — |
| 1 | 1.10 | Characterize response headers and `/assets` caching (spec step 10) | dispatch:cheap | todo | — |
| 1 | 1.11 | Security-headers middleware, immutable `/assets`, `--no-server-header` (spec step 11) | dispatch | todo | — |
| 1 | 1.12 | Origin-verify middleware and the `CloudFront-Viewer-Address` source (spec step 12) | dispatch:capable | todo | — |
| 1 | 1.13 | Lambda Web Adapter in the image; `worker` entrypoint (spec step 13) | dispatch | todo | — |
| 2 | 2.1 | `deploy/lambda/cert.yaml` — ACM certificate in us-east-1 (spec Phase 2 step 1) | inline | todo | — |
| 2 | 2.2 | `deploy/lambda/template.yaml` — functions, URL, schedule, CloudFront, DNS, IAM (spec Phase 2 step 1) | inline | todo | — |
| 2 | 2.3 | Inbox wiring for the Lambda stack — bucket, topic, SES receipt rule (spec Phase 2 step 5) | inline | todo | — |
| 2 | 2.4 | `deploy/lambda/deploy.sh` — the release script (spec Phase 2 step 2) | inline | todo | — |
| 2 | 2.5 | Neon project and first deploy against an empty database (spec Phase 2 step 3) | inline | todo | — |
| 2 | 2.6 | Smoke probes on `https://trips.botito.app`, recorded (spec Phase 2 steps 4–5) | inline | todo | — |
| 2 | 2.7 | `deploy/lambda/README.md` and links (spec Phase 2 step 6) | inline | todo | — |
| 2 | 2.8 | Archive the Delta into the living capability specs (spec Phase 2 step 7) | dispatch:cheap | todo | — |
| 2 | 2.9 | Correct the spec's unverified assumptions from Phase 0 | inline | todo | — |

## Goal

Add a second deployment target — the same image on AWS Lambda through the Lambda Web Adapter, Neon serverless Postgres, `trips.botito.app` through CloudFront — that runs zero compute when idle, while the compose (Hetzner) target keeps working unchanged.

## Scope

Spec Phases 0–2: verify the platform facts, make the image and the app Lambda-ready (Phase 1, compose behaviour unchanged apart from the owner-approved 4 MiB upload limit and the headers/caching that move from Caddy into the app), describe the infrastructure in AWS SAM, stand the Lambda target up against an empty Neon database with smoke probes, and document it.

## Non-goals

- **Phase 3 (cutover) and Phase 4 (decommission, cost measurement).** The spec gates cutover on Phases 1–2 being *merged* and probed; it moves production data and stops the Hetzner app, so it runs after this PR merges, with the owner's go-ahead. Runbook lives in `deploy/lambda/README.md`.
- Changing what the app does for the user beyond the 4 MiB upload limit (A1).
- Moving the SPA to S3, a custom domain for the Hetzner target, dropping compose.

## Risks

- Platform facts in the spec were written from memory (spec "Unverified platform facts"); step 0.1 verifies them and step 2.9 corrects the spec.
- New AWS accounts can have a low Lambda concurrency quota, which makes reserved concurrency unsettable; recorded in 0.2 and handled in the template as a parameter.
- Neon project creation needs the owner's Neon account (no credentials on this machine). Step 2.5 is blocked until the owner provides a Neon API key or the connection strings.
- The tracker descriptor (`.ai/trackers/github.md`) has no `acquire-lock` operation, so the PR claim uses the comment-election fallback, as earlier runs in this repo did.

## Implementation Plan

### Phase 0 — Verify and measure

#### 0.1 Record verified platform facts (spec Phase 0 step 1)
- Verify against current AWS, LWA and Neon documentation every item of spec Phase 0 step 1; record fact, source and match/mismatch in `phase-0-findings.md` in this run folder.

#### 0.2 Record the AWS account and production measurements (spec Phase 0 steps 2–4)
- Route 53 `botito.app` zone presence, nothing answering on `trips.botito.app`, SES receipt rule sets and SNS topics per region, Lambda concurrency quota, production database size and migration head on the Hetzner host. Append to `phase-0-findings.md`.

### Phase 1 — Lambda-ready image and app (compose unchanged)

Steps 1.1–1.13 are spec Phase 1 steps 1–13, verbatim in scope; see the spec's Implementation Plan for each Step's bullets. Spec step 14 (full validation gate) is the checkpoint that closes the Phase, not a commit.

### Phase 2 — Stand up the Lambda target (no real users)

#### 2.1 `deploy/lambda/cert.yaml`
- CloudFormation stack for us-east-1: ACM certificate for `trips.botito.app`, DNS validation in the `botito.app` hosted zone (zone id parameter). Output the ARN.

#### 2.2 `deploy/lambda/template.yaml`
- SAM template per spec "The web function", "The worker function", "Domain" and "Security": web function (image, Function URL `AuthType: NONE`, `InvokeMode: RESPONSE_STREAM`, `AWS_LWA_INVOKE_MODE=response_stream`, reserved concurrency parameter default 10, env from SSM), worker function (`command: ["worker"]`, no URL, reserved concurrency 1, timeout 300 s, async retries 0), EventBridge schedule `rate(6 hours)`, CloudFront distribution (two behaviours, origin request policy incl. `CloudFront-Viewer-Address`, `X-Origin-Verify` custom header), Route 53 `A`/`AAAA` aliases, least-privilege IAM.
- A backend test loads the template and pins the security-relevant properties (no wildcard resources, invoke mode, worker has no URL, origin-verify header wired).

#### 2.3 Inbox wiring for the Lambda stack
- Production has no inbox configured today (0.2), so the Lambda stack's inbox is the first one: its own encrypted bucket + prefix, SNS topic, SES receipt rule for a recipient under `botito.app`, MX record; IAM scoped to that prefix. Conditional on a stack parameter so the stack deploys without it.

#### 2.4 `deploy/lambda/deploy.sh`
- Refuses a dirty tree; deploys `cert.yaml` when missing; builds and pushes the image to ECR; runs `migrate` in the built image against `DATABASE_URL_DIRECT`; `sam deploy`. Uses `AWS_PROFILE` from the caller.

#### 2.5 Neon project and first deploy
- Neon project in the matching region, pooled and direct URLs into SSM SecureString; deploy; create a test owner. Record the outcome (no secrets) in the run folder.

#### 2.6 Smoke probes
- Spec Phase 2 step 4 probes plus the inbox test confirmation; record results, cold-start timing and screenshots in the run folder and on the PR.

#### 2.7 `deploy/lambda/README.md`
- Provisioning, variables, release, rollback, cutover runbook (spec Phase 3), cost notes; links from `deploy/README.md` and the root `README.md`.

#### 2.8 Archive the Delta
- Create `.ai/specs/capabilities/inbox-ingestion.md`, `attachments.md`, `http-delivery.md` from the spec's Delta.

#### 2.9 Correct the spec's unverified assumptions
- Edit the spec where Phase 0 findings differ (marked "verify"), so the merged spec states verified facts.

## External References

- None passed via `--skill-url`.
