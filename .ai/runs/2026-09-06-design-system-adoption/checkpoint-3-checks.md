# Checkpoint 3 — Phase 3 complete (Steps 3.1 – 3.4)

- Checkpoint index: 3
- Steps covered: 3.1 … 3.4
- Commit range: `91d5aa9 … 001e1dc` (plus the executor's NOTIFY commit `80cb3fe`)
- Touched areas: `frontend/src/styles/chrome.css` (new), `index.css`, `components.css`,
  `frontend/src/features/trips/AppShell.tsx`, `AppShell.test.tsx` (new), `TimelinePage.tsx`,
  `DayDetailPage.tsx`, `frontend/src/locales/{en,pl}.json`.

## Checks

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ pass | One new ICU key, `trip.headerContext`, present in both locales. |
| `python3 scripts/check_css_tokens.py` | ✅ pass | 268 `var()` references across 42 files resolve. |
| `python3 scripts/check_contrast.py` | ✅ pass | 15/15 pairs unchanged. |
| `(cd frontend && npm run typecheck)` | ✅ pass | |
| `(cd frontend && npm run test -- --run)` | ✅ pass | **135 passed / 135** (was 131; +4 in the new `AppShell.test.tsx`, covering the optional `context` and `dock` props rendered and omitted). |
| `(cd frontend && npm run build)` | ✅ pass | CSS 21.81 kB, gzip 6.51 kB. |
| `(cd backend && uv run ruff check .)` / `pytest` | ⏭️ not run | No file under `backend/` is touched. Both run in full at the final gate. |

## Step review (`engine.stepReview: checkpoint`)

Reviewed `590a4ee..001e1dc`. No blocker. Findings:

- **minor, accepted (3.2)** — `DayDetailPage` now issues one extra best-effort
  `GET /trips/:id`. The day endpoint returns only `trip_id`, so the header's context
  line is otherwise impossible on that route. It calls an endpoint that already
  exists, adds no client method beyond the existing `fetchTrip`, and its failure path
  is the line's absence and nothing else. It is worth naming because the spec's API
  section says "no `api/` module is touched" — that claim is about **preview
  surfaces**, which issue no requests at all, and this is not one. Flagged for the
  reviewer rather than assumed benign.
- **minor, accepted (3.2)** — the context line is hidden below 768px rather than
  truncated. At 360px there is no room for it and the trip is already named in the
  page's `<h1>`; a two-character ellipsis in the header would be chrome that says
  nothing.
- **good (3.1)** — the sign-out control took `.button-quiet`, which allowed the
  `.app-shell button:not([class])` catch-all from checkpoint 2 to be deleted exactly
  as its comment anticipated. The specificity workaround did not outlive its cause.
- **process nit (3.3)** — the executor's NOTIFY append landed as its own commit
  (`80cb3fe`) rather than inside a Step commit. Harmless to the 1:1 Step↔commit
  contract (it carries no code), recorded so the log is honest.

## UI verification

Twelve PNGs in `checkpoint-3-artifacts/` — the five routes × two locales at 1440×1000,
plus the timeline in both locales at **360×800**, which is the width the spec's own
edge-case table calls out.

What Phase 3 delivers, visible against `checkpoint-2-artifacts/`:

- The header is now real chrome: sticky, full-bleed, frosted (`--frost-bg` +
  `backdrop-filter` behind `@supports`, opaque fallback declared first), a `--hairline`
  bottom border, the wordmark in `headline-sm` on the left and the locale switch and
  sign-out grouped right. `--header-height` is a custom property, which is what the
  sticky filter bar in Step 4.4 and the day anchors in 4.5 will offset by.
- The trip title and date range appear in the header on trip-scoped routes, one line,
  ellipsised.
- The page grid is in place with the dock slot empty — **no screen passes a dock yet**,
  by design, so every screen renders as a single centred column at the reading measure
  and reserves nothing. Phase 4 fills the dock.
- At 360px the timeline is a single column with no horizontal scrolling.

## Verdict

✅ Checkpoint 3 passes. The chrome and the grid are in; what remains is putting the
screens into them. Next: Step 4.1.
