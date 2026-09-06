# Checkpoint 1 — Phase 1 complete (Steps 1.1 – 1.6)

- Checkpoint index: 1
- Steps covered: 1.1 … 1.6
- Commit range: `04a8ba8 … 5722517` (plan commit `a4912a8` precedes them)
- Touched areas: `frontend/src/styles/` (new), `frontend/src/index.css`,
  `frontend/src/main.tsx`, `frontend/package.json` + lockfile, `scripts/` (two new
  dependency-free gates), the gate's four restatements (`.ai/agentic.config.json`,
  the CI workflow, `AGENTS.md`, `SDLC.md`, `README.md`), `.ai/scripts/` (two new QA
  scripts).

## Checks

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ pass | `en`, `pl` in sync; no key added in Phase 1. |
| `python3 scripts/check_css_tokens.py` | ✅ pass | **new in Step 1.3** — 244 `var()` references across 38 files all resolve against `tokens.css`. This is the guard against the silent-CSS-failure case; it runs again at Step 2.5 when the bridge is deleted. |
| `python3 scripts/check_contrast.py` | ✅ pass | **new in Step 1.5** — 15 declared pairs, 12 body at ≥4.5:1 and 3 large/UI-boundary at ≥3:1. Full table in `contrast-table.txt`. |
| `(cd frontend && npm run typecheck)` | ✅ pass | |
| `(cd frontend && npm run test -- --run)` | ✅ pass | 127 passed / 127. Unchanged from `main` — Phase 1 changes no rule outside `:root` and no component. |
| `(cd frontend && npm run build)` | ✅ pass | CSS bundle 15.13 → 18.00 kB (the token layer, inlined by Vite's `@import` handling); the font ships as separate `unicode-range`-gated woff2 subsets. |
| `(cd backend && uv run ruff check .)` | ⏭️ not run | No file under `backend/` is touched in this phase, by the spec's own non-goal. Runs in full at the final gate. |
| `(cd backend && uv run pytest)` | ⏭️ not run | Same reason. `deploy-db-1` is up, so the final gate will verify the database layer rather than skip it. |

## Step review (`engine.stepReview: checkpoint`)

Reviewed `origin/main..5722517` against the `om-code-review` checklist. No blocker
and no major finding. Recorded, not fixed:

- **minor** — the bridge block re-declares `--radius-md: 0.75rem`, which the
  canonical block above it already sets to the same value. Harmless (identical
  value, later declaration wins), deliberate (it makes the one token whose meaning
  moves visible in the bridge's own diff), and it disappears with the bridge at
  Step 2.5.
- **nit** — `PLAN.md`'s Scope line still says the font ships as `wght` + `latin-ext`.
  The variable package publishes no separate `latin-ext.css`; its single `wght.css`
  carries every subset behind `unicode-range`. Logged in `NOTIFY.md` at Step 1.1;
  the plan text is left as written rather than rewritten mid-run.

## UI verification

Ran, and it is the only check in this phase that can see anything. The environment
is `.ai/scripts/test-env-up.sh` (the production app factory over the real build, one
origin), seeded by the new `.ai/scripts/qa-seed.py` with the brief's Malaysia trip —
15 days, 13 items, all three statuses, all five kinds, four deliberately empty days.
Captured by the new `.ai/scripts/qa-screenshots.sh` through the `agent-browser`
provider at 1440×1000.

Artifacts: `checkpoint-1-artifacts/` — ten non-empty PNGs, five routes × two locales.

- `01-login-{pl,en}.png`, `02-trips-{pl,en}.png`, `03-trip-create-{pl,en}.png`,
  `04-timeline-{pl,en}.png`, `05-day-detail-{pl,en}.png`

What they show, against `.ai/specs/assets/design-system-adoption/current-*.png`:

- Plus Jakarta Sans renders throughout, in the family rather than a fallback —
  the diacritics in *Przesiadka*, *śniadanie*, *bagaż rejestrowany* and
  *Pamiątki i pakowanie* keep their optical balance at 400 and 700.
- The palette is the design's: the `#0F3F6D` primary on links and controls in
  place of the skeleton's invented `#2f6f5e` green, the `#F8FAFC` canvas, `#E2E8F0`
  hairlines.
- The corrected status chips read as designed — *Gotowe* on `#ECFDF5`/`#047857`,
  *Do zarezerwowania* on `#FFFBEB`/`#B45309`, *Do zaplanowania* on `#F1F5F9`.
- **No layout movement**, which is the whole point of the bridge: every element
  sits where `current-*.png` has it. The component recipes and the grid are
  Phases 2 and 3.

### One evidence defect found and fixed inside this checkpoint

The first capture pass produced byte-identical PNGs for `pl` and `en` on every
authenticated screen. The cause is a real product behaviour rather than a script
bug: signed in, the owner's **stored** locale wins over the one chosen on `/login`,
because R01 makes the choice follow the owner rather than the browser. The capture
script now switches locale a second time through the header's own switch after
signing in. Re-captured; the ten files are now genuinely five routes in two
languages. A screenshot set that silently photographs one locale twice is worse
than none, so this is recorded rather than quietly corrected.

### An observation about the API, out of this spec's scope

`POST /api/v1/auth/login` answers `204` with its cookies **before** its request
transaction commits: FastAPI exits a `yield` dependency — here `get_db`, which owns
the commit — after the response has been sent. A client fast enough to reuse the
cookie inside that window is answered `401` by a server that has already accepted
it. A browser never is; two dependency-free scripts in a row were, every time.
`qa-seed.py` polls until the session is visible rather than sleeping blind. This
touches no file this spec may change (`backend/` is an explicit non-goal), so it is
recorded here and surfaced in the PR summary rather than fixed in this run.

## Verdict

✅ Checkpoint 1 passes. Phase 1 is complete and the application renders in the
design's typeface and palette with its layout untouched. Next: Step 2.1.
