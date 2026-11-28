# Deployment record — Lambda + Neon (Steps 2.5–2.6)

No secret appears in this file. Values live in SSM `/trip-planner/*` (SecureString, eu-central-1).

## Step 2.5 — Neon project and first deploy (2026-11-28)

| What | Outcome |
|---|---|
| Neon project | `trips` (`broad-darkness-02702202`), **aws-eu-central-1**, Postgres 18.7, branch `production`. Linked with `neon init` (`neon.ts`); `neon deploy` reported no policy changes and pulled `DATABASE_URL` (pooled, `-pooler` host) and `DATABASE_URL_UNPOOLED` (direct) into `.env.local` (gitignored) |
| SSM | `/trip-planner/database-url-pooled`, `/trip-planner/database-url-direct` from those two; `session-secret`, `origin-verify-secret` generated; `probe-owner-password` for the probe account |
| App engine against Neon | both URLs connect through `db/session.py`'s `engine_options` (pooled with `DB_POOL=null` → NullPool + `prepare_threshold=None`; direct with the default pool); `channel_binding=require` works with the psycopg 3 driver |
| `deploy.sh` run 1–3 | failed before touching the stack, each fixed as a review-fix Step: Docker 20.10 has no `--provenance` (2.4-review-fix); SAM refuses empty `Key=` overrides (2.4-review-fix-2); SAM requires `--image-repository` for image functions (2.4-review-fix-3) |
| `deploy.sh` run 4 (`e6ca6c1`) | image built and pushed; **migrations 0001→0009 applied to Neon through the direct endpoint**; `sam deploy` created stack `trip-planner`; inbox receipt rule set activated |
| Owner | `probe@trips.botito.app` created from the built image against the direct endpoint. Cutover (`pg_restore --clean`) replaces it with the owner's real data |

## Step 2.6 — smoke probes on `https://trips.botito.app` (2026-11-28)

Run against `e6ca6c1`, then re-run against `b35e83f` (the reviewed head, redeployed): **16/16 pass both times.**

| Probe | Result |
|---|---|
| `GET /login` | 200 |
| Security headers on `/login`, an API response and an asset | all present; HSTS `max-age=63072000; includeSubDomains`; no `Server` header |
| Unauthenticated `GET /api/v1/trips` | 401 |
| `http://trips.botito.app/login` | 301 → `https://` |
| Raw Function URL `/login` | 403 `forbidden_origin` |
| Raw Function URL `/api/v1/health` | 200 (readiness exemption) |
| Hashed asset, second fetch | `x-cache: Hit from cloudfront`, `Cache-Control: public, max-age=31536000, immutable` |
| Wrong password / owner sign-in | 401 / 204 |
| Trip created | 201 |
| 4 MiB PDF upload, then download | 201; 200 with 4 194 304 bytes |
| 4 MiB + 1 byte upload | 413 `attachment_too_large` |
| A stored 10 MiB attachment (inserted as a pre-change row) | 200, 10 485 760 bytes in 1.06 s — streamed through CloudFront |
| Client IP for the login rate limit, with a spoofed `X-Forwarded-For: 203.0.113.99` | `login_attempt.source_ip` = the real viewer address. `CloudFront-Viewer-Address` arrives through the managed `AllViewerExceptHostHeader` policy |
| Inbox: SES mail to `inbox@trips.botito.app` | SES → S3 → SNS → CloudFront → web function → kick → worker; listed within ~8 s (quarantined: SES rewrites the envelope sender, so authentication alignment fails). Released from quarantine, it was fetched from S3, ingested, and appears in `/inbox` as `received`. Repeated after the redeploy: kicked and processed, no worker error |
| SNS subscription | confirmed by the app itself; dead-letter queue attached |
| Local run against Neon | `uvicorn` on this machine with the pooled `DATABASE_URL` from `.env.local`: health 200, `/login` 200, sign-in 204, and it read back the trip written through Lambda |

### Cold start after idle (spec "Done when")

Idle from 06:20:04 to 06:41:04 UTC (21 minutes); the probe ran at 06:41:04.

| Request | Time |
|---|---|
| First `GET /login` (Lambda cold start: image, Python, uvicorn, adapter readiness) | **4.72 s** (Lambda `Init Duration` 4 154 ms) |
| First sign-in (Neon resumes from suspend; Argon2; 0.4 s response floor) | **3.29 s** |
| Next API call, warm | 0.17 s |

**Zero compute while idle.** Neon's operation log shows `suspend_compute` at 06:25:45 and the next `start_compute` at 06:41:13, which was the probe. The probe's Lambda request paid a fresh init, so no instance was left running.

During the idle window, internet scanners sent 277 requests for paths like `/.env` and `phpinfo.php`, presumably after finding the new hostname in certificate-transparency logs. Each got the SPA's `index.html` (not any real file), and none touched the database, so Neon stayed suspended. This is the cost floor of any public hostname: it wakes Lambda for milliseconds, not the database.

## Owner account and cutover (2026-11-28)

- **No cutover needed.** The owner confirmed the Hetzner deployment holds no real data, so spec Phase 3's dump and restore are moot.
- **Test data wiped.** All application tables on Neon were truncated: the probe owner, the probe trips, the test attachments and the test inbox messages. The schema stays at head (`0009`), and the leftover test MIME objects were removed from the inbox bucket.
- **Owner account.** `michal.klosinski@gmail.com` (locale `pl`) was created from the deployed image. Its generated password is in SSM `/trip-planner/owner-password` (SecureString). Sign-in was verified (204), and `/me` returned the new owner. `/trip-planner/probe-owner-password` was deleted.
