# Execution plan — trip and stage editing

Source doc: `.ai/specs/2026-09-25-trip-and-stage-editing.md` (on spec PR #14 —
design-only; this branch does not carry it)
Engine: om-auto-create-pr (steps: 13, --loop: no)
Closes #8 · Refs #14

## Goal

Give the owner a way to correct a trip after creating it — its name, dates,
route and bases — so that fixing a wrong date no longer means deleting the trip
and losing every item and attachment on it.

## Scope

Client-only. The four endpoints this reaches (`PATCH /trips/{id}` and the three
stage routes) shipped with #6 and are unchanged here.

- New: `/trips/:id/edit` (`TripEditPage`), `api/stages.ts`, `errorDetail.ts`.
- Changed: `TimelinePage` gains an "Edit trip" action; `App.tsx` gains a route;
  `en.json` / `pl.json` gain four detail messages.

**Non-goals** (from the spec's resolved assumptions): stage reordering; editing
from the `/trips` list; a draft-survives-401 store for this form; any backend
change, migration, endpoint or response-shape change.

## Risks

- The refusal copy is the part that is not mechanical: a message naming the
  wrong dates is worse than the generic one it replaces. Mitigated by a test per
  code against a fixture `error.field`, in both locales, and by keeping the
  existing generic keys as the fallback.
- Two save behaviors on one screen (trip fields batched, stages immediate) make
  in-flight state the likely bug. Both directions of the mutual lock are
  specified and tested.

## Implementation Plan

### Phase 1 — Edit the trip's own fields

1.1 `errorDetail.ts` — the `field`-aware message builder for the four range
refusals, with locale-formatted dates and the generic-key fallback.
1.2 The eight locale keys (four codes × en/pl).
1.3 `TripEditPage` — load, prefill, inline validation, live dock summary;
stages read-only at this step.
1.4 The `/trips/:id/edit` route in `App.tsx`.
1.5 The "Edit trip" action on `TimelinePage`.
1.6 Wire Save to `updateTrip` — all five trip fields, explicit `return_place`,
navigate on success.
1.7 Render the refusals: alert above Save, focus moved to it, anchored by code,
typed values preserved.
1.8 The ticket's headline scenario as an automated test, plus the full gate.

### Phase 2 — Manage the trip's stages

2.1 `api/stages.ts` — `createStage` / `updateStage` / `deleteStage`.
2.2 Editable stage cards with per-card Save and the trip refetch, plus both
directions of the in-flight lock.
2.3 "Add destination" through `createStage`.
2.4 Remove behind `ConfirmDialog`, disabled at one stage.
2.5 The stage walkthrough as an automated test, plus the full gate.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Edit the trip's own fields

- [ ] 1.1 errorDetail.ts — field-aware refusal messages
- [ ] 1.2 Locale keys for the four detail messages
- [ ] 1.3 TripEditPage — load, prefill, validate, dock summary
- [ ] 1.4 The /trips/:id/edit route
- [ ] 1.5 The "Edit trip" action on TimelinePage
- [ ] 1.6 Save wired to updateTrip
- [ ] 1.7 Refusals rendered and anchored
- [ ] 1.8 Headline scenario test and the full gate

### Phase 2: Manage the trip's stages

- [ ] 2.1 api/stages.ts
- [ ] 2.2 Editable stage cards with per-card save and the in-flight lock
- [ ] 2.3 Add destination
- [ ] 2.4 Remove destination behind a confirmation
- [ ] 2.5 Stage walkthrough test and the full gate
