# om-prepare-test-env — trip_planner specifics

Repo-local extension. Records what the generated launchers had to learn the hard
way, so the next run does not rediscover it.

## The environment shape, and why it is not the container

`.ai/scripts/test-env-up.sh` runs `create_production_app` directly with
`STATIC_DIR` pointed at `frontend/dist`, rather than building `deploy/Dockerfile`.
That keeps every property QA cares about — one origin serving both the API and
the *built* SPA, so cookies, CSRF and `mount_spa`'s deep-link fallback behave
exactly as deployed — while booting in seconds.

Building the image was tried first and abandoned: `docker compose build` hung for
20+ minutes at zero CPU on an image it had already built successfully, on a
machine carrying ~68 GB of images and several other live compose projects. If the
daemon is idle on your machine, `docker compose -f deploy/compose.yml up --build`
is still the closest thing to the deployed artifact and worth using for a release
check.

## Gotchas the launchers already handle

- **Compose 2.18 merges `ports`.** Layering a port override on
  `deploy/compose.yml` publishes *both* the base file's `8000:8000` and the
  override, so the port is not really configurable and the stack dies on
  `address already in use`. `!override` needs Compose ≥ 2.24.
- **PostgreSQL on :55432 is usually already up.** The test suite's own
  `docker compose -f deploy/compose.dev.yml up -d db` may run under a different
  compose project name, so looking for this project's container finds nothing and
  starting a second server loses the port race. The up script reuses *any*
  container publishing the port and records `dbStartedByThisRun` so the down
  script knows whether stopping it is its business.
- **QA uses its own database**, `trip_planner_qa`, dropped and recreated on every
  non-reused run. The suite's per-session throwaway databases live on the same
  server and must not meet QA's data.
- **The four required environment variables** (`DATABASE_URL`, `SESSION_SECRET`,
  `APP_BASE_URL`, `ENVIRONMENT`) are validated at startup by
  `create_production_app`, so a missing one is a crash naming it. `SESSION_SECRET`
  must be at least 32 characters.

## Chrome needs a short TMPDIR

`agent-browser` (and any Chrome launch) fails on this repository's agent
worktrees with:

```
FATAL:process_singleton_posix.cc:313] Socket path too long: …/SingletonSocket
```

Chrome derives its singleton socket path from `TMPDIR`, and the worktree paths
under `.ai/cezar/tmp/<uuid>/` exceed the ~104-byte `sun_path` limit. Export a
short one before any browser operation:

```bash
export TMPDIR=/tmp
```

With that set, `agent-browser doctor --json` reports 9/9 passing.

## The owner account

Created by the up script with `--replace`, so re-running it resets the password
rather than failing on an existing row. Address and password live in the
gitignored `.ai/qa/test-env.env`; they are disposable fixtures for a throwaway
database, never real credentials.
