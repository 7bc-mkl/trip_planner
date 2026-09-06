# Visual evidence — design-system-adoption

Attached to the spec PR and referenced from `.ai/specs/2026-09-06-design-system-adoption.md`.

## Current state — the running application, 2026-09-06

Captured through the configured browser provider (`agent-browser`) against the shared test
environment (`.ai/scripts/test-env-up.sh`), on `main` at `b954dbd`, with a seeded fifteen-day
Malaysia trip. Data is fixture data typed for this capture, not anyone's real plan.

| File | Screen |
|---|---|
| `current-01-login.png` | `/login` |
| `current-02-trips.png` | `/trips` |
| `current-03-timeline.png` | `/trips/:id` |
| `current-04-day-detail.png` | `/trips/:id/days/:date` |
| `current-05-trip-creator.png` | `/trips/new` |

## Proposed — illustrative mockups

Self-contained static HTML with no application code behind it, rendered to PNG by the same browser
provider. They communicate layout, hierarchy and the token set — not pixel-perfect design, and not a
promise about markup.

| File | Shows |
|---|---|
| `mockup-01-tokens-and-components.*` | Palette, type scale, buttons, fields, status chips, segmented control, elevations |
| `mockup-02-timeline.*` | `/trips/:id` — trip banner, readiness tile and ring, sticky filter bar, the timeline rail, the dock (Polish) |
| `mockup-03-day-detail.*` | `/trips/:id/days/:date` — day header, item cards, the item editor dialog (English) |
| `mockup-04-trip-creator.*` | `/trips/new` — grouped field cards, the segmented route mode, numbered stages, the summary dock (Polish) |

`_mockup.css` is shared by all four.

## `fonts/`

`pjs-latin.woff2` and `pjs-latin-ext.woff2` are the Plus Jakarta Sans variable subsets, taken from
the `@fontsource-variable/plus-jakarta-sans` package. They exist here only so the mockups render in
the real typeface with no network request, and so the `latin-ext` subset visibly carries the Polish
diacritics the spec's Q2 turns on. Plus Jakarta Sans is licensed under the SIL Open Font License 1.1.
The application will load the font from the npm package, not from this directory.
