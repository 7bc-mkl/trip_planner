# Execution plan — Walking skeleton, Phases 2, 3 and 4

- Date: 2026-09-05 · Engine: `om-auto-create-pr` · Slug: `walking-skeleton-phase-2-4`
- Branch: `feat/walking-skeleton-phase-2-4` · Base: `main`
- Source doc: `.ai/specs/2026-09-05-walking-skeleton.md` (merged on `main` via spec PR #1)
- Builds on: PR #2, `feat/walking-skeleton-phase-0-1`, merged as `74fa180`

`Engine: om-auto-create-pr (steps: 20, --loop: no)`

## 🎯 Goal

Turn the authenticated empty shell that Phases 0 and 1 shipped into the product the
brief describes: a multi-stop trip with a generated day-by-day timeline, hand-entered
items carrying the three statuses, the readiness counter that answers "how much of
this is actually arranged", and the outstanding filter plus the trip-management tail
that make a second trip survivable.

## 📋 Scope

In scope — exactly Phase 2 steps 1-6, Phase 3 steps 1-8 and Phase 4 steps 1-6 of the
spec's Implementation Plan, no more:

- **Phase 2.** `trip`, `trip_stage`, `trip_day` tables with every `CHECK`/`UNIQUE`
  constraint including the deferrable one; `domain/days.py` and `domain/stages.py` as
  pure functions; `POST /trips`, `GET /trips`, `GET /trips/{id}`; the `/trips` list,
  the `/trips/new` multi-stop creator with its three route modes, and the
  `/trips/:id` timeline with its deliberate empty state.
- **Phase 3.** The `item` table with both check constraints and the nullable span
  columns; `domain/items.py` span validation and `domain/readiness.py`; the day-detail
  endpoint with prev/next; item `POST`/`PATCH`/`DELETE` with server-assigned
  `position`; `readiness` on both trip payloads; the `/trips/:id/days/:date` screen
  with its focus-managed item editor; status chips carrying a translated text node and
  a `data-status` attribute; items and the counter tile on the timeline and the list.
- **Phase 4 (the spec's slippable tail).** The *All* / *Only outstanding* radio group
  reflected in the URL; the per-type chips with counts; `PATCH /trips/{id}` with the
  date-range regeneration and mode-stability rules; `DELETE /trips/{id}` with its
  confirmation dialog; stage `POST`/`PATCH`/`DELETE` with dense `position`
  reassignment; the end-to-end walk of the brief's own success flow.

Two Alembic revisions, one per phase that adds tables (`0003` trips, `0004` items),
each with a working `downgrade`. Phase 4 adds no tables, exactly as the spec's
Migrations section promises.

Every new user-visible string lands in **both** `en.json` and `pl.json` in the same
commit, because `scripts/check_locales.py` runs first in the gate and an English-only
key is a red gate, not a follow-up.

## 🚫 Non-goals

Explicitly not touched, so a reviewer can tell absence from oversight:

- Anything A05 cut from this milestone: chat and the AI assistant, sharing and magic
  links, attachments and reservation documents, cost and budget data. Specs for the
  latter two are already in flight on PRs #3 and #4 and this PR must not pre-empt them.
- Filter query parameters on the API. A11 puts filtering in the browser and the
  timeline payload is complete; adding a `?status=` parameter would be a contract
  surface nothing asks for.
- Manual item reordering. `position` is server-assigned and the spec's `item` table
  says reordering is out of scope for this milestone.
- Optimistic locking on concurrent edits, and any scheduled cleanup of expired
  sessions or old login attempts. The spec's Edge Cases section names both as
  documented-but-not-built, so a reviewer finds a decision rather than a gap.
- A `backend/trip_planner/locales/` root. The `ErrorCode` enum plus the
  `test_errors.py` parity test is the whole backend-i18n mechanism this milestone
  needs, and Phase 1 already built it.
- Re-doing any Phase 0 or Phase 1 work. Those shipped in PR #2 and are on `main`.

## 📐 Approach and the decisions it forces

Four choices are worth stating before the diff, because each is the kind that is
cheap now and a migration later.

**The stage↔day relation stays derived.** `trip_day` carries no `stage_id`; the day's
stages are computed by date containment in `domain/stages.py`. The spec is explicit
about why — a stored key would need re-maintaining on every stage date edit and could
silently contradict the stage's own dates. The cost is a pure function called per day;
the benefit is that it cannot drift.

**The readiness arithmetic lives in `domain/readiness.py` and nowhere else.** Both the
list payload and the timeline payload call the same function, and the API test asserts
the served figure equals the domain function's. The field is `tracked`, never `total`.

**The route mode is derived from `return_place`, and the server defends it.** No
discriminator column: `NULL` is one-way, equal-after-folding is round trip, different
is open-jaw. The mode-stability rule — rewriting `return_place` when `departure_place`
is edited in round-trip mode — is what stops a typo correction from silently
converting the trip, and it is a Phase 4 test rather than a comment.

**Trip mutation never destroys an item.** Shortening a range past a day that carries
items is `409 days_have_items` listing the dates and changing nothing; only empty days
are removed. This is the rule that makes the date editor safe to use.

## ⚠️ Risks

| Risk | Mitigation |
|---|---|
| The deferrable `UNIQUE (trip_id, position)` is easy to write as an ordinary constraint, and the difference only shows up under a mid-transaction reorder. | Phase 4 step 5 asserts a delete-from-the-middle reorder in one statement; the migration test round-trips upgrade/downgrade. |
| 20 steps in one PR is a large diff for one review pass. | One commit per step with a conventional subject, so the PR reads as a sequence rather than a dump; the Progress section carries each SHA. |
| Phase 4 is the slippable tail. Running short and half-landing it would leave a filter that filters nothing or a `PATCH` without its 409s. | Phase 4 is committed step-by-step and each step is independently complete; if the run cannot finish it, the remaining steps are filed as follow-up issues and the PR ships Phases 2-3, per the run brief. |
| The item time span (`end_date`, `end_time`) is validated in `domain/` rather than by a `CHECK`, because the trip's own `end_date` is on another table. | `domain/items.py` is the single validation path for both `POST` and `PATCH`, unit-tested directly, and the API tests assert `422 invalid_time_span` through the endpoints. |
| New error codes must reach both locale files or the gate fails on a condition nothing can produce yet. | Each code is added in the same commit as the endpoint that raises it, and `tests/test_errors.py` already asserts every enum member resolves in both locales. |

## 📋 Implementation Plan

### Phase 2 — Trip creation and the empty timeline (R03, D06)

1. Migration `0003` and models for `trip`, `trip_stage`, `trip_day`, with every
   `CHECK` and `UNIQUE` constraint including the deferrable `(trip_id, position)`.
   Verify: the database itself rejects an inverted date range and a duplicate
   `(trip_id, date)`; upgrade/downgrade round-trips.
2. `domain/days.py`: `generate_days(start, end)`, inclusive, bounded at 366.
   Verify: a one-day trip, a leap-day span, and the bound raising `trip_too_long`.
3. `domain/stages.py`: `stages_for_day(stages, date)` ordered by `position`, and the
   `→`-joined label truncated after two with `+n`. Verify: a travel day shared by two
   stages, three stages sharing a date, a stage with no dates, a day in no stage.
4. `POST /trips` creating trip, stages and days in one transaction; `GET /trips`;
   `GET /trips/{id}` with derived `stage_ids` and an always-empty `items` array.
   Verify: the three route modes, `stages_required`, `stage_outside_trip`, stages
   without dates, and another owner's trip answering `404`.
5. The `/trips` list screen and the `/trips/new` creator with the route-mode toggle
   and inline validation. Verify: each route mode produces the right request body, and
   the primary action stays disabled until the form is valid.
6. The `/trips/:id` timeline rendering days with their stage labels and a deliberate
   empty state. Verify: a trip with no items renders every day and the empty-state
   copy in both locales.

### Phase 3 — Items, statuses and the readiness counter (D05, R02, P1)

1. Migration `0004` and model for `item` with both `CHECK` constraints and the
   nullable span columns. Verify: the database rejects a fourth status value.
2. `domain/items.py` span validation and `domain/readiness.py`
   `readiness(items) -> (arranged, tracked)`. Verify: all-`to_plan` returning `(0, 0)`,
   the mixed case, the empty case, and a spanning item counted once.
3. `GET /trips/{id}/days/{date}` with prev/next dates. Verify: the first and last day
   of a trip, and a date outside the trip answering `404`.
4. Item `POST`, `PATCH` (including `date` to move between days) and `DELETE`, with
   server-assigned `position` and the ordering rule. Verify: the default status,
   untimed items sorting last, `invalid_time_span`, and `422 date_outside_trip`.
5. `readiness` on the `GET /trips` and `GET /trips/{id}` payloads as
   `{arranged, tracked}`. Verify: the served figure matches the domain function.
6. The `/trips/:id/days/:date` screen: ordered item list, day navigation, and the item
   editor dialog. Verify: creating, editing and deleting an item, and focus returning
   to the trigger when the dialog closes.
7. Status chips rendering a translated text node and a `data-status` attribute.
   Verify: the three translated labels exist in both locale files and no status is
   conveyed by a CSS class alone.
8. Items on the timeline's day cards, spanning items marked "→ dd.MM", and the counter
   tile with its `tracked = 0` copy on both the timeline and the trip list. Verify: the
   fraction, the zero state in both locales, and an item created in the day detail
   appearing on the timeline.

### Phase 4 — The filter and the trip-management tail (the slippable phase)

1. The filter bar as a radio group — *All* / *Only outstanding* — filtering
   client-side and reflected in the URL. Verify: switching the filter changes the item
   list and leaves the counter untouched.
2. The per-type chips with their counts. Verify: the counts sum to the item total.
3. `PATCH /trips/{id}` with the date-range regeneration rules and the round-trip
   mode-stability rule. Verify: extending adds days; shortening past a day with items
   answers `409 days_have_items` and changes nothing; shortening past a stage answers
   `409 stages_outside_new_range`; shortening past an empty day removes it; editing
   `departure_place` in round-trip mode rewrites `return_place`.
4. `DELETE /trips/{id}` and its confirmation dialog. Verify: the cascade removes
   stages, days and items, and none of another trip's.
5. Stage `POST`/`PATCH`/`DELETE` with dense `position` reassignment in a single
   statement. Verify: positions stay dense after a delete from the middle and the
   deferred constraint is not violated mid-transaction.
6. End-to-end verification of the brief's own success flow: log in, create a
   three-stage open-jaw trip, add items across several days including one overnight
   flight, set statuses, read the counter, filter to what is outstanding. Verify: an
   integration test walking that path, with screenshots on this PR.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 2: Trip creation and the empty timeline

- [x] 2.1 Migration and models for trip, trip_stage, trip_day — 7646c9a
- [x] 2.2 domain/days.py — generate_days, inclusive, bounded at 366 — e26cd4b
- [x] 2.3 domain/stages.py — stages_for_day and the truncated label — f1a1858
- [x] 2.4 POST /trips, GET /trips, GET /trips/{id} — dfde501
- [x] 2.5 The /trips list and the /trips/new multi-stop creator — 8e40817
- [x] 2.6 The /trips/:id timeline with its empty state — 8e40817 (landed with 2.5: the timeline shares AppShell and format.ts with the list, and splitting the commit would have left one of them not building)

### Phase 3: Items, statuses and the readiness counter

- [x] 3.1 Migration and model for item — d64353c
- [x] 3.2 domain/items.py span validation and domain/readiness.py — bf31897
- [x] 3.3 GET /trips/{id}/days/{date} with prev/next — 2186fb2
- [x] 3.4 Item POST, PATCH and DELETE — 2186fb2
- [x] 3.5 readiness on the trip list and timeline payloads — 2186fb2
- [x] 3.6 The /trips/:id/days/:date screen and the item editor dialog — 4a92d29
- [x] 3.7 Status chips with a translated text node and data-status — 4a92d29
- [x] 3.8 Items and the counter tile on the timeline and the trip list — 4a92d29

### Phase 4: The filter and the trip-management tail

- [x] 4.1 The All / Only outstanding filter, reflected in the URL — 9f1023d
- [x] 4.2 The per-type chips with counts — 9f1023d
- [x] 4.3 PATCH /trips/{id} with range regeneration and mode stability — 449b605
- [x] 4.4 DELETE /trips/{id} and its confirmation dialog — 449b605 (endpoint), e1bc24f (dialog)
- [x] 4.5 Stage POST/PATCH/DELETE with dense position reassignment — 449b605
- [x] 4.6 End-to-end walk of the brief's success flow, with screenshots — 03d9b9f
