# Execution plan — design system adoption

- Date: 2026-09-06
- Slug: `design-system-adoption`
- Branch: `feat/design-system-adoption`
- Base: `main`
- Engine: `om-auto-create-pr-loop` (steps: 33, `--loop`: no — the spec's Implementation Plan exceeds `engine.loopStepThreshold` = 20)
- Source spec: `.ai/specs/2026-09-06-design-system-adoption.md` (merged to `main` as PR #10)
- Invoked by: `om-auto-implement-spec`

## Tasks

> Authoritative status table. `Status` is one of `todo` or `done`. On landing a Step, flip `Status` to `done` and fill the `Commit` column with the short SHA. The first row whose `Status` is not `done` is the resume point for `om-auto-continue-pr-loop`. Step ids and `Exec` cells are immutable once the plan is committed — per-Step commits touch only `Status` and `Commit`.

| Phase | Step | Title | Exec | Status | Commit |
|-------|------|-------|------|--------|--------|
| 1 | 1.1 | Load Plus Jakarta Sans (spec step 1) | dispatch:cheap | done | 04a8ba8 |
| 1 | 1.2 | Transcribe the token layer into `styles/tokens.css` (spec step 2) | group:A | done | 57c3081 |
| 1 | 1.3 | Add the compatibility bridge and the token-completeness check (spec step 3) | group:A | done | 53898f6 |
| 1 | 1.4 | Split the base layer into `styles/base.css` (spec step 4) | dispatch | done | 8fe1d89 |
| 1 | 1.5 | Contrast script over the token file (spec step 5) | dispatch:cheap | done | ec3851b |
| 1 | 1.6 | Phase-1 screenshot set — five routes × two locales (spec step 6) | inline | done | 5722517 |
| 2 | 2.1 | Split `components.css` and rewrite the button recipes (spec step 7) | group:B | done | 9a7d802 |
| 2 | 2.2 | Rewrite the input, select, textarea and date recipes (spec step 8) | group:B | done | 1f26ad4 |
| 2 | 2.3 | Rewrite the status chip recipes and add the dot (spec step 9) | group:B | done | 7e2151c |
| 2 | 2.4 | Elevation utilities, cards, dialogs and the frosted backdrop (spec step 10) | group:B | done | 87acf35 |
| 2 | 2.5 | Migrate off the bridge aliases and delete the bridge (spec step 11) | dispatch | done | 9a7c625 |
| 2 | 2.6 | Phase-2 screenshot set (spec step 12) | inline | done | 6ac2230 |
| 3 | 3.1 | Rebuild the header in `styles/chrome.css` and `AppShell` (spec step 13) | group:C | done | 91d5aa9 |
| 3 | 3.2 | The optional `context` prop on trip-scoped routes (spec step 14) | group:C | done | ceac09f |
| 3 | 3.3 | The optional `dock` prop and the responsive page grid (spec step 15) | group:C | done | a552668 |
| 3 | 3.4 | Phase-3 screenshot set, including 360px (spec step 16) | inline | done | 001e1dc |
| 4 | 4.1 | `/login` and `/trips` restyled (spec step 17) | dispatch | done | pending |
| 4 | 4.2 | The trip banner on `/trips/:id` (spec step 18) | group:D | done | pending |
| 4 | 4.3 | The readiness ring behind the optional `ring` prop (spec step 19) | group:D | done | pending |
| 4 | 4.4 | The sticky pill filter bar (spec step 20) | group:D | done | pending |
| 4 | 4.5 | The timeline rail, day anchors and item cards (spec step 21) | group:D | done | pending |
| 4 | 4.6 | `/trips/new` — the multi-stop creator (spec step 22) | dispatch | todo | — |
| 4 | 4.7 | `/trips/:id/days/:date` — the day detail (spec step 23) | dispatch | todo | — |
| 4 | 4.8 | Phase-4 screenshot set and the before/after pairs (spec step 24) | inline | todo | — |
| 5 | 5.1 | The preview primitives in `features/preview/` (spec step 25) | dispatch | todo | — |
| 5 | 5.2 | The share preview and its State A dialog (spec step 26) | dispatch | todo | — |
| 5 | 5.3 | The chat drawer preview (spec step 27) | dispatch | todo | — |
| 5 | 5.4 | The day-documents panel preview (spec step 28) | dispatch | todo | — |
| 5 | 5.5 | The reservation-disclosure preview in `ItemDialog` (spec step 29) | dispatch | todo | — |
| 5 | 5.6 | The `data-preview` census test (spec step 30) | dispatch:cheap | todo | — |
| 5 | 5.7 | Phase-5 screenshot set (spec step 31) | inline | todo | — |
| 6 | 6.1 | The icon sprite and the `<Icon>` wrapper (spec step 32) | dispatch | todo | — |
| 6 | 6.2 | Final verification pass — contrast, diacritics, locales, bundle (spec step 33) | inline | todo | — |

## Goal

Replace the walking skeleton's placeholder skin with the `modern_premium_travel_companion` design
system, and stand up the four V1 capabilities that do not exist yet — chat, sharing, attachments,
reservation data — as inert, honest preview surfaces in their designed positions.

## Scope

- `frontend/src/` only, plus two repo-level check scripts under `scripts/`.
- The style layer split into `frontend/src/styles/{tokens,base,chrome,components,screens}.css`, with
  `index.css` reduced to five ordered `@import` lines.
- Plus Jakarta Sans self-hosted via `@fontsource-variable/plus-jakarta-sans` (`wght` + `latin-ext`).
- The five existing routes restyled; additive optional props only
  (`AppShell.dock/context/drawer`, `ItemRow.railDot`, `ReadinessTile.ring`).
- `frontend/src/features/preview/` — `PreviewBadge`, `PreviewAction`, `PreviewNotice` — and the four
  preview surfaces the spec declares, all carrying `data-preview="true"`.
- The starter sprite `frontend/public/icons.svg` replaced by a bundled `frontend/src/assets/icons.svg`.

## Non-goals

- **No backend change** — not one file under `backend/`.
- No new route, no router change, no API call from any preview surface.
- No CSS framework, no component library, no Tailwind, no visual-regression tooling.
- No dark mode.
- Nothing from the spec's **Cut** table: booking/buying, budget and cost accounting, AI trip
  generation, PDF/e-mail import, a trip-wide documents centre, maps/routing, weather, export,
  "Zadania & Przygotowanie", guest comments, dead chrome.
- No locale key renamed or repurposed — new keys only.

## Delivery shape — one PR, six reviewable phases

The spec's rollback table describes six PRs. The pipeline contract (`om-auto-implement-spec`) is
**exactly one implementation PR per spec**, so this run ships all six phases on this single PR, with
one commit per Step and a checkpoint every ~5 Steps. Each phase therefore remains a contiguous,
independently reviewable and revertible commit range — with the spec's own caveat intact: Phase 2
deletes the compatibility bridge, so Phase 2 may only be reverted together with anything after it.

## Risks

- **Silent visual regression.** None of the six gate commands can see. Mitigated by the per-phase
  screenshot sets (Steps 1.6, 2.6, 3.4, 4.8, 5.7) and the two machine checks the spec invents: the
  token-completeness check (Step 1.3, re-run at 2.5 and 6.1) and the contrast script (Step 1.5).
- **An undefined `var()` surviving the bridge deletion.** CSS fails silently; the token-completeness
  check is the guard, run at both ends of the bridge's life.
- **`--radius-md` changes meaning under the same name** (10px → 12px) — the silent break
  `BACKWARD_COMPATIBILITY.md` names as the worst kind. The bridge pins the new value explicitly and
  the Phase 2 migration removes the alias entirely.
- **Preview surfaces outliving their features.** The `data-preview` census test (Step 5.6) fails on a
  forgotten preview and on an undeclared new one.
- **R02 regression while adding the readiness ring.** Step 4.3 ships the zero-denominator guard test.
- The backend `pytest` leg needs a reachable PostgreSQL; `deploy/compose.dev.yml`'s `db` service is
  up in this environment. A run reporting skips has not verified the database layer.

## External References

None — no `--skill-url` was passed. The design source is the in-repo export at
`.ai/specs/research/design/stitch_inteligentny_planer_podr_y/modern_premium_travel_companion/DESIGN.md`.

## Implementation Plan

Every Step is exactly one commit. `(automated)` and `(visual QA)` markers are the spec's own; the
`(visual QA)` items are a checklist, not tests.

### Phase 1 — The typeface and the token layer

**1.1 Load Plus Jakarta Sans (spec step 1)**
- Add `@fontsource-variable/plus-jakarta-sans` as a regular dependency; `package-lock.json` in the
  same commit per `AGENTS.md`.
- Import `wght.css` and `latin-ext.css` from `frontend/src/main.tsx`.
- *(automated)* `npm run build` succeeds and emits two woff2 assets.

**1.2 Transcribe the token layer into `styles/tokens.css` (spec step 2)**
- Full set: colour roles, type scale, radii, spacing, `--sidebar-width`,
  `--timeline-track-offset`, the three elevations, the corrected contrast values.
- Resolve the two `DESIGN.md` frontmatter/prose conflicts in favour of the prose
  (`--primary: #0F3F6D`, `--canvas: #F8FAFC`), keeping `#00294d` as `--primary-deep`; comment each
  resolution.
- *(automated)* the file contains no selector other than `:root`; every layout metric absent from
  `DESIGN.md` carries a comment naming its derivation.

**1.3 Add the compatibility bridge and the token-completeness check (spec step 3)**
- Alias **every** surviving skeleton name — `--colour-*`, `--space-1..8`, `--radius-sm/md/lg`,
  `--shadow-card`, `--font-sans` — in a clearly-marked bridge block.
- Reduce `index.css`'s `:root` block to an import of `tokens.css`.
- Add `scripts/check_css_tokens.py` (no dependencies, plain `python3`, in the house style of
  `scripts/check_locales.py`): collect every `var(--x)` under `frontend/src` and fail on any name
  `tokens.css` does not define. Wire it into `validation.commands`, the CI workflow and `AGENTS.md`
  together, as `AGENTS.md` requires.
- *(automated)* the new check passes and the full suite passes unchanged.

**1.4 Split the base layer into `styles/base.css` (spec step 4)**
- Move the reset, `body`, headings, links, focus ring and reduced-motion rules out of `index.css`.
- Bind `h1`–`h4` to the type scale; switch the focus ring to `--primary` with a 2px offset and add
  the `--primary-fixed` override for dark surfaces.

**1.5 Contrast script over the token file (spec step 5)**
- Add `scripts/check_contrast.py` (plain `python3`): parse `tokens.css`, compute WCAG ratios for
  every declared foreground/background pair, fail below 4.5:1 for body text and 3:1 for large text
  and UI boundaries. Wire it into `validation.commands`, CI and `AGENTS.md`.
- Record the resulting contrast table for the PR body.

**1.6 Phase-1 screenshot set (spec step 6)**
- Five routes × two locales via the `agent-browser` provider against a locally booted app.
- *(automated)* ten non-empty PNGs under the run folder's checkpoint artifacts.
- Non-blocking: if the environment cannot boot, record the skip reason in the checkpoint file, in
  `NOTIFY.md` and on the PR, and continue.

### Phase 2 — The component recipes, and the bridge goes

**2.1 Split `components.css` and rewrite the button recipes (spec step 7)**
- Recipes: primary, deep (`--primary-deep`), ghost, danger, danger-solid. No accent-button recipe —
  `--secondary` fails contrast behind text (3.56:1) and its documented uses are all cut.

**2.2 Rewrite the input, select, textarea and date recipes (spec step 8)**
- `#FFFFFF` on 1px `#CBD5E1`, `--radius`, a 2px `--primary` active outline; the invalid state adds a
  border colour and keeps the existing `role="alert"` text; a `:disabled` state now, because Phase 5
  needs it.

**2.3 Rewrite the status chip recipes and add the dot (spec step 9)**
- The three corrected triples from the spec's contrast table; a 6px dot as an `aria-hidden` sibling
  of the existing glyph.
- *(automated)* a test asserts each chip still exposes its glyph and its translated label.

**2.4 Elevation utilities, cards, dialogs and the frosted backdrop (spec step 10)**
- Cards and rows at elevation-1, hover/focus at elevation-2; dialogs and drawers at elevation-3 at
  `--radius-xl` over a `#0F172A`/20% backdrop with `backdrop-filter: blur(12px)` inside `@supports`
  and a 96%-opaque fallback declared first.

**2.5 Migrate off the bridge aliases and delete the bridge (spec step 11)**
- *(automated)* `grep -rE '\-\-(colour-|space-[0-9]|shadow-card)' frontend/src` returns nothing and
  the token-completeness check passes.

**2.6 Phase-2 screenshot set (spec step 12)**

### Phase 3 — The chrome and the grid

**3.1 Rebuild the header (spec step 13)**
- `styles/chrome.css` + `AppShell.tsx`: sticky, frosted with its `@supports` fallback,
  `--header-height` as a custom property, the **Smart Trip Planner** wordmark in `headline-sm`
  linking to `/trips`, controls grouped right.
- *(automated)* `AppShell`'s existing tests pass unchanged.

**3.2 The optional `context` prop (spec step 14)**
- Populated on trip-scoped routes, truncated to one line.
- *(automated)* new keys exist in both locales; a test renders `AppShell` without `context`.

**3.3 The optional `dock` prop and the page grid (spec step 15)**
- ≥1280px split at `var(--sidebar-width)`, capped at 90rem and centred; 768–1279px stacked with dock
  content above the canvas; <768px single column. Screens passing no dock render one centred column.

**3.4 Phase-3 screenshot set (spec step 16)**
- Adds a 360px capture of the timeline in both locales — twelve PNGs.

### Phase 4 — The screens

**4.1 `/login` and `/trips` (spec step 17)**
- The centred login card; trip rows as elevation-1 cards with the compact readiness value; the
  restyled empty state keeping its dashed border.

**4.2 The trip banner (spec step 18)**
- `--primary-deep` block, title in `display-lg` clamped at two lines with an accessible `title`, an
  icon-led meta row, the readiness tile inside the banner at ≥1280px reflowing below it when narrow.

**4.3 The readiness ring behind the optional `ring` prop (spec step 19)**
- A two-stop `conic-gradient` on a masked disc, `aria-hidden`, rendered only above a zero
  denominator, beside the untouched "x of y" text.
- *(automated)* the R02 regression guard: at a zero denominator no ring element and no percentage
  string is rendered and the text node is unchanged.

**4.4 The sticky pill filter bar (spec step 20)**
- Pills over the existing radio group (`:checked + label` styling, markup unchanged), sticky beneath
  the header at ≥768px, count chips on the draft recipe.

**4.5 The timeline rail (spec step 21)**
- Sticky two-line day anchors formatted through `Intl`, the continuous 1.5px track at
  `--timeline-track-offset`, `ItemRow`'s optional `railDot`, item cards with the icon tile; the
  empty-day invitation stays on the rail.

**4.6 `/trips/new` (spec step 22)**
- Eyebrow/title/subtitle heading, grouped field cards, the segmented route-mode control, numbered
  stage cards with icon removal carrying a visible accessible name, the summary in the dock, the
  full-width primary action. No change to form state, validation or submit.

**4.7 `/trips/:id/days/:date` (spec step 23)**
- Breadcrumb and eyebrow heading, ghost icon buttons keeping the disabled treatment, the shared item
  card, the dialog with the segmented status control (still a labelled radio group).

**4.8 Phase-4 screenshot set (spec step 24)**
- Five routes × two locales at desktop, plus the timeline and day detail at 360px — fourteen PNGs —
  plus a before/after pair per route for the PR body.

### Phase 5 — The V1 preview surfaces

**5.1 The preview primitives (spec step 25)**
- `frontend/src/features/preview/` with `PreviewBadge`, `PreviewAction`, `PreviewNotice`, their
  styles in `components.css`, and their copy in both locales.
- *(automated)* `PreviewAction` renders `aria-disabled="true"` and **not** native `disabled`, stays
  in the tab order, includes the badge text in its accessible name, and its `onClick` does nothing;
  `PreviewNotice` renders a real paragraph; every string resolves in `en` and `pl`.

**5.2 The share preview (spec step 26)**
- "Udostępnij" as a `<PreviewAction>` in the timeline's action row, opening a focus-trapped dialog
  carrying PR #3's State A consequence sentence, a preview "Utwórz link" and a `<PreviewNotice>`.
- *(automated)* focus trap and return; the fabrication guard — no token, URL field or revoke control.

**5.3 The chat drawer preview (spec step 27)**
- Header toggle, right-edge drawer at elevation-3 (full-height sheet below 1280px), the trip-context
  line, an empty transcript with its `<PreviewNotice>`, a disabled composer and send button.
- *(automated)* traps focus, closes on `Escape` and backdrop click, returns focus to the toggle, and
  its close button is focusable and first in order.

**5.4 The day-documents panel preview (spec step 28)**
- PR #4's heading and position, an empty state, a `<PreviewNotice>`, a `<label>` over a **disabled**
  `<input type="file">`.
- *(automated)* the input is disabled and labelled; the panel does not appear on the timeline; no
  fabricated document row.

**5.5 The reservation-disclosure preview (spec step 29)**
- Collapsed by default inside `ItemDialog`, expandable, three disabled fields, a `<PreviewNotice>`.
- *(automated)* never auto-opened by attaching, saving or changing status; moving an item to *done*
  still takes exactly one interaction and the readiness counter is unchanged.

**5.6 The `data-preview` census test (spec step 30)**
- Asserts the exact set of four preview surfaces at the positions the spec declares.

**5.7 Phase-5 screenshot set (spec step 31)**
- Including the drawer open and the share dialog open, both locales — sixteen PNGs.

### Phase 6 — Icons and the verification pass

**6.1 The icon sprite and the `<Icon>` wrapper (spec step 32)**
- `frontend/src/assets/icons.svg`: five item-kind glyphs, two chevrons, three workstream-B glyphs.
- `<Icon>` with `aria-hidden="true"` / `focusable="false"`; point the item card, day navigation and
  preview controls at it; delete `frontend/public/icons.svg`.
- *(automated)* no reference to the deleted file survives; every icon has a translated text label
  beside it; the build emits the hashed sprite; the token-completeness check still passes.

**6.2 Final verification pass (spec step 33)**
- The full validation gate, the contrast script over the final token file, the census test, bundle
  size before/after.
- *(visual QA)* diacritics at every weight in use; a `prefers-reduced-motion` capture; a
  forced-colors capture in which every preview still reads as unavailable through its badge text.

## Handoff & Notifications

- Live handoff: `.ai/runs/2026-09-06-design-system-adoption/HANDOFF.md`
- Notifications log: `.ai/runs/2026-09-06-design-system-adoption/NOTIFY.md`
