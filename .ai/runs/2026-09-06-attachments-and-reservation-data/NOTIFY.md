# Notify — 2026-09-06-attachments-and-reservation-data

> Append-only log. Every entry is UTC-timestamped. Never rewrite prior entries.

## 2026-09-06T16:27:06Z — run started
- Brief: implement `.ai/specs/2026-09-05-attachments-and-reservation-data.md` — attachments on days
  and items, plus reservation data (confirmation number and cost) on the item.
- External skill URLs: none.
- Engine decision: `Engine: om-auto-create-pr-loop (steps: 28, --loop: no)` — the spec's
  Implementation Plan drafts 28 Steps across 4 phases, over the configured threshold of 20.
- Slot check: free — no `feat/attachments-and-reservation-data` branch, no run folder for the slug,
  and no open PRs in the repository at all.
- Decision: `python-multipart` will be added as a backend dependency in Step 1.6. FastAPI needs it
  for `multipart/form-data`, and it is not in `backend/pyproject.toml` today. It is the only
  dependency this run adds; the spec's "no image library" rule is asserted by a test in Step 1.2.

## 2026-09-06T17:05:00Z — checkpoint 1
- Steps covered: 1.1..1.5 (`f6360f9..da84350`). Backend vocabulary complete; no endpoint wired yet.
- Outcome: PASS. `check_locales` / `check_css_tokens` / `check_contrast` green, `ruff` clean,
  `pytest` **520 passed / 0 skipped**, frontend typecheck and 149 tests green. `npm run build` is
  deferred to the final gate because no application source changed in this window.
- UI verification skipped, with reason: no Step in the window touched a page, component or
  stylesheet — the frontend diff is a generated type union and nine locale keys.
- Step review (checkpoint mode): no blocker and no major findings. Two nits recorded and deferred
  to the final review — `normalise_filename` strips after truncating, and `INSTALLATION_LOCK_KEY`
  shares an advisory keyspace with `hashtext(trip_id)` (harmless extra serialisation at worst).
- Decision — Tasks-table SHA reconciliation. The per-Step "commit, read SHA, edit PLAN.md, amend"
  procedure can only ever record the *pre-amend* SHA, because amending changes the SHA it just
  recorded. Executors therefore record the pre-amend value and the main session rewrites the whole
  `Commit` column to the real post-amend SHAs at every checkpoint. All five rows were reconciled
  here (1.1 `a76361d`, 1.2 `223399b`, 1.3 `17215fb`, 1.4 `8cc3dc2`, 1.5 `da84350`), so
  `om-auto-continue-pr-loop` resumes against SHAs that actually exist on the branch.
- Environment note: `frontend/node_modules` was absent in this worktree and `npm ci` was run. The
  first typecheck failure was that absence, not the diff.
