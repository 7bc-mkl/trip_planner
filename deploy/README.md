# Deploying Smart Trip Planner

One image, one host, one database. The SPA is built into the same image that
serves the API, so there is one origin, one certificate and nothing to keep in
step (spec A12).

```
internet ──443──▶ caddy ──▶ app ──▶ db
                  TLS       :8000   (no published port)
```

Files in this directory:

| File | What it is |
|---|---|
| `Dockerfile` | The image: SPA build stage → FastAPI serving the bundle. |
| `entrypoint.sh` | `migrate` (the release step) and `serve` (takes traffic). |
| `compose.yml` | The same shape **locally**, for exercising the image. |
| `compose.prod.yml` | The deployment. TLS in front, database private, restarts. |
| `Caddyfile` | TLS, the HTTP redirect, HSTS. |
| `deploy.sh` | The repeatable release. |

## Provisioning a host

Anything that runs Docker will do. The current deployment is a Hetzner CPX22
(Ubuntu 26.04, 2 vCPU, 4 GB) — one instance, which is what this milestone needs.

```bash
# Docker Engine and the compose plugin.
ssh root@HOST 'curl -fsSL https://get.docker.com | sh'

# Only SSH and the two web ports. The database is not on this list and must
# never be: it is reachable on the compose network and nowhere else.
ssh root@HOST 'ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable'
```

### The hostname

`ENVIRONMENT=production` refuses to start unless `APP_BASE_URL` is `https://`,
and a certificate authority will not issue for a bare IP address — so the
deployment needs a DNS name even before it has a brand.

Until a real domain is registered this uses [sslip.io], public wildcard DNS that
resolves `167-235-52-206.sslip.io` to `167.235.52.206`. The certificate is a
genuine Let's Encrypt one; only the name is borrowed. Moving to a real domain is
an `A` record plus `APP_HOSTNAME` and `APP_BASE_URL` in the env file.

[sslip.io]: https://sslip.io

## First release

**1. Point DNS at the host.** With sslip.io there is nothing to do; with a real
domain, an `A` record to the host's address, confirmed before step 3 — Caddy's
first certificate attempt happens at startup.

**2. Write the env file on the host**, once, by hand. It never lives in this
repository and `deploy.sh` will not create it.

```bash
ssh root@HOST
mkdir -p /srv/trip-planner
umask 077
cat > /srv/trip-planner/.env <<EOF
POSTGRES_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
SESSION_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
APP_BASE_URL=https://167-235-52-206.sslip.io
APP_HOSTNAME=167-235-52-206.sslip.io
ENVIRONMENT=production
ACME_EMAIL=you@example.com
EOF
chmod 600 /srv/trip-planner/.env
```

The four variables the application itself requires are `DATABASE_URL`,
`SESSION_SECRET`, `APP_BASE_URL` and `ENVIRONMENT`; `compose.prod.yml` composes
`DATABASE_URL` from `POSTGRES_PASSWORD` so the password exists in one place.
`SESSION_SECRET` must be at least 32 characters — the app refuses a shorter one,
because a short secret looks configured.

**3. Release.**

```bash
./deploy/deploy.sh root@HOST

# Or, to pin an identity without editing ~/.ssh/config:
DEPLOY_SSH="ssh -i ~/.ssh/trip-planner -o IdentitiesOnly=yes" ./deploy/deploy.sh root@HOST
```

**4. Create the owner.** There is no sign-up; the owner account is made here, and
the password is typed at the prompt so it never reaches `argv` or the shell
history.

```bash
ssh -t root@HOST 'cd /srv/trip-planner/app && \
  docker compose -f deploy/compose.prod.yml --env-file /srv/trip-planner/.env \
  run --rm app trip-planner create-owner --email you@example.com'
```

Add `--replace` to set a new password for an existing owner — that is also the
recovery path for a forgotten one.

## Subsequent releases

```bash
git checkout main && git pull
./deploy/deploy.sh root@HOST
```

`deploy.sh` refuses a dirty working tree, ships exactly the commit you are on,
records its sha in `/srv/trip-planner/REVISION`, builds, runs migrations to
completion, and only then starts the app. A failed migration leaves the previous
container serving.

## Verifying a release

The milestone's own test (A05), run from anywhere:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://167-235-52-206.sslip.io/login
#  → 200   the SPA shell

curl -sS -o /dev/null -w '%{http_code}\n' https://167-235-52-206.sslip.io/api/v1/trips
#  → 401   nothing is reachable without a session (R08)
```

## Rolling back

Each phase is one Alembic revision with a working `downgrade`, so a rollback is a
checkout and a release:

```bash
git checkout <previous-sha>
./deploy/deploy.sh root@HOST
```

A release whose migration must also be undone needs the downgrade run explicitly
**before** deploying the older image, since the older code does not know the
newer schema:

```bash
ssh root@HOST 'cd /srv/trip-planner/app && \
  docker compose -f deploy/compose.prod.yml --env-file /srv/trip-planner/.env \
  run --rm app alembic downgrade -1'
```

## Operating notes

- **Logs.** `docker compose -f deploy/compose.prod.yml --env-file /srv/trip-planner/.env logs -f app`.
- **Rotating `SESSION_SECRET` signs every session out**, by design: the stored
  session token is a keyed HMAC under it. That is the lever to pull if a session
  is believed stolen.
- **Backups.** The database lives in the `trip-planner_db-data` volume and
  attachments live in the database, so one `pg_dump` covers everything:
  `docker compose … exec -T db pg_dump -U trip_planner trip_planner | gzip > backup.sql.gz`.
  Nothing schedules this yet.
- **`migrate-and-serve` is single-instance only.** It exists for platforms with
  no release hook. This compose file has one, so it is not used — and the day a
  second replica appears, every replica would otherwise race to migrate.
- **Reclaiming disk.** Each release builds a new image and leaves the previous
  one dangling; nothing prunes them, so a long-lived host eventually fails a
  build with no space left. `docker image prune -f` removes the dangling ones
  (it is left manual because pruning is destructive and this host has 75 GB).
- **One instance, one host.** No failover. A host that dies takes the URL with
  it; restoring is provisioning a new host and replaying this page.
