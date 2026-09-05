# Walking skeleton — trip, timeline, statuses, counter, login

- Date: 2026-09-05 · Author: `om-auto-write-spec` (autonomous) · Status: draft, gated on the assumptions below
- Source brief: `.ai/specs/product-brief.md` (signed 2026-09-05)
- Visual reference: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/` — a preliminary mockup, adapted here, not a contract
- Mode: `om-spec-writing --autonomous`. Every question this spec answered on its own is listed under **Resolved assumptions (autonomous defaults)** and is open to override before merge.

## 📝 TLDR

Build the first working slice of Smart Trip Planner: an owner logs in with e-mail and password, creates a multi-stop trip from a date range, a departure point, an optional return point and one or more stages, gets an empty timeline of days generated from those dates, fills the days with items that each carry a type, a time, free text and one of exactly three statuses, and reads at a glance how much of the trip is arranged. It is the walking skeleton A05 names as the test of whether the *Now* scope is buildable — a thin vertical cut through authentication, the data model, the API and the UI, deployable to the public internet, with nothing in it that is not load-bearing.

The two decisions that carry the whole spec are the multi-stop shape and the status field, because both would be a migration rather than an addition if they are wrong. Everything else here — screens, endpoints, library choices — is an addition-shaped decision that a later PR can revise cheaply.

## 📝 Problem Statement

The owner plans multi-stop trips and the plan lives in three places at once — his head, his mailbox, and "trochę w excelu" — so the one question he actually needs answered, *what is still not arranged*, exists nowhere in one piece (P1). Showing that state to a travel companion means retelling it (P2). Both problems rest on a single respondent who is also the builder, with no frequency and no cost attached; the brief says so plainly and A01 is accepted untested by D15. This spec does not lean on P2 at all — sharing is deferred (D08, D09) — and it addresses P1 by making the readiness counter a first-class object of the product rather than a badge in a corner.

The concrete deadline that shapes this document is A05's smallest test: *a walking skeleton by 2026-09-15 — one trip, its days, items with the three statuses, the counter, deployed and behind a login; whatever is not standing by then gets cut, chat first*. This spec is exactly that list and nothing else. It ships against a repository that today contains no product code, only conventions (`AGENTS.md`, `SDLC.md`, `scripts/check_locales.py`, the agent pipeline config).

Evidence and its limits, carried forward honestly from the brief: P1 and P2 are `[INTERVIEW]` claims from one session with one person; the design export is `[DOCUMENT]` evidence of an intended shape, explicitly labelled by the owner "wstępny design, do dostosowania w trakcie prac"; there is no benchmark data (brief Q01, open).

## 📝 Scope

### In scope

| # | Capability | Contract it serves |
|---|---|---|
| S1 | Owner authentication with e-mail and password; no screen showing a plan is reachable without an owner session | R08, D11, D14 |
| S2 | Create a trip: title, date range, departure point, optional return point that may differ from the departure point, one or more stages (bases) | R03, D06 |
| S3 | Days generated from the trip's date range at creation — the "Utwórz pustą oś czasu do ręcznego planowania" action of the design export | D03, D06 |
| S4 | Items on a day: type (accommodation, transport, activity, meal, other), an optional time, a title, free-text notes, and a status | brief glossary, D03 |
| S5 | Exactly three statuses — *do zaplanowania*, *do zarezerwowania*, *gotowe* | R02, D05 |
| S6 | The timeline view: days with their items, the readiness counter, a filter down to what is still left | R02, D05 |
| S7 | A day detail view where an item is created, edited and deleted properly | brief Key flows, "arranging one item" |
| S8 | Polish and English, both first-class, from the first commit; `scripts/check_locales.py` green | R01, R09 |

### Out of scope — each already decided and deferred, not re-litigated here

| Deferred | Decision | Where the design export shows it |
|---|---|---|
| Chat as an editing surface; the assistant; any suggestion | D03 (manual timeline first), D04 (planning, not shopping) | "VoyageAI Concierge" drawer, "Pomoc Asystenta", "Tryb sugestii AI", "Wypełnij pusty harmonogram z sugestiami AI", "Inteligentny Asystent Dnia", "Zasugeruj transfer kolejowy", "Optymalizuj trasę z AI", "Sugerowana optymalizacja czasowa" — **all out of scope; not designed here** |
| The read-only magic link and everything a guest sees | D08, D09 | the "Udostępnij" button — **out of scope** |
| File and image attachments | brief Q03 is open on size, formats, and link exposure | "Załączniki i dokumenty dnia", the PDF/PKPASS dropzone, "Przeciągnij e-bilety PDF", photo galleries — **out of scope** |
| Cost, budget, currency and reservation data | D07 (stored when they arrive with material the user has), R04; brief Q04 on multi-currency is open | PLN/EUR toggle, "Szacowany budżet 4 820 PLN", per-item prices, "Suma cząstkowa", "Wydatki potwierdzone" — **out of scope** |
| Booking, buying, live prices, live inventory | D04, R07 | "Zarezerwuj przez AI", "Kup 2 bilety (GetYourGuide / Official)", "Wybierz ofertę od 180 PLN/dzień", the Sixt/Europcar comparison — **out of scope** |
| Preparation tasks separate from timeline items | brief Q02, open — not decided for v1 | "Zadania & Przygotowanie" checklist — **out of scope** |
| Maps, routes, GPS, weather, PDF/Calendar export, reservation import | brief "Later" list, D12 | "Podgląd trasy", "Otwórz GPS", "Lizbona: 22°C • Lekki wiatr", "Eksportuj PDF", "Eksportuj do Google Calendar", "Import rezerwacji" — **out of scope** |
| Multiple owners, registration, invitations, co-editing | D09 (one editor), D15 (one user) | the account menu — **out of scope beyond logout and locale** |

Nothing in this table is *excluded* — N01 and D12 say the product excludes nothing permanently. Every row is *deferred*, and the boundary is the list above plus the *Now* list in the brief.

## 📝 Proposed Solution

A conventional three-tier slice with no cleverness anywhere, because the risk in this milestone is calendar risk (A05), not technical risk:

- A **FastAPI** service over **PostgreSQL** with **SQLAlchemy 2.0** and **Alembic** migrations, exposing a small JSON API under `/api/v1`, authenticated by an opaque server-side session in an `HttpOnly` cookie.
- A **React + TypeScript + Vite** single-page app with four routes, talking only to that API, translated by **react-i18next with ICU message formatting**.
- One first migration that already carries the multi-stop shape and the three-value status, so that neither becomes a migration later.

Alternatives considered and why they lost:

- **A server-rendered app (Jinja/HTMX) instead of an SPA.** It would be faster to the walking skeleton and would sidestep an entire build toolchain. Rejected because `AGENTS.md` fixes the stack as "a Python backend serving a React single-page frontend" — a repository convention that predates this spec and is not this document's to overturn.
- **SQLite instead of PostgreSQL.** Cheaper locally. Rejected because D14 puts the app on the public internet from day one; a deployment-grade database from the start avoids a dialect switch under time pressure, and the day-generation and date-range constraints below read better with real `DATE` and `CHECK` support.
- **Storing the trip's route as a list of legs (flights/transfers) the way the design export's "Odcinki podróży (Loty / Transfery)" panel does.** Rejected: a leg is a transport *item* on a day, which S4 already covers. Modelling legs twice — once as route structure, once as items — would create two sources of truth about the same journey and is exactly the kind of thing that becomes a migration.
- **JWT access tokens instead of server-side sessions.** Rejected: logout must actually revoke, there is no second service to federate to, and a stateless token buys nothing at one user while making revocation a design problem.

## 📝 Architecture

```
frontend/                      React SPA (Vite, TypeScript strict)
  src/
    api/                       typed fetch client; one module per resource
    features/auth/             login screen, session context, route guard
    features/trips/            trip list, trip creator
    features/timeline/         timeline screen, readiness counter, filter bar
    features/day/              day detail screen, item editor
    i18n/                      i18next bootstrap, ICU formatter, locale switch
    locales/en.json  pl.json   the parity gate's reference and target

backend/
  trip_planner/
    api/                       FastAPI routers (auth, trips, stages, days, items)
    domain/                    pure functions: day generation, readiness, stage resolution
    db/                        SQLAlchemy models, session, Alembic env
    security/                  password hashing, session tokens, CSRF, rate limit
    cli.py                     `create-owner` management command
  migrations/                  Alembic revisions
  tests/                       pytest
```

Boundaries that matter:

- **`domain/` is pure.** Day generation, the readiness arithmetic and stage-to-day resolution are functions over plain values with no database access, so each is unit-testable without fixtures and each is reusable when the same rule appears in a second place (the counter appears on the timeline header and, later, per day).
- **The API is the fence, the SPA route guard is only UX.** Every endpoint that touches a trip re-derives ownership from the session; the guard exists so the browser does not flash a protected screen, not so the server can trust it (R08, D14).
- **The frontend never computes the readiness counter.** The server returns `{arranged, total}` alongside the timeline so that one implementation of R02 exists, in `domain/`, with tests.
- **No external calls at all.** There is no maps client, no geocoder, no LLM provider, no price feed (D04, R07). This removes the whole class of "what does the user see when the third party is down" failure modes from this milestone, which is why the Failure Scenarios section below is about the database, the session and validation rather than about integrations.

### API versioning decision

`BACKWARD_COMPATIBILITY.md` records `Versioning: TODO — decide the strategy in the first API spec`. This is the first API spec, and it decides: **a URL version prefix, `/api/v1`**, with additive-only evolution inside a version. A version segment costs one path component today and is the only mechanism that lets a status code or an error code change without the expand/contract dance the compatibility table otherwise demands — cheap insurance for something reachable from the public internet. The implementation PR replaces that TODO line with this decision.

## 📝 Data Model

This is the section the milestone turns on. The two shapes below — how a multi-stop trip is stored, and how a status is stored — are the ones the owner named as migration risks.

### `owner`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `email` | TEXT, unique, case-insensitive | stored lower-cased; uniqueness on the lower-cased value |
| `password_hash` | TEXT | Argon2id, via `argon2-cffi`; never logged, never returned by any endpoint |
| `locale` | TEXT, `CHECK (locale IN ('pl','en'))`, default `'pl'` | the owner's UI language, so it survives a new browser (R01) |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

A real table with a real primary key even though D15 says there is exactly one user. That is not scope creep: "owner login" needs somewhere to put the hash, and a singleton row in a properly-shaped table is the cheapest thing that does not have to be migrated if D15 is ever revisited. What *is* out of scope is everything around it — no registration endpoint, no invitations, no roles, no password reset (Phase 1 note below).

### `trip`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `owner_id` | UUID FK → `owner.id`, `ON DELETE CASCADE`, indexed | every query scopes on it |
| `title` | TEXT NOT NULL | free text, e.g. "Malezja, październik 2026" |
| `start_date`, `end_date` | DATE NOT NULL | inclusive; `CHECK (end_date >= start_date)` |
| `departure_place` | TEXT NOT NULL | free text |
| `return_place` | TEXT NULL | free text; **NULL means one-way — the trip does not return** |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

**The open-jaw question, answered by two nullable-aware text columns rather than by structure.** R03 requires that a trip "may return from a different place than it departed", and D06 requires that the model carry this from the first migration. The design export's own control offers three route modes — *W obie strony*, *Inne miasto powrotu (Open-jaw / Multi-city)*, *W jedną stronę* — and those three modes fall out of these two columns with no discriminator column and no second table:

| Route mode in the UI | Stored as |
|---|---|
| Round trip (*W obie strony*) | `return_place = departure_place` |
| Open-jaw (*Inne miasto powrotu*) | `return_place ≠ departure_place` |
| One-way (*W jedną stronę*) | `return_place IS NULL` |

There is no `is_open_jaw` flag to keep in sync with the data, and no state the two columns cannot express. Places are **free text**, not references to a places table: D04 rules out live lookups, so any structured place entity would be a guess about a schema we cannot populate. Adding a nullable `departure_place_id` beside the text later is an addition; inventing the wrong place entity now would be a migration.

### `trip_stage` — a base (etap)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_id` | UUID FK → `trip.id`, `ON DELETE CASCADE`, indexed | |
| `position` | INTEGER NOT NULL | 0-based display order within the trip; `UNIQUE (trip_id, position)` |
| `place` | TEXT NOT NULL | free text, e.g. "Kuala Lumpur" |
| `start_date`, `end_date` | DATE NOT NULL | inclusive; `CHECK (end_date >= start_date)` |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

A trip has **one or more** stages (R03). Stage date ranges must lie inside the trip's range, and **stages may share a boundary date**: the design export's own example does exactly that — *Etap: Delhi (10.11 – 13.11)* and *Etap: Agra & Jaipur (13.11 – 17.11)* both contain the 13th, because the 13th is the travel day between them. So there is deliberately **no non-overlap constraint**; a day may resolve to zero, one or two stages, and the timeline renders "Delhi → Agra" when it resolves to two. Gaps are allowed too — a day belonging to no stage is a day in transit.

### `trip_day`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_id` | UUID FK → `trip.id`, `ON DELETE CASCADE` | |
| `date` | DATE NOT NULL | `UNIQUE (trip_id, date)` |
| `created_at` | TIMESTAMPTZ | |

Rows are generated for every date from `start_date` to `end_date` inclusive when the trip is created — this *is* the "create an empty timeline" action. **`trip_day` deliberately carries no `stage_id`.** The stage or stages covering a day are derived by date containment in `domain/`, because a stored foreign key would have to be re-maintained on every stage date edit and could silently contradict the stage's own dates — the "changing what it means while keeping its name" failure `BACKWARD_COMPATIBILITY.md` calls the worst kind. Derivation is a pure function that cannot drift, and adding a denormalised `stage_id` later, if the query cost ever justifies it, is an addition.

### `item`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_day_id` | UUID FK → `trip_day.id`, `ON DELETE CASCADE`, indexed | an item belongs to a **day**, never directly to a stage |
| `position` | INTEGER NOT NULL | order within the day, tie-break for items with no time |
| `kind` | TEXT NOT NULL, `CHECK (kind IN ('accommodation','transport','activity','meal','other'))` | |
| `status` | TEXT NOT NULL, `CHECK (status IN ('to_plan','to_book','done'))`, default `'to_plan'` | see below |
| `start_time` | TIME NULL | local wall-clock; NULL means "sometime that day" |
| `title` | TEXT NOT NULL | short label, e.g. "Nocleg: Memmo Alfama" |
| `notes` | TEXT NULL | free text, the item's description |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

**The status field, answered by a check-constrained text column with English identifiers.** R02 and D05 fix exactly three statuses. Two sub-decisions:

1. **English identifiers in the database and on the wire; Polish and English labels in the locale files.** `to_plan` / `to_book` / `done` are the stored values; *do zaplanowania* / *do zarezerwowania* / *gotowe* and *to plan* / *to book* / *done* are translation keys. R09 is explicit that code is English and only the interface is bilingual, and storing a Polish string as an enum value would make the English UI a translation of the database instead of a translation of the product.
2. **A `CHECK`-constrained `TEXT` column, not a PostgreSQL `ENUM` type.** R02 is active until 2026-12-31 and a superseding decision row is the documented way to change it; if that ever happens, altering a check constraint is an ordinary migration, whereas altering a native enum type is the awkward one. This is the more reversible of two shapes that are otherwise identical to use.

**No `cost`, no `currency`, no `confirmation_number`, no attachment relation.** D07 keeps cost data for when it arrives with material the user already has, which is the attachments feature; adding nullable columns for data nothing in this milestone can populate would be inventory nobody updates.

### The readiness counter (R02) — arithmetic, stated once

For a trip:

```
total    = count(items where status IN ('to_book', 'done'))
arranged = count(items where status = 'done')
```

Items still `to_plan` are outside **both** halves of the fraction — that is what the brief's glossary means by "items still *do zaplanowania* stay out of the arithmetic", and it is why the counter cannot be read as "done out of everything". A trip with ten items, all of them still *do zaplanowania*, reads **0 of 0**, not 0 of 10, because nothing has been decided yet and there is nothing to be behind on. The wording is `"{{arranged}} of {{total}} arranged"` / `"{{arranged}} z {{total}} załatwionych"`.

### Relationship summary

```
owner 1─n trip 1─n trip_stage          (ordered bases; ranges may share a boundary day)
             1─n trip_day 1─n item     (days generated from the range; items live on days)
             stage ↔ day: derived by date containment, never stored
```

### Migration

One Alembic revision creates all five tables plus `session` (below). It is the first migration in the repository, so the "safe against rows that already exist" rule in `BACKWARD_COMPATIBILITY.md` is vacuous here; the down-revision drops them. Every later phase in the plan below that adds a table gets its own revision in the same PR as the code that needs it.

## 📝 API Contracts

JSON over HTTPS, all under `/api/v1`, all cookie-authenticated except `POST /auth/login`. Request bodies are validated by Pydantic v2 models at the boundary — this resolves the `AGENTS.md` row "TODO: name the validation library once chosen", and the implementation PR fills that row in.

Conventions: dates are ISO `YYYY-MM-DD`, times are ISO `HH:MM` local wall-clock with **no** timezone (see Edge Cases), unknown fields are rejected, and errors are `{"error": {"code": "<stable_code>", "field": "<name|null>"}}` — a **stable machine-readable code**, never a prose message. The SPA maps codes to locale keys; this is what keeps R01 satisfied without a second locale root on the backend (`scripts/check_locales.py` skips `backend/trip_planner/locales/` while it does not exist, and this milestone does not create it).

### Authentication

| Method | Path | Body / Response | Notes |
|---|---|---|---|
| `POST` | `/auth/login` | `{email, password}` → `204` + `Set-Cookie: session=…` + CSRF cookie | `401 invalid_credentials` for both a wrong password and an unknown e-mail — identical body, identical timing budget, no user enumeration |
| `POST` | `/auth/logout` | → `204` | deletes the session row; idempotent |
| `GET` | `/auth/me` | → `{id, email, locale}` | `401` when there is no valid session |
| `PATCH` | `/auth/me` | `{locale}` → `{id, email, locale}` | the only mutable field in this milestone |

There is no registration endpoint, no password-reset endpoint and no invitation endpoint. The single owner account is created by a management command:

```
uv run trip-planner create-owner --email <address>     # password read from stdin, never from argv
```

### Trips

| Method | Path | Notes |
|---|---|---|
| `GET` | `/trips` | the owner's trips: `{id, title, start_date, end_date, departure_place, return_place, readiness:{arranged,total}}` |
| `POST` | `/trips` | `{title, start_date, end_date, departure_place, return_place?, stages:[{place, start_date, end_date}]}` → `201` with the full trip **and its generated days**. This single call is the design export's "Utwórz pustą oś czasu do ręcznego planowania". At least one stage is required (R03) |
| `GET` | `/trips/{tripId}` | the timeline payload: trip, ordered stages, ordered days each with its derived `stage_ids` and its items, and `readiness` |
| `PATCH` | `/trips/{tripId}` | title, dates, departure/return place. Changing the range regenerates days — see Edge Cases |
| `DELETE` | `/trips/{tripId}` | cascades to stages, days and items |

### Stages, days, items

| Method | Path | Notes |
|---|---|---|
| `POST` / `PATCH` / `DELETE` | `/trips/{tripId}/stages[/{stageId}]` | `position` is reassigned server-side to stay dense |
| `GET` | `/trips/{tripId}/days/{date}` | the day detail payload: the day, its derived stages, its ordered items, and prev/next dates for the day navigator |
| `POST` | `/trips/{tripId}/days/{date}/items` | `{kind, status?, start_time?, title, notes?}` → `201`; `status` defaults to `to_plan` |
| `PATCH` | `/trips/{tripId}/items/{itemId}` | any item field, plus `date` to move the item to another day of the same trip |
| `DELETE` | `/trips/{tripId}/items/{itemId}` | |

Every path is nested under `/trips/{tripId}` so the ownership scope is impossible to forget in a handler. A trip belonging to a different owner answers **`404`, not `403`** — a `403` would confirm the resource exists.

### Query parameters on the timeline

`GET /trips/{tripId}?status=outstanding` and `?kind=accommodation|transport|activity|meal|other` filter the items in the returned days. `readiness` is **always computed over the unfiltered set**, so the counter does not change when the user filters — a counter that moved with the filter would answer a different question every time it was read.

## 📝 UI/UX

Four routes. The design export is the visual reference for three of them; each is listed with what is adapted and what is dropped, because the export was drawn for a product with an assistant, prices and documents in it.

Mockups of the proposed screens live beside this spec and are attached to this spec's PR. They are illustrative statics — layout and flow, not pixel-perfect design — rendered from self-contained HTML with no application code behind them. There are **no current-state screenshots**: the repository contains no product code yet, so there is no running application to photograph.

| Screen | Mockup |
|---|---|
| `/trips/new` — the multi-stop creator, Polish locale | [`assets/walking-skeleton/mockup-01-trip-creator.png`](assets/walking-skeleton/mockup-01-trip-creator.png) |
| `/trips/:id` — the timeline, the counter and the filter bar, Polish locale | [`assets/walking-skeleton/mockup-02-timeline.png`](assets/walking-skeleton/mockup-02-timeline.png) |
| `/trips/:id/days/:date` — the day detail and the item editor, **English locale** | [`assets/walking-skeleton/mockup-03-day-detail.png`](assets/walking-skeleton/mockup-03-day-detail.png) |

Two of the three are rendered in Polish and one in English on purpose: R01 makes both locales first-class, and a spec that only ever pictures one of them is not showing the product it describes. `/login` has no mockup — it is a two-field form and the spec's own rule is that standard CRUD does not earn a picture.

### `/login`

E-mail, password, submit, a locale switch, and nothing else. No "remember me", no "forgot password", no sign-up link — none of those exist behind the API. On `401` the form shows one generic message in the active locale. This is the only unauthenticated route; every other route redirects here, preserving the intended path so that login lands the user where they were going.

### `/trips` — trip list

A list of the owner's trips, each row showing the title, the date range, the route summary (`Warszawa → Kuala Lumpur → Warszawa`, or `→ Katowice` when the return place differs) and the readiness counter. A "New trip" action. An empty state for a first-time account. This screen is not in the design export; it is the smallest thing that makes more than one trip navigable, and it is standard CRUD — the implementation is not specified further here.

### `/trips/new` — the multi-stop creator

Adapted from `kreator_podr_y_manualny_i_wieloodcinkowy`:

- **Kept:** the route-mode toggle (*W obie strony* / *Inne miasto powrotu (Open-jaw)* / *W jedną stronę*), which writes exactly the three `return_place` states in the data model; the trip date range; the ordered list of stages with a place and a date range each, add and remove; the live summary panel ("15 dni / 14 n. · 3 bazy"); and the primary action **"Utwórz pustą oś czasu do ręcznego planowania"** — the button whose semantics this whole screen exists to deliver.
- **Dropped, and why:** the "Kreator manualny / Tryb sugestii AI / Import rezerwacji" mode tabs and the "Wypełnij pusty harmonogram z sugestiami AI" secondary action (D03, D04 — no assistant); the "Odcinki podróży (Loty / Transfery)" leg editor with its flight numbers (legs are transport *items*, see Proposed Solution); the PNR / e-ticket dropzone (attachments out of scope); the "Budżet i koszty manualne" panel (D07); the "Potrzebujesz pomocy AI?" side card.
- **States:** the primary action is disabled until the trip has a title, a valid range and at least one stage; validation errors appear against the field that caused them; a stage range outside the trip range is refused inline before the request is sent, and again by the server.

### `/trips/:id` — the timeline

Adapted from `g_wny_pulpit_i_o_czasu`, which is the screen the counter lives on:

- **Kept:** the trip header with title, date range and route summary; the **readiness counter** rendered as the export's "STATUS LOGISTYKI · 7 z 11 pozycji" tile, here reading "x of y arranged"; the filter bar, as *All* / *Only outstanding* / one chip per item type, mirroring "Wszystko (11) · Noclegi (3) · Transport (4) · Atrakcje i Jedzenie (4) · Tylko do zrobienia (3)"; the vertical day-by-day timeline with a date chip per day and a card per item; the per-item status chip; the item's time, type icon, title and notes.
- **Dropped, and why:** the entire "VoyageAI Concierge" drawer and every AI card in it (D03, D04); the PLN/EUR toggle and the "SZACOWANY BUDŻET 4 820 PLN" tile and all per-item prices (D07, R04, brief Q04 open); "Eksportuj PDF" and "Udostępnij" (Later list; D08 sharing deferred); reservation codes, "Opłacono z góry", "Zarezerwuj przez AI" and "Kup bilety online" (R07); ticket-PDF pills and photo cards (attachments out of scope); the per-day weather strip (Later list).
- **The counter's exact behaviour:** it shows `arranged of total` per the arithmetic above; when `total` is 0 it renders "nothing arranged yet" rather than a fraction or a percentage, because the percentage is undefined and a "0%" would read as failure where the honest reading is "you have not decided anything yet". The counter never changes when a filter is applied.
- **The filter's exact meaning:** *Only outstanding* is `status ≠ done` — both *do zaplanowania* and *do zarezerwowania* — because it answers "what do I still have to touch", which is a different and equally useful question from the one the counter answers. See the Resolved assumptions.
- **Empty states:** a trip whose days are all empty shows the days with an invitation to add the first item, not a blank page; that empty timeline is the deliverable of Phase 2 and must look deliberate.

### `/trips/:id/days/:date` — the day detail

Adapted from `szczeg_y_dnia_i_aktywno_ci`:

- **Kept:** the breadcrumb (Trips → trip → day), the day heading with its derived stage or stages, prev/next day navigation, the numbered ordered list of the day's items, and the item editor — type, time, title, notes, status — as a dialog opened from an item or from "Add item", with save and delete.
- **Dropped, and why:** the "Podgląd trasy" map with "Otwórz GPS" (Later list); "Załączniki i dokumenty dnia" and "Dodaj plik / zdjęcie / bilet" (attachments out of scope); "Zadania & Przygotowanie" (brief Q02 open — not decided for v1); the "Inteligentny Asystent Dnia" panel and "Sugerowana optymalizacja czasowa" (D03, D04); "Eksportuj do Google Calendar" and "Optymalizuj trasę z AI" (Later list); per-item photos, ratings, prices, ticket numbers and vendor comparisons (D07, R07, attachments).
- **The status control is the point of this screen.** Moving an item to *gotowe* here is the action the counter on the timeline reacts to, and it is the brief's "arranging one item" flow with its attachment step removed.

### Cross-cutting UI rules

- **Bilingual, both first-class (R01).** Every string goes through i18next; the `<html lang>` attribute follows the active locale; dates, times and numbers are formatted through `Intl` with the active locale, never concatenated. The locale switch is in the header and persists to `owner.locale` for a signed-in user and to `localStorage` before login.
- **Status is never colour alone.** Each status chip carries its translated text and a distinct shape/icon as well as a colour, so the three statuses are distinguishable to a colour-blind reader and in a screenshot.
- **Keyboard and focus.** The item editor is a focus-trapped dialog that returns focus to its trigger; the filter bar is a real radio group; the timeline's day headings are real headings so the page is navigable by landmark.
- **Design tokens.** `modern_premium_travel_companion/DESIGN.md` supplies the palette, the Plus Jakarta Sans type scale, radii and spacing; those become CSS custom properties. The brand name is **Smart Trip Planner** — "VoyageAI" from the export is dropped (D01).

## 📝 Edge Cases & Failure Scenarios

| Case | Behaviour |
|---|---|
| `end_date < start_date` on a trip or stage | `422 invalid_date_range`, refused client-side first |
| A stage range not contained in the trip range | `422 stage_outside_trip` naming the stage |
| A trip created with zero stages | `422 stages_required` — R03 says one or more |
| Trip range shortened so that a day carrying items falls outside it | `409 days_have_items` listing the offending dates; **no item is ever destroyed by a date edit**. The owner deletes or moves those items first. Days without items are removed silently |
| Trip range extended | new `trip_day` rows are inserted for the new dates; existing days and items are untouched |
| Trip range longer than 366 days | `422 trip_too_long`. A bound exists so that one bad date entry cannot generate an unbounded number of rows |
| Two stages covering the same day | allowed and rendered as "A → B"; this is the travel day, and the design export's own example does it |
| A day covered by no stage | allowed; rendered without a stage label — a day in transit |
| Item with no time | sorted after all timed items of that day, ordered among itself by `position`; rendered as "all day" |
| `total = 0` for the counter | "nothing arranged yet"; no fraction, no percentage, no division |
| Deleting a stage | days and items survive — days belong to the trip, not to the stage. Only the derived label changes |
| Deleting a trip | cascades to stages, days and items; a confirmation dialog naming the trip, since there is no undo in this milestone |
| Session expires mid-edit | the API answers `401`; the SPA routes to `/login` carrying the return path, and unsaved dialog input is preserved in component state for the length of that navigation only |
| Repeated failed logins | rate-limited per e-mail and per source address; the response and its timing are identical to an ordinary failure so the limiter cannot be used to enumerate accounts |
| A trip id belonging to nobody, or to another owner | `404`, identically |
| CSRF | unsafe methods require a double-submit token header matching a non-`HttpOnly` cookie; `SameSite=Lax` on the session cookie is the first line and this is the second (D14 — public internet from day one) |
| Database unavailable | `503` with a stable code; the SPA shows a retry state rather than an empty timeline, because an empty timeline is indistinguishable from a real empty trip and would be a lie about the plan |
| Concurrent edits from two tabs | last write wins; `updated_at` is returned but not enforced. At one user (D15) optimistic locking is machinery without a failure to prevent. Documented rather than silently absent |

**Times and dates carry no timezone, deliberately.** A trip's days are calendar dates and an item's time is the wall-clock time at the place it happens; storing them as `DATE` and `TIME` and never converting is correct for a plan that a human reads, and it removes any dependency on timezone data for places we do not resolve (D04). The cost is that the app cannot say "your flight leaves in 3 hours" — nothing in the *Now* scope asks it to.

## 📝 Internationalisation — the library, chosen and justified

**The choice is `react-i18next` (with `i18next` and `i18next-icu`), and the deciding factor is `scripts/check_locales.py`.** That gate flattens every locale file to dotted leaf keys and fails when Polish has a key English does not define — which is precisely what i18next's *default* pluralisation would produce, because Polish resolves to four CLDR plural categories (`one`, `few`, `many`, `other`) against English's two, so a single "x of y arranged" string would ship as `counter_one`/`counter_other` in `en.json` and `counter_one`/`counter_few`/`counter_many`/`counter_other` in `pl.json` and turn the parity gate red on the first pluralised string in a product whose central UI element is a counter. Adding `i18next-icu` moves the plural selection *inside* one key's value as an ICU `{count, plural, ...}` expression, so both files keep byte-for-byte identical key sets and the gate passes unchanged — no edit to `check_locales.py`, no special-casing of suffixes, no exception to R01. Everything else follows: plain JSON resource files in exactly the `en.json` / `pl.json` layout the gate already supports, no extraction or compile step between adding a key and running the gate, a `Trans` component for strings with markup in the middle (the counter, which emphasises its numbers), `Intl`-backed date and number formatting through the same formatter so that R01's extension to dates and numbers is satisfied by one mechanism, and language detection with persistence. The alternatives lose on the same axis: **FormatJS / react-intl** has first-class ICU but keeps messages in compiled, id-keyed build artifacts, which is friction against a gate that reads the source JSON; **Lingui** is excellent and also ICU-based, but its macro-and-compile pipeline is more machinery than a two-locale personal application needs before 2026-09-15; and a **hand-rolled context** would be the smallest thing that works right up to the first Polish plural and the first locale-formatted date, both of which appear on the timeline in Phase 4.

The implementation PR replaces the `i18n | TODO — library not yet chosen` row in `AGENTS.md` with this decision, in the same PR that introduces the dependency.

## 📝 Risks & Impact Review

- **Blast radius: none, and that is the point.** The repository has no product code, so this spec breaks nothing. It *creates* the surfaces `BACKWARD_COMPATIBILITY.md` currently lists as "not yet created" — the HTTP API and the database schema — and every one of its inventory rows starts applying the moment Phase 1 merges. The compatibility file's `Versioning: TODO` is resolved above.
- **The identified migration risks are the two shapes in the Data Model section**, and they are the reason this spec is gated (see Resolved assumptions A2). If the multi-stop shape is wrong, the fix is a data migration across `trip`, `trip_stage` and `trip_day`; if the status shape is wrong, the fix is a check-constraint migration plus a backfill. Both were designed for the cheaper failure: text places rather than a guessed place entity, derived rather than stored day-to-stage links, and a check constraint rather than a native enum.
- **Rollback story.** Each phase is one Alembic revision with a working `downgrade`, and each phase leaves the application running. Rolling back Phase 4 leaves a usable timeline without a counter; rolling back Phase 3 leaves an empty timeline; rolling back Phase 2 leaves a login screen and nothing behind it. There is no point in the plan where a rollback leaves a half-migrated database, because no phase alters a column another phase already shipped.
- **Product-decision compliance.** Nothing here contradicts an active row in the brief's Non-goals, Business rules or Decisions tables, so nothing needs a superseding row. The spec *answers* brief open question Q05 (the i18n library), which the brief itself assigns to "the first frontend PR"; it leaves Q01 (benchmark), Q02 (preparation tasks), Q03 (attachments) and Q04 (currency) open and out of scope.
- **Calendar risk is the real risk (A05).** The plan below is ordered so that the cut line is visible: if 2026-09-15 arrives during Phase 4, the app still logs in, creates a multi-stop trip, generates days and edits items with statuses — the counter is the last thing built and the only thing that can slip without making the rest useless. If it arrives during Phase 3, there is a deployed, authenticated, empty timeline, which is A05's own minimum minus items.
- **Security posture (D14).** Argon2id hashing, opaque server-side sessions with real revocation, `HttpOnly` + `Secure` + `SameSite=Lax` cookies, a CSRF double-submit token, login rate limiting, no user enumeration, `404` rather than `403` for other owners' resources, and no secret in any log line or error body. There is no password reset in this milestone — the recovery path is the `create-owner` command on the server, which is honest at one user and must not be quietly relied on at two.
- **What this spec does not protect against.** A03 — that a hand-maintained plan stays current enough to be trusted — is untestable before the app exists and is not addressed by any design decision here. The counter is only as true as the statuses the owner sets.

## 📝 Decisions in play

| Id | How this spec relies on it |
|---|---|
| R01 / R09 | Both locales first-class from the first commit; ICU pluralisation chosen so the parity gate passes unmodified; code, spec and PR bodies English |
| R02 / D05 | Exactly three statuses; the counter's numerator is `done` and its denominator is `to_book + done`; `to_plan` is outside the arithmetic |
| R03 / D06 | Multi-stop and a differing return point are in the first migration, via `trip.departure_place` / `trip.return_place` and the ordered `trip_stage` table |
| R07 / D04 | No external calls of any kind in this milestone |
| R04 / D07 | No cost, currency, or reservation columns |
| R08 / D11 / D14 | E-mail-and-password owner login; nothing showing a plan reachable without a session; public-internet security posture from day one |
| R06 / D08 / D09 | Sharing and guests deferred entirely — no share token, no guest route |
| D03 | Manual timeline; chat is not built |
| D01 | The product is Smart Trip Planner; the export's "VoyageAI" brand is dropped |
| D15 | One owner; a real `owner` table but no registration, roles or invitations |
| N01 / D12 | Everything above is deferred, not excluded |
| Brief Q05 | Answered by this spec (the brief assigns it to the first frontend PR) |
| Brief Q01, Q02, Q03, Q04 | Left open; the features they concern are out of scope |

**Nothing in this spec proposes to supersede an active entry.** No owner approval is required on that count; the approval this spec does need is on its two autonomous assumptions below.

## ⚠️ Resolved assumptions (autonomous defaults)

This spec was written in `--autonomous` mode. Each question below was resolved by the most reversible, smallest-scope answer available, and each is open to override before merge.

| # | Question | Resolved as | Rationale |
|---|---|---|---|
| A1 | Should this brief be split into more than one spec? | **No — one spec, four phases** | The pieces are not independently deployable: a timeline without login is not shippable under D14, and items without a trip have nowhere to live. Splitting would create four specs with a strict dependency chain and no independent value, which is the opposite of the scope-cohesion rule's intent |
| A2 | How is the multi-stop shape stored, so that R03 and D06 are satisfied from the first migration? | **`trip.departure_place` + nullable `trip.return_place` + an ordered `trip_stage` table; day-to-stage derived by date containment, never stored; places as free text** — ⚠ **NEEDS HUMAN CONFIRMATION** | The three route modes fall out with no discriminator column, boundary-sharing travel days are expressible, and every deferred refinement (a place entity, a stored `stage_id`) is an addition rather than a migration. Marked for confirmation because the owner named this the one thing that would be a migration if it is wrong, and no brief decision fixes the shape below the level of R03 |
| A3 | Native `ENUM` or a `CHECK`-constrained `TEXT` column for `item.status`, and in which language are the values stored? | **`CHECK`-constrained `TEXT`, values `to_plan` / `to_book` / `done`** | R09 puts code in English and only the UI in Polish; a check constraint is an ordinary migration to change, a native enum type is not. Identical to use, cheaper to revise |
| A4 | What exactly does the "filter down to what is still left" show? | **`status ≠ done` — both *do zaplanowania* and *do zarezerwowania*** | The counter already answers "how much of what I decided is booked"; the filter answers the different question "what do I still have to touch". Narrower readings are reachable through the per-status chips the same filter bar carries |
| A5 | Which i18n library? (brief Q05) | **`react-i18next` + `i18next-icu`** | The only way to keep `en.json` and `pl.json` key-identical across Polish's four plural categories without editing `scripts/check_locales.py`; see the internationalisation section for the full argument |
| A6 | Which backend framework, ORM and database? | **FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic + PostgreSQL** | Mainstream, `uv`-installable, and Pydantic fills the `AGENTS.md` "validation library — TODO" row. Postgres over SQLite because D14 deploys publicly from day one and a dialect switch under deadline pressure is the expensive failure |
| A7 | How is the owner session carried? | **Opaque server-side session token in an `HttpOnly` + `Secure` + `SameSite=Lax` cookie, with a CSRF double-submit token** | Logout must genuinely revoke; there is no second service to federate to. A JWT would make revocation a design problem in exchange for statelessness nothing here needs |
| A8 | How does the owner account come to exist — self-serve registration or a provisioned account? | **Provisioned by a `create-owner` management command; no registration endpoint, no password reset** | D15 says one user, and a public sign-up form on an internet-facing app is attack surface serving nobody. Adding registration later is an endpoint; removing one after it has been reachable is not |
| A9 | What happens to items on days that a shortened trip range would delete? | **`409` naming the dates; the owner moves or deletes them first. A date edit never destroys an item** | Data loss is a blocker finding under `BACKWARD_COMPATIBILITY.md`, and this is the reversible half of a choice whose other half is irreversible |
| A10 | API versioning strategy (the `BACKWARD_COMPATIBILITY.md` TODO) | **`/api/v1` prefix, additive-only within a version** | One path component, and the only mechanism that lets an error code or status code change later without the expand/contract dance the compatibility table otherwise requires |

## 📋 Phasing

Each phase is independently shippable and leaves the application working and deployable.

- **Phase 0 — Foundation and a green gate.** The repository can build, test and lint itself, in both locales.
- **Phase 1 — Owner authentication.** The application is deployable to the public internet with nothing reachable behind the login (R08, D14). This is the phase that makes every later phase safe to ship.
- **Phase 2 — Trip creation and the empty timeline.** A multi-stop trip exists, with its days (R03, D06).
- **Phase 3 — Items, statuses and the day detail.** The plan can be filled in by hand (D03, D05).
- **Phase 4 — The readiness counter and the filter.** The product answers its central question (R02, P1).

## 📋 Implementation Plan

Every step below is testable and leaves the application working. This structure is what `om-auto-implement-spec` hands to `om-auto-create-pr`.

### Phase 0 — Foundation and a green gate

1. Scaffold `backend/` as a `uv` project: `pyproject.toml`, `uv.lock`, `ruff` configuration, a `pytest` suite with one passing smoke test, and a FastAPI app exposing `GET /api/v1/health`. Verify: `(cd backend && uv run ruff check .)` and `(cd backend && uv run pytest)` pass.
2. Scaffold `frontend/` as a Vite + React + TypeScript project with strict mode, Vitest, and one passing smoke test. Verify: `npm run typecheck`, `npm run test -- --run` and `npm run build` pass.
3. Add `react-i18next`, `i18next` and `i18next-icu`; create `frontend/src/locales/en.json` and `pl.json` with the first shared keys; wire the provider, the `<html lang>` binding and the locale switch. Include at least one ICU-pluralised key so the arrangement is proven. Verify: `python3 scripts/check_locales.py` reports both locales in sync, and a test asserts the Polish *few* and *many* forms render.
4. Add PostgreSQL, SQLAlchemy 2.0 and Alembic with an empty baseline revision, plus a pytest fixture that migrates a throwaway database per session. Verify: `alembic upgrade head` and `downgrade base` both succeed in a test.
5. Replace the `i18n` and validation-library `TODO` rows in `AGENTS.md`, and the `Versioning: TODO` line in `BACKWARD_COMPATIBILITY.md`, with the decisions this spec makes. Verify: no `TODO` remains for a decision this spec resolved.
6. Add the GitHub Actions workflow that runs the six validation-gate commands in the order `.ai/agentic.config.json` lists them. Verify: the workflow is green on the PR.

### Phase 1 — Owner authentication (R08, D11, D14)

1. Migration and models for `owner` and `session` (`id`, `owner_id`, `token_hash`, `created_at`, `expires_at`, `last_seen_at`). Verify: upgrade/downgrade round-trip test.
2. `security/`: Argon2id hash and verify via `argon2-cffi`; opaque 256-bit token generation; constant-time comparison against the stored hash. Verify: unit tests, including that a hash is never equal to its password and never appears in `repr`.
3. `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/me` with the cookie and CSRF handling described above. Verify: tests for success, wrong password, unknown e-mail (identical response), missing CSRF token on an unsafe method, and logout actually invalidating the token.
4. Login rate limiting per e-mail and per source address. Verify: a test that the limiter engages and that its response is indistinguishable from an ordinary failure.
5. A FastAPI dependency that resolves the session or raises `401`, applied to every non-auth route by default rather than opted into per route. Verify: a test that enumerates the application's routes and asserts each one either is in the public allow-list or carries the dependency — the test that keeps R08 true as routes are added.
6. `trip-planner create-owner` CLI reading the password from stdin. Verify: a test that the password never appears in `sys.argv` or in the command's output.
7. The `/login` screen, the session context, the route guard and the redirect-with-return-path. Verify: component tests for the guard redirecting, and for the error message rendering in both locales.

### Phase 2 — Trip creation and the empty timeline (R03, D06)

1. Migration and models for `trip`, `trip_stage` and `trip_day` exactly as specified, with every `CHECK` and `UNIQUE` constraint. Verify: tests that the database itself rejects an inverted date range and a duplicate `(trip_id, date)`.
2. `domain/days.py`: `generate_days(start, end) -> list[date]`, inclusive, bounded at 366. Verify: unit tests for a one-day trip, a leap-day span, and the bound.
3. `domain/stages.py`: `stages_for_day(stages, date) -> list[stage]` by containment, returning zero, one or two. Verify: unit tests for a travel day shared by two stages and for a day in no stage.
4. `POST /trips` creating the trip, its stages and all its days in one transaction; `GET /trips`; `GET /trips/{id}` returning the timeline payload with derived `stage_ids`. Verify: tests for the three route modes, for `stages_required`, for `stage_outside_trip`, and that another owner's trip answers `404`.
5. `PATCH /trips/{id}` with the date-range regeneration rule, and `DELETE /trips/{id}`. Verify: tests that extending adds days, that shortening past a day with items answers `409` and changes nothing, and that shortening past an empty day removes it.
6. `PATCH`/`POST`/`DELETE` for stages with dense `position` reassignment. Verify: tests that positions stay dense after a delete from the middle.
7. The `/trips` list screen and the `/trips/new` creator, including the route-mode toggle and inline validation. Verify: component tests for each route mode producing the right request body, and for the primary action staying disabled until the form is valid.
8. The `/trips/:id` timeline rendering days with their stage labels and a deliberate empty state. Verify: a component test that a trip with no items renders every day and the empty-state copy in both locales.

### Phase 3 — Items, statuses and the day detail (D03, D05)

1. Migration and model for `item` with both `CHECK` constraints. Verify: a test that the database rejects a fourth status value — the constraint that makes R02 structural rather than conventional.
2. `GET /trips/{id}/days/{date}` returning the day payload with prev/next dates. Verify: tests for the first and last day of a trip, and for a date outside the trip answering `404`.
3. Item `POST`, `PATCH` (including `date` to move an item between days) and `DELETE`, with the ordering rule. Verify: tests for the default status, for untimed items sorting last, and for a move to a day of a different trip being refused.
4. The `/trips/:id/days/:date` screen: the ordered item list, day navigation, and the item editor dialog with type, time, title, notes and status. Verify: component tests for creating, editing and deleting an item, and for focus returning to the trigger when the dialog closes.
5. Status chips rendered with text and shape as well as colour, in both locales. Verify: a test asserting the three translated labels exist in `en.json` and `pl.json` and that the chip is legible without colour.
6. Items rendered on the timeline's day cards. Verify: a component test that an item created in the day detail appears on the timeline.

### Phase 4 — The readiness counter and the filter (R02, P1)

1. `domain/readiness.py`: `readiness(items) -> (arranged, total)` with `to_plan` excluded from both. Verify: unit tests for all-`to_plan` returning `(0, 0)`, for the mixed case, and for the empty case.
2. `readiness` on the `GET /trips` and `GET /trips/{id}` payloads. Verify: an API test that the figure matches the domain function and that it does **not** change when a filter parameter is present.
3. `?status=outstanding` and `?kind=` filtering of the returned items. Verify: tests that *outstanding* returns both non-`done` statuses and that an unknown value is a `422`.
4. The counter tile on the timeline and the trip list, with its `total = 0` copy. Verify: component tests for the fraction, for the zero state, and for the Polish plural forms of "pozycja".
5. The filter bar as a radio group with the *All* / *Only outstanding* / per-type options, driving the query parameter and reflected in the URL. Verify: component tests that switching a filter changes the item list and leaves the counter untouched.
6. End-to-end verification of the brief's own success flow: log in, create a three-stage open-jaw trip, add items across several days, set statuses, read the counter, filter to what is outstanding. Verify: an integration test walking that path, and screenshots on the implementation PR.
