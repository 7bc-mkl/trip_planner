# Checkpoint 3 — Steps 2.1..2.5

- Fired: 2026-09-06T20:40Z, after 5 Steps landed since checkpoint 2.
- Commit range: `59ff245..d83e6eb`.
- Steps covered: 2.1, 2.2, 2.3, 2.4, 2.5.
- Touched areas: `frontend/src/api/` (`attachments.ts` new, `client.ts`, `items.ts`),
  `frontend/src/features/trips/` (`UploadDropzone`, `DayAttachments`, `ItemAttachments`,
  `AttachmentRow` — all new — plus `DayDetailPage`, `ItemDialog`, `ItemRow`, `format.ts`),
  `frontend/src/components/Icon.tsx`, `frontend/src/assets/icons.svg`,
  `frontend/src/styles/components.css`, both locale files.
  **This window is the first time the feature has had a rendered surface**, so UI verification ran
  for real.

## Checks run

| Check | Result | Notes |
|---|---|---|
| `python3 scripts/check_locales.py` | ✅ PASS | |
| `python3 scripts/check_css_tokens.py` | ✅ PASS | Every `var()` in the new CSS resolves. |
| `python3 scripts/check_contrast.py` | ✅ PASS | Still 16 declared pairs — **no row was added**, because the state pills reuse the shipped status-chip triples and the failure pill reuses the already-declared `--danger-surface` / `--on-danger-surface`. |
| `(cd backend && uv run ruff check .)` | ✅ PASS | |
| `(cd backend && uv run pytest)` | ✅ PASS | 600 passed, 0 skipped — unchanged, as no backend code moved. |
| `(cd frontend && npm run typecheck)` | ✅ PASS | |
| `(cd frontend && npm run test -- --run)` | ✅ PASS | **213 tests** (was 149 at checkpoint 2). |
| `(cd frontend && npm run build)` | ✅ PASS | Run this time — frontend source changed. |

**All eight gate commands are green, and the feature is still defective.** That gap is the most
important thing this checkpoint records, and it is the argument for doing the browser walk at all.

## UI verification — ran for real

The QA environment was brought up with `.ai/scripts/test-env-up.sh`: `create_production_app` serving
the real `npm run build` bundle from **one origin** in front of a freshly recreated PostgreSQL
database, so cookies and CSRF behave as deployed. A subagent drove `agent-browser` v0.34.0 through
the full path — log in, create a trip, open a day, upload to the day, upload a refusal case, add an
item, upload to the item, delete with confirmation — in **both locales**.

**Verdict: PARTIAL.** Everything Steps 2.1–2.5 were asked to build does work end to end:

- the day panel renders below the item list with the correct empty state and the right headings in
  both locales;
- PDF and PNG upload and show filename, size and — for the PNG — the lazy-loaded original as its
  preview with the filename as `alt`; a PDF shows the document glyph;
- the item strip exists, and on an unsaved item shows guidance rather than a control that throws;
- an item upload works and the item row then shows the paperclip with its count;
- the delete dialog **names the file** in both locales; cancel keeps, confirm removes;
- the action reads **Pobierz / Download**, never "Preview", and its `href` answers `200` with
  `Content-Disposition: attachment`;
- both the wrong-type and the over-10 MB refusals are translated in both locales, and the oversize
  case correctly offers no "try again".

### Defects found — none of which any gate command could see

1. **Polish text leaks into the English UI (major, R01/R09).** The `aria-live` announcement stores a
   string formatted at upload time and never re-renders. Upload in Polish, switch to English: the
   page is entirely English except that line, still reading "Wysyłanie …: 100%". `check_locales.py`
   structurally cannot catch this — both keys exist and are in sync; what is wrong is *when* the
   string was formatted. Evidence: `screenshot-defect-stale-polish-status-in-english.png`.
2. **A rejected upload still announces "100%" (major, accessibility).** HTML bytes named `.jpg` are
   correctly refused with a translated message, but the live region above still says the upload
   reached 100%. A screen-reader user is told a failed upload succeeded.
3. **The completed upload queue never clears (major).** After two successful uploads each file
   appears **twice** — once as a real attachment row, once again below the dropzone as "✓ Dodany".
   The duplication grows with every upload and only a reload clears it.
4. **The queue goes stale against reality (major).** After a confirmed delete the attachment row
   disappears correctly, but the queue still shows the file as added — asserting a file that no
   longer exists.
5. **Cosmetic (nit).** In the narrow item modal a long filename wraps mid-word.

Defects 1–4 are routed as two fix Steps appended to the Tasks table, per the step-review contract
(blocker/major → fix now; minor/nit → defer to the final review):

- **2.2-review-fix-1** — defects 1 and 2: derive the announcement from state at render time rather
  than at event time, and make a terminal failure announce the failure.
- **2.2-review-fix-2** — defects 3 and 4: a successful upload's queue entry retires once the host
  list has refreshed, so the attachment row is the file's one representation.

Defect 5 is deferred to the final `om-auto-review-pr` pass with the nits from checkpoints 1 and 2.

## Process deviation recorded

Step 2.4's executor produced **two** commits — the code commit `2672e2f` and a docs-only
`96fa3a7` logging its scope decisions — against the one-Step-one-commit rule. It was not
force-fixed: the second commit changes no code, so bisect-by-Step is unaffected, and rewriting
pushed history to tidy a docs commit would cost more than the deviation does. Subsequent executor
prompts carry an explicit instruction not to repeat it, and Step 2.5 produced exactly one commit.

## Environment notes (not application defects)

- `agent-browser` was not on `PATH`; the cached v0.34.0 binary was used, as the provider descriptor
  allows.
- Chrome refused to launch until `TMPDIR` was overridden to `/tmp` — the worktree's temp path is too
  long for Chromium's singleton socket. Worth knowing for Step 3.7 and for any later QA run from a
  deeply nested worktree.

## Artifacts

`checkpoint-3-artifacts/` — 14 screenshots plus `browser-session.log` (credentials redacted). The
credentials in `.ai/qa/test-env.env` were never echoed into any artifact, filename or report.
