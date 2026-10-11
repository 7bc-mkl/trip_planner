# Execution plan — the reservation inbox, Phase 2 (routing)

- Date: 2026-10-10 · Branch: `feat/reservation-inbox-routing` · Stacked on `feat/reservation-inbox` (PR #19)
- Source doc: `.ai/specs/2026-09-26-reservation-inbox.md`
- Base: `main`, once #19 merges. Until then this branch sits on top of it.

## Goal

**Routing (D20): a forwarded confirmation arrives already pointed at the trip it
belongs to.** Deterministic candidate selection in SQL narrows the owner's trips
to those whose range covers a travel date the message carries; a model then
chooses among *those candidates only*, or confirms the single one. Zero
candidates never reaches a model at all.

## Why this is unblocked now

The spec gated Phase 2 behind the **A07/A08 paper check**, which ran on
2026-10-10 against four real forwarded confirmations and is recorded in the
spec. It did what a gate is for: it **amended the rule** before any code was
written. Step 2.1 below implements the amended rule, not the original one.

## What needs no decision, and what does

**Needs nothing:** all five steps. D24 fixes the shape — one explicitly selected
provider out of Anthropic, Gemini and OpenAI — and the spec requires **all
three** adapters to be built behind one contract. Which one a deployment uses is
configuration (`INBOX_MODEL_PROVIDER`), not a thing this code decides. The suite
makes **no real network call**, so no credential is needed to build or test any
of it.

**Needs the owner, before it runs rather than before it is written:**
selecting a provider, reviewing that provider's data-retention terms (D24 leaves
this explicitly to the operator), and supplying the key. With none of that set,
the deployment stays in Phase 1 behaviour: stored and queued, no model egress.

## Scope

The spec's Phase 2, all five steps. **Out:** Phase 3 (action items, the approval
sheet) and Phase 4 (document egress, polish) — later phases, unchanged by this.

## Risks

- **This is the first code that sends the owner's mail off-box.** Everything in
  Phase 1 was local. The egress record is committed *before* the call, so a
  timeout or a crash cannot erase the fact that data may have left.
- **The payload is the thing to get wrong.** Tests assert against a *captured
  request body* that it carries only the message text, three headers, and the
  candidate trips' id/title/destinations/dates — and **no attachment byte**.
- **A model-chosen trip outside the candidate set must be inexpressible.**
  Rejected before a proposal exists, so "route this to the trip you are not
  allowed to see" cannot be written down.
- **Three adapters, one contract.** The risk is a provider's wire format leaking
  into domain code. Parametrized contract tests run the same cases against all
  three.

## Implementation Plan

### Phase 1: The deterministic half

2.1 (spec Phase 2 step 1) Travel-date extraction and candidate selection in
`domain/inbound.py` — the ±1-day range rule and the candidate query, **with the
three exclusions the paper check produced**: strip the forwarded-header block;
ignore dates earlier than the message's own `Date`; ignore deadline-adjacent
dates. Verify: zero/one/several candidates; Polish month names, full and
abbreviated English — **no ISO case, because none of four real confirmations
carried one**; no date at all; a boundary exactly one day out; and one case per
exclusion built from a structure actually observed.

### Phase 2: The model boundary

2.2 (spec step 2) `integrations/model.py` — provider-neutral request/response
contract and factory; `integrations/{anthropic,gemini,openai}.py`. The
`inbound_model_egress` migration. Shared prompt, rejecting Pydantic schema,
payload limits, timeout, bounded retry, budget. Verify: parametrized contract
tests across all three for valid output, malformed JSON, unknown fields,
timeout, 429 and budget exhaustion; selection tests for each provider and for
missing/unknown/mismatched credentials; only the selected adapter is called.
**No real network call.**

2.3 (spec step 3) Wiring routing into the ingestion worker — `received` →
`routed`/`unrouted`, `attempts`, `routing_reason` as translated keys with
arguments, `text_sent_at`, and a committed egress row before each call. Verify:
a trip outside the candidate set is rejected; the cap queues the message with a
reason; the captured payload carries only what it should and **no attachment
byte**.

### Phase 3: Surfacing it

2.4 (spec step 4) The routed state in the UI — the trip a message was placed on,
the reason, and re-placement. Verify: component tests for routed, for each
unrouted reason, both locales.

2.5 (spec step 5) README and `AGENTS.md`'s external-APIs row for the model
integration actually built: selector, model name, the three credential names,
failure mode and budget. Verify: each documented variable name matches
`config.py`.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: The deterministic half

- [x] 2.1 Travel-date extraction and candidate selection, with the three exclusions — 23558bc

### Phase 2: The model boundary

- [x] 2.2 `integrations/model.py`, the three adapters, and the egress migration — c7441d0
- [ ] 2.3 Routing wired into the ingestion worker

### Phase 3: Surfacing it

- [ ] 2.4 The routed state in the UI
- [ ] 2.5 README and AGENTS.md for the model integration
