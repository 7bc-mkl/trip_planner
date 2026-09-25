# Trip and stage editing — the screen that reaches the endpoints already built

## 📝 TLDR

The owner cannot change a trip after creating it. A wrong date, a renamed trip,
a base added late: all of them today mean deleting the trip and re-creating it,
which destroys every item, every attachment and every reservation on it. The
server has been able to do this correctly since the walking skeleton — `PATCH
/trips/{id}` and the three stage endpoints exist, are careful about data loss,
and are covered by 41 tests — but nothing in the SPA calls them. This spec
proposes `/trips/:id/edit`: one screen, reusing the creator's form, that edits
the trip's own fields and manages its stages, and that turns the server's four
refusals into copy naming the exact days and places the owner has to fix.

Proposed behavior throughout; nothing below is built yet.

## 📝 Problem Statement

`frontend/src/api/trips.ts:86` defines `updateTrip`. Nothing calls it. There is
no client function at all for `POST /trips/{id}/stages`, `PATCH
/trips/{id}/stages/{stageId}` or `DELETE /trips/{id}/stages/{stageId}`. The four
screens the walking skeleton shipped — `/trips`, `/trips/new`, `/trips/:id`,
`/trips/:id/days/:date` — create a trip and fill it in, and offer exactly one
destructive way out: `trip.delete`.

That is not an oversight in the walking skeleton — its UI/UX section described
those four screens and no more (issue #8 makes the same point). It is a gap
between what the server guarantees and what the owner can reach:

- **The consequence is data loss by the only available route.** `PATCH` was
  written so that shortening a trip past a day carrying items answers `409
  days_have_items` and changes nothing (`backend/trip_planner/api/trips.py:289`).
  With no UI, the owner's only way to change a date is `DELETE /trips/{id}`,
  whose cascade drops every stage, day, item and attachment — precisely what the
  refusal exists to prevent.
- **The refusals are already designed to be shown.** All four 409s name what is
  wrong in `error.field`: `days_have_items` and `days_have_attachments` carry a
  comma-separated list of ISO dates, `items_outside_new_range` the start days of
  the offending items, `stages_outside_new_range` the offending places. Today
  nothing reads that field for these codes.
- **The product brief's *Now* list is "one traveller takes one real multi-stop
  trip from empty to fully planned".** A plan that cannot be corrected is not a
  plan that survives contact with a real trip; the Malaysia trip the brief is
  written around will change its dates at least once.

Evidence is the code and the ticket, not user research: there is one user, and
he filed this. No usage data exists for this product.

## 📝 Proposed Solution

A new authenticated route, **`/trips/:id/edit`**, reached from an "Edit trip"
action next to "Delete trip" in the timeline header. It is a form screen built
from the same pieces as `/trips/new` — `AppShell`, the `field-card` groups, the
route-mode radio group, the `stage-card` list — not a modal: the creator's form
is the full set of controls this screen needs, and a dialog holding all of it
would be a screen wearing an overlay.

Two save behaviors on one screen, because that is what the API is:

- **The trip's own fields** (title, dates, departing/returning place, route
  mode) are one `PATCH /trips/{id}` behind one **Save** button. The endpoint is
  transactional and runs all four refusals before mutating anything, so one
  request is one atomic decision.
- **Stages apply immediately**, one request per stage: adding appends through
  `POST`, editing a stage's place or dates commits through `PATCH` when the card
  is saved, removing calls `DELETE`. There is no bulk stage endpoint, and
  batching N stage calls behind one Save button would be a multi-request "save"
  with no rollback — a failure halfway would leave the trip in a state neither
  the owner nor the screen asked for. Immediate apply is the honest reading of
  the contract; each card reports its own outcome.

**Alternatives considered.**

*A modal on the timeline.* Rejected: it would hold the whole creator form, and
the 409 copy needs room to list several dates against the field that caused
them. It also gives the edit no URL, so a failed save cannot be returned to.

*Inline editing on the timeline itself* (click the title to rename, click the
date chip to shift). Rejected for this iteration: it multiplies the number of
places a `PATCH` can fire from, and the date field is exactly the one whose
failure needs the most explanation.

*One Save for everything, sequencing trip then stages.* Rejected as above — it
promises atomicity the API cannot deliver.

## 📝 Architecture

Client-only. **No backend file changes, no migration, no new endpoint, no change
to any response shape.** Every contract this spec consumes shipped with #6 and
is covered by `backend/tests/test_trip_management_api.py`. That is the whole
point of the ticket: the server side is done.

The only new reach is one route and one API module; `TimelinePage` gains a link
and nothing else, and `TripCreatePage` is not touched.

New modules:

- `frontend/src/features/trips/TripEditPage.tsx` — the screen.
- `frontend/src/api/stages.ts` — `createStage`, `updateStage`, `deleteStage`,
  typed against the existing `Stage` / `StageInput` in `api/trips.ts`. A new
  module rather than more functions in `trips.ts`, matching the backend's own
  split into `api/trips.py` and `api/stages.py`.
- `frontend/src/features/trips/errorDetail.ts` — turns an `ApiError`'s `field`
  into a localized sentence for the four range refusals (below).
- `routeMode.ts` is reused as-is: `routeModeOf(trip)` already derives the mode
  a loaded trip is in, and `returnPlaceFor(mode, …)` already produces the
  `return_place` a mode implies. This screen is the second consumer that
  function's doc comment anticipated.

**The mode-stability interaction.** The server rewrites `return_place` to follow
`departure_place` when a round trip's departure changes without an explicit
`return_place` (`api/trips.py:275`). This screen always sends `return_place`
explicitly, derived from the radio group by `returnPlaceFor` — so the rule never
fires for this caller and the mode the owner sees selected is the mode that is
saved. The rule stays where it is for any other client; this is a deliberate
"explicit wins", which is what the server's own comment says it is.

## 📝 API Contracts

No change, and no migration: `position` stays server-owned — stages append at
the end and renumber densely on delete, and this screen exposes no reordering
(Resolved assumptions, Q3). The endpoints are consumed as-is:

| Call | Used for | Failure codes this screen must render |
|---|---|---|
| `PATCH /trips/{id}` | Save the trip's own fields | `invalid_date_range`, `trip_too_long`, `days_have_items`, `days_have_attachments`, `stages_outside_new_range`, `items_outside_new_range`, `validation_error` |
| `POST /trips/{id}/stages` | Add a base | `stage_outside_trip`, `invalid_date_range`, `validation_error` |
| `PATCH /trips/{id}/stages/{stageId}` | Edit a base | `stage_outside_trip`, `invalid_date_range`, `not_found` |
| `DELETE /trips/{id}/stages/{stageId}` | Remove a base | `stages_required` (the last stage), `not_found` |

`TripUpdate` and `StageUpdate` both read `model_fields_set`, so **omitting** a
key and sending `null` are different requests. The two endpoints therefore get
**different, deliberate** request-shape rules:

- **`PATCH /trips/{id}` always sends all five trip fields.** The screen holds
  every one of them in a form, so there is nothing it does not know; and sending
  `return_place` explicitly on every save is what keeps the server's
  mode-stability rewrite from firing (above) — the mode the owner sees selected
  is the mode that is saved, including `null` for one-way. A partial body would
  make that guarantee depend on which fields happened to be dirty.
- **The stage `PATCH` sends only the keys that changed.** A stage's dates are
  genuinely tri-state — a date, `null` for "undecided" (R03), or untouched — and
  only omission expresses the third. An empty date input becomes `null`, never
  `""`.

Both models are `extra="forbid"`: the client sends no field the model does not
declare — in particular `stages` is not part of `TripUpdate`.

## 📝 UI/UX

### The entry point

`TimelinePage`'s `actions` slot gains a `button-quiet` "Edit trip" before the
existing `button-danger` "Delete trip" — a `Link` styled as a button, so it is
navigable and middle-clickable. No new token, no new glyph (the sprite shipped
by the design-system run carries the five item kinds and two chevrons; none of
them is a pencil, and none is invented here).

### `/trips/:id/edit`

Same shell as the creator, with the trip's current values loaded in. Three
groups, in the creator's order so the two screens read the same way:

1. **The trip** — name, start date, end date.
2. **Route** — the three-mode radio group, departing place, and the returning
   place shown only in open-jaw mode.
3. **Destinations** — the stage list.

The main column ends with **Save** (`button-primary--deep`, the creator's
recipe) and a quiet **Cancel** returning to `/trips/:id`. The dock carries the
same live "days / nights / bases" summary the creator shows, so the consequence
of a date edit is visible before it is saved.

### States

| State | What the owner sees |
|---|---|
| Loaded, untouched | Save disabled — nothing has changed. |
| Locally invalid | The creator's inline complaints, same keys: end before start, a stage outside the trip range. Save disabled. |
| A request in flight | **Nothing else may be submitted.** While the trip save runs, the stage list is disabled; while any stage request *or the refetch that follows it* is outstanding, trip Save is disabled. Both directions matter: a trip `PATCH` fired against state an in-flight refetch is about to replace would save one view of the trip and then navigate away from another. |
| Refused (409) | A `role="alert"` message **above Save**, naming the days or places (below), and anchored to the field that caused it: the date group for the three date refusals, the stage list for `stages_outside_new_range`. Nothing on the screen is reset — the owner's typed values stay so the edit can be corrected rather than retyped. |
| Saved | Navigate to `/trips/:id`, which refetches; the timeline is the confirmation. |

### Surfacing the four refusals — the interesting part

This is what the ticket calls out, and it is the reason the screen earns its
own spec. Today `error.days_have_items` reads *"Those days already have items on
them"* — true, and useless: the owner cannot tell which. The server already
names them. So each of the four codes gains a **detail** key taking the list:

| Code | `error.field` carries | New key | English value |
|---|---|---|---|
| `days_have_items` | ISO dates | `error.days_have_items_detail` | These days already have items on them: {dates}. Move or delete those items first, then shorten the trip. |
| `days_have_attachments` | ISO dates | `error.days_have_attachments_detail` | These days already have attachments on them: {dates}. Move or remove those files first, then shorten the trip. |
| `items_outside_new_range` | ISO start dates | `error.items_outside_new_range_detail` | Items starting on {dates} run past the new end date. Shorten or delete them first, then shorten the trip. |
| `stages_outside_new_range` | place names | `error.stages_outside_new_range_detail` | These destinations fall outside the new dates: {places}. Adjust them first, then shorten the trip. |

`errorDetail.ts` splits `field` on `,`, trims, and — for the three date codes —
formats each date **through the locale** (`Intl`, the same path `format.ts`
already uses), never by string concatenation, then joins with the locale's list
separator. The existing generic keys stay: they are the fallback when `field` is
null or unparseable, and other callers still use them. A place name is rendered
verbatim as owner-entered text; it is interpolated as an ICU argument, so React
escapes it and a place called `<b>` is not markup.

Polish values land in the same commit — `check_locales.py` is the first command
of the validation gate and fails on an English key without its Polish
counterpart.

### Stages on this screen

Each stage renders as the creator's `stage-card`, with its own place and two
optional dates, plus:

- **Save** on the card, enabled once that card differs from the server's copy;
  it fires the stage `PATCH` and reports success or failure on the card itself,
  through the card's own `role="alert"`.
- **Remove**, disabled when the trip has exactly one stage — the same disabled
  affordance the creator uses for the same rule (R03), so the `stages_required`
  refusal is explained rather than triggered. Removing asks for confirmation
  through the existing `ConfirmDialog`, naming the place: a stage is a decision,
  and there is no undo.
- **Add destination** appends a blank card; it is saved by its own Save, which
  issues `POST`. An unsaved blank card is local only and leaving the screen
  discards it.

After any successful stage mutation the screen **refetches the trip**: stage
positions renumber densely on delete, and day→stage derivation changes with
every stage date, so keeping a local copy in step would be re-implementing
`stages_for_day` in the browser.

### Accessibility

Every control is labelled; the ordinal badge stays `aria-hidden` as in the
creator (the place field's own label already reads "Destination 1"). Refusal
messages are `role="alert"` and focus moves to the summary when a save is
refused, so a keyboard user is not left at the bottom of a form that silently
did nothing. The delete confirmation reuses `ConfirmDialog`, which already
traps focus and restores it.

No new CSS token and no new color pair: every class this screen uses exists for
the creator and the timeline, so `check_css_tokens.py` and `check_contrast.py`
have nothing new to judge.

## 📝 Edge Cases & Failure Scenarios

- **Shortening past days that hold items *and* attachments.** The server answers
  `days_have_items` first, by design (`api/trips.py:260`). The screen shows that
  one; once the items are moved, a retry may answer `days_have_attachments`.
  Two rounds is correct, not a bug — the alternative is one message the owner
  cannot act on in one pass anyway.
- **An item that survives but spans past the new end.** `items_outside_new_range`
  names the item's *start* day, which is where the owner has to go. The copy
  says "starting on", so the date is not mistaken for the offending end date.
- **Removing the last stage.** Prevented by a disabled button; if it were
  reached (two tabs, one removing), the `stages_required` refusal renders on the
  card and the refetch restores the truth.
- **Two tabs editing one trip.** Last write wins — there is no optimistic
  concurrency on `PATCH` and this spec does not add one (single-owner product,
  brief D08/A06: nobody else can edit). A stale tab's stage `PATCH` against a
  deleted stage answers `404 not_found`, which the card renders and the refetch
  resolves.
- **Widening the range.** Always allowed; new empty days appear. The screen says
  nothing special — the timeline showing them is the feedback.
- **`trip_too_long`** (over 366 days) and **`invalid_date_range`** are caught
  client-side before the request, exactly as the creator catches them, and again
  server-side for any other caller.
- **A dead backend (503).** The load shows the existing service-unavailable copy
  rather than an empty form, for the same reason `TimelinePage` does: an empty
  form would be a lie about the trip.
- **Navigating away with unsaved trip fields.** They are discarded. No draft
  store, no "are you sure" (Resolved assumptions, Q5).

## 📝 Risks & Impact Review

- **No contract surface changes.** No endpoint, no schema, no error code, no
  response field. `BACKWARD_COMPATIBILITY.md` §1's table has no applicable row —
  the only additions are four locale keys, which §4 treats as additive.
- **Reversibility.** The whole change is one route, one page component, one API
  module, four locale keys and one button in `TimelinePage`. Reverting is
  deleting them; no data written by this feature has a shape that outlives it.
- **The real risk is the refusal copy being wrong**, because it is the part that
  is not mechanical: a message naming the wrong dates is worse than the generic
  one it replaces. Mitigated by testing each of the four codes against a fixture
  `field` value in both locales, and by keeping the generic key as the fallback.
- **Product direction, not a defect:** this adds a screen the walking-skeleton
  spec did not describe, five days before assumption A05's date. It is built
  because the owner asked for issue #8 directly; see *Decisions in play*.

## 📝 Decisions in play

From `.ai/specs/product-brief.md`:

- **Scope / *Now*** — the *Now* list does not name "edit a trip after creation";
  it names creating one and filling it in. This spec adds a capability beyond
  that list. N01 records that the brief has no exclusions and that the *Now*
  list is the only boundary, so extending it is a scope decision, not a rule
  violation. It is taken here on the owner's direct instruction to fix issue #8.
  **Proposed:** the brief's Scope gains a line for correcting a trip after
  creation. Owner: Michal Klosinski. Non-blocking — the work does not depend on
  the brief being edited first.
- **A05** (the *Now* scope is buildable by 2026-09-30) — this spends days that
  were not budgeted in it. Worth the owner knowing; it is his call, and he made
  it by filing and assigning the ticket.
- **R03** (a trip has one or more bases) — honored, not changed: the last stage
  cannot be removed, enforced in the UI by a disabled control and by the server
  regardless.
- **D06** (multi-stop from the first migration) — this is the screen that makes
  multi-stop editable, which D06's data model has allowed since day one.

## Resolved assumptions (autonomous defaults)

Written by `om-spec-writing --autonomous`. Each is the most reversible option;
correct any of them before merge.

| # | Question | Applied default | Why | Confirm? |
|---|---|---|---|---|
| Q1 | Modal on `/trips/:id`, or its own route? | Its own route, `/trips/:id/edit` | The controls are the whole creator form; a modal holding it is a screen in an overlay, and gives a refused save no URL to return to | reversible |
| Q2 | Do stage changes batch behind the trip's Save, or apply immediately? | Immediately, one request per stage; trip fields stay behind one Save | There is no bulk stage endpoint — batching would be a multi-request save with no rollback, promising atomicity the API cannot give | reversible |
| Q3 | Does this screen let stages be reordered? | No — deferred | `position` is server-owned with no reorder endpoint; adding one is a new contract surface for a capability nobody has asked for | reversible |
| Q4 | Can a trip be edited from the `/trips` list too? | No — only from `/trips/:id` | One entry point is the smallest thing that closes the gap; a second is cheap to add later | reversible |
| Q5 | Does the edit form get the draft-survives-401 store `ItemDialog` uses? | No | That store exists because a dialog unmounts mid-keystroke on a session expiry; a full-page form that 401s sends the owner to `/login` and back to a trip whose values are all still on the server | reversible |
| Q6 | Split trip-field editing and stage editing into two specs? | No — one spec, two phases, which may ship as two PRs | They are not peers: Phase 2 has no screen, no form state and no error-rendering module without Phase 1, so a second spec would say only "add cards to the page the first spec built" | reversible |

## 📋 Phasing

- **Phase 1 — Edit the trip's own fields.** The route, the screen, the entry
  point, `updateTrip` finally called, and the four refusals rendered with their
  dates and places. Shippable alone: it closes the data-loss path the ticket
  names, since the dates are what the owner gets wrong.
- **Phase 2 — Manage the trip's stages.** The stage API module and add / edit /
  remove on the same screen. Shippable alone on top of Phase 1.

## 📋 Implementation Plan

Every step is testable and leaves the application working. The full eight-command
validation gate — `check_locales.py`, `check_css_tokens.py`, `check_contrast.py`,
`ruff`, `pytest`, `typecheck`, `vitest`, `build` — runs at each phase boundary.

### Phase 1 — Edit the trip's own fields

1. `features/trips/errorDetail.ts`: `detailedErrorMessage(error, t, language)`
   returning the detail sentence for `days_have_items`,
   `days_have_attachments`, `items_outside_new_range` and
   `stages_outside_new_range` when `error.field` parses, and the existing
   generic key otherwise. Dates are formatted through `Intl` for the active
   locale; places pass through as text. Verify: unit tests for each of the four
   codes with a multi-value `field`, for a `null` field, for an unparseable
   field, for a place name containing a comma, and one asserting the dates
   render differently under `pl` and `en`.
2. The eight new locale keys (four codes × `en` + `pl`) in
   `src/locales/en.json` and `pl.json`, as ICU messages taking `{dates}` /
   `{places}`. Verify: `check_locales.py` green; a test that every key
   `errorDetail.ts` can produce resolves to a non-empty string in both locales.
3. `features/trips/TripEditPage.tsx` — load by `tripId`, render the trip group
   and the route group prefilled from the loaded trip (`routeModeOf` for the
   radio), with the creator's inline validation and the live dock summary.
   Stages render **read-only** at this step, so the screen is honest about what
   it can do. Verify: component tests that the form prefills each field from a
   fixture trip, that all three route modes prefill correctly (including a
   one-way trip's absent return place), that the loading and 503 states render,
   and that Save is disabled until something changes.
4. Register `/trips/:id/edit` inside the authenticated section of `App.tsx`,
   before the catch-all. Verify: a routing test that an authenticated render of
   the path shows the edit screen and an unauthenticated one redirects to
   `/login`.
5. The "Edit trip" action in `TimelinePage`'s `actions` slot. Verify: a
   component test that it links to `/trips/:id/edit` and that the delete flow is
   unchanged.
6. Wire Save to `updateTrip`, sending only the trip's own keys — `return_place`
   always explicit, from `returnPlaceFor` — and navigating to `/trips/:id` on
   success. Verify: tests that the request body carries exactly the five trip
   fields and no `stages` key; that a round trip whose departure place is edited
   sends the matching `return_place`; that switching to one-way sends `null`;
   and that a success navigates.
7. Render the refusals: the `role="alert"` summary above Save, fed by
   `detailedErrorMessage`, focus moved to it, anchored to the date group or the
   stage list by code, with the typed values preserved. Verify: a test per
   refusal code asserting the named dates/places appear in the message, that
   focus lands on the alert, and that the form's values survive the refusal.
8. **The ticket's headline scenario, as an automated test**, not only as
   evidence: create a trip, put an item on its last day, move the end date
   earlier, assert the refusal names *that* day, move the item, retry, assert
   the save succeeds and the timeline shows the shorter range. Written at the
   integration level the repo already uses for cross-screen flows. Verify: that
   test, plus the full eight-command validation gate, plus screenshots of the
   refusal in both locales attached to the PR as evidence.

### Phase 2 — Manage the trip's stages

9. `api/stages.ts`: `createStage`, `updateStage`, `deleteStage` over the
   existing `request` helper, typed against `Stage` / `StageInput`, sending
   `null` rather than `""` for a cleared date and omitting keys that did not
   change. Verify: tests asserting method, path and body for each, including
   that a cleared date sends `null` and an untouched one is absent.
10. Editable stage cards on `TripEditPage`, each with its own dirty state and
    Save calling `updateStage`, followed by a trip refetch. Verify: tests that
    editing a place and saving issues the `PATCH` and refetches; that a
    `stage_outside_trip` refusal renders on that card and leaves the other cards
    alone; that a card is disabled while the trip-level save is in flight; and
    the mirror of that — trip Save is disabled while a stage request or its
    following refetch is outstanding.
11. "Add destination" appending a blank card saved through `createStage`, and
    the discard-on-leave behavior of an unsaved one. Verify: tests that the
    `POST` body carries the place and the two dates, that the new stage appears
    after the refetch, and that an unsaved blank card sends nothing.
12. Remove, behind `ConfirmDialog` naming the place, calling `deleteStage`, with
    the button disabled at one stage. Verify: tests that the dialog names the
    place, that confirming issues the `DELETE` and refetches, that cancelling
    sends nothing, that the button is disabled on a single-stage trip, and that
    a `stages_required` refusal renders on the card.
13. Phase gate: an automated walkthrough adding a base to an existing trip,
    editing its dates and removing it — asserting the dock's destination list on
    `/trips/:id` reflects each change — plus the full validation gate, with
    screenshots in both locales attached to the PR as evidence.
