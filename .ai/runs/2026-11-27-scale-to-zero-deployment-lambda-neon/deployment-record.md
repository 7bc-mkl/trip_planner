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
