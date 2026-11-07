# Execution plan — the reservation inbox, Phase 3 (extraction and the action item)

- Date: 2026-11-07 · Branch: `feat/reservation-inbox-action-items` · Base: `main`
- Source doc: `.ai/specs/2026-09-26-reservation-inbox.md`
- Builds on: Phase 1 (#19, the inbox spine) and Phase 2 (#21, routing), both merged.

## Goal

**D21 made real: a forwarded confirmation becomes an action item the owner
approves, field by field, and R04's reservation data arrives without being
typed.** The routing call that already picks a trip also returns a sparse set of
extracted fields; the deterministic target rule points the proposal at an
existing item or at a day for a new one; and the owner's approval is the only
code path through which inbound content ever writes to `item`.

## Scope

The spec's Phase 3, all nine steps. **Out:** Phase 4 (the "read this document"
egress action, quarantine counter polish, the duplicate hint, the owner retry
action) — the slippable tail, unchanged by this.

## Decisions taken inside the spec's latitude

- **The approval service lives outside `inbound/`**, in
  `trip_planner/approvals.py`. `tests/test_inbox_boundary.py` forbids any module
  under `inbound/` (and the scheduler) from referencing `Item`/`TripDay`;
  building a proposal has to *read* the routed trip's items to target one, so the
  module that reads and — on approval only — writes them is a separate one, and
  step 9 asserts that it is the only inbound-originated writer.
- **One model call, not two.** Phase 2's routing response widens with the
  sparse `fields` object the spec's adapter contract names; extraction is not a
  second egress.
- **Re-targeting is a request of its own** (`POST /inbox/action-items/{id}/retarget`),
  which re-snapshots the new target's current values and bumps `revision`. The
  spec's approval body still carries `target_item_id`, and a value that differs
  from the stored target is refused as `409 action_item_conflict`. Applying a
  re-target inside the approval would write against values for which no
  snapshot exists, which is exactly the "overwritten unseen" case the re-diff is
  there to prevent.
- **A conflict refreshes the snapshot.** On `409 action_item_conflict` the
  server records the item's current values and bumps `revision` before
  answering, so the reloaded sheet shows what is true now and a second, informed
  approval can succeed.
- **Hand-placed messages get proposals by an explicit owner act**
  (`POST /inbox/messages/{id}/action-items` naming a target): zero fields, the
  message's documents. Classification (`place`) still creates nothing, as the
  spec requires.
- **Approvable fields** are `title`, `kind`, `confirmation_number`, `cost`
  (amount and currency as one fact), `start_time`, `end_time`, `end_date`, plus
  `set_status`. `start_date` is used for targeting and to choose the day of a new
  item; moving an existing item between days stays with the ordinary edit
  screen.

## Risks

- **Overwriting something the owner typed.** Mitigated by the default-tick rule
  (pure, unit-tested), the allow-list body, the snapshot re-diff and the revision
  token — four layers, each tested.
- **The approval path bypassing a shipped limit.** Re-pointing an attachment is
  an `UPDATE` that consults no limiter, so the trip quota and per-parent cap are
  re-checked explicitly and tested.
- **Model output reaching the screen as prose.** The proposal stores typed,
  validated values only; reasons stay translation keys.

## Implementation Plan

### Phase 1: Data and pure rules

- 1.1 Alembic revision `0009` creating `inbound_action_item` with its `CHECK`s and the partial pending index; the `InboundActionItem` model.
- 1.2 `domain/extraction.py` — the extraction schema, validation and coercion through `domain/money.py` and the item-span rules.
- 1.3 The proposal diff and the deterministic item-target rule in `domain/inbound.py`.

### Phase 2: The approval service and API

- 2.1 Action items created from routing (the widened model response) and by hand, via `approvals.py`.
- 2.2 `approve` — allow-list, revision, re-diff, conflict refusal, attachment re-point, quota and per-parent re-checks, `applied` recorded.
- 2.3 `reject`, `undo` and `retarget`.

### Phase 3: The sheet, end to end, and the guarantees

- 3.1 The action-item sheet and the inbox's "awaiting you" region, both locales.
- 3.2 End-to-end test of the brief's own flow with a stubbed provider.
- 3.3 The guarantee tests: only the approval service writes `item`; injection yields at most a declinable proposal; no inbox field reaches a guest-visible shape.

## Progress

PR: #22

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Data and pure rules

- [x] 1.1 Alembic revision 0009 and the InboundActionItem model — 623f5b3
- [x] 1.2 domain/extraction.py — df15dde
- [x] 1.3 Proposal diff and item-target rule — eb2b059

### Phase 2: The approval service and API

- [x] 2.1 Action items from routing and by hand — 06260a9
- [x] 2.2 Approve — 06260a9
- [x] 2.3 Reject, undo and retarget — 06260a9

### Phase 3: The sheet, end to end, and the guarantees

- [x] 3.1 The action-item sheet — 762bdb4
- [x] 3.2 End-to-end flow test — 2d424fe
- [x] 3.3 Guarantee tests — 939740e
