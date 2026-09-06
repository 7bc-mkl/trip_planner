# Final gate — spec complete (Phase 5 cut by the owner)

Fired when every remaining row in the Tasks table reached `done`: Steps 1.1 – 4.8 and 6.1 – 6.2,
**26 Steps**. Phase 5's seven Steps were cut by the owner at the safety checkpoint — see
`PLAN.md` → "Scope change". This gate subsumes checkpoint 5.

## Full validation gate — all eight commands, in order

| # | Command | Result |
|---|---|---|
| 1 | `python3 scripts/check_locales.py` | ✅ `en`, `pl` in sync |
| 2 | `python3 scripts/check_css_tokens.py` | ✅ 499 `var()` references across 44 files resolve against `tokens.css` |
| 3 | `python3 scripts/check_contrast.py` | ✅ 16 pairs, all meeting WCAG AA (13 body ≥ 4.5:1, 3 large/UI-boundary ≥ 3:1) |
| 4 | `(cd backend && uv run ruff check .)` | ✅ All checks passed |
| 5 | `(cd backend && uv run pytest)` | ✅ **414 passed** — not skipped; the database is reachable, so the data layer is genuinely verified |
| 6 | `(cd frontend && npm run typecheck)` | ✅ |
| 7 | `(cd frontend && npm run test -- --run)` | ✅ **148 passed / 148** (main: 127; this run adds 21) |
| 8 | `(cd frontend && npm run build)` | ✅ |

Two of those eight commands did not exist before this run. Both were built by the spec, in
Steps 1.3 and 1.5, and both are wired into `.ai/agentic.config.json`, the CI workflow,
`AGENTS.md`, `SDLC.md` and `README.md` together, as `AGENTS.md` requires.

## Contrast — the final token file

`contrast-table.txt` holds the full run. Every pair passes. Two values are the design's own
failures, **corrected rather than inherited**, with the ratio recorded beside each token:

| Role | `DESIGN.md` | Ratio | Adopted | Ratio |
|---|---|---|---|---|
| Confirmed chip text on `#ECFDF5` | `#059669` | 3.58:1 ❌ | `#047857` | **5.21:1** ✅ |
| In-progress chip text on `#FFFBEB` | `#D97706` | 3.07:1 ❌ | `#B45309` | **4.84:1** ✅ |
| Field boundary on `#FFFFFF` | `#CBD5E1` | 1.48:1 ❌ | `--field-border: #84919F` | **3.21:1** ✅ |

The third is this run's own finding, not the spec's: `DESIGN.md` prescribes `#CBD5E1` for the
input border, which fails WCAG 1.4.11 for a boundary required to identify a control. The token
was split by role — `--hairline-strong` keeps the design's value for decorative use (the
elevation-2 hover border, the dashed dropzone), and fields consume the corrected one.

Step 4.2 added a sixteenth pair, `--danger-surface` on `--primary-deep` (11.45:1), because
`--danger` on the deep banner fill is 1.6:1 and the banner carries a delete action.

## Integration suite

⏭️ **Skipped — the repository has no integration or E2E suite.** `frontend/package.json`
defines `test` (Vitest, jsdom) and nothing else; there is no Playwright, Cypress or equivalent
runner, and `.ai/agentic.config.json`'s `validation.commands` names none. Adding one is out of
this spec's scope by its own non-goals ("no visual-regression tooling", Q7) and would be its
own spec.

The browser-driven verification that *did* run is recorded under **Visual QA** below: five
routes × two locales at two viewports, at every phase boundary, plus the specimen captures.

## Design-system / style compliance pass

⏭️ **Skipped — the repository has no design-system lint or style-compliance skill.** There is
no repo-local skill under `.ai/skills/` for it (only `om-prepare-test-env`) and no configured
command. The nearest equivalents are the two checks this run *built*: `check_css_tokens.py`
(every `var()` resolves against the token file — the machine-checkable half of "consume the
design system, do not invent values") and `check_contrast.py` (the palette meets WCAG AA).
Both are in the gate above and both pass.

## Bundle size — before and after

Measured by building `origin/main` in a throwaway worktree and this branch's HEAD.

| Asset | `main` | This branch | Δ |
|---|---|---|---|
| CSS | 11.52 kB (gzip 2.34) | 33.70 kB (gzip **7.99**) | +22.18 kB raw, **+5.65 kB gzip** |
| JS | 353.56 kB (gzip 111.28) | 359.40 kB (gzip **112.46**) | +5.84 kB raw, **+1.18 kB gzip** |
| Icon sprite | — | 3.67 kB (gzip 1.48) | new; replaces an unreferenced starter sprite of the same shape |
| Webfont (fetched) | — | **49.06 kB** | new: `latin` 27.34 + `latin-ext` 21.72 |
| Webfont (never fetched) | — | 8.35 kB | `vietnamese`, gated by `unicode-range`; no page in this product renders those glyphs |

Against the spec's own estimate: it predicted "roughly 45–55 KB" of font and "a few kilobytes
compressed" of CSS. The font a Polish or English page actually fetches is **49.06 kB**, inside
that range, and the CSS grew **5.65 kB gzip**. The estimate held.

The font is cached across navigations and `font-display: swap` keeps first paint text-visible,
so the cost is one-time and never blocking.

## Visual QA

Artifacts in `final-gate-artifacts/`. Per-phase sets are in `checkpoint-1..4-artifacts/`.

| Check | Result |
|---|---|
| Five routes × two locales, 1440×1000 | ✅ 10 captures |
| Timeline and day detail at 360×800, both locales | ✅ 4 captures — **after a correction**, see below |
| **Polish diacritics at every weight in use** | ✅ `qa-diacritics-specimen.png` — `ą ć ę ł ń ó ś ź ż` and their capitals at 400/500/600/700/800, plus `display-lg` at 700 and `body-sm` at 400. Every glyph is in Plus Jakarta Sans's own forms: the ogonek on `ą`/`ę`, the stroke through `ł`, the acute on `ć ń ó ś ź`, the dot on `ż`. No per-glyph fallback — which is the silent failure the `latin-ext` subset exists to prevent, and the reason this capture is a specimen rather than a glance at a screen. |
| `prefers-reduced-motion: reduce` | ✅ `qa-reduced-motion-timeline.png` — the timeline renders complete and correct with no transition, no hover scale, and the readiness ring at its final value. |
| **Forced-colors / high-contrast** | ⚠️ **Could not run.** The configured browser provider (`agent-browser` v0.34.0) exposes `set media [dark\|light] [reduced-motion]` and no forced-colors emulation, and its CDP passthrough would need a WebSocket client the toolchain does not have. Noted rather than faked. The assertable half of the contract *is* covered by the suite: every status chip renders a translated text node and a glyph beside its `data-status` attribute, so nothing conveys status through a background or a shadow alone — Step 2.3 added two tests for exactly that, and they are in the 148. What remains unverified is the *rendering* under forced colors, which needs a human on a machine with high-contrast mode on. |
| Preview surfaces read as unavailable through badge text | ⏭️ **n/a — Phase 5 cut.** There are no preview surfaces in this PR. |

## Census test

⏭️ **n/a — Phase 5 cut.** The `data-preview` census test is Step 5.6's deliverable and has
nothing to assert: `grep -r 'data-preview' frontend/src` returns nothing, which is the correct
state for a PR that ships no preview surfaces.

## Verdict

✅ The final gate passes. All eight validation commands are green including the backend suite;
the contrast, token-completeness and bundle-size evidence is recorded above; the two checks
that could not run are named with their reason, and the two that are `n/a` are `n/a` because
the owner cut the phase that would have given them something to check.

## Correction — this gate's own 360px check was too shallow

The row above originally read *"✅ single column, no horizontal scrolling"*. Both halves were
true and both missed the point: at 360px the timeline's item titles were breaking to roughly
one character per line — `Petr / onas / Tow / ers / — / skyb / ridg / e` — in the very files
this gate signed off. The authoritative code review caught it from these committed artifacts,
and it landed as Step 4.9-review-fix.

Recording it because the failure is instructive rather than embarrassing: a visual check that
asks only "does it overflow" will pass a screen nobody can read. The question a 360px capture
has to answer is "is this usable", and that needs a human or an agent to actually look at the
image rather than tick a geometric property.

## Post-review re-verification (after Steps 4.9 / 6.3 / 6.4-review-fix)

The review's two majors and one of its minors were re-checked in Chrome against the fixes, not
merely re-read:

| Claim | Before | After |
|---|---|---|
| Header paints over the modal, its controls stay clickable | `overlay z=10, header z=20`; `elementFromPoint` at the header's right returned `BUTTON.button-quiet "Sign out"`, **outside** the overlay | `overlay z=30, header z=20`; the same probe returns `DIV.dialog-overlay`, **inside** the overlay |
| 360px timeline title | broken per character | first title `230px × 24px`, one line, full text `WAW → KUL, LOT 7822 / MH 3` |
| Sticky day anchor covered by the wrapped filter bar | bar measured **88px** at 768/800px against a token claiming 52px; anchor sticky and covered | token corrected to `3.5rem` (56px, the measured single-row height); anchor `static` at 768/800px where the bar wraps, `sticky` from 900px where it demonstrably fits |

Gate after the fixes: all eight commands green, **149 frontend tests** (+1 — the layering
contract now has a regression test that was proved to fail when the overlay is put back to 10).
The screenshot sets in `final-gate-artifacts/` were re-captured after the fixes, with the
hardened capture script that now reads the applied locale back and fails on a mismatch, waits
on `document.fonts.ready`, and asserts an expected element per screen before shooting.
