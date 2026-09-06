# Checkpoint 2 — Phase 2 complete (Steps 2.1 – 2.6)

- Checkpoint index: 2
- Steps covered: 2.1 … 2.6
- Commit range: `9a7d802 … 6ac2230`
- Touched areas: `frontend/src/styles/{components,screens,tokens}.css` (two of them new),
  `frontend/src/index.css` (now imports only), `frontend/src/features/trips/StatusChip.tsx`,
  `frontend/src/features/trips/items.test.tsx`.

## Checks

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ pass | No key added in Phase 2. |
| `python3 scripts/check_css_tokens.py` | ✅ pass | 257 `var()` references across 40 files resolve. **This is the check the phase was built around**: it ran immediately after the bridge was deleted, when an undefined `var()` would otherwise have dropped a property silently. |
| `python3 scripts/check_contrast.py` | ✅ pass | 15/15 pairs unchanged. |
| `(cd frontend && npm run typecheck)` | ✅ pass | |
| `(cd frontend && npm run test -- --run)` | ✅ pass | **131 passed / 131** (was 127; +4 from Step 2.3's colour-blind contract tests). |
| `(cd frontend && npm run build)` | ✅ pass | CSS bundle 20.94 kB (gzip 6.25 kB). |
| `(cd backend && uv run ruff check .)` / `pytest` | ⏭️ not run | No file under `backend/` is touched. Both run in full at the final gate. |
| `grep -rE '\-\-(colour-\|space-[0-9]([^a-z]\|$)\|shadow-card)' frontend/src` | ✅ empty | The bridge is gone and nothing reads it. |

## Step review (`engine.stepReview: checkpoint`)

Reviewed `160167c..6ac2230` against the `om-code-review` checklist. No blocker. Findings,
all raised by the executors themselves rather than found after the fact:

- **major, fixed in place (2.1)** — `.app-shell button` was an element catch-all at
  specificity (0,1,1), outranking every `.button-*` class recipe, so the rewritten
  primary recipe was invisible on every authenticated screen. Narrowed to
  `.app-shell button:not([class])`, which matches only the unclassed sign-out
  control. This is the one selector change in the phase, and without it Phase 2
  would have shipped a rewrite nobody could see.
- **minor, deliberate (2.1)** — `/login`'s submit is unclassed markup, so it cannot
  reach `.button-primary` without a TSX change Step 2.1 forbids. Its primary
  declarations are duplicated in `screens.css` with a comment naming Step 4.1 as the
  place the duplication goes.
- **minor, recorded (2.4)** — there is no 96%-opaque frost token in `tokens.css`, so
  the `@supports` fallback derives one with `color-mix(in srgb, var(--surface) 96%,
  transparent)`. Derived rather than invented, and it degrades to the fully opaque
  fallback where `color-mix` is unsupported. A token would be the better home if a
  second consumer appears.
- **minor, recorded (2.4)** — the disabled field pairs `--text-subtle` on
  `--surface-sunken` at 4.34:1, under the 4.5:1 body floor, and its boundary at
  2.93:1, under the 3:1 UI floor. WCAG explicitly exempts inactive components, and
  the spec's Step 8 prescribes exactly that treatment, so it is left as specified and
  named here rather than silently improved. Phase 5's preview fields are its main
  consumer — worth a look during the UX review.
- **nit, relayed (2.5)** — the spec's own verification grep for this Step,
  `grep -rE '\-\-(colour-|space-[0-9]|shadow-card)' frontend/src`, can never return
  empty after the migration: `--space-[0-9]` also matches the *canonical*
  `--space-2xs`, `--space-2xl` and `--space-3xl`. The boundary-guarded form
  (`--space-[0-9]([^a-z]|$)`) is the one that means what the spec intended, and it is
  empty. Anyone wiring this grep into CI needs the boundary.

## UI verification

Ten PNGs in `checkpoint-2-artifacts/`, five routes × two locales, captured the same
way as checkpoint 1 so the two sets diff directly.

What changed against `checkpoint-1-artifacts/`, i.e. what Phase 2 delivers:

- **Buttons** are on the design's recipes: the solid `#0F3F6D` primary at `--radius`
  (visible on *Dodaj element* / *Add item* and on the login card's submit), the ghost
  treatment on secondary controls. Nothing falls back to a browser default.
- **Fields** sit on `--surface` inside the corrected 1px `--field-border`, at
  `--radius`, with the 2px `--primary` active outline.
- **Status chips** carry the corrected triples and the design's 6px dot beside the
  existing glyph and translated label — *Do zarezerwowania* on `#FFFBEB`/`#B45309`,
  *Do zaplanowania* on `#F1F5F9`, *Gotowe* on `#ECFDF5`/`#047857`.
- **Cards** are elevation-1 on a hairline at `--radius-lg`, lifting to elevation-2 on
  hover *and* on `:focus-visible` — a hover-only lift is invisible to a keyboard, so
  both are declared in one rule.
- The layout is still the skeleton's single centred column. That is correct: the grid
  and the chrome are Phase 3.

## Verdict

✅ Checkpoint 2 passes. The two-vocabulary window is closed — the repository now holds
exactly one token vocabulary, the design's. Next: Step 3.1, the frosted header.
