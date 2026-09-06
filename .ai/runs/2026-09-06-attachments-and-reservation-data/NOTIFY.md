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

## 2026-09-06T18:12:00Z — Step 1.8 scope decision: the reservation fields moved to Step 3.1
- Situation: Step 1.8 was drafted to add both the attachment counts/lists **and** the three
  reservation fields (`confirmation_number`, `cost_amount`, `cost_currency`) to `ItemRead` and
  `ItemUpdate`. Those three are `item` **columns**, and Step 3.1 adds them on its own Alembic
  revision precisely so Phase 3 rolls back alone (assumption A1). At 1.8 the columns do not exist.
- Decision: **resolution (ii)** — the attachment half landed in Step 1.8; the reservation half moves
  into Step 3.1's commit, alongside the migration and the model columns it reads and writes.
- Why: the split holds cleanly. Nothing in the attachment work needs the reservation columns, and
  nothing in the reservation contract can be written without them — a serialiser field for a column
  that does not exist is not a half-landed contract, it is a broken one, and `ItemUpdate` would have
  had to accept fields it could not persist. Pulling `0006_item_reservation` forward into Phase 1
  (resolution (i)) would have bought nothing and would have destroyed the property the phase split
  exists for: Phase 3 rolling back on its own.
- Effect on the plan: PLAN.md's Step 1.8 text now describes the attachment half only and records
  this decision; Step 3.1's text now carries the API half verbatim — the `Decimal` on the wire, the
  `model_fields_set` clear-vs-omit rule, `422 invalid_cost` for one half alone through
  `domain/money.py`, `422 invalid_reservation_field` past 500 characters, `""` meaning clear, and no
  second copy of the reservation's dates. The cost/confirmation tests move with it.
- Step ids, `Exec` cells and the Tasks table's shape are unchanged; only the two Step descriptions
  and row 1.8's `Status`/`Commit` were touched.
