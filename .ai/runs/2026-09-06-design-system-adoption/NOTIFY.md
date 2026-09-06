# Notify — 2026-09-06-design-system-adoption

> Append-only log. Every entry is UTC-timestamped. Never rewrite prior entries.

## 2026-09-06T13:02:02Z — run started
- Brief: implement `.ai/specs/2026-09-06-design-system-adoption.md` — adopt the design system as the app's real visual layer and stand up the four V1 preview surfaces.
- External skill URLs: none
- Engine: `om-auto-create-pr-loop` (steps: 33, --loop: no) — routed by `om-auto-create-pr` because the spec's Implementation Plan exceeds `engine.loopStepThreshold` = 20.
- Decision: the spec's rollback table describes six PRs; the `om-auto-implement-spec` contract is exactly one implementation PR per spec, so all six phases ship on one PR as six contiguous, independently reviewable commit ranges. Recorded in PLAN.md under "Delivery shape".

## 2026-09-06T13:06:07Z — Step 1.1 scope decision: single `wght.css` import, not `wght.css` + `latin-ext.css`
- The spec (Q2 / "The typeface") assumes `@fontsource-variable/plus-jakarta-sans` publishes a separate, individually-importable `latin-ext.css` alongside `wght.css`, for "two woff2 files, one per subset". Verified against the installed package (5.3.0) and every published version back to 5.0.0: the variable build only ever ships `index.css`/`wght.css`/`wght-italic.css`, each of which already bundles **all four** subsets (`latin`, `latin-ext`, `cyrillic-ext`, `vietnamese`) as separate `@font-face` blocks gated by `unicode-range` inside the one file. There is no `latin-ext.css` to import; `require.resolve` confirms the file does not exist in the package.
- Since `wght.css` already contains the `latin-ext` `@font-face` block, importing it alone already renders Polish diacritics in the family (the functional goal Q2 names) — a second import isn't needed and doesn't exist.
- Chose the single officially-documented import (`@fontsource-variable/plus-jakarta-sans/wght.css`) over hand-authoring custom `@font-face` rules against the package's `files/*` export to force exactly two subsets. Hand-rolling would hit the "two woff2 assets" checkpoint number exactly, but means maintaining copies of vendor-generated `@font-face` declarations by hand — judged worse than a one-line, upgrade-safe import.
- Consequence: `npm run build` emits **three** distinct woff2 files under `frontend/dist/assets/` (`latin`, `latin-ext`, `vietnamese`) plus `cyrillic-ext` inlined as base64 in the CSS (below Vite's 4KB asset-inline threshold) — not the two the plan's Step 1.1 checkpoint line names. Functionally equivalent (a browser only ever fetches the woff2 whose `unicode-range` matches text actually on the page — this app never renders Cyrillic or Vietnamese glyphs), but the literal asset count differs. Flagging for the checkpoint reviewer and for Step 6.2's bundle-size pass.
