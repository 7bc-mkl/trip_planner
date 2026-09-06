# Design system adoption — the walking skeleton gets its real visual layer

- Date: 2026-09-06
- Status: draft, awaiting confirmation of Q1 in **Resolved assumptions**
- Brief: "Let's make the application look like on the design."
- Predecessor: `.ai/specs/2026-09-05-walking-skeleton.md` (merged as PRs #2 and #6)
- Design source: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/`

## 📝 TLDR

The walking skeleton shipped every screen the product needs to plan a trip, and it shipped them in a
placeholder skin: a hand-picked green, a handful of ad-hoc greys, and a `--font-sans` declaring Plus
Jakarta Sans that no build step ever loads. The walking-skeleton spec said the full token set from
the design export would land "with the screens that need it in Phases 2 to 4"; the screens landed and
the tokens did not. This spec closes exactly that gap. It replaces the placeholder token set with the
`modern_premium_travel_companion` design system — palette, Plus Jakarta Sans type scale, radii,
spacing, elevation levels and the component recipes — and restyles the five existing routes to the
layout language of the export's screens. It is a presentation-layer change: no backend, no new
endpoint, no new product capability, no new route.

## 📝 Problem Statement

The application works and looks unfinished, and the two facts are independent — this is not a polish
request dressed up as a spec, it is unfinished work from a milestone that deferred it on purpose.

The evidence is in the repository, not in an opinion:

- `frontend/src/index.css:1-8` opens with a comment saying so in as many words: "This is the minimum
  that makes the screens this milestone ships look deliberate; the full token set from the design
  export lands with the screens that need it in Phases 2 to 4." All four phases have landed.
- `--font-sans` (`frontend/src/index.css:32`) names `'Plus Jakarta Sans'` first, and nothing in the
  repository ever loads that family. There is no `@font-face`, no `<link>` in `index.html`, no font
  package in `package.json`. Every screen renders in whatever the operating system offers as
  `ui-sans-serif`. The typography section of `DESIGN.md` — the tight negative tracking on headings,
  the positive tracking on small labels, the explicit promise that Polish diacritics keep their
  optical balance — describes a typeface the user has never seen.
- `--colour-accent: #2f6f5e` is a green invented for the skeleton. The design system's primary is
  `#0F3F6D`, a deep oceanic sapphire, and its secondary is a terracotta `#EA580C`. Neither appears
  anywhere in the codebase. The status colours at `index.css:540-550` are four hard-coded literals
  (`#b8781f`, `#8a5a12`, `#fdf6e9`, `#eef5f2`) invented for the same reason.
- The layout is a single 56rem centred column (`index.css:214-217`) on every authenticated screen.
  The design is a split-surface workspace: a 22rem contextual dock beside the itinerary canvas on
  desktop, a stack on tablet, a single column on mobile.
- `frontend/public/icons.svg` is the unmodified Vite starter sprite — six symbols (`bluesky-icon`,
  `discord-icon`, `documentation-icon`, `github-icon`, `social-icon`, `x-icon`) referenced from
  nowhere in `src/` or `index.html`. It is where the item-type icons the design calls for ought to
  live instead.

Why it matters beyond taste: D10 makes the success test "the Malaysia trip of October 2026 planned
end to end in the app", and D02 makes the owner the only user. A tool one person has to choose to
open every day, in preference to a mailbox and a spreadsheet that already work, is competing on
whether it is pleasant to sit in front of. That is the whole of the argument, and it is enough.

The before-and-after is attached to this spec's PR: `assets/design-system-adoption/current-*.png`
are screenshots of the running application today, and `mockup-*.png` are the proposed screens.

## 📝 Scope

### In scope

- The full `DESIGN.md` token set as CSS custom properties: colour roles, the Plus Jakarta Sans type
  scale, radii, the spacing scale, and the four documented elevation levels.
- Loading Plus Jakarta Sans for real, with the Latin Extended subset that Polish diacritics need.
- The component recipes the design specifies and this app already has surfaces for: buttons, status
  chips and badges, the timeline itinerary card, input fields, cards and their hover elevation, the
  modal treatment.
- The application chrome: the frosted sticky header with the **Smart Trip Planner** lockup, the
  responsive grid (a 22rem dock beside the canvas on desktop, stacked below 1280px), and sticky day
  anchors on the timeline.
- Restyling all five existing routes: `/login`, `/trips`, `/trips/new`, `/trips/:id`,
  `/trips/:id/days/:date`.
- Replacing the starter icon sprite with the item-type and chrome icons the restyled screens use.
- Keeping every accessibility and i18n contract the walking skeleton established — status never by
  colour alone, the focus-trapped item dialog, the filter bar as a real radio group, every string
  through i18next, `<html lang>` following the locale — and correcting the design's own contrast
  failures rather than shipping them.

There is **no data model and no API contract in this spec**: it adds no entity, no field, no
migration, no endpoint, and changes no request or response shape.

### Out of scope — and the honest authority for each cut

The design export is a picture of a *bigger product than this one*. Roughly a third of its pixels
depict capabilities that are already-recorded cuts. Restyling does not smuggle them in. This table is
the single authority; the per-screen sections below refer to it rather than repeating it.

| Cut from the export | Where it appears | Authority |
|---|---|---|
| The "VoyageAI Concierge" drawer, every AI card, "Zaplanuj z AI", "Zarezerwuj przez AI", "Inspiracje Asystenta" | Every screen | A05 (chat cut first), D03 |
| The PLN/EUR toggle, "SZACOWANY BUDŻET", the budget slider, all per-item prices | Timeline header, creator | D07, R04, brief Q04 open |
| Reservation codes, "Opłacono z góry", "Kup bilety online", vendor comparisons, ratings | Item cards | D04, R07 — not designed here; nothing in the export's booking surface is styled |
| Ticket-PDF pills, the upload dropzone, "Rezerwacje i Dokumenty" as a destination, photo cards | Creator, day detail, nav | A05 (attachments cut), brief Q03 open |
| "Eksportuj PDF", "Eksportuj do Google Calendar" | Timeline header, day detail | D12 (*Later*) |
| "Udostępnij" | Timeline header | A05; the link's shape is fixed by D08/D09, and spec PR #3 owns it |
| The per-day weather strip, "Podgląd trasy" and the route map, "Optymalizuj trasę z AI" | Timeline, day detail | D12 (*Later*) |
| "Zadania & Przygotowanie" | Day detail | Brief Q02, undecided |
| The notification bell, the avatar menu, "Centrum pomocy", "Status API", the marketing footer | Chrome | No feature behind any of them; chrome for a product with more in it |
| Dark mode | Not in the export | The export ships one light scheme; a second is new design work, not adoption (Q5) |

The consequence, stated plainly because it is the one thing likely to disappoint: **after this spec
ships, the application will still not look like the screenshots.** It will look like the same design
*system* applied to the product that actually exists. The screenshots show a trip with prices, an AI
column, a document vault and a weather strip; ours shows a trip with days, items, three statuses and
a counter. That gap is A05's, not this spec's, and Q1 below is the place to overturn the reading if
it is wrong.

Also out of scope, for reasons of blast radius rather than product scope:

- **No backend change.** Not one file under `backend/`.
- **No new route, no changed component behaviour, and no change to any existing prop.** Three
  components gain *optional* props (see Architecture); nothing is removed, renamed or given a new
  meaning.
- **No CSS framework.** No Tailwind, no CSS-in-JS, no component library — `AGENTS.md` names the
  stack as React + plain CSS, and a restyle is the worst moment to also migrate the styling
  strategy: every visual regression would be indistinguishable from a migration bug.
- **No visual-regression tooling** (Q7).

### Scope cohesion — why this is one spec and not three

An adversarial review of the first draft argued this bundles three capabilities: tokens and recipes;
layout and the timeline rail; iconography. The independence test is real — Phases 1 and 2 do function
without Phases 3 to 5. It stays one spec for two reasons.

First, the deliverable the brief asks for is "the application looks like the design", and the palette
without the layout does not deliver it: the single 56rem column is the thing that makes the timeline
read as a form rather than an itinerary. Half of this is not a shippable answer to the request, only
a shippable increment toward it.

Second, the split would be a document split, not a delivery split — each phase already ships as its
own PR against its own reviewable diff. What the review was really protecting against is the
compatibility bridge outliving its usefulness, and that is fixed directly: **the bridge is created and
deleted inside Phases 1–2** rather than surviving to Phase 5. If a phase slips, the repository is
left in a coherent state with one token vocabulary.

## 📝 Proposed Solution

Three layers, applied in that order, each independently shippable and each leaving the application
working.

**1. Retoken.** Replace the *contents* of the custom-property block, not the property names. The
existing screens make 197 `var()` references across six token families; repointing those names at the
design's roles restyles every screen at once, without touching a single selector. The design's own
role vocabulary lands alongside as the canonical set, and every surviving skeleton name becomes an
alias for one phase so the change can be verified screen by screen instead of in one unreviewable
diff.

**2. Re-recipe.** Rewrite the component blocks against the design's component section, which is
specific enough to implement directly: 40px primary buttons in `#0F3F6D` with a `#0C3257` hover,
confirmed chips on `#ECFDF5` with an `#A7F3D0` hairline and a 6px emerald dot, cards at elevation-1
lifting to elevation-2 on hover, dialogs at elevation-3 over a 12px-blurred `#0F172A`/20% backdrop.

**3. Re-lay-out.** Introduce the grid the design is built on and move the existing content into it.
This is the only layer that touches TSX, and it touches it as little as possible: a header that is
sticky and frosted instead of a bottom-bordered flex row, a page grid with a contextual dock, and a
timeline that renders as a rail with day anchors and status dots rather than a list of bordered
boxes.

### Alternatives considered

- **Adopt a component library (Radix Themes, shadcn/ui, Mantine) and re-express the tokens through
  it.** Rejected. It converts a styling task into a rewrite of every screen's markup, it puts a
  dependency between us and the design export for no capability we lack, and the accessibility
  properties this app already has — the focus-trapped dialog, the radio-group filter bar, the
  glyph-plus-text status chip — are hand-built precisely so they are testable. We would trade tested
  behaviour for untested behaviour to gain styling we are about to write anyway.
- **Tailwind plus a token config generated from `DESIGN.md`.** Rejected for this milestone, on the
  same argument plus one more: the design's frontmatter is already a token file. Converting it to CSS
  custom properties is a transcription; converting it to a Tailwind config is a transcription *and* a
  build-pipeline change *and* a rewrite of 798 lines of working CSS, all landing in the same PR as
  the visual change it is supposed to enable.
- **Copy the export's generated `code.html` files into the app.** Rejected outright. They are
  Tailwind-CDN documents built for a different product, with hard-coded Polish copy (violating R01 on
  its own), inline data, and markup for features we do not have. They are reference material.

### Research — what the neighbours do

Checked against the itinerary products the brief benchmarks (Wanderlog, TripIt, Google Travel) and
against how mature design systems ship tokens. Brief Q01 is still open; this was a design-language
comparison, not a feature benchmark. Two findings changed the design:

- **The vertical time rail is the genre's convention, and we should not be clever about it.** Every
  itinerary product renders a day as a dated anchor with a connected vertical line and one card per
  item, time on the left in tabular figures. The export draws exactly that; our current timeline
  draws a bordered box per day containing an unrailed list. This is the layout change with the most
  to gain, and it is why "tokens only" is not the whole answer.
- **Status gets a shape, not just a colour, everywhere.** TripIt's confirmed/unconfirmed and
  Wanderlog's booked markers are icon-led. Our glyph-plus-text chip already beats both on
  accessibility; adding the design's coloured recipes makes it match them on legibility. Keeping the
  glyph *and* adding the colour is strictly better than either.

What they carry that we can skip: density controls, map/list toggles, per-item vendor cards and
multi-traveller avatars — all serving products with more data per item than ours has.

## 📝 Architecture

The changed surface is `frontend/src/` and nothing else.

### The style layer, after

`frontend/src/index.css` is 798 lines and holds tokens, base rules, components and five screens'
worth of rules in one file. The token block roughly doubles under the full set and the component
blocks roughly double under the recipes. It gets split by concern, imported in a fixed order —
cascade order is the contract, so the imports live in one place and are commented as ordered:

```
frontend/src/styles/
  tokens.css        The DESIGN.md frontmatter, transcribed. Custom properties only,
                    no selector beyond :root. This file is the design contract.
  base.css          Reset, body, headings bound to the type scale, focus ring,
                    link defaults, reduced-motion.
  chrome.css        The header, the page grid, the dock, landmarks.
  components.css    Buttons, inputs, chips, cards, dialogs, empty states.
  screens.css       What is genuinely screen-specific: the login card, the trip
                    banner, the timeline rail, the creator's stage rows.
frontend/src/index.css   Five @import lines, in order, and nothing else.
```

Vite inlines CSS `@import` at build time, so the shipped bundle is one stylesheet either way and the
ordering stays visible in the CSS rather than depending on module evaluation order in a TSX file.
This is internal module structure — explicitly *not* a protected surface per
`BACKWARD_COMPATIBILITY.md`.

### Tokens: two levels, and the bridge

`tokens.css` carries the design's role names as the canonical layer — `--primary`, `--canvas`,
`--surface`, `--hairline`, `--text`, `--elevation-1..3`, the type-scale roles, the radius tiers, the
spacing scale, `--sidebar-width`, `--timeline-track-offset`. The full transcription belongs in the
file, not in this document; what belongs here is the three decisions that transcription cannot make
for itself.

**Naming.** The design's role names are adopted unprefixed rather than kept under `--colour-*`. The
prefix existed to separate a handful of invented colours from everything else; once every token *is*
a design role, the prefix distinguishes nothing, and matching the export's vocabulary is what makes a
value in `DESIGN.md` findable in the CSS. Values not in `DESIGN.md` (layout metrics) carry a comment
naming their derivation.

**Two contradictions inside `DESIGN.md`, resolved.** The frontmatter's `primary` is `#00294d` while
the prose's Primary role is `#0F3F6D` (the frontmatter's `primary-container`); the frontmatter's
`surface` is `#faf8ff` while the prose's neutral canvas is `#F8FAFC`. **The prose wins in both
cases** — it is the part that assigns roles to values, and the rendered screens match it. The
frontmatter's `#00294d` is kept as `--primary-deep`, which is what the trip banner in
`g_wny_pulpit_i_o_czasu` is actually filled with.

**The bridge, and the exact thing it must cover.** Repointing only `--colour-*` would break the
build: of the 197 `var()` references in `index.css`, only 81 are `--colour-*`. The rest are
`--space-1..8` (89), `--radius-sm` (14), `--radius-md` (4), `--radius-lg` (4), `--shadow-card` (4)
and `--font-sans` (1). Two of those are traps: the new scale renames `--space-N` to
`--space-{2xs..3xl}`, and `--radius-md` **changes meaning** under the same name (10px → 0.75rem/12px)
— the silent break `BACKWARD_COMPATIBILITY.md` calls the worst kind. So the bridge aliases **every
surviving skeleton name**, not just the colours:

```css
/* Bridge — created in Phase 1 step 3, deleted in Phase 2 step 11. Nothing new
   may reference these; they exist so the palette change and the rule rewrite are
   two reviewable diffs instead of one. */
--colour-accent: var(--primary);
--colour-bg: var(--canvas);
/* … the remaining --colour-* names … */
--space-1: var(--space-2xs);   /* 0.25rem */
--space-2: var(--space-xs);    /* 0.5rem  */
--space-3: var(--space-sm);    /* 0.75rem */
--space-4: var(--space-md);    /* 1rem    */
--space-6: var(--space-lg);    /* 1.5rem  */
--space-8: var(--space-xl);    /* 2rem    */
--radius-sm: 0.25rem;          /* kept: the design's `sm` tier, same value */
--radius-md: 0.75rem;          /* WAS 10px — the one value that moves */
--radius-lg: var(--radius-lg);
--shadow-card: var(--elevation-1);
--font-sans: /* unchanged name, now with a loaded family behind it */;
```

The bridge is what makes Phase 1 shippable on its own: the moment those aliases are in place, every
one of the 798 existing lines renders in the design's palette and the reviewer looks at five screens
rather than at a diff. Phase 2 migrates the rules off the aliases recipe by recipe and deletes the
bridge in its last step, so the two-vocabulary window is two phases long and closes before the
layout work starts.

### The typeface

`@fontsource-variable/plus-jakarta-sans` — the **variable** package, a regular dependency in
`frontend/package.json`, imported once from `main.tsx` as `wght.css` plus `latin-ext.css`. Two woff2
files, one per subset, covering the whole 200–800 axis; the static `@fontsource/…` package would be
eight files for the four weights we use, which is why it is not the one named. `latin-ext` is what
carries `ą ć ę ł ń ó ś ź ż`, and omitting it would fall back per-glyph — precisely the
optical-balance failure `DESIGN.md`'s typography section warns about. `font-display: swap` (the
package default) keeps first paint text-visible.

No Google Fonts `<link>`: the application is on the public internet from day one (D14), a third-party
font request is a third-party request on every page load for every user, and its failure mode — CDN
blocked, offline dev — is that the design silently does not apply.

### Iconography

`frontend/public/icons.svg` (the starter's six social symbols) is deleted and replaced by
`frontend/src/assets/icons.svg`, a sprite holding the glyphs the restyled screens use: the five item
kinds the API already defines (`accommodation`, `transport`, `activity`, `meal`, `other`), plus
chevrons for day navigation. Consumed through a small `<Icon name=… />` wrapper around
`<svg><use href=… /></svg>` with `aria-hidden="true"` and `focusable="false"` on every instance,
because in each case a translated text label sits beside it. Moving the sprite from `public/` into
`src/assets/` puts it through the bundler, so it is content-hashed and cacheable rather than served
unversioned.

No icon font and no icon package: a sprite of eight glyphs is smaller than any dependency that would
supply them, and it survives with CSS disabled in a way an icon font does not.

### Component signatures — what actually changes

The first draft claimed no component API changes at all. That was wrong, and the correction matters
because additive optional props are the mechanism the layout work uses:

| Component | Change | Breaking? |
|---|---|---|
| `AppShell` | Two new **optional** props: `dock?: ReactNode` (the contextual column) and `context?: ReactNode` (the header's trip context). Existing `{ title, breadcrumb?, actions?, children }` unchanged. | No — additive |
| `ItemRow` | One new **optional** prop: `railDot?: boolean`, so the timeline can render the status dot on the rail and the day detail can leave it off. | No — additive |
| `ReadinessTile` | One new **optional** prop: `ring?: boolean`. The banner passes it; the compact list variant does not. | No — additive |
| Everything else | Unchanged: `StatusChip`, `FilterBar`, `ItemDialog`, `ConfirmDialog`, `LocaleSwitch`. | — |

Nothing else moves: no route, no loader, no state shape, no `data-status` / `data-nothing-tracked`
test hook (they are load-bearing for both the test suite and the colour-blindness contract), and no
locale key renamed or repurposed — new keys only, which `BACKWARD_COMPATIBILITY.md` §4 permits and the
parity gate enforces.

## 📝 UI/UX

Each screen lists what is adopted from the export and what has to change in TSX. What the export
shows and we do not build is in the **Out of scope** table above and is not restated per screen.

Mockups of the proposed screens and screenshots of the current ones live in
`assets/design-system-adoption/` and are attached to this spec's PR:

| | Screen | Evidence |
|---|---|---|
| Proposed | Tokens, type scale and component recipes | [`mockup-01-tokens-and-components.png`](assets/design-system-adoption/mockup-01-tokens-and-components.png) |
| Proposed | `/trips/:id` — banner, filter bar, rail, dock (Polish) | [`mockup-02-timeline.png`](assets/design-system-adoption/mockup-02-timeline.png) |
| Proposed | `/trips/:id/days/:date` — day detail and the item editor (**English**) | [`mockup-03-day-detail.png`](assets/design-system-adoption/mockup-03-day-detail.png) |
| Proposed | `/trips/new` — the multi-stop creator (Polish) | [`mockup-04-trip-creator.png`](assets/design-system-adoption/mockup-04-trip-creator.png) |
| Current | `/login`, `/trips`, `/trips/:id`, `/trips/:id/days/:date`, `/trips/new` | `current-01…05-*.png` |

Two locales on purpose: R01 makes both first-class, and a spec that only ever pictures one is not
showing the product it describes.

### Cross-cutting

- **The header.** Sticky, `rgba(255,255,255,0.85)` with `backdrop-filter: blur(8px)`, a hairline
  bottom border, and `--header-height` exposed as a custom property for the sticky layers below it.
  Left: the **Smart Trip Planner** wordmark in `headline-sm`, linking to `/trips` (D01 — the export's
  "VoyageAI" lockup supplies the layout, never the name). Right: the locale switch and sign-out.
  Between them, on trip-scoped routes only, the trip title and date range, truncated with an
  ellipsis — the export's trip picker without being a picker, since there is one trip in view and
  `/trips` is one click away.
  - **The export's four-tab nav is not adopted** (Q4). Two of its four destinations do not exist
    here, and a nav bar with dead tabs is worse than no nav bar.
- **The page grid**, owned by `chrome.css` and applied by `AppShell`:
  - ≥1280px: `grid-template-columns: minmax(0, 1fr) var(--sidebar-width)`, `gap:
    var(--gutter-desktop)`, capped at 90rem and centred. At that cap the dock is 22/90 of the width —
    close to 3 of 12 columns rather than the export's nominal 4, because 22rem is the export's own
    `sidebar-width` token and the fixed rem value is the one worth being faithful to.
  - 768–1279px: one column; dock content renders **above** the canvas as a horizontal summary strip,
    not below it — on a tablet the readiness figure is the thing worth seeing first.
  - <768px: one column, `--gutter-mobile`, same strip.
  - Screens passing no dock render a single centred column and do not reserve the space.
- **What fills the dock**, now that the export's concierge drawer is cut (Q9): trip metadata
  promoted out of the main column — the readiness figure, the stage list with dates, the per-type
  item counts, the route summary. Nothing new is computed; existing content moves.
- **Motion.** Hover elevation and the header blur are the only transitions, both ≤150ms, both inside
  `@media (prefers-reduced-motion: no-preference)`, as is the design's "subtle scale transition" on
  primary buttons at `scale(1.01)`.
- **Contrast is corrected, not inherited.** Every foreground/background pair is verified to WCAG AA
  (4.5:1 body text, 3:1 large text and UI boundaries). Three of the design's own values fail and are
  darkened in `tokens.css` with the ratio recorded beside them; the corrected set is fixed here
  rather than left to a step-time rule:

  | Role | `DESIGN.md` | Ratio | Adopted | Ratio |
  |---|---|---|---|---|
  | Confirmed chip text on `#ECFDF5` | `#059669` | 3.58:1 ❌ | `#047857` | **5.21:1** ✅ |
  | In-progress chip text on `#FFFBEB` | `#D97706` | 3.07:1 ❌ | `#B45309` | **4.84:1** ✅ |
  | Draft chip text on `#F1F5F9` | `#475569` | 6.92:1 ✅ | unchanged | 6.92:1 ✅ |
  | `--secondary` `#EA580C` as a text/background pair with white | — | 3.56:1 ❌ | defined as a token, **not used behind text** | — |
  | `--text-subtle` `#64748B` on `#FFFFFF` | — | 4.76:1 ✅ | unchanged; not permitted below 13px | 4.76:1 ✅ |

  `label-sm` (11px) therefore uses `--text-muted` (`#334155`, 10.35:1 on white), and the 11px chip
  labels use the corrected chip foregrounds above.

### `/login`

- **Adopted:** a single elevation-1 card at `--radius-lg` with `1.5rem` padding, centred on the
  `#F8FAFC` canvas, wordmark above it, locale switch beside the wordmark; inputs at 1px `#CBD5E1`
  with the 2px `#0F3F6D` active outline; the submit button on the primary recipe.
- **TSX:** none. The markup already has the shape; only rules change.

### `/trips` — trip list

- **Adopted by analogy** (Q10 — no counterpart in the export, and leaving it in the old skin would
  make the app look half-migrated): each trip becomes an elevation-1 card at `--radius-lg`, lifting
  to elevation-2 with a `#CBD5E1` border on hover and `:focus-visible`; title in `headline-md`, dates
  and route in `body-sm` `--text-muted`, compact readiness value right-aligned. The empty state keeps
  its dashed border, which is the one place the export's dropzone recipe transfers cleanly.
- **TSX:** none.

### `/trips/new` — the multi-stop creator

Reference: `kreator_nowej_podr_y`, `kreator_podr_y_manualny_i_wieloodcinkowy`. See
[`mockup-04`](assets/design-system-adoption/mockup-04-trip-creator.png).

- **Adopted:** the two-column split, with the live summary panel promoted into the dock — exactly the
  "trip at a glance" card the export puts there; the eyebrow / `headline-xl` title / `body-lg`
  subtitle heading treatment; grouped field cards with hairline separators instead of the current
  bordered `fieldset`; the route-mode radios rendered as a **segmented control** (a real radio group
  underneath — the segmentation is `:checked + label` styling, not a rebuild as buttons); stage rows
  as numbered cards with an icon remove-button carrying a visible accessible name and a ghost "add
  stage"; the primary action full-width at the foot in `--primary-deep`, as the export's "Wygeneruj
  plan podróży" is.
- **TSX:** small. The summary paragraph moves into the dock slot, and each route-mode label gains a
  `<span>` for the segmented control to paint. No change to the form's state, validation or submit.

### `/trips/:id` — the timeline

Reference: `g_wny_pulpit_i_o_czasu`. The screen with the most to gain and the most to get wrong. See
[`mockup-02`](assets/design-system-adoption/mockup-02-timeline.png) against
`current-03-timeline.png`.

- **The trip banner.** The export's dark header block: `--primary-deep` fill, `--radius-lg`, white
  type, title in `display-lg` (`display-lg-mobile` below 768px), and a meta row beneath carrying the
  date range, day count and route summary. The readiness tile sits inside the banner on the right at
  ≥1280px, as the export's "STATUS LOGISTYKI" tile does, and drops below the meta row when the banner
  narrows.
- **The readiness tile.** Layout adopted; **arithmetic not** — the walking-skeleton spec already
  established that the export's own numbers contradict R02, and nothing here revisits that.
  Concretely (Q8): the ring renders only when the denominator is greater than zero; the
  `data-nothing-tracked="true"` state keeps today's neutral, ringless, percentage-free treatment,
  because a 0% ring reads as failure at a denominator where a percentage is undefined. The ring is a
  two-stop `conic-gradient` on a masked disc — no SVG, no library — is `aria-hidden="true"`, and sits
  beside the existing "x of y" text node, which remains the only accessible expression of the value.
- **The filter bar.** Pill-shaped filters in the export's day-selector style: unselected as ghost
  pills with a `--hairline` border, selected as solid `--primary` with white text. The markup stays a
  `<fieldset>` of radios with a `<legend>`; the pills are `:checked`-driven label styling. The
  per-type count chips keep the draft-badge recipe and stay non-interactive. The bar becomes sticky
  beneath the header at ≥768px — on a fifteen-day trip the filter currently scrolls away exactly when
  it is most wanted.
- **The timeline rail** — the structural change of the spec. A day is a sticky two-line date anchor
  (`PAŹ / 10`, formatted through `Intl`) with a 1.5px `--hairline` line running down at
  `--timeline-track-offset`, and one card per item hanging off it, each with a status dot on the rail
  in its status colour. The rail runs continuously between sparse days rather than restarting per
  day. The empty-day invitation keeps its place on the rail rather than becoming a gap.
- **The item card.** Time in bold tabular figures on the left, the type icon in a rounded tile beside
  it, title in `headline-sm`, notes in `body-sm` `--text-muted`, status chip top-right. The type
  stops being a grey text pill and becomes icon-plus-label.
- **TSX:** moderate, confined to structure. `TimelinePage` renders the banner and passes the dock;
  the day list gains the anchor/rail wrapper; `ItemRow` gains the icon tile and the optional rail
  dot. No state, no data, no removed prop.

### `/trips/:id/days/:date` — the day detail

Reference: `szczeg_y_dnia_i_aktywno_ci`. See
[`mockup-03`](assets/design-system-adoption/mockup-03-day-detail.png).

- **Adopted:** breadcrumb in `label-md` `--text-subtle` above a `headline-xl` day heading with the
  derived stage as an eyebrow; prev/next day as ghost icon buttons keeping the disabled-not-hidden
  treatment and its reasoning; the same item cards as the timeline, so an item looks like itself on
  both screens; the item editor as an elevation-3 dialog at `--radius-xl` over a 12px-blurred
  `#0F172A`/20% backdrop, fields on the input recipe, status as the segmented pill group.
- **The status control is still the point of this screen**, and now it looks like it: the three
  statuses as a segmented group of pills in their chip colours, the selected one filled. It remains a
  radio group with visible labels and glyphs — the pill is a coat of paint on the contract, not a
  replacement for it.
- **TSX:** small. A wrapper around the status radios and an icon slot in the day navigation.

### The accessibility contract, as assertions

Each of these is already asserted in `frontend/src/**/*.test.tsx` and must still pass, unchanged,
after every phase:

- The status chip renders a translated text node and a `data-status` attribute; colour is an addition
  to the glyph and the label, never a replacement. The new rail dot is `aria-hidden` decoration
  beside the chip.
- The item dialog traps focus and returns it to its trigger.
- The filter bar is a real radio group with a legend; the pills are styling.
- Every string comes from i18next with a key in both locales; `scripts/check_locales.py` is the
  enforcement.
- `:focus-visible` is never removed. The ring moves to `--primary` with a 2px offset, and switches to
  `--primary-fixed` (`#D3E4FF`) on dark surfaces via a scoped override — a `#0f3f6d` ring on a
  `#00294d` banner is invisible.

## 📝 Edge Cases & Failure Scenarios

| Case | Behaviour |
|---|---|
| The webfont fails to load (blocked, offline, corrupt cache) | `font-display: swap` shows the fallback stack immediately and swaps in when it arrives. No rule depends on the webfont's presence. Nothing errors. |
| Polish diacritics fall back per-glyph | The failure the `latin-ext` subset exists to prevent, and it is silent — the page looks *almost* right. Hence the explicit rendering check in Phase 1 step 1 and again in step 26. |
| A very long trip title | The banner title clamps to two lines with an accessible `title`; the header's trip context truncates to one line. Neither pushes the readiness tile off the banner. |
| A trip with zero items | The tile stays in its `data-nothing-tracked` state — no ring, no percentage, muted value — and every day on the rail shows its invitation. Easy to regress while adding a ring, which is why step 18 tests it explicitly. |
| A fifteen-day trip with sparse items | The rail runs continuously between sparse days; sticky day anchors keep the current date on screen. |
| Three sticky layers on a short viewport | The day anchor's `top` is `calc(var(--header-height) + var(--filter-bar-height))`, both custom properties; below 768px the filter bar stops being sticky — a phone gives up the filter before it gives up the plan. |
| `backdrop-filter` unsupported (older Firefox, some Linux GTK builds) | Every frosted surface declares its solid fallback first and the blur inside `@supports`. The fallback is 96% opaque rather than 85%, so text stays legible without the blur. |
| `prefers-reduced-motion: reduce` | No transitions, no hover scale. The ring renders at its final value. |
| Forced-colors / high-contrast mode | Elevation and background tints disappear; hairlines, glyphs and text carry the interface. Nothing here conveys meaning through a shadow or a background alone, which is what makes that survivable. |
| 200% zoom / 320px viewport | Same code path as mobile: single column, no horizontal scrolling, dock content above the canvas. |
| A test asserts on a class name a phase renames | The suite queries by role, label and text — but if one breaks, it was coupled to styling, and the fix is to re-query by role, never to keep the old class as a hostage. Any such change is called out in its PR. |
| An undefined `var()` survives the bridge deletion | CSS fails silently: the property is dropped and the element loses its padding or colour with no error anywhere. Step 3 and step 25 both run the token-completeness check for exactly this reason. |
| The bundle grows | The font is the only meaningful addition: two variable woff2 files, roughly 45–55 KB total, cached across navigations. CSS grows by an estimated 400–600 lines, a few kilobytes compressed. Build output size is recorded before Phase 1 and after Phase 5. |

## 📝 Risks & Impact Review

- **Blast radius: every screen, no data.** This spec can make the application ugly or unusable; it
  cannot lose a trip, corrupt a row, or break the API. No migration, nothing to reconcile. That
  asymmetry is why the risk is `risk-low` despite touching every route.
- **Rollback, per phase**, because this ships as five PRs and not one:

  | Phase | Reverting it alone leaves | Independently revertible? |
  |---|---|---|
  | 1 (tokens, font) | The old palette and font stack; nothing else depends on it yet | Yes |
  | 2 (recipes + bridge deletion) | **No** — Phase 2 deletes the bridge, so reverting it alone would leave Phase 3+ rules referencing tokens the revert restores under different meanings. Revert 2 only together with anything after it. | Only with its successors |
  | 3 (chrome, grid) | The old single-column shell; screens still styled | Yes |
  | 4 (screens) | The new grid with the previous screen rules | Yes |
  | 5 (icons, verification) | The starter sprite back; everything else intact | Yes |

  The one non-independent phase is called out rather than hidden, and it is the price of closing the
  two-vocabulary window early instead of late.
- **The genuine risk is silent regression.** A restyle passes `typecheck`, `test` and `build` while
  looking wrong, because none of the six gate commands can see. The mitigation is the verification
  split below — every step declares whether it is machine-verified or eyes-verified, and the
  eyes-verified ones are a QA checklist, not a test.
- **Contract compatibility:** none of the seven protected surfaces in `BACKWARD_COMPATIBILITY.md` is
  touched. §4 (translation keys) is the only one in the neighbourhood, and this spec is additive
  there. Component props are additive-optional, and internal file layout is explicitly unprotected.
- **Product-decision compatibility:** the cut table is the audit. Every element of the export that is
  *not* implemented has a named authority, and no element is implemented that a decision excludes.
  This spec proposes to supersede nothing.
- **Scope creep has a specific shape here:** every screenshot in the export is an invitation to build
  the feature it depicts. A PR in this series that adds a budget figure, a document pill or an
  assistant panel is out of scope on its face, whatever it looks like.

## 📝 Decisions in play

| Id | How this spec relies on it |
|---|---|
| D01 | The brand rendered is **Smart Trip Planner**; the export's "VoyageAI" lockup supplies layout only. |
| D05, R02 | The readiness tile's layout is adopted and its arithmetic is not; the ring is suppressed at a zero denominator. |
| D04, R07 | Nothing in the export's booking, pricing or vendor surface is styled. |
| D07, R04, brief Q04 | Budget and currency chrome is not styled; the currency question stays open and unprejudiced. |
| D08, D09 | "Udostępnij" is not styled into existence here; spec PR #3 owns sharing. |
| D12, N01 | Weather, maps, PDF and calendar export are *Later*, not excluded — this spec styles nothing for them and forecloses nothing. |
| D14 | Drives self-hosting the font rather than a third-party CDN request. |
| A05 | The authority for every AI, chat, attachment and document cut in the table above. |
| R01 | Both locales are first-class in the visual work too: every screenshot set is captured in Polish and English, and the type scale is verified against Polish diacritics. |
| Brief Q02, Q03 | Task lists and attachments stay unstyled and unbuilt while the questions are open. |

This spec proposes to supersede none of them.

## ⚠️ Resolved assumptions (autonomous defaults)

This spec was written in an unattended run. The questions below were resolved by the run itself, each
toward the most reversible, smallest-surface answer, and each is listed here to be overridden before
merge rather than after.

| # | Question | Applied default | Why | Confirm? |
|---|---|---|---|---|
| Q1 | "Look like the design" — restyle the product that exists, or also build the capabilities the export depicts (AI concierge, budget, documents, sharing, weather)? | **Restyle only.** Presentation layer, no new capability. | Every depicted capability is an already-recorded cut (A05, D04, D07, D08, D12) with its own authority, and two have specs in flight (PRs #3 and #4). Building them here would silently overturn A05 and duplicate open work. The consequence is real, though: the app will still not look like the screenshots, because a third of them is features we do not have. | ⚠ **NEEDS HUMAN CONFIRMATION** |
| Q2 | How is Plus Jakarta Sans delivered? | **Self-hosted** via `@fontsource-variable/plus-jakarta-sans`, `wght` + `latin-ext`. | No third-party request from a publicly deployed app (D14), works offline in development, and `latin-ext` is what makes Polish diacritics render in the family rather than per-glyph. The variable package is two files against the static one's eight. One reversible dependency. | ok |
| Q3 | CSS-only, or may the restyle change markup? | **CSS-first**; TSX changes only where the design needs structure that does not exist. Three components gain optional props (`AppShell.dock`, `AppShell.context`, `ItemRow.railDot`, `ReadinessTile.ring`); nothing existing is changed or removed. | Keeps the diff reviewable and keeps every existing test meaningful: if roles and existing props do not move, a red test means a real regression. Additive optional props are non-breaking. | ok |
| Q4 | Adopt the export's four-tab top navigation? | **No tab row.** Brand, trip context, locale and sign-out; only destinations that exist are linked. | Two of the four tabs lead to cut features. Dead navigation is worse than none, and adding it would be the one place a restyle leaked scope. | ok |
| Q5 | Ship a dark mode? | **No.** Light scheme only. | The export defines one scheme; a dark palette is new design work, not adoption. Purely additive later. | ok |
| Q6 | Keep one 798-line `index.css` or split it? | **Split** into `styles/{tokens,base,chrome,components,screens}.css`, imported in a fixed, commented order. | The file roughly doubles under this spec. File layout below a boundary is explicitly unprotected, and separating the token file from everything else is what the design-system practice this spec benchmarks converges on. | ok |
| Q7 | Add visual-regression tooling (Playwright snapshots, Storybook, Chromatic)? | **No new tooling.** Verification is the vitest suite for what is assertable, plus a declared manual QA checklist and per-phase screenshot sets in both locales through the configured browser provider. | The honest counter-argument — that this leaves the *visual* half of a visual change unverified by machine — is real, and the mitigation is not to pretend otherwise: every step below is labelled **(automated)** or **(visual QA)**, so nothing is called a test that a human has to look at. Adding VRT is its own spec with its own flakiness budget, and it is additive whenever the owner wants it. | ok |
| Q8 | Adopt the export's percentage progress ring on the readiness tile? | **Yes, arithmetic unchanged and suppressed at zero:** renders only above a zero denominator, `aria-hidden`, never replaces the "x of y" text. | R02 owns the arithmetic and the walking-skeleton spec already documented why a zero denominator gets no percentage. This takes the export's shape without its sums. | ok |
| Q9 | The export's right-hand column holds the cut concierge drawer. What goes there? | Existing trip metadata promoted out of the main column: readiness, stage list with dates, per-type counts, route summary. Collapses above the canvas below 1280px. | Nothing new is computed or invented; the dock earns its space with content the screen already carries. If it proves thin, the grid degrades to the single column tablet already uses. | ok |
| Q10 | `/trips` has no counterpart in the export. Restyle it? | **Yes**, by analogy from the card and empty-state recipes. | A route left in the old skin is the most visible possible bug in a design-adoption milestone, and it is the first screen after login. | ok |
| Q11 | Is this one spec or three (tokens / layout / icons)? | **One spec, five phases**, with the compatibility bridge created and destroyed inside Phases 1–2. | Each phase already ships as its own PR, so a split would divide the document and not the delivery; and "palette without layout" does not answer the brief. See **Scope cohesion** for the full argument and the risk the phase structure carries instead. | ok |

## 📋 Phasing

Five phases. Each is independently shippable and each leaves every screen working and every gate
green. Each ends with a screenshot set of all five routes in **both locales** — that set is the
review artifact, because no command in the validation gate can see.

| Phase | Delivers | Visible after it |
|---|---|---|
| 1 | The typeface and the token layer, with the compatibility bridge | Every screen in the real palette and the real typeface, same layout |
| 2 | The component recipes; the bridge deleted | Buttons, inputs, chips, cards and dialogs as the design specifies them, on one token vocabulary |
| 3 | The chrome and the grid | The frosted header, the split-surface layout, the dock |
| 4 | The screens | The trip banner, the timeline rail, the creator and the day detail as the export lays them out |
| 5 | Icons and the verification pass | The starter sprite gone; contrast, diacritics and locale evidence recorded |

Phases 1 and 2 are the majority of the visible gain for a minority of the risk; if anything slips, it
slips from the tail, and the repository is never left holding two token vocabularies.

## 📋 Implementation Plan

Every step declares how it is verified. **(automated)** means a command or a test in the existing
gate can fail on it. **(visual QA)** means a human — or an agent with the browser provider — looks at
a screenshot; those are a checklist, not tests, and Q7 explains why that is the accepted trade.

### Phase 1 — The typeface and the token layer

1. Add `@fontsource-variable/plus-jakarta-sans` to `frontend/package.json` (lockfile in the same
   commit, per `AGENTS.md`) and import `wght.css` + `latin-ext.css` from `main.tsx`.
   *(automated)* `npm run build` succeeds and emits two woff2 assets.
   *(visual QA)* `ą ć ę ł ń ó ś ź ż` at 400 and 700 render in Jakarta forms, not a fallback.
2. Create `frontend/src/styles/tokens.css` with the full set — colour roles, type scale, radii,
   spacing, `--sidebar-width`, `--timeline-track-offset`, the three elevations, the corrected
   contrast values from the UI/UX table — resolving the two frontmatter/prose conflicts in favour of
   the prose and commenting each resolution.
   *(automated)* the file contains no selector other than `:root`; every colour, type, radius and
   elevation value is traceable to `DESIGN.md`, and every layout metric not in `DESIGN.md` carries a
   comment naming its derivation.
3. Add the compatibility bridge covering **every** surviving skeleton name — `--colour-*`,
   `--space-1..8`, `--radius-sm/md/lg`, `--shadow-card`, `--font-sans` — and reduce `index.css`'s own
   `:root` block to an import of `tokens.css`.
   *(automated)* a token-completeness check — a short script that collects every `var(--x)` in
   `frontend/src` and fails on any name `tokens.css` does not define — passes, and the full suite
   passes unchanged. This check is the guard against the silent-CSS-failure edge case and runs again
   in step 25.
   *(visual QA)* every screen renders in the new palette with no layout movement.
4. Move the reset, `body`, headings, links, focus ring and reduced-motion rules into
   `styles/base.css`; bind `h1`–`h4` to the type scale; switch the focus ring to `--primary` and add
   the `--primary-fixed` override for dark surfaces.
   *(visual QA)* keyboard-tab every screen — the ring is visible on the canvas and on any dark
   surface.
5. Record the contrast table for every pair `tokens.css` defines, in the PR body.
   *(automated)* a contrast script over the token file fails on any body-text pair below 4.5:1 or any
   large-text/boundary pair below 3:1.
6. Capture the phase-1 screenshot set: five routes × two locales.
   *(automated)* ten non-empty PNGs exist. *(visual QA)* they are reviewed.

### Phase 2 — The component recipes, and the bridge goes

7. Split `components.css` out of `index.css` and rewrite the button recipes: primary (`--primary`,
   40px, `#0C3257` hover, guarded scale), deep (`--primary-deep`, the form-completing action), ghost,
   danger, danger-solid. No accent-button recipe: `--secondary` is defined as a token, but its
   documented uses are all cut, and it fails contrast behind text (3.56:1) — a recipe for it would be
   speculative dead CSS.
   *(automated)* existing button assertions pass. *(visual QA)* no button falls back to browser
   defaults.
8. Rewrite the input, select, textarea and date-input recipes: `#FFFFFF` on 1px `#CBD5E1`,
   `--radius`, 2px `--primary` active outline; the invalid state adds a border colour *and* keeps the
   existing `role="alert"` text.
   *(automated)* the login and item-dialog form tests pass, including the invalid-state assertions.
9. Rewrite the status chip recipes to the three corrected triples and add the 6px dot as an
   `aria-hidden` sibling of the existing glyph.
   *(automated)* every status assertion passes, and a test asserts each chip still exposes its glyph
   and translated label — the colour-blind contract, assertable in jsdom because it is about text
   nodes and attributes, not paint.
10. Introduce the elevation utilities and apply them: cards and list rows at elevation-1 with
    hover/focus at elevation-2; dialogs at elevation-3 at `--radius-xl` over a `#0F172A`/20% backdrop
    with `backdrop-filter: blur(12px)` inside `@supports` and a 96%-opaque fallback first.
    *(automated)* the dialog focus-trap tests pass. *(visual QA)* the dialog is legible with
    `backdrop-filter` disabled.
11. Migrate the last rules off the bridge aliases and delete the bridge.
    *(automated)* `grep -rE '\-\-(colour-|space-[0-9]|shadow-card)' frontend/src` returns nothing, and
    the step-3 token-completeness check passes.
12. Capture the phase-2 screenshot set. *(automated)* ten non-empty PNGs. *(visual QA)* reviewed
    against phase 1's.

### Phase 3 — The chrome and the grid

13. Rebuild the header in `styles/chrome.css` and `AppShell.tsx`: sticky, frosted with its `@supports`
    fallback, `--header-height` as a custom property, wordmark in `headline-sm`, controls grouped
    right.
    *(automated)* `AppShell`'s existing tests pass unchanged. *(visual QA)* the header stays put while
    the page scrolls.
14. Add the optional `context` prop and populate it on trip-scoped routes, truncating to one line.
    *(automated)* the new keys exist in both locales (the parity gate), and a test renders `AppShell`
    without `context` to prove the prop is optional. *(visual QA)* a 120-character title does not wrap
    the header.
15. Add the optional `dock` prop and the page grid: the 1280px split, the 768–1279px stack with dock
    content above the canvas, the <768px single column. Screens passing no dock render one centred
    column.
    *(automated)* a test renders `AppShell` with and without `dock`. *(visual QA)* at 1280px, 1024px
    and 360px there is no horizontal scrolling and the dock is where the spec says.
16. Capture the phase-3 set, adding a 360px capture of the timeline in both locales.
    *(automated)* twelve non-empty PNGs.

### Phase 4 — The screens

17. `/login` and `/trips`: the centred login card, trip rows as elevation-1 cards with the compact
    readiness value, the restyled empty state.
    *(automated)* the auth and trip tests pass, including the empty state. *(visual QA)* both locales.
18. `/trips/:id` — the banner: the `--primary-deep` block with title, icon-led meta row and the
    readiness tile; title clamped at two lines; tile reflows below 1280px.
    *(automated)* the trip-header tests pass. *(visual QA)* a long title neither wraps the tile away
    nor clips.
19. `/trips/:id` — the readiness ring behind the new optional `ring` prop: a `conic-gradient` disc,
    `aria-hidden`, rendered only above a zero denominator, beside the untouched "x of y" text.
    *(automated)* a new unit test asserts that at a zero denominator no ring element and no percentage
    string is rendered, and that the text node is unchanged — the R02 regression guard.
20. `/trips/:id` — the filter bar: pills over the existing radio group, sticky beneath the header at
    ≥768px, count chips on the draft recipe.
    *(automated)* every filter test passes and the group is still operable as a radio group.
    *(visual QA)* the bar stays put while the timeline scrolls.
21. `/trips/:id` — the rail: sticky two-line day anchors, the continuous track at
    `--timeline-track-offset`, `ItemRow`'s optional rail dot, item cards with the icon tile; the
    empty-day invitation stays on the rail.
    *(automated)* the timeline and filter tests pass; a test renders `ItemRow` without `railDot`.
    *(visual QA)* a fifteen-day trip with sparse items shows a continuous rail and keeps the current
    day anchor on screen.
22. `/trips/new`: the eyebrow/title/subtitle heading, grouped field cards, the segmented route-mode
    control, numbered stage cards with icon removal, the summary in the dock, the full-width primary
    action.
    *(automated)* every creation and validation test passes; the remove control's accessible name is
    asserted; the primary action's disabled logic is unchanged.
23. `/trips/:id/days/:date`: breadcrumb and eyebrow heading, ghost icon buttons keeping the disabled
    treatment, the shared item card, the dialog with the segmented status control.
    *(automated)* the item-editor tests pass, including focus trap and focus return; the status
    control is still a labelled radio group.
24. Capture the phase-4 set — five routes × two locales at desktop width, plus the timeline and day
    detail at 360px, plus a before/after pair per route in the PR body.
    *(automated)* fourteen non-empty PNGs.

### Phase 5 — Icons and the verification pass

25. Add `frontend/src/assets/icons.svg` with the five item-kind glyphs and the two chevrons; add the
    `<Icon>` wrapper with `aria-hidden` / `focusable="false"`; point the item card and day navigation
    at it; delete `frontend/public/icons.svg`.
    *(automated)* no reference to the deleted file survives (`grep` over `src/` and `index.html`);
    every icon has a translated text label beside it (asserted per call site); `npm run build` emits
    the hashed sprite; the step-3 token-completeness check still passes.
26. Final verification pass.
    *(automated)* the six gate commands; the contrast script over the final token file; bundle-size
    before/after recorded.
    *(visual QA)* the diacritics check repeated at every weight in use; a `prefers-reduced-motion`
    capture; a forced-colors capture. Every artifact goes in the PR body.
