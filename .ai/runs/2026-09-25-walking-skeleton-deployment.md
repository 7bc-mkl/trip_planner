# Execution plan — deploy the walking skeleton

**Source doc:** `.ai/specs/2026-09-05-walking-skeleton.md`
**Issue:** #5
**Engine:** om-auto-create-pr (steps: 11, --loop: no)

## 🎯 Goal

Put the application on the public internet behind TLS, so A05's "deployed" test is
actually met rather than assumed: a real URL where `/login` answers `200` and an
unauthenticated `/api/v1/trips` answers `401`, both recorded on the PR.

## 📋 Scope

Phase 1 step 9 of the spec has two halves. The **artifacts** half (`deploy/Dockerfile`,
`deploy/entrypoint.sh`, `deploy/compose.yml`, the fatal startup check) shipped in #2.
This run is the **deployment** half, descoped on 2026-09-05 and tracked as issue #5.

In scope:

- The production compose shape: a TLS-terminating reverse proxy, Postgres reachable
  only from the application, the `migrate` release step gating the app.
- A repeatable release procedure committed to the repository, so the deployment is
  reproducible by someone who was not here for it.
- The provisioning and first release onto the host the owner supplied
  (`167.235.52.206`), the owner account, and the recorded verification.

**Non-goals** (explicitly not touched):

- No application code changes. If a deployment failure turns out to need one, it is
  a finding on the PR, not a quiet fix.
- No second replica, no horizontal scaling, no managed-Postgres migration. The spec
  deploys one instance; `migrate-and-serve` stays unused because the compose release
  step is a real hook.
- No CI/CD pipeline. The release script is run by hand for this milestone.
- No custom domain purchase.

## 📐 Decisions taken in this run

Both are autonomous defaults under the shared run contract, and both are cheap to
reverse:

1. **Host: the Hetzner box the owner supplied** (`167.235.52.206`, Ubuntu 26.04,
   x86_64, 3.8 GB RAM, 75 GB disk). This settles the open "choose a host" item in
   issue #5 and supersedes the GCP candidate noted there — that project hosts an
   unrelated product. Self-hosted Docker Compose also means the proxy, the database
   and the release step are all described by files in this repository.
2. **Hostname: `167-235-52-206.sslip.io`.** No domain was supplied, and
   `ENVIRONMENT=production` refuses to start without an `https://` base URL — which
   needs a DNS name, because a certificate authority will not issue for a bare IP.
   `sslip.io` is public wildcard DNS resolving that label to this exact address, so
   Let's Encrypt can issue a genuine certificate over HTTP-01. Moving to a real
   domain later is one line in the host's env file plus a DNS record.

## 📋 Implementation Plan

### Phase 1 — The production deployment shape, in the repository

1. `deploy/Caddyfile` — automatic HTTPS from Let's Encrypt, HTTP redirected, HSTS,
   and the proxy headers the app's `--proxy-headers` uvicorn already trusts.
2. `deploy/compose.prod.yml` — proxy + Postgres (no published port) + `migrate`
   release job + app, with the app gated on `service_completed_successfully` and
   every required variable read from the host's env file.
3. `deploy/deploy.sh` — the repeatable release: sync the checkout to the host, build
   the image, run migrations, then swap traffic; refuses to run without the env file.
4. `deploy/README.md` — provisioning, the four variables, owner creation, rollback,
   and what rotating `SESSION_SECRET` costs.
5. Tests locking the shape down: the app waits for the migrate step, Postgres
   publishes no port, the proxy sets HSTS, production is pinned to `https://`, and
   no deployment file carries a secret.

### Phase 2 — Provision and release

1. Provision the host: Docker Engine + compose plugin, and a firewall that leaves
   only 22/80/443 open.
2. Generate the secrets on the host, write the env file (mode `0600`, never
   committed, never echoed), and run the first release.
3. Create the owner account with `trip-planner create-owner`, password on stdin.

### Phase 3 — Verify and record

1. Probe the live URL over TLS: `/login` → `200`, unauthenticated
   `/api/v1/trips` → `401`, unauthenticated `/api/v1/auth/me` → `401`; capture the
   certificate issuer and the HSTS header.
2. Sign in through a real browser against the deployed instance and attach
   screenshots to the PR as the evidence A05 asks for.

## ⚠️ Risks

- **Let's Encrypt rate limits on `sslip.io`.** It is on the Public Suffix List, so
  each label is its own registered domain and the shared limit does not apply.
  A failed issuance still leaves the site on the proxy's internal certificate, which
  would fail the TLS half of the test loudly rather than silently.
- **Single instance, single host.** A reboot without `restart: unless-stopped`
  would leave the milestone's URL dead; the compose file sets it.
- **`migrate` failing mid-release.** The app is gated on the migrate step
  completing, so a failed migration leaves the previous container serving rather
  than starting a new image against a half-migrated database.
- **Secrets live only on the host.** Losing the env file signs every session out
  and needs a new `SESSION_SECRET`; the README says so.

## Progress

PR: #13

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: The production deployment shape, in the repository

- [x] 1.1 `deploy/Caddyfile` — automatic HTTPS, HTTP redirect, HSTS — af0ccf3
- [x] 1.2 `deploy/compose.prod.yml` — proxy, private Postgres, migrate gate, app — af0ccf3
- [x] 1.3 `deploy/deploy.sh` — the repeatable release — af0ccf3
- [x] 1.4 `deploy/README.md` — provisioning, variables, owner, rollback — af0ccf3
- [x] 1.5 Tests locking the production deployment shape down — af0ccf3

### Phase 2: Provision and release

- [x] 2.1 Provision the host (Docker, firewall) — Docker 29.8.1 + compose v5.5.1; ufw allows only 22/80/443
- [x] 2.2 Generate secrets, write the env file, run the first release — `/srv/trip-planner/.env` (0600, host-only); released f23263e
- [x] 2.3 Create the owner account — `trip-planner create-owner`, password on stdin

### Phase 3: Verify and record

- [x] 3.1 Probe `/login`, `/api/v1/trips` and `/api/v1/auth/me` over TLS — 200 / 401 / 401, Let's Encrypt certificate, HSTS present
- [x] 3.2 Browser evidence of the deployed app, attached to the PR — login, signed-in trip list, and a trip created against the live database
