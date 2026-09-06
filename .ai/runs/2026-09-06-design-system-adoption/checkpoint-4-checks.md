# Checkpoint 4 — Phase 4 complete (Steps 4.1 – 4.8)

- Checkpoint index: 4
- Steps covered: 4.1 … 4.8
- Commit range: `4bbbad2 … 8d85675`
- Touched areas: every screen — `LoginPage`, `TripListPage`, `TimelinePage`, `TripCreatePage`,
  `DayDetailPage`, `ItemRow`, `ItemDialog`, `ReadinessTile`, `StatusChip`, the new
  `statusGlyph.ts`, `format.ts`, `AppShell`, the style layer's `screens.css` and
  `components.css`, both locale files, and `scripts/check_contrast.py`.

## Checks — the full eight-command gate, run in order

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ pass | Six new keys across the phase, all present in both locales. |
| `python3 scripts/check_css_tokens.py` | ✅ pass | 498 `var()` references across 43 files resolve. |
| `python3 scripts/check_contrast.py` | ✅ pass | **16** pairs now — Step 4.2 added `--danger-surface` on `--primary-deep` (11.45:1), because `--danger` on the deep banner fill is 1.6:1 and the banner carries a delete action. |
| `(cd backend && uv run ruff check .)` | ✅ pass | Run for completeness; no backend file is touched. |
| `(cd backend && uv run pytest)` | ✅ pass | **414 passed**, not skipped — `deploy-db-1` is reachable, so the database layer is genuinely verified. |
| `(cd frontend && npm run typecheck)` | ✅ pass | |
| `(cd frontend && npm run test -- --run)` | ✅ pass | **141 passed / 141** (was 135; +6 across the phase). |
| `(cd frontend && npm run build)` | ✅ pass | CSS 33.61 kB, gzip 7.97 kB. |

## Step review (`engine.stepReview: checkpoint`)

Reviewed `40d88c0..8d85675`. No blocker. The findings worth a reviewer's attention:

- **major, needs a human eye (4.7)** — the day detail's status control **was a `<select>`,
  not a radio group.** The spec's step 23 says the segmented pills leave it "still a
  labelled radio group" — describing a contract the code did not actually have. Following
  the spec therefore meant *converting* the widget: it is now
  `<fieldset><legend>Status</legend>` with three radios carrying their translated labels and
  chip glyphs. The group's accessible name and every i18n key are unchanged, and one test
  line moved from `selectOptions(getByLabelText('Status'))` to a `getByRole('group')` +
  `getByRole('radio')` query — a re-query by role, which is exactly what the spec prescribes
  when a test was coupled to a widget rather than a contract. This is the one place in the
  phase where "a coat of paint on the contract" was actually a change of widget, and it is
  called out rather than buried.
- **minor, accepted (4.2)** — the dock does **not** repeat the readiness figure that Q9's
  list mentions. Two identical "x of y" nodes would break the five existing assertions that
  treat the counter as unique, and R02 makes that counter the product's main object; the
  banner renders it once, where the export puts it.
- **minor, accepted (4.2)** — the banner is painted across `.page-heading` and `.trip-banner`
  joined by a `:has()`-scoped rule rather than duplicating the title. A second copy would be a
  second heading with the same accessible name. Without `:has()` support the heading degrades
  onto the canvas — legible, unstyled, never broken.
- **minor, accepted (4.5)** — one accessible name moves: the day link, from
  "sob, 10 paź Kuala Lumpur" to "paź 10", because the spec draws the anchor as `PAŹ / 10`.
  The stage label moved to the day's own column. Every existing assertion still holds.
- **minor, accepted (4.4, 4.6, 4.7)** — the segmented controls use `label:has(:checked)`
  rather than the spec's literal `:checked + label`: the radio sits **inside** its label in
  this codebase, so a sibling selector would have required a markup rebuild — the opposite of
  what the spec asks for.
- **minor, accepted (4.6)** — the creator's eyebrow renders through `AppShell`'s existing
  `breadcrumb` slot, CSS-scoped per screen, rather than a new prop. The spec's Scope names
  only `dock`, `context` and `drawer` as additive props, and 4.7 reuses the same arrangement
  with the breadcrumb and eyebrow as siblings, keeping one `<h1>` with one accessible name.

## UI verification

Fourteen PNGs in `checkpoint-4-artifacts/`: five routes × two locales at 1440×1000, plus the
timeline and the day detail in both locales at 360×800.

What Phase 4 delivers, against `checkpoint-3-artifacts/`:

- **The timeline is the export's screen.** The `--primary-deep` banner with the title in
  `display-lg`, the icon-led meta row and the readiness tile with its `conic-gradient` ring;
  the pill filter bar; and the structural change the spec is really about — a continuous
  1.5px rail with sticky two-line `Intl` date anchors, one card per item hanging off it with a
  status dot on the rail. The dock beside it carries the stage list with dates, the per-type
  counts and the route summary — **nothing new is computed**.
- **The creator** has the eyebrow/title/subtitle heading, grouped field cards, the segmented
  route-mode control, the numbered stage card with a named remove control, and the
  full-width `--primary-deep` action reading what it does rather than what the export promised.
  Its live summary is in the dock.
- **The day detail** has the breadcrumb, the stage eyebrow, ghost prev/next controls keeping
  the disabled-not-hidden treatment, the shared item card, and the status segmented group.
- **The item tiles are visibly empty circles.** That is Step 6.1's glyph slot, deliberately
  built and deliberately unfilled — the sprite is Phase 6. Same for the meta-row and
  day-navigation glyphs.

## Verdict

✅ Checkpoint 4 passes, and the full eight-command gate is green including the backend suite.
The application now looks like the design on every existing screen. What remains is
workstream B (Phase 5, the four inert preview surfaces) and Phase 6 (the icon sprite and the
verification pass).
