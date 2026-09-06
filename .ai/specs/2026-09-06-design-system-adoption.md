# Design system adoption — the real visual layer, and the shape of V1

- Date: 2026-09-06 (revised the same day after the owner answered Q1)
- Status: ready — Q1 answered by the owner on the PR; no assumption is gated
- Brief: "Let's make the application look like on the design."
- Owner's scope ruling (Q1): *"Provide UI for all the functionalities that we plan to deliver. Cut the ones we don't plan to deliver in V1. For functionalities that are not there yet, make them inactive or if disabling is not practical simply leave a UI element without backend attached."*
- Predecessor: `.ai/specs/2026-09-05-walking-skeleton.md` (merged as PRs #2 and #6)
- Neighbours: `.ai/specs/2026-09-05-trip-sharing-magic-link.md` (PR #3) and `.ai/specs/2026-09-05-attachments-and-reservation-data.md` (PR #4) own the behaviour behind two of the surfaces this spec stands up
- Design source: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/`

## 📝 TLDR

Two things, deliberately in one milestone. **First**, the walking skeleton's placeholder skin is
replaced by the `modern_premium_travel_companion` design system: its palette, the Plus Jakarta Sans
type scale that `--font-sans` has been naming without ever loading, radii, spacing, elevations and
component recipes, plus the split-surface layout the export is built on. **Second**, every
capability in the brief's V1 *Now* list that does not exist yet — chat, sharing, attachments,
reservation data — gets its real UI surface in the right place, rendered inert: present, discoverable
and honest about not working yet, with no backend attached. Everything the export shows that V1 is
not delivering is cut outright. The result is an application that looks finished and whose shape
tells the truth about what V1 will be.

No backend change, no endpoint, no migration, no new data.

## 📝 Problem Statement

Two problems, and the second is the reason this spec grew after the owner ruled on Q1.

**The application looks unfinished, and that is unfinished work rather than taste.** The evidence is
in the repository:

- `frontend/src/index.css:1-8` says so in as many words: "This is the minimum that makes the screens
  this milestone ships look deliberate; the full token set from the design export lands with the
  screens that need it in Phases 2 to 4." All four phases have landed.
- `--font-sans` (`index.css:32`) names `'Plus Jakarta Sans'` first, and nothing in the repository
  loads that family — no `@font-face`, no `<link>` in `index.html`, no font package in
  `package.json`. Every screen renders in whatever the operating system offers as `ui-sans-serif`.
  `DESIGN.md`'s typography section — the tight negative tracking on headings, the positive tracking
  on small labels, the promise that Polish diacritics keep their optical balance — describes a
  typeface the user has never seen.
- `--colour-accent: #2f6f5e` is a green invented for the skeleton. The design's primary is `#0F3F6D`
  and its secondary a terracotta `#EA580C`; neither appears in the codebase. The status colours at
  `index.css:540-550` are four hard-coded literals invented for the same reason.
- The layout is a single 56rem centred column (`index.css:214-217`) on every authenticated screen,
  where the design is a split-surface workspace with a 22rem contextual dock.
- `frontend/public/icons.svg` is the unmodified Vite starter sprite — six social symbols referenced
  from nowhere in `src/` or `index.html`.

**The application's shape hides what V1 is.** Four of the eight capabilities in the brief's *Now*
list — chat (D03), sharing (D08, D09), attachments, and reservation data (D07, R04) — are planned,
specified or in flight, and none of them has a single pixel anywhere in the product. A05 cut them
from the walking skeleton's *implementation*, and the walking-skeleton spec correctly refused to
style features it was not building. But A05 is a sequencing assumption, not a scope decision, and
the consequence today is an app whose surface is indistinguishable from one where those features are
not coming. Standing their surfaces up inert fixes that, and it does something practical besides: it
turns each remaining implementation PR into filling in a shape that already exists and has already
been reviewed, rather than negotiating placement while also writing the backend.

Why any of this matters: D10 makes the success test the Malaysia trip of October 2026 planned end to
end in the app, and D02 makes the owner its only user. A tool one person must choose to open every
day, in preference to a mailbox and a spreadsheet that already work, competes on being pleasant to
sit in front of and on looking like it is going somewhere.

The before-and-after is attached to this spec's PR: `assets/design-system-adoption/current-*.png`
are the running application today; `mockup-*.png` are the proposed screens.

## 📝 Scope

### Workstream A — the design system

- The full `DESIGN.md` token set as CSS custom properties: colour roles, the Plus Jakarta Sans type
  scale, radii, spacing, the four documented elevation levels.
- Loading Plus Jakarta Sans for real, with the Latin Extended subset Polish diacritics need.
- The component recipes: buttons, status chips and badges, the timeline itinerary card, input
  fields, cards and their hover elevation, the modal and drawer treatment.
- The chrome: the frosted sticky header with the **Smart Trip Planner** lockup, the responsive grid
  (a 22rem dock beside the canvas on desktop, stacked below 1280px), sticky day anchors.
- Restyling the five existing routes: `/login`, `/trips`, `/trips/new`, `/trips/:id`,
  `/trips/:id/days/:date`.
- Replacing the starter icon sprite with the item-type and chrome icons the restyled screens use.
- Keeping every accessibility and i18n contract the walking skeleton established, and **correcting
  the design's own contrast failures** rather than shipping them.

### Workstream B — the V1 surface, inert

Per the owner's ruling. Each surface is rendered in its designed position, in the design system's
own components, with nothing behind it:

| Surface | In V1 because | Behaviour owned by | What this spec ships |
|---|---|---|---|
| **Chat / the assistant drawer** | *Now* list; D03 (chat adds and changes items) | No spec yet — this is the next one to write | The drawer, its header, its trip context line, an empty transcript with the not-yet notice, and a disabled composer. The right-edge toggle in the header. |
| **Sharing** — "Udostępnij", the share dialog, the `Shared` chip | *Now* list; D08, D09 | `2026-09-05-trip-sharing-magic-link.md` (PR #3) | The action in the timeline's action row, opening the dialog in its **State A** layout with that spec's consequence sentence and a preview-state "Create link". No token is minted, so no `Shared` chip can be true — it is specified and not rendered. |
| **Attachments** — day documents panel, item paperclip, the dropzone | *Now* list ("a day detail view … with file and image attachments") | `2026-09-05-attachments-and-reservation-data.md` (PR #4) | The day-documents panel with its heading and its empty state, and the labelled file input rendered disabled. No paperclip glyph on item cards: the count would have to be zero for everything, and a zero-count affordance on every card is noise. |
| **Reservation data** — confirmation number, amount, currency | *Now*-adjacent; D07, R04 | Same spec (PR #4) | The collapsed "Dane rezerwacji (opcjonalne)" disclosure inside the item editor, with its three fields present and disabled. Collapsed by default and never auto-opened, exactly as PR #4 requires. |

Nothing in workstream B calls an endpoint, stores a value, or renders fabricated data.

There is **no data model and no API contract in this spec**: no entity, field, migration, endpoint,
or changed request or response shape.

### Cut — what V1 is not delivering

The design export depicts a larger product. These elements are removed from the adaptation entirely
— not previewed, not stubbed, not styled:

| Cut | Where in the export | Why it is not V1 |
|---|---|---|
| Booking and buying: "Zarezerwuj przez AI", "Kup bilety online", "Wybierz ofertę od 180 PLN/dzień", vendor comparisons, ratings, live offers | Item cards, creator | D04, R07 — the first version performs no booking, no payment and no live price or inventory lookup. This is the export's largest single block and the one real product exclusion. |
| Budget and accounting: the PLN/EUR toggle, "SZACOWANY BUDŻET", the budget slider, per-item prices on the timeline | Timeline banner, creator | D12 *Later* (cost accounting as a real feature); brief Q04 (multi-currency) open. Per-item amounts live in PR #4's optional reservation panel and are deliberately absent from the timeline — a money column on the central screen would quietly make this a budget tracker. |
| AI trip generation: "Zaplanuj z AI", "Wypełnij pusty harmonogram z sugestiami AI", "Inspiracje Asystenta", destination presets, travel-style and transport pickers, the recommended-route hero | Creator | D03 — chat *adds and changes items*; it does not generate whole trips. The creator's V1 action is "Utwórz pustą oś czasu do ręcznego planowania". |
| Automatic import: "Import PDF / E-mail", the PNR dropzone on the creator, auto-read dates | Creator | D12 *Later* — automatic parsing of reservation PDFs and e-mails. Manual attachment upload (workstream B) is the V1 half of this. |
| A trip-wide documents centre ("Rezerwacje i Dokumenty" as a destination) | Nav, `centrum_rezerwacji_i_dokument_w` | Not in the *Now* list, and PR #4 puts documents on the day detail rather than in a vault. A whole route with nothing behind it is a bigger promise than this spec should make. |
| Maps and routing: "Podgląd trasy", "Otwórz GPS", "Zarys trasy 8 dni", "Optymalizuj trasę z AI" | Creator, day detail, timeline | D12 *Later* |
| Weather: the per-day strip, "24°C w maju" | Timeline, creator | D12 *Later* |
| Export: "Eksportuj PDF", "Eksportuj do Google Calendar" | Timeline, day detail | D12 *Later* |
| "Zadania & Przygotowanie" | Day detail | Brief **Q02 is open** — a preparation task is not yet a V1 concept. Cut rather than previewed, because previewing it would answer Q02 by building it. If Q02 comes back "yes", it becomes a preview surface then. |
| Guest comments and suggestions on a shared plan | Implied by the export's share flow | D09 — one editor; a guest reads and nothing more. *Later*. |
| Chrome with nothing behind it: the notification bell, the avatar menu, "PRO", "v3.4 GPT-4o", "Centrum pomocy", "Status API", "Prywatność", "Regulamin", the marketing footer | Header and footer | No feature behind any of them, in V1 or later. Chrome for a product with more in it. |
| Dark mode | Not in the export | The export ships one light scheme; a second is new design work, not adoption. |

Also out of scope for blast-radius reasons: **no backend change** (not one file under `backend/`);
**no new route**; **no CSS framework** (`AGENTS.md` names the stack as React + plain CSS, and a
restyle is the worst moment to migrate the styling strategy — every visual regression would be
indistinguishable from a migration bug); **no visual-regression tooling** (Q7).

### Scope cohesion

An adversarial review of the first draft argued that the design work alone was three specs — tokens,
layout, icons — and the owner's ruling has since added a fourth workstream. The independence test is
real: each part functions without the others. It stays one spec, for reasons that survived the
scope change.

The deliverable the brief asks for is "the application looks like the design", and none of the parts
delivers that alone: the palette without the layout leaves the timeline reading as a form, and both
without workstream B leave an app that looks finished while hiding half of what V1 is. More
practically, the split would divide the document and not the delivery — each phase already ships as
its own PR against its own reviewable diff. What the review was really protecting against was the
compatibility bridge outliving its usefulness, and that is fixed directly: **the bridge is created
and deleted inside Phases 1–2**, so the repository never holds two token vocabularies for long.

Workstream B is sequenced last (Phase 5) for the same reason: it is the part most likely to be cut
or changed, and putting it at the end means cutting it costs nothing already shipped.

## 📝 Proposed Solution

Four layers, in order, each independently shippable and each leaving the application working.

**1. Retoken.** Replace the *contents* of the custom-property block, not the property names. The
existing screens make 197 `var()` references across six token families; repointing those names at the
design's roles restyles every screen at once without touching a selector. The design's role
vocabulary lands as the canonical set, and every surviving skeleton name becomes an alias for one
phase so the change can be verified screen by screen instead of in one unreviewable diff.

**2. Re-recipe.** Rewrite the component blocks against the design's component section, which is
specific enough to implement directly: 40px primary buttons in `#0F3F6D` with a `#0C3257` hover,
confirmed chips on `#ECFDF5` with an `#A7F3D0` hairline and a 6px dot, cards at elevation-1 lifting
to elevation-2 on hover, dialogs and drawers at elevation-3 over a 12px-blurred `#0F172A`/20%
backdrop.

**3. Re-lay-out.** Introduce the grid the design is built on and move the existing content into it: a
sticky frosted header, a page grid with a contextual dock, and a timeline that renders as a rail with
day anchors and status dots rather than a list of bordered boxes.

**4. Stand up the V1 surface, inert.** Add the four workstream-B surfaces in their designed
positions, through one shared preview mechanism (below) that is honest, accessible, and trivially
deletable by the implementation PR that replaces it.

### The preview pattern — one mechanism, defined once

The owner's ruling offers two mechanisms ("make them inactive or … leave a UI element without backend
attached") and the right choice differs by element type. Rather than decide case by case, one pattern
covers all four surfaces:

- **A discrete control** — a button, an action, a toggle — is **not** given the native `disabled`
  attribute. It renders with `aria-disabled="true"`, keeps its place in the tab order, carries a
  visible `Wkrótce` / `Soon` badge, and its handler is a no-op. Native `disabled` removes the control
  from keyboard navigation and offers the user no way to discover *why* it is unavailable, which for
  a feature that is coming is the wrong answer; `aria-disabled` is announced as "dimmed/unavailable"
  and still explains itself.
- **A data-entry field** — the reservation inputs, the chat composer, the file input — *does* get
  native `disabled`. Here the native behaviour is exactly right: a field that accepts typing and
  then discards it is worse than one that refuses it, and a file input that opens a picker leading
  nowhere is a small lie.
- **A whole surface** — the chat drawer, the day-documents panel, the share dialog — cannot be
  "disabled" at all. It renders with its real chrome and, in place of its content, one short notice
  in the empty-state recipe naming what it will do and where the plan for it lives.
- **Every preview surface carries `data-preview="true"`.** One attribute gives the CSS one selector,
  the tests one assertion, and the implementation PRs one `grep` for everything they must delete.
- **A preview never fabricates.** No placeholder messages in the chat transcript, no example
  documents, no sample confirmation number, no count, no spinner that never resolves, no progress
  bar. An empty state that is honestly empty is the only honest preview.

The notice copy is one sentence plus a pointer, in both locales:

> *Ta część powstaje. Plan jest już napisany — zobacz `<spec>`.*
> *This part is being built. The plan for it is written — see `<spec>`.*

For chat, which has no spec yet, the pointer is omitted and the sentence stands alone.

### Alternatives considered

- **Ship the preview surfaces as fully-styled fakes with sample content** — a chat transcript with
  two example messages, a document list with a sample voucher. Rejected. It photographs better and
  it is a lie: the owner would be the person deceived, D02 makes him the only user, and the first
  time he clicked a fake message the app would have spent trust it cannot re-earn.
- **Hide the not-yet features entirely until each is built** — the first draft's answer, before the
  owner ruled. Rejected by the ruling, and the ruling is right: it leaves the product's shape a
  secret and makes each implementation PR renegotiate placement.
- **Feature flags with the real UI behind them.** Rejected as premature: a flag implies a working
  implementation to switch on. There is none. When each feature lands, its preview is deleted and
  the real thing takes the same position — the `data-preview` attribute is the flag, and it has one
  state.
- **Adopt a component library (Radix Themes, shadcn/ui, Mantine).** Rejected. It converts a styling
  task into a rewrite of every screen's markup, adds a dependency for no capability we lack, and
  trades this app's hand-built, *tested* accessibility properties — the focus-trapped dialog, the
  radio-group filter bar, the glyph-plus-text status chip — for untested ones.
- **Tailwind plus a token config generated from `DESIGN.md`.** Rejected for this milestone: the
  design's frontmatter is already a token file, so CSS custom properties are a transcription, while
  Tailwind is a transcription *and* a build-pipeline change *and* a rewrite of 798 working lines,
  all in the same PR as the visual change it is meant to enable.
- **Copy the export's generated `code.html` files into the app.** Rejected outright: Tailwind-CDN
  documents for a different product, with hard-coded Polish copy (violating R01 on its own), inline
  data, and markup for features we do not have. Reference material.

### Research — what the neighbours do

Checked against the itinerary products the brief benchmarks (Wanderlog, TripIt, Google Travel) and
against how mature design systems ship tokens. Brief Q01 is still open; this was a design-language
comparison, not a feature benchmark. Three findings changed the design:

- **The vertical time rail is the genre's convention, and we should not be clever about it.** Every
  itinerary product renders a day as a dated anchor with a connected vertical line and one card per
  item, time on the left in tabular figures. The export draws exactly that; our timeline draws a
  bordered box per day containing an unrailed list. This is the layout change with the most to gain.
- **Status gets a shape, not just a colour, everywhere.** TripIt's confirmed/unconfirmed and
  Wanderlog's booked markers are icon-led. Our glyph-plus-text chip already beats both on
  accessibility; adding the design's coloured recipes matches them on legibility.
- **Nobody previews unbuilt features, and the products that do it badly are instructive.** The
  common failure is a "Pro" upsell dressed as a feature — a control that looks live, does nothing,
  and teaches the user to distrust controls. The distinguishing move in the ones that work is
  labelling the state in words rather than only dimming it, which is why the `Soon` badge is text
  and not an opacity.

What they carry that we can skip: density controls, map/list toggles, per-item vendor cards and
multi-traveller avatars — all serving products with more data per item than ours has.

## 📝 Architecture

The changed surface is `frontend/src/` and nothing else.

### The style layer, after

`index.css` is 798 lines holding tokens, base rules, components and five screens in one file. The
token block roughly doubles under the full set and the component blocks roughly double under the
recipes. It gets split by concern, imported in a fixed order — cascade order is the contract, so the
imports live in one place and are commented as ordered:

```
frontend/src/styles/
  tokens.css        The DESIGN.md frontmatter, transcribed. Custom properties only,
                    no selector beyond :root. This file is the design contract.
  base.css          Reset, body, headings bound to the type scale, focus ring,
                    link defaults, reduced-motion.
  chrome.css        The header, the page grid, the dock, the drawer, landmarks.
  components.css    Buttons, inputs, chips, cards, dialogs, empty states, previews.
  screens.css       The login card, the trip banner, the timeline rail, the
                    creator's stage rows.
frontend/src/index.css   Five @import lines, in order, and nothing else.
```

Vite inlines CSS `@import` at build time, so the shipped bundle is one stylesheet either way and the
ordering stays visible in the CSS rather than depending on module evaluation order in a TSX file.
Internal module structure is explicitly *not* a protected surface per `BACKWARD_COMPATIBILITY.md`.

### Tokens: two levels, and the bridge

`tokens.css` carries the design's role names as the canonical layer — `--primary`, `--canvas`,
`--surface`, `--hairline`, `--text`, `--elevation-1..3`, the type-scale roles, the radius tiers, the
spacing scale, `--sidebar-width`, `--timeline-track-offset`. The transcription belongs in the file,
not in this document; what belongs here is the three decisions transcription cannot make for itself.

**Naming.** The design's role names are adopted unprefixed rather than kept under `--colour-*`. The
prefix existed to separate a handful of invented colours from everything else; once every token *is*
a design role it distinguishes nothing, and matching the export's vocabulary is what makes a value in
`DESIGN.md` findable in the CSS. Values not in `DESIGN.md` (layout metrics) carry a comment naming
their derivation.

**Two contradictions inside `DESIGN.md`, resolved.** The frontmatter's `primary` is `#00294d` while
the prose's Primary role is `#0F3F6D` (the frontmatter's `primary-container`); the frontmatter's
`surface` is `#faf8ff` while the prose's neutral canvas is `#F8FAFC`. **The prose wins in both
cases** — it is the part that assigns roles to values, and the rendered screens match it. The
frontmatter's `#00294d` is kept as `--primary-deep`, which is what the trip banner in
`g_wny_pulpit_i_o_czasu` is actually filled with.

**The bridge, and the exact thing it must cover.** Repointing only `--colour-*` would break the
build: of the 197 `var()` references in `index.css`, only 81 are `--colour-*`. The rest are
`--space-1..8` (89), `--radius-sm` (14), `--radius-md` (4), `--radius-lg` (4), `--shadow-card` (4)
and `--font-sans` (1). Two are traps: the new scale renames `--space-N` to `--space-{2xs..3xl}`, and
`--radius-md` **changes meaning** under the same name (10px → 0.75rem/12px) — the silent break
`BACKWARD_COMPATIBILITY.md` calls the worst kind. So the bridge aliases **every surviving skeleton
name**:

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
--shadow-card: var(--elevation-1);
```

Phase 1 makes every one of the 798 existing lines render in the design's palette, so the reviewer
looks at five screens rather than at a diff. Phase 2 migrates rules off the aliases recipe by recipe
and deletes the bridge in its last step, closing the two-vocabulary window before the layout work
starts.

### The typeface

`@fontsource-variable/plus-jakarta-sans` — the **variable** package, a regular dependency, imported
once from `main.tsx` as `wght.css` plus `latin-ext.css`. Two woff2 files, one per subset, covering the
whole 200–800 axis; the static `@fontsource/…` package would be eight files for the four weights we
use, which is why it is not the one named. `latin-ext` carries `ą ć ę ł ń ó ś ź ż`, and omitting it
would fall back per-glyph — precisely the optical-balance failure `DESIGN.md` warns about.
`font-display: swap` keeps first paint text-visible.

No Google Fonts `<link>`: the application is on the public internet from day one (D14), a
third-party font request is a third-party request on every page load for every user, and its failure
mode — CDN blocked, offline dev — is that the design silently does not apply.

### Iconography

`frontend/public/icons.svg` (the starter's six social symbols) is deleted and replaced by
`frontend/src/assets/icons.svg`, a sprite holding the glyphs the restyled screens use: the five item
kinds the API already defines (`accommodation`, `transport`, `activity`, `meal`, `other`), chevrons
for day navigation, and the three workstream-B glyphs (chat, share, paperclip). Consumed through a
small `<Icon name=… />` wrapper around `<svg><use href=… /></svg>` with `aria-hidden="true"` and
`focusable="false"` on every instance, because a translated text label always sits beside it. Moving
the sprite from `public/` into `src/assets/` puts it through the bundler, so it is content-hashed and
cacheable rather than served unversioned.

No icon font and no icon package: a sprite of eleven glyphs is smaller than any dependency that would
supply them, and it survives with CSS disabled in a way an icon font does not.

### The preview primitives

Three small components in `frontend/src/features/preview/`, and nothing else:

| Component | Renders | Used by |
|---|---|---|
| `<PreviewBadge />` | The translated `Wkrótce` / `Soon` label in the design's draft-badge recipe | Every preview control |
| `<PreviewAction>` | A button with `aria-disabled="true"`, `data-preview="true"`, a no-op handler, and a `<PreviewBadge>` | "Udostępnij", the chat toggle, "Dodaj plik" |
| `<PreviewNotice specHref?>` | The empty-state recipe with the one-sentence notice and an optional pointer to the owning spec | The chat drawer, the documents panel, the share dialog |

They live in their own feature folder rather than in `components/` for one reason: **this code is
designed to be deleted.** When PR #4's implementation lands, it removes the documents panel's
`<PreviewNotice>` and the disabled input; when the last of the four surfaces is real, the folder goes
with it. A `grep` for `data-preview` finds every site, and a test asserts the count matches the
number of surfaces this spec declares — so a preview that outlives its feature fails the suite rather
than quietly becoming permanent.

### Component signatures — what actually changes

Additive optional props only. Nothing is removed, renamed, or given a new meaning:

| Component | Change | Breaking? |
|---|---|---|
| `AppShell` | Three new **optional** props: `dock?`, `context?` (the header's trip context), `drawer?` (the right-edge chat drawer and its toggle). Existing `{ title, breadcrumb?, actions?, children }` unchanged. | No — additive |
| `ItemRow` | One new **optional** prop: `railDot?: boolean`, so the timeline renders the status dot on the rail and the day detail does not. | No — additive |
| `ReadinessTile` | One new **optional** prop: `ring?: boolean`. The banner passes it; the compact list variant does not. | No — additive |
| `ItemDialog` | Renders the collapsed reservation disclosure. No prop change — the disclosure is internal and inert. | No |
| Everything else | Unchanged: `StatusChip`, `FilterBar`, `ConfirmDialog`, `LocaleSwitch`, `RequireSession`. | — |

Nothing else moves: no route, no loader, no state shape, no `data-status` / `data-nothing-tracked`
test hook (load-bearing for both the suite and the colour-blindness contract), and no locale key
renamed or repurposed — new keys only, which `BACKWARD_COMPATIBILITY.md` §4 permits and
`scripts/check_locales.py` enforces.

## 📝 Data Model

None. No entity, field, relation or migration. Stated explicitly rather than omitted.

## 📝 API Contracts

None — and for workstream B this is a stronger claim than usual: **no preview surface issues a
request.** No endpoint is called, no client method is added, and no `api/` module is touched. A
preview that fetched something would be a feature with a broken backend, which is a different and
worse thing than a preview.

## 📝 UI/UX

Each screen lists what is adopted from the export and what changes in TSX. What the export shows and
V1 is not delivering lives in the **Cut** table above and is not restated per screen.

Mockups of the proposed screens and screenshots of the current ones live in
`assets/design-system-adoption/` and are attached to this spec's PR:

| | Screen | Evidence |
|---|---|---|
| Proposed | Tokens, type scale, component recipes, **and the preview states** | [`mockup-01-tokens-and-components.png`](assets/design-system-adoption/mockup-01-tokens-and-components.png) |
| Proposed | `/trips/:id` — banner, filter bar, rail, dock, **share action and chat drawer** (Polish) | [`mockup-02-timeline.png`](assets/design-system-adoption/mockup-02-timeline.png) |
| Proposed | `/trips/:id/days/:date` — day detail, **documents panel**, item editor with the **reservation disclosure** (English) | [`mockup-03-day-detail.png`](assets/design-system-adoption/mockup-03-day-detail.png) |
| Proposed | `/trips/new` — the multi-stop creator (Polish) | [`mockup-04-trip-creator.png`](assets/design-system-adoption/mockup-04-trip-creator.png) |
| Current | `/login`, `/trips`, `/trips/:id`, `/trips/:id/days/:date`, `/trips/new` | `current-01…05-*.png` |

Two locales on purpose: R01 makes both first-class, and a spec that only ever pictures one is not
showing the product it describes.

### Cross-cutting

- **The header.** Sticky, `rgba(255,255,255,0.85)` with `backdrop-filter: blur(8px)`, a hairline
  bottom border, and `--header-height` exposed as a custom property for the sticky layers beneath it.
  Left: the **Smart Trip Planner** wordmark in `headline-sm`, linking to `/trips` (D01 — the export's
  "VoyageAI" lockup supplies the layout, never the name). Right: the chat toggle (preview), the
  locale switch and sign-out. Between them, on trip-scoped routes, the trip title and date range,
  truncated with an ellipsis — the export's trip picker without being a picker, since there is one
  trip in view and `/trips` is one click away.
  - **The export's four-tab nav is not adopted** (Q4). Of its four destinations, two are routes that
    exist and are one click away already, one is the documents centre this spec cuts, and one is the
    AI creator mode D03 rules out. A nav bar that is half dead tabs is worse than no nav bar.
- **The page grid**, owned by `chrome.css` and applied by `AppShell`:
  - ≥1280px: `grid-template-columns: minmax(0, 1fr) var(--sidebar-width)`, `gap:
    var(--gutter-desktop)`, capped at 90rem and centred. At that cap the dock is 22/90 of the width —
    close to 3 of 12 columns rather than the export's nominal 4, because 22rem is the export's own
    `sidebar-width` token and the fixed rem value is the one worth being faithful to.
  - 768–1279px: one column; dock content renders **above** the canvas as a horizontal summary strip
    — on a tablet the readiness figure is the thing worth seeing first.
  - <768px: one column, `--gutter-mobile`, same strip.
  - Screens passing no dock render a single centred column and do not reserve the space.
- **The dock's content** (Q9), now that the export's concierge drawer moves to the right edge where
  the export actually puts it: trip metadata promoted out of the main column — the readiness figure,
  the stage list with dates, per-type item counts, the route summary. Nothing new is computed.
- **Motion.** Hover elevation, the header blur and the drawer's slide are the only transitions, all
  ≤150ms and all inside `@media (prefers-reduced-motion: no-preference)`, as is the design's "subtle
  scale transition" on primary buttons at `scale(1.01)`.
- **Contrast is corrected, not inherited.** Every foreground/background pair is verified to WCAG AA
  (4.5:1 body text, 3:1 large text and UI boundaries). Three of the design's own values fail and are
  darkened in `tokens.css` with the ratio recorded beside them; the corrected set is fixed here
  rather than deferred to a step-time rule:

  | Role | `DESIGN.md` | Ratio | Adopted | Ratio |
  |---|---|---|---|---|
  | Confirmed chip text on `#ECFDF5` | `#059669` | 3.58:1 ❌ | `#047857` | **5.21:1** ✅ |
  | In-progress chip text on `#FFFBEB` | `#D97706` | 3.07:1 ❌ | `#B45309` | **4.84:1** ✅ |
  | Draft chip text on `#F1F5F9` | `#475569` | 6.92:1 ✅ | unchanged | 6.92:1 ✅ |
  | `--secondary` `#EA580C` behind white text | — | 3.56:1 ❌ | defined as a token, **never used behind text** | — |
  | `--text-subtle` `#64748B` on `#FFFFFF` | — | 4.76:1 ✅ | unchanged; not permitted below 13px | 4.76:1 ✅ |

  `label-sm` (11px) therefore uses `--text-muted` (`#334155`, 10.35:1 on white), and the 11px chip
  labels use the corrected foregrounds above.
- **The preview pattern's own accessibility rules**, which are the part most easily got wrong:
  - A preview control is `aria-disabled="true"`, never `disabled` — it stays reachable by keyboard,
    and its accessible name includes the badge text, so a screen reader announces *"Udostępnij,
    wkrótce, dimmed"* rather than an unexplained dead button.
  - The badge is a **text node**, not an opacity and not a colour. Dimming alone conveys state by
    presentation only, which fails for the same reason a colour-only status chip would.
  - A preview notice is a real `<p>` inside the surface's normal flow, not a tooltip and not a toast:
    it must be readable without hovering and must survive with styles disabled.
  - Activating a preview control does nothing and says nothing — no toast, no alert. The badge
    already said it, and an alert on every click is an interruption the user did not ask for.

### `/login`

- **Adopted:** a single elevation-1 card at `--radius-lg` with `1.5rem` padding, centred on the
  `#F8FAFC` canvas, wordmark above it, locale switch beside the wordmark; inputs at 1px `#CBD5E1`
  with the 2px `#0F3F6D` active outline; the submit button on the primary recipe.
- **Preview surfaces:** none. Sign-up, password reset and social login are not V1 and are not hinted
  at — the walking-skeleton spec already ruled that out and nothing here revisits it.
- **TSX:** none. Only rules change.

### `/trips` — trip list

- **Adopted by analogy** (Q10 — no counterpart in the export, and leaving it in the old skin would
  make the app look half-migrated): each trip becomes an elevation-1 card at `--radius-lg`, lifting
  to elevation-2 with a `#CBD5E1` border on hover and `:focus-visible`; title in `headline-md`, dates
  and route in `body-sm` `--text-muted`, compact readiness value right-aligned. The empty state keeps
  its dashed border, the one place the export's dropzone recipe transfers cleanly.
- **Preview surfaces:** none. PR #3 specifies a `Shared` chip on the trip row, but that chip is only
  true when a token exists and no token can exist here — a chip that is never shown is not a preview,
  it is nothing, and rendering a false one would be the fabrication the pattern forbids.
- **TSX:** none.

### `/trips/new` — the multi-stop creator

Reference: `kreator_nowej_podr_y`, `kreator_podr_y_manualny_i_wieloodcinkowy`. See
[`mockup-04`](assets/design-system-adoption/mockup-04-trip-creator.png).

- **Adopted:** the two-column split with the live summary panel promoted into the dock — exactly the
  "trip at a glance" card the export puts there; the eyebrow / `headline-xl` title / `body-lg`
  subtitle heading treatment; grouped field cards with hairline separators instead of the current
  bordered `fieldset`; the route-mode radios as a **segmented control** (a real radio group
  underneath — the segmentation is `:checked + label` styling, not a rebuild as buttons); stage rows
  as numbered cards with an icon remove-button carrying a visible accessible name and a ghost "add
  stage"; the primary action full-width at the foot in `--primary-deep`, as the export's "Wygeneruj
  plan podróży" is — but reading "Utwórz pustą oś czasu do ręcznego planowania", which is what it
  does.
- **Preview surfaces:** the chat toggle in the header, as on every authenticated screen. Nothing
  screen-specific: the export's AI creator modes and import are cut, not previewed, because D03 and
  D12 say V1 is not delivering them.
- **TSX:** small. The summary paragraph moves into the dock slot, and each route-mode label gains a
  `<span>` for the segmented control to paint. No change to the form's state, validation or submit.

### `/trips/:id` — the timeline

Reference: `g_wny_pulpit_i_o_czasu`. The screen with the most to gain and the most to get wrong. See
[`mockup-02`](assets/design-system-adoption/mockup-02-timeline.png) against
`current-03-timeline.png`.

- **The trip banner.** The export's dark header block: `--primary-deep` fill, `--radius-lg`, white
  type, title in `display-lg` (`display-lg-mobile` below 768px), and a meta row carrying the date
  range, day count and route summary. The readiness tile sits inside the banner on the right at
  ≥1280px, as the export's "STATUS LOGISTYKI" tile does, dropping below the meta row when the banner
  narrows. The action row beneath carries **"Udostępnij"** as a `<PreviewAction>` — the export's own
  position for it, beside the "Eksportuj PDF" this spec cuts.
- **The readiness tile.** Layout adopted; **arithmetic not** — the walking-skeleton spec already
  established that the export's own numbers contradict R02. Concretely (Q8): the ring renders only
  above a zero denominator; the `data-nothing-tracked="true"` state keeps today's neutral, ringless,
  percentage-free treatment, because a 0% ring reads as failure where a percentage is undefined. The
  ring is a two-stop `conic-gradient` on a masked disc — no SVG, no library — is `aria-hidden`, and
  sits beside the existing "x of y" text node, which remains the only accessible expression of the
  value.
- **The share dialog (preview).** "Udostępnij" opens PR #3's **State A** layout: its consequence
  sentence verbatim ("Każdy, kto ma ten link, zobaczy ten plan…"), and its primary action "Utwórz
  link" as a `<PreviewAction>`, above a `<PreviewNotice>` pointing at that spec. It is a real
  focus-trapped dialog on the shared recipe, because a preview of a dialog that traps focus wrongly
  teaches nothing useful. **No token, no URL field, no revoke** — State B does not exist without a
  backend, and drawing an example link would be fabricating a secret.
- **The filter bar.** Pill-shaped filters in the export's day-selector style: unselected as ghost
  pills with a `--hairline` border, selected as solid `--primary` with white text. The markup stays a
  `<fieldset>` of radios with a `<legend>`; the pills are `:checked`-driven label styling. Per-type
  count chips keep the draft-badge recipe and stay non-interactive. The bar becomes sticky beneath
  the header at ≥768px — on a fifteen-day trip the filter currently scrolls away exactly when it is
  most wanted.
- **The timeline rail** — the structural change of the spec. A day is a sticky two-line date anchor
  (`PAŹ / 10`, formatted through `Intl`) with a 1.5px `--hairline` line running down at
  `--timeline-track-offset`, and one card per item hanging off it, each with a status dot on the rail
  in its status colour. The rail runs continuously between sparse days rather than restarting per
  day. The empty-day invitation keeps its place on the rail rather than becoming a gap.
- **The item card.** Time in bold tabular figures on the left, the type icon in a rounded tile beside
  it, title in `headline-sm`, notes in `body-sm` `--text-muted`, status chip top-right. The type
  stops being a grey text pill and becomes icon-plus-label. **No paperclip and no price:** the
  attachment count would be zero on every card, and PR #4 is explicit that costs never appear on the
  timeline.
- **The chat drawer (preview).** Anchored to the right viewport edge as the export anchors its
  concierge, at elevation-3 over a 12px-blurred backdrop, `--radius-xl`, opened by the header toggle
  and closed by `Escape` or the backdrop. Inside: the drawer header with the trip context line the
  export shows ("Zna Twój plan: Malezja, 15 dni"), an empty transcript area carrying a
  `<PreviewNotice>`, and the composer — a disabled `<textarea>` with its placeholder and a disabled
  send button. It is focus-trapped and returns focus to its toggle, on the same mechanism as the item
  dialog, because that behaviour is the part worth having right before there is anything to say into
  it. Below 1280px it is a full-height sheet rather than a drawer.
  - **Nothing about the assistant's future behaviour is designed here.** No message shapes, no
    suggestion chips, no model or provider, no streaming. Chat is the next spec to write, and this is
    a placeholder for its surface, not a head start on its design.
- **TSX:** moderate, confined to structure. `TimelinePage` renders the banner, the action row and the
  dock; the day list gains the anchor/rail wrapper; `ItemRow` gains the icon tile and the optional
  rail dot; `AppShell` gains the drawer slot and its toggle.

### `/trips/:id/days/:date` — the day detail

Reference: `szczeg_y_dnia_i_aktywno_ci`. See
[`mockup-03`](assets/design-system-adoption/mockup-03-day-detail.png).

- **Adopted:** breadcrumb in `label-md` `--text-subtle` above a `headline-xl` day heading with the
  derived stage as an eyebrow; prev/next day as ghost icon buttons keeping the disabled-not-hidden
  treatment and its reasoning; the same item cards as the timeline, so an item looks like itself on
  both screens; the item editor as an elevation-3 dialog at `--radius-xl` over a 12px-blurred
  `#0F172A`/20% backdrop, fields on the input recipe, status as the segmented pill group.
- **The documents panel (preview).** PR #4's "Załączniki i dokumenty dnia" / "Day files and
  documents" panel, in the export's position below the item list: the heading, an empty state, a
  `<PreviewNotice>` pointing at that spec, and the real shape of the control it will use — a
  `<label>` over a **disabled** `<input type="file">` reading "Dodaj plik / zdjęcie / bilet". Disabled
  is right here: a picker that opens and leads nowhere is worse than one that will not open.
- **The reservation disclosure (preview).** Inside the item editor, below the notes field: PR #4's
  collapsed "Dane rezerwacji (opcjonalne)" / "Reservation details (optional)" disclosure. Expanding
  it is a real disclosure — that part works — and inside are its three **disabled** fields
  (confirmation number, amount, currency) and a `<PreviewNotice>`. It is collapsed by default and
  **never auto-opened**, honouring PR #4's fourth invariant, which its own spec broke in an earlier
  draft and fixed. Moving an item to *gotowe* still asks for nothing, still takes one click, and the
  disclosure's presence changes nothing about R02's counter.
- **The status control is still the point of this screen**, and now it looks like it: the three
  statuses as a segmented group of pills in their chip colours, the selected one filled. It remains a
  radio group with visible labels and glyphs — the pill is a coat of paint on the contract, not a
  replacement for it.
- **TSX:** small. A wrapper around the status radios, an icon slot in the day navigation, the
  documents panel, and the disclosure inside `ItemDialog`.

### The accessibility contract, as assertions

Each is already asserted in `frontend/src/**/*.test.tsx` and must still pass, unchanged, after every
phase:

- The status chip renders a translated text node and a `data-status` attribute; colour is an addition
  to the glyph and the label, never a replacement. The new rail dot is `aria-hidden` decoration
  beside the chip.
- The item dialog traps focus and returns it to its trigger. The share dialog and the chat drawer
  join it on the same mechanism and get the same assertions.
- The filter bar is a real radio group with a legend; the pills are styling.
- Every string comes from i18next with a key in both locales; `scripts/check_locales.py` is the
  enforcement, and the preview copy is not exempt.
- `:focus-visible` is never removed. The ring moves to `--primary` with a 2px offset and switches to
  `--primary-fixed` (`#D3E4FF`) on dark surfaces via a scoped override — a `#0f3f6d` ring on a
  `#00294d` banner is invisible.

## 📝 Edge Cases & Failure Scenarios

| Case | Behaviour |
|---|---|
| The webfont fails to load (blocked, offline, corrupt cache) | `font-display: swap` shows the fallback immediately and swaps in when it arrives. No rule depends on the webfont's presence. Nothing errors. |
| Polish diacritics fall back per-glyph | The failure the `latin-ext` subset exists to prevent, and it is silent — the page looks *almost* right. Hence the explicit rendering check in Phase 1 step 1 and again at the end. |
| A very long trip title | The banner title clamps to two lines with an accessible `title`; the header's trip context truncates to one line. Neither pushes the readiness tile off the banner. |
| A trip with zero items | The tile stays in its `data-nothing-tracked` state — no ring, no percentage, muted value — and every day on the rail shows its invitation. Easy to regress while adding a ring, which is why step 19 tests it. |
| A fifteen-day trip with sparse items | The rail runs continuously between sparse days; sticky anchors keep the current date on screen. |
| Three sticky layers on a short viewport | The day anchor's `top` is `calc(var(--header-height) + var(--filter-bar-height))`, both custom properties; below 768px the filter bar stops being sticky — a phone gives up the filter before it gives up the plan. |
| `backdrop-filter` unsupported (older Firefox, some Linux GTK builds) | Every frosted surface declares its solid fallback first and the blur inside `@supports`. The fallback is 96% opaque, so text stays legible without the blur. |
| `prefers-reduced-motion: reduce` | No transitions, no hover scale, no drawer slide — the drawer appears in place. The ring renders at its final value. |
| Forced-colors / high-contrast mode | Elevation and background tints disappear; hairlines, glyphs and text carry the interface. Nothing conveys meaning through a shadow or a background alone — including the preview state, which is why the badge is text. |
| 200% zoom / 320px viewport | Same code path as mobile: single column, no horizontal scrolling, dock content above the canvas, the drawer a full-height sheet. |
| **A user activates a preview control** | Nothing happens — no navigation, no toast, no alert, no console noise. The badge and the notice already said why, and an interruption on every click would be worse than the dead control. |
| **A user tabs into the chat drawer** | Focus is trapped as in any dialog and returns to the toggle on close. The disabled composer is skipped (native `disabled` behaviour, which is correct for a field); the `<PreviewNotice>` is reachable as text. A drawer that trapped focus with nothing focusable inside it would be a keyboard trap, so the close button is always focusable and always first. |
| **A preview outlives its implementation** | The `data-preview` census test fails: it asserts the exact set of preview surfaces this spec declares, so both a forgotten preview and an undeclared new one turn the suite red. This is the mechanism that stops "temporary" from becoming "permanent". |
| **A preview drifts from the spec it previews** | It will, and that is tolerable in one direction only: the preview may be *less* than PR #3 or PR #4 specifies, never *different*. Each preview's copy is quoted from its owning spec, and the implementation PR replaces the surface wholesale rather than editing it — so a drifted preview is deleted, not reconciled. |
| A test asserts on a class name a phase renames | The suite queries by role, label and text — but if one breaks, it was coupled to styling, and the fix is to re-query by role, never to keep the old class as a hostage. Any such change is called out in its PR. |
| An undefined `var()` survives the bridge deletion | CSS fails silently: the property is dropped and the element loses its padding or colour with no error anywhere. Steps 3 and 11 both run the token-completeness check for exactly this reason. |
| The bundle grows | The font is the only meaningful addition: two variable woff2 files, roughly 45–55 KB total, cached across navigations. CSS grows by an estimated 500–700 lines, a few kilobytes compressed; the preview components are a few hundred bytes of TSX. Build output size is recorded before Phase 1 and after Phase 6. |

## 📝 Risks & Impact Review

- **Blast radius: every screen, no data.** This spec can make the application ugly or confusing; it
  cannot lose a trip, corrupt a row, or break the API. No migration, nothing to reconcile, and
  workstream B issues no requests at all. That asymmetry is why the risk stays `risk-low` despite
  touching every route.
- **The honesty risk is the one workstream B introduces, and it is real.** The owner will spend
  October planning a real trip in an app with four visible things that do not work. Mitigations are
  built in — the badge is a word rather than a dimming, nothing is fabricated, activating a preview
  is silent — but the residual cost is a slightly noisier interface for the person who asked for it.
  It is his call and it is a defensible one: the alternative hides the product's shape from its only
  user and stakeholder. If it grates in real use, deleting a preview is a one-line change per
  surface, and the census test names them all.
- **The "temporary becomes permanent" risk** is the reason for `data-preview`, the dedicated feature
  folder, and the census test. Without those, a preview surface is indistinguishable from a feature
  nobody has got around to, and in twelve months nobody can tell which is which.
- **Rollback, per phase**, because this ships as six PRs and not one:

  | Phase | Reverting it alone leaves | Independently revertible? |
  |---|---|---|
  | 1 (tokens, font) | The old palette and font stack; nothing depends on it yet | Yes |
  | 2 (recipes + bridge deletion) | **No** — Phase 2 deletes the bridge, so reverting it alone would leave later rules referencing tokens the revert restores under different meanings. Revert it only together with anything after it. | Only with its successors |
  | 3 (chrome, grid) | The old single-column shell; screens still styled | Yes |
  | 4 (screens) | The new grid with the previous screen rules | Yes |
  | 5 (preview surfaces) | The restyled app with no workstream B — the first draft's scope exactly | Yes, and cleanly: this is the phase most likely to be reverted |
  | 6 (icons, verification) | The starter sprite back; everything else intact | Yes |

  The one non-independent phase is named rather than hidden, and it is the price of closing the
  two-vocabulary window early instead of late.
- **The genuine verification risk is silent regression.** A restyle passes `typecheck`, `test` and
  `build` while looking wrong, because none of the six gate commands can see. The mitigation is the
  verification split: every step below declares whether it is machine-verified or eyes-verified, and
  the eyes-verified ones are a QA checklist, not tests.
- **Contract compatibility:** none of the seven protected surfaces in `BACKWARD_COMPATIBILITY.md` is
  touched. §4 (translation keys) is the only one nearby, and this spec is additive there. Component
  props are additive-optional; internal file layout is explicitly unprotected.
- **Product-decision compatibility:** the **Cut** table is the audit. Every element of the export
  that is not implemented has a named authority; every element that *is* previewed is in the brief's
  *Now* list. This spec proposes to supersede nothing.
- **Neighbour-spec compatibility:** PR #3 and PR #4 own the behaviour behind two preview surfaces.
  This spec quotes their copy and adopts their positions; it decides nothing on their behalf and
  changes neither. If either changes before implementing, the preview is deleted with it. A merge
  conflict between this spec and theirs is a signal that the preview was too specific, not that
  their spec is wrong.
- **Scope creep has a specific shape here:** every screenshot in the export is an invitation to build
  the feature it depicts, and workstream B makes that invitation louder by putting empty containers
  next to it. A PR in this series that gives a preview surface a working backend is out of scope on
  its face — that work belongs to PR #3, PR #4, or the chat spec that does not exist yet.

## 📝 Decisions in play

| Id | How this spec relies on it |
|---|---|
| D01 | The brand rendered is **Smart Trip Planner**; the export's "VoyageAI" lockup supplies layout only. |
| D03 | Chat gets a surface because it is a *Now* capability; the export's AI trip generation is cut because chat adds and changes items rather than generating whole trips. |
| D04, R07 | Nothing in the export's booking, pricing, vendor or live-inventory surface is styled or previewed. |
| D05, R02 | The readiness tile's layout is adopted and its arithmetic is not; the ring is suppressed at a zero denominator. The reservation disclosure changes nothing about the counter. |
| D07, R04 | The reservation fields exist as a preview because cost data is kept when it arrives; budget and currency *chrome* is cut because accounting is *Later*, and brief Q04 stays open and unprejudiced. |
| D08, D09 | The share action and State A of the dialog are previewed; PR #3 owns the behaviour, and guest comments stay cut. |
| D12, N01 | Weather, maps, PDF and calendar export are *Later*, not excluded — nothing is styled for them and nothing is foreclosed. |
| D14 | Drives self-hosting the webfont rather than a third-party CDN request. |
| A05 | Named as a sequencing assumption rather than a scope decision — which is exactly what makes previewing its casualties legitimate rather than a violation. |
| R01 | Both locales stay first-class in the visual work: every mockup and screenshot set is captured in Polish and English, the type scale is verified against Polish diacritics, and preview copy is not exempt from the parity gate. |
| Brief Q02 | "Zadania & Przygotowanie" is cut rather than previewed, because previewing it would answer an open question by building it. |
| Brief Q03, Q04 | Attachment limits and multi-currency stay open; the preview surfaces show no size cap, no format list and no currency list. |

This spec proposes to supersede none of them.

## ✅ Resolved assumptions

Eleven questions were resolved by the autonomous run that drafted this spec and posted for override.
**Q1 was overridden by the owner on 2026-09-06** and the spec was rewritten around the answer; four
new questions arose from that answer and are resolved here in the same way. No assumption is gated —
the ⚠ marker that held this PR in draft is cleared.

| # | Question | Answer | Source |
|---|---|---|---|
| Q1 | "Look like the design" — restyle only, or also stand up the capabilities the export depicts? | **Provide UI for everything V1 plans to deliver; cut what it does not; render the not-yet-built inactive, or without a backend where disabling is impractical.** | **The owner**, on PR #10 |
| Q2 | How is Plus Jakarta Sans delivered? | Self-hosted via `@fontsource-variable/plus-jakarta-sans`, `wght` + `latin-ext`. No third-party request from a publicly deployed app (D14), works offline, and `latin-ext` is what makes the diacritics render in the family. Two files against the static package's eight. | Autonomous default |
| Q3 | CSS-only, or may the restyle change markup? | CSS-first; TSX only where the design needs structure that does not exist. Additive optional props only (`AppShell.dock/context/drawer`, `ItemRow.railDot`, `ReadinessTile.ring`). If roles and existing props do not move, a red test means a real regression. | Autonomous default |
| Q4 | Adopt the export's four-tab top navigation? | No tab row. Two tabs are routes already one click away, one is the documents centre this spec cuts, one is the AI creator mode D03 rules out. | Autonomous default |
| Q5 | Ship a dark mode? | No. The export defines one scheme; a second is new design work. Purely additive later. | Autonomous default |
| Q6 | Keep one 798-line `index.css`, or split it? | Split into `styles/{tokens,base,chrome,components,screens}.css` in a fixed, commented order. File layout below a boundary is explicitly unprotected, and separating the token file is what every design system benchmarked here converges on. | Autonomous default |
| Q7 | Add visual-regression tooling? | No new tooling. The vitest suite covers what is assertable; the rest is a declared manual QA checklist plus per-phase screenshot sets. Every step is labelled **(automated)** or **(visual QA)** so nothing a human must look at is called a test. Adding VRT is its own spec and stays additive. | Autonomous default |
| Q8 | Adopt the export's percentage ring on the readiness tile? | Yes, arithmetic unchanged and the ring suppressed at a zero denominator; `aria-hidden`, never replacing the "x of y" text. | Autonomous default |
| Q9 | What fills the export's right-hand column? | Trip metadata promoted out of the main column. The concierge drawer that occupied it in the export now exists as a preview at the right *edge*, where the export actually anchors it — the dock and the drawer are different surfaces. | Autonomous default, revised by Q1 |
| Q10 | `/trips` has no counterpart in the export. Restyle it? | Yes, by analogy from the card and empty-state recipes. It is the first screen after login and the most visible place to leave half-migrated. | Autonomous default |
| Q11 | One spec or three? | One spec, six phases, with the bridge created and destroyed inside Phases 1–2 and workstream B sequenced last. | Autonomous default |
| **Q12** | How is "inactive" expressed, concretely? | Three mechanisms by element type, defined once: controls get `aria-disabled` + a text `Wkrótce`/`Soon` badge + a no-op handler (never native `disabled`, which removes them from the tab order and explains nothing); data-entry fields get native `disabled` (a field that accepts input and discards it is worse than one that refuses it); whole surfaces get a `<PreviewNotice>` in place of content. Everything carries `data-preview="true"`. | Follows from Q1 |
| **Q13** | Does the export's "Rezerwacje i Dokumenty" centre become a preview route? | No — cut. It is not in the *Now* list, and PR #4 puts documents on the day detail rather than in a trip-wide vault. A whole route with nothing behind it promises more than this spec should. | Follows from Q1 |
| **Q14** | Does chat get a route or a drawer? | A right-edge drawer opened from the header, as the export anchors it — no route, no URL, no history entry. A route would need a place in the router and a redirect story for a feature with no spec; a drawer is deleted by removing one slot. | Follows from Q1 |
| **Q15** | How do the previews avoid outliving the features they preview? | A `data-preview` census test asserting the exact set of surfaces this spec declares, so both a forgotten preview and an undeclared new one turn the suite red; the preview primitives live in their own feature folder designed for deletion. | Follows from Q1 |

## 📋 Phasing

Six phases. Each is independently shippable and each leaves every screen working and every gate
green. Each ends with a screenshot set of all five routes in **both locales** — that set is the
review artifact, because no command in the validation gate can see.

| Phase | Delivers | Visible after it |
|---|---|---|
| 1 | The typeface and the token layer, with the compatibility bridge | Every screen in the real palette and the real typeface, same layout |
| 2 | The component recipes; the bridge deleted | Buttons, inputs, chips, cards and dialogs as designed, on one token vocabulary |
| 3 | The chrome and the grid | The frosted header, the split-surface layout, the dock |
| 4 | The screens | The trip banner, the timeline rail, the creator and the day detail as the export lays them out |
| 5 | **The V1 preview surfaces** | Chat, sharing, documents and reservation data visible, inert and honest |
| 6 | Icons and the verification pass | The starter sprite gone; contrast, diacritics and locale evidence recorded |

Phases 1 and 2 are the majority of the visible gain for a minority of the risk. Phase 5 is the one
most likely to be cut or revised, and it is last so that cutting it costs nothing already shipped.

## 📋 Implementation Plan

Every step declares how it is verified. **(automated)** means a command or a test in the existing
gate can fail on it. **(visual QA)** means a human — or an agent with the browser provider — looks at
a screenshot; those are a checklist, not tests, and Q7 explains why that is the accepted trade.

### Phase 1 — The typeface and the token layer

1. Add `@fontsource-variable/plus-jakarta-sans` (lockfile in the same commit, per `AGENTS.md`) and
   import `wght.css` + `latin-ext.css` from `main.tsx`.
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
   `--space-1..8`, `--radius-sm/md/lg`, `--shadow-card`, `--font-sans` — and reduce `index.css`'s
   `:root` block to an import of `tokens.css`.
   *(automated)* a token-completeness check — a short script collecting every `var(--x)` in
   `frontend/src` and failing on any name `tokens.css` does not define — passes, and the full suite
   passes unchanged. This is the guard against the silent-CSS-failure case and runs again in step 11.
   *(visual QA)* every screen renders in the new palette with no layout movement.
4. Move the reset, `body`, headings, links, focus ring and reduced-motion rules into
   `styles/base.css`; bind `h1`–`h4` to the type scale; switch the focus ring to `--primary` and add
   the `--primary-fixed` override for dark surfaces.
   *(visual QA)* keyboard-tab every screen — the ring is visible on the canvas and on dark surfaces.
5. Record the contrast table for every pair `tokens.css` defines, in the PR body.
   *(automated)* a contrast script over the token file fails on any body-text pair below 4.5:1 or any
   large-text/boundary pair below 3:1.
6. Capture the phase-1 screenshot set: five routes × two locales.
   *(automated)* ten non-empty PNGs exist. *(visual QA)* reviewed.

### Phase 2 — The component recipes, and the bridge goes

7. Split `components.css` out of `index.css` and rewrite the button recipes: primary, deep
   (`--primary-deep`, the form-completing action), ghost, danger, danger-solid. No accent-button
   recipe: `--secondary`'s documented uses are all cut and it fails contrast behind text (3.56:1), so
   a recipe for it would be speculative dead CSS.
   *(automated)* existing button assertions pass. *(visual QA)* no button falls back to browser
   defaults.
8. Rewrite the input, select, textarea and date-input recipes: `#FFFFFF` on 1px `#CBD5E1`,
   `--radius`, 2px `--primary` active outline; the invalid state adds a border colour *and* keeps the
   existing `role="alert"` text; a `:disabled` state is defined now because Phase 5 needs it.
   *(automated)* the login and item-dialog form tests pass, including the invalid-state assertions.
9. Rewrite the status chip recipes to the three corrected triples and add the 6px dot as an
   `aria-hidden` sibling of the existing glyph.
   *(automated)* every status assertion passes, and a test asserts each chip still exposes its glyph
   and translated label — the colour-blind contract, assertable in jsdom because it is about text
   nodes and attributes, not paint.
10. Introduce the elevation utilities and apply them: cards and rows at elevation-1 with hover/focus
    at elevation-2; dialogs and drawers at elevation-3 at `--radius-xl` over a `#0F172A`/20% backdrop
    with `backdrop-filter: blur(12px)` inside `@supports` and a 96%-opaque fallback first.
    *(automated)* the dialog focus-trap tests pass. *(visual QA)* the dialog is legible with
    `backdrop-filter` disabled.
11. Migrate the last rules off the bridge aliases and delete the bridge.
    *(automated)* `grep -rE '\-\-(colour-|space-[0-9]|shadow-card)' frontend/src` returns nothing, and
    the step-3 token-completeness check passes.
12. Capture the phase-2 screenshot set. *(automated)* ten non-empty PNGs. *(visual QA)* reviewed.

### Phase 3 — The chrome and the grid

13. Rebuild the header in `styles/chrome.css` and `AppShell.tsx`: sticky, frosted with its `@supports`
    fallback, `--header-height` as a custom property, wordmark in `headline-sm`, controls grouped
    right.
    *(automated)* `AppShell`'s existing tests pass unchanged. *(visual QA)* the header stays put while
    the page scrolls.
14. Add the optional `context` prop and populate it on trip-scoped routes, truncating to one line.
    *(automated)* the new keys exist in both locales; a test renders `AppShell` without `context` to
    prove the prop is optional. *(visual QA)* a 120-character title does not wrap the header.
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
19. `/trips/:id` — the readiness ring behind the optional `ring` prop: a `conic-gradient` disc,
    `aria-hidden`, rendered only above a zero denominator, beside the untouched "x of y" text.
    *(automated)* a new unit test asserts that at a zero denominator no ring element and no percentage
    string is rendered and the text node is unchanged — the R02 regression guard.
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

### Phase 5 — The V1 preview surfaces

25. Add `frontend/src/features/preview/` with `PreviewBadge`, `PreviewAction` and `PreviewNotice`,
    their styles in `components.css`, and their copy in both locales.
    *(automated)* unit tests assert: `PreviewAction` renders `aria-disabled="true"` and **not** the
    native `disabled` attribute, stays in the tab order, includes the badge text in its accessible
    name, and its `onClick` does nothing; `PreviewNotice` renders a real paragraph; every string
    resolves in `en` and `pl` and the parity gate passes.
26. The share preview: "Udostępnij" as a `<PreviewAction>` in the timeline's action row, opening a
    focus-trapped dialog carrying PR #3's State A consequence sentence, a preview "Utwórz link" and a
    `<PreviewNotice>` pointing at that spec.
    *(automated)* the dialog traps focus and returns it to its trigger, and a test asserts no token,
    URL field or revoke control is rendered — the fabrication guard.
27. The chat drawer preview: the header toggle, the right-edge drawer at elevation-3 (full-height
    sheet below 1280px), the trip-context line, an empty transcript with its `<PreviewNotice>`, and a
    disabled composer with a disabled send button.
    *(automated)* the drawer traps focus, closes on `Escape` and on backdrop click, returns focus to
    the toggle, and its close button is focusable and first in order — the keyboard-trap guard; the
    composer carries the native `disabled` attribute.
28. The documents-panel preview on the day detail: PR #4's heading and position, an empty state, a
    `<PreviewNotice>`, and a `<label>` over a **disabled** `<input type="file">`.
    *(automated)* the input is `disabled` and labelled; the panel does not appear on the timeline; no
    fabricated document row is rendered.
29. The reservation-disclosure preview inside `ItemDialog`: collapsed by default, expandable, three
    disabled fields, a `<PreviewNotice>`.
    *(automated)* the disclosure is collapsed on open and is never auto-opened by attaching, saving or
    changing status (PR #4 invariant 4); moving an item to *done* still requires exactly one
    interaction and the readiness counter is unchanged — the R02 and invariant-2 guard.
30. The `data-preview` census test: assert the exact set of preview surfaces — four, at the positions
    this spec declares — so a forgotten preview or an undeclared new one fails the suite.
    *(automated)* the census test itself.
31. Capture the phase-5 set, including the drawer open and the share dialog open, in both locales.
    *(automated)* sixteen non-empty PNGs. *(visual QA)* every preview reads as "coming", not as
    "broken".

### Phase 6 — Icons and the verification pass

32. Add `frontend/src/assets/icons.svg` with the five item-kind glyphs, two chevrons and the three
    workstream-B glyphs; add the `<Icon>` wrapper with `aria-hidden` / `focusable="false"`; point the
    item card, day navigation and preview controls at it; delete `frontend/public/icons.svg`.
    *(automated)* no reference to the deleted file survives (`grep` over `src/` and `index.html`);
    every icon has a translated text label beside it, asserted per call site; `npm run build` emits
    the hashed sprite; the token-completeness check still passes.
33. Final verification pass.
    *(automated)* the six gate commands; the contrast script over the final token file; the census
    test; bundle-size before/after recorded.
    *(visual QA)* the diacritics check at every weight in use; a `prefers-reduced-motion` capture; a
    forced-colors capture, in which every preview must still read as unavailable through its badge
    text rather than through dimming. Every artifact goes in the PR body.
