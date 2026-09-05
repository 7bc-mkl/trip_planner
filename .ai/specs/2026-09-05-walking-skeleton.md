# Walking skeleton — trip, timeline, statuses, counter, login

- Date: 2026-09-05 · Author: `om-auto-write-spec` (autonomous) · Status: draft, gated on the assumptions below
- Source brief: `.ai/specs/product-brief.md` (signed 2026-09-05)
- Visual reference: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/` — a preliminary mockup, adapted here, not a contract
- Mode: `om-spec-writing --autonomous`. Every question this spec answered on its own is listed under **Resolved assumptions (autonomous defaults)** and is open to override before merge.

## 📝 TLDR

Build the first working slice of Smart Trip Planner: an owner logs in with e-mail and password, creates a multi-stop trip from a date range, a departure point, an optional return point and one or more stages, gets an empty timeline of days generated from those dates, fills the days with items that each carry a type, a time, free text and one of exactly three statuses, and reads at a glance how much of the trip is arranged — on a deployed, internet-facing installation. It is the walking skeleton A05 names as the test of whether the *Now* scope is buildable: a thin vertical cut through authentication, the data model, the API, the UI and the deployment, with nothing in it that is not load-bearing.

The three decisions that carry the whole spec are the multi-stop shape, the status field and the item's time span, because each would be a migration rather than an addition if it is wrong. Everything else here — screens, endpoints, library choices — is an addition-shaped decision that a later PR can revise cheaply.

## 📝 Problem Statement

The owner plans multi-stop trips and the plan lives in three places at once — his head, his mailbox, and "trochę w excelu" — so the one question he actually needs answered, *what is still not arranged*, exists nowhere in one piece (P1). Showing that state to a travel companion means retelling it (P2). This spec addresses P1 by making the readiness counter a first-class object of the product rather than a badge in a corner; it does not address P2 at all, and the Scope section below is explicit that this is a cut under A05's authority rather than a product decision.

The concrete deadline that shapes this document is A05's smallest test: *a walking skeleton by 2026-09-15 — one trip, its days, items with the three statuses, the counter, deployed and behind a login; whatever is not standing by then gets cut, chat first*. It ships against a repository that today contains no product code, only conventions (`AGENTS.md`, `SDLC.md`, `scripts/check_locales.py`, the agent pipeline config).

Evidence and its limits, carried forward honestly from the brief: P1 and P2 are `[INTERVIEW]` claims from one session with one person who is also the builder, with no frequency and no cost attached; the design export is `[DOCUMENT]` evidence of an intended shape, explicitly labelled by the owner "wstępny design, do dostosowania w trakcie prac"; there is no benchmark data at all (brief Q01, open).

## 📝 Scope

### In scope

| # | Capability | Contract it serves |
|---|---|---|
| S1 | Owner authentication with e-mail and password; no screen showing a plan reachable without an owner session; deployed to the public internet | R08, D11, D14 |
| S2 | Create a trip: title, date range, departure point, optional return point that may differ from the departure point, one or more stages (bases) | R03, D06 |
| S3 | Days generated from the trip's date range — the "Utwórz pustą oś czasu do ręcznego planowania" action of the design export | D06, and the brief's *Now* bullet 2 |
| S4 | Items on a day: type (accommodation, transport, activity, meal, other), an optional time span, a title, free-text notes, and a status | brief glossary; *Now* bullet 3 |
| S5 | Exactly three statuses — *do zaplanowania*, *do zarezerwowania*, *gotowe* | R02, D05 |
| S6 | The timeline view: days with their items, the readiness counter, a filter down to what is still left | R02, D05; *Now* bullet 4 |
| S7 | A day detail view where an item is created, edited and deleted properly | brief Key flows, "arranging one item" |
| S8 | Polish and English, both first-class, from the first commit; `scripts/check_locales.py` green | R01, R09 |

### Out of scope — and the honest authority for each cut

**Read this table carefully, because it is easy to get wrong.** Several things this milestone does not build are *inside* the brief's *Now* list, mandated by active decision rows. Chat is in *Now* under D03 ("chat **adds and changes items**"); the read-only magic link is in *Now* under D08 and D09; attachments are named in *Now* bullet 5 ("a day detail view for editing an item properly, **with file and image attachments**"); R04 says cost and reservation data **are stored** when they arrive. **None of those decisions authorises deferring the thing it mandates.**

The authority for every cut below is **A05** — the riskiest-assumption row whose own smallest test is *"a walking skeleton by 2026-09-15 … whatever is not standing by then gets cut, chat first"* — together with the owner's scoping instruction for this milestone. This spec therefore covers a **strict subset** of the *Now* list, and the remainder stays in scope for the first version, to be covered by later specs. It is not a superseding decision and does not need one: A05 is the brief's own mechanism for sequencing *Now*, not for shrinking it.

| Deferred to a later spec | Authority for cutting it *here* | Where the design export shows it — and what we do with that |
|---|---|---|
| Chat as an editing surface; the assistant; any suggestion | A05 ("cut … chat first"), naming chat explicitly and first | "VoyageAI Concierge", "Pomoc Asystenta", "Tryb sugestii AI", "Wypełnij pusty harmonogram z sugestiami AI", "Inteligentny Asystent Dnia", "Zasugeruj transfer kolejowy", "Optymalizuj trasę z AI" — **not designed here.** D04/R07 additionally fix that when it is built it will not search live inventory |
| The read-only magic link and everything a guest sees | A05 (not in the skeleton's list) | the "Udostępnij" button — **not designed here.** D08/D09 fix its shape for the later spec: one link per trip, read-only, one editor |
| File and image attachments | A05 (not in the skeleton's list); brief Q03 also still open on size, formats and link exposure | "Załączniki i dokumenty dnia", "Dodaj plik / zdjęcie / bilet", the PDF/PKPASS dropzone, photo galleries — **not designed here** |
| Cost, currency and reservation data | A05 (not in the skeleton's list). R04 keeps this data *when it arrives with an attachment* — so it is downstream of attachments and cannot ship before them. Brief Q04 (multi-currency) is open | PLN/EUR toggle, "Szacowany budżet", per-item prices, "Suma cząstkowa" — **not designed here** |
| Booking, buying, live prices, live inventory | D04 and R07 — this one **is** a real decision-backed exclusion from the first version, not an A05 cut | "Zarezerwuj przez AI", "Kup 2 bilety", "Wybierz ofertę od 180 PLN/dzień", the Sixt/Europcar comparison — **not designed here** |
| Preparation tasks separate from timeline items | brief Q02 is open — undecided for v1, so there is nothing to build to | "Zadania & Przygotowanie" — **not designed here** |
| Maps, routes, GPS, weather, PDF/Calendar export, reservation import | D12 — the brief's *Later* list; a genuine deferral | "Podgląd trasy", "Otwórz GPS", the weather strip, "Eksportuj PDF", "Eksportuj do Google Calendar", "Import rezerwacji" — **not designed here** |
| Multiple owners, registration, invitations, co-editing | D09 (one editor) and D15 (one user) — decision-backed | the account menu — **out of scope beyond sign-out and the locale switch** |

Nothing here is *excluded*: N01 and D12 say the product excludes nothing permanently.

### The slippable tail

A05 says what gets cut if 2026-09-15 arrives first, and a plan that does not name its own cut line is not managing the risk it identifies. In priority order, **the last things built and the first things to drop are**: the per-type filter chips, `DELETE /trips`, `PATCH /trips` with its date-range regeneration protocol, and stage editing after creation (a mis-entered trip can be deleted and recreated in under a minute). Everything else — login, deployment, trip creation, days, items, the three statuses, the readiness counter, the outstanding filter — is the skeleton and none of it is optional. **The counter is explicitly not slippable**: the brief calls it "the main object of the product, not a badge in a corner", P1 *is* the counter, and a skeleton without it is a to-do list. It is therefore built in Phase 3 alongside items, not left to the end.

## 📝 Proposed Solution

A conventional three-tier slice with no cleverness anywhere, because the risk in this milestone is calendar risk (A05), not technical risk:

- A **FastAPI** service over **PostgreSQL** with **SQLAlchemy 2.0** and **Alembic** migrations, exposing a small JSON API under `/api/v1`, authenticated by an opaque server-side session in an `HttpOnly` cookie.
- A **React + TypeScript + Vite** single-page app with four routes, talking only to that API, translated by **react-i18next with ICU message formatting**.
- A **single container image** serving both the API and the built SPA behind TLS, so "deployed" in A05 means one artifact and one host.
- A first `item` migration that already carries a **time span**, and a first trip migration that already carries the **multi-stop shape** and the three-value **status**, so that none of the three becomes a migration later.

Alternatives considered and why they lost:

- **A server-rendered app (Jinja/HTMX) instead of an SPA.** Faster to the skeleton, and it would sidestep an entire build toolchain. Rejected because `AGENTS.md` fixes the stack as "a Python backend serving a React single-page frontend" — a repository convention that predates this spec and is not this document's to overturn.
- **SQLite instead of PostgreSQL.** Cheaper locally. Rejected because D14 puts the app on the public internet from day one; a deployment-grade database from the start avoids a dialect switch under time pressure, and the login-attempt table, the deferrable unique constraint and the functional index below all want real Postgres.
- **Two deployables (an API host and a static SPA host).** Rejected: one image with one origin removes CORS, removes a second TLS certificate, and makes the CSRF and cookie story trivial. At one user there is no scaling argument on the other side.
- **Storing the trip's route as a list of legs the way the design export's "Odcinki podróży (Loty / Transfery)" panel does.** Rejected: a leg is a transport *item* on a day, and the item model below carries a time span precisely so that a leg fits in it. Modelling legs twice — once as route structure, once as items — would create two sources of truth about the same journey.
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
    errors.py                  the ErrorCode enum — the single source of both locales' keys
    cli.py                     `create-owner` management command
  migrations/                  Alembic revisions
  tests/                       pytest
deploy/                        Dockerfile, compose file, release checklist
```

Boundaries that matter:

- **`domain/` is pure.** Day generation, the readiness arithmetic and stage-to-day resolution are functions over plain values with no database access, so each is unit-testable without fixtures and each has exactly one implementation.
- **The API is the fence; the SPA route guard is only UX.** Every trip-scoped route takes a `get_owned_trip(trip_id, session)` FastAPI dependency that resolves the trip **and** its owner in one place — URL nesting alone enforces nothing, and a handler that joins by hand can forget the owner clause. The Phase 1 route-enumeration test asserts every `/trips/…` route carries it.
- **The frontend never computes the readiness counter.** The server returns it alongside the timeline so that one implementation of R02 exists, in `domain/`, with tests.
- **Filtering happens in the browser.** The timeline payload is already fully in the client; filtering it server-side would add query parameters, a `422` path and an API test, and would turn "the counter must not move with the filter" from a non-issue into a server invariant. See A11.
- **No external calls at all.** No maps client, no geocoder, no LLM provider, no price feed (D04, R07). That removes the whole class of "what does the user see when the third party is down" failure modes from this milestone, which is why the Failure Scenarios section is about the database, the session and validation rather than about integrations.

### API versioning decision

`BACKWARD_COMPATIBILITY.md` records `Versioning: TODO — decide the strategy in the first API spec`. This is the first API spec, and it decides: **a URL version prefix, `/api/v1`**, with additive-only evolution inside a version. A version segment costs one path component today and is the only mechanism that lets a status code or an error code change without the expand/contract dance the compatibility table otherwise demands — cheap insurance for something reachable from the public internet. The implementation PR replaces that TODO line with this decision.

## 📝 Data Model

This is the section the milestone turns on: the shapes below are the ones that would be a migration rather than an addition if they are wrong.

### `owner`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `email` | TEXT NOT NULL | normalised to lower-case and trimmed **on write**, with a plain `UNIQUE` on the stored value plus a `UNIQUE INDEX ON lower(email)` as a belt-and-braces guard. The login lookup applies the identical normalisation |
| `password_hash` | TEXT NOT NULL | Argon2id via `argon2-cffi`; excluded from every response model, and the model's `__repr__` is overridden so it cannot reach a log line |
| `locale` | TEXT NOT NULL, `CHECK (locale IN ('pl','en'))`, default `'pl'` | the owner's UI language, so it survives a new browser (R01) |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

A real table with a real primary key even though D15 says there is exactly one user. That is not scope creep: "owner login" needs somewhere to put the hash, and a singleton row in a properly-shaped table is the cheapest thing that does not have to be migrated if D15 is ever revisited. What *is* out of scope is everything around it — no registration, no invitations, no roles, no password reset.

### `session`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `owner_id` | UUID FK → `owner.id`, `ON DELETE CASCADE`, indexed | |
| `token_hash` | TEXT NOT NULL, unique | SHA-256 of the opaque 256-bit token. The token itself exists only in the cookie; a database dump does not yield a usable session |
| `created_at`, `expires_at`, `last_seen_at` | TIMESTAMPTZ NOT NULL | 30-day absolute expiry, refreshed on use when more than a day old (a sliding window that does not write on every request) |

Logout deletes the row, which is the whole reason this table exists rather than a JWT. Expired rows are deleted lazily on lookup; no scheduler in this milestone.

### `login_attempt`

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL pk | |
| `email_normalised` | TEXT NOT NULL, indexed | |
| `source_ip` | INET NOT NULL, indexed | |
| `attempted_at` | TIMESTAMPTZ NOT NULL, indexed | |

The rate limiter's storage. It lives in Postgres rather than in a process-local dictionary because a public deployment (D14) runs more than one worker and an in-process counter would be decorative. Rows older than the window are deleted on each check; there is already a database and there is no Redis in the stack.

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

**The open-jaw question, answered by two nullable-aware text columns rather than by structure.** R03 requires that a trip "may return from a different place than it departed", and D06 requires that the model carry this from the first migration. The design export's own control offers three route modes — *W obie strony*, *Inne miasto powrotu (Open-jaw / Multi-city)*, *W jedną stronę* — and those fall out of these two columns with no discriminator column and no second table:

| Route mode in the UI | Stored as |
|---|---|
| Round trip (*W obie strony*) | `return_place` equals `departure_place` after normalisation |
| Open-jaw (*Inne miasto powrotu*) | `return_place` differs from `departure_place` |
| One-way (*W jedną stronę*) | `return_place IS NULL` |

**The mode-stability rule, which the shape alone does not give you.** Because the mode is *derived* from string comparison, it can drift: `"Warszawa"` and `"Warszawa "` are different strings, and the English UI's `"Warsaw"` is a third. Two rules close that: comparison is on the trimmed, case-folded value; and when a trip is in round-trip mode and `departure_place` is edited, the server rewrites `return_place` to match in the same transaction. Without the second rule, correcting a typo in the departure city silently converts a round trip into an open-jaw one.

Places are **free text**, not references to a places table: D04 rules out live lookups, so any structured place entity would be a guess about a schema we cannot populate. Adding a nullable `departure_place_id` beside the text later is an addition; inventing the wrong place entity now would be a migration.

### `trip_stage` — a base (etap)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_id` | UUID FK → `trip.id`, `ON DELETE CASCADE`, indexed | |
| `position` | INTEGER NOT NULL | 0-based display order; `UNIQUE (trip_id, position) DEFERRABLE INITIALLY DEFERRED` so a multi-statement reorder does not violate it mid-transaction |
| `place` | TEXT NOT NULL | free text, e.g. "Kuala Lumpur" |
| `start_date`, `end_date` | DATE NULL | inclusive when present; `CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)` |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

A trip has **one or more** stages (R03). Stage dates are **nullable**, because R03 asks the creation form for "dates, a starting point and one or more destinations" — the trip's dates, not a date range per stage — and a traveller who knows "Kuala Lumpur, Penang, Langkawi" but has not yet decided how to split fourteen days must still be able to create the trip. A stage without dates contributes no label to any day; those days simply render without one, which is a state the timeline already has to handle.

Stage ranges, when present, must lie inside the trip's range, and **stages may share boundary dates**: the design export's own example does exactly that — *Etap: Delhi (10.11 – 13.11)* and *Etap: Agra & Jaipur (13.11 – 17.11)* both contain the 13th, because the 13th is the travel day between them. There is therefore deliberately **no non-overlap constraint**. A day resolves to *any number* of stages, ordered by `position`; the label is those places joined with `→`, truncated after two with a `+n` count.

### `trip_day`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_id` | UUID FK → `trip.id`, `ON DELETE CASCADE` | |
| `date` | DATE NOT NULL | `UNIQUE (trip_id, date)` |
| `created_at` | TIMESTAMPTZ | |

Rows are generated for every date from `start_date` to `end_date` inclusive when the trip is created — this *is* the "create an empty timeline" action. **`trip_day` deliberately carries no `stage_id`.** The stage or stages covering a day are derived by date containment in `domain/`, because a stored foreign key would have to be re-maintained on every stage date edit and could silently contradict the stage's own dates — the "changing what it means while keeping its name" failure `BACKWARD_COMPATIBILITY.md` calls the worst kind. Derivation is a pure function that cannot drift, and adding a denormalised `stage_id` later, if query cost ever justifies it, is an addition.

### `item`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_day_id` | UUID FK → `trip_day.id`, `ON DELETE CASCADE`, indexed | the item's **start** day; an item belongs to a day, never directly to a stage |
| `position` | INTEGER NOT NULL | assigned server-side as `max(position)+1` within the day on create; the tie-break for items with no time. Manual reordering is out of scope for this milestone |
| `kind` | TEXT NOT NULL, `CHECK (kind IN ('accommodation','transport','activity','meal','other'))` | |
| `status` | TEXT NOT NULL, `CHECK (status IN ('to_plan','to_book','done'))`, default `'to_plan'` | see below |
| `start_time` | TIME NULL | local wall-clock; NULL means "sometime that day" |
| `end_time` | TIME NULL | local wall-clock |
| `end_date` | DATE NULL | NULL means the item ends on its start day |
| `title` | TEXT NOT NULL | short label, e.g. "Nocleg: Memmo Alfama" |
| `notes` | TEXT NULL | free text, the item's description |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

**The status field, answered by a check-constrained text column with English identifiers.** R02 and D05 fix exactly three statuses. Two sub-decisions:

1. **English identifiers in the database and on the wire; Polish and English labels in the locale files.** `to_plan` / `to_book` / `done` are the stored values; *do zaplanowania* / *do zarezerwowania* / *gotowe* and *to plan* / *to book* / *done* are translation keys. R09 is explicit that code is English and only the interface is bilingual, and storing a Polish string as an enum value would make the English UI a translation of the database instead of a translation of the product.
2. **A `CHECK`-constrained `TEXT` column, not a PostgreSQL `ENUM` type.** R02 is active until 2026-12-31 and a superseding decision row is the documented way to change it; if that ever happens, altering a check constraint is an ordinary migration, whereas altering a native enum type is the awkward one. Identical to use, cheaper to revise.

**The time span, and why it is in the first `item` migration.** An item with only a `start_time` cannot express the single most common transport item on the owner's own Malaysia trip: a long-haul flight leaving Warsaw at 23:50 on the 10th and landing in Kuala Lumpur at 14:00 on the 11th. Nor can it express three nights in one hotel. Without a span the user must split such an item in two, and the two halves then count as **two** entries in the readiness arithmetic — so the shape of the item silently changes the number the whole product exists to show. Nullable `end_time` and `end_date` cost nothing now; adding a second day pointer later to a table already full of split-in-two flights is a backfill nobody can perform correctly. This is the third migration-class risk, alongside the multi-stop shape and the status, and it is the one the first draft of this spec missed.

Rules for the span: `end_date`, when present, must be `>= ` the start day's date and `<=` the trip's `end_date`; when `end_date` is NULL and both times are present, `end_time >= start_time`. Both are enforced in `domain/` and returned as `422 invalid_time_span`. The item is rendered once, on its start day, with an "→ 11.10" marker when it ends later; it is **counted once** in the readiness arithmetic.

**No `cost`, no `currency`, no `confirmation_number`, no attachment relation.** Not because R04 forbids them — R04 says the opposite, that this data is kept when it arrives — but because it arrives *with an attachment*, and attachments are cut from this milestone under A05. Adding nullable columns for data nothing here can populate would be inventory nobody updates.

### The readiness counter (R02) — arithmetic, stated once

For a trip, over its items:

```
arranged = count(status = 'done')
tracked  = count(status IN ('to_book', 'done'))
```

Items still `to_plan` are outside **both** halves of the fraction — that is what the brief's glossary means by "items still *do zaplanowania* stay out of the arithmetic", and it is why the counter cannot be read as "done out of everything".

**The field is called `tracked`, not `total`.** Every consumer — the frontend, a later export, the next agent — will read `total` as *the number of items*, which it is not. `BACKWARD_COMPATIBILITY.md` names "changing what it means while keeping its name" as the worst class of break, and a field that starts out misnamed has already made it. The payload is `{"arranged": n, "tracked": m}`.

Copy, in one place so it cannot be specified twice: when `tracked > 0` the counter reads `"{arranged} of {tracked} arranged"` / `"{arranged} z {tracked} załatwionych"`. When `tracked = 0` — whether the trip has no items at all or has ten items all still *do zaplanowania* — it renders **"nothing arranged yet"** / **"nic jeszcze nie załatwione"**, with no fraction, no percentage and no progress bar: the percentage is undefined, and a "0%" would read as failure where the honest reading is "you have not decided anything yet". The same rule applies to the counter shown on each row of the trip list.

### Relationship summary

```
owner 1─n session, login_attempt
owner 1─n trip 1─n trip_stage          (ordered bases; dates optional; ranges may share boundary days)
             1─n trip_day 1─n item     (days generated from the range; items live on their start day, may span into later days)
             stage ↔ day: derived by date containment, never stored
```

### Migrations

There is **one Alembic revision per phase**, in the same PR as the code that needs it, each with a working `downgrade`: an empty baseline (Phase 0), `owner` + `session` + `login_attempt` (Phase 1), `trip` + `trip_stage` + `trip_day` (Phase 2), `item` (Phase 3). Phase 4 adds no tables. No phase alters a column an earlier phase shipped, which is what makes the phase-by-phase rollback story below true. The "safe against rows that already exist" rule in `BACKWARD_COMPATIBILITY.md` is vacuous for all four, since each creates tables that did not exist.

## 📝 API Contracts

JSON over HTTPS, all under `/api/v1`, all cookie-authenticated except `POST /auth/login`. Request bodies are validated by Pydantic v2 models at the boundary — this resolves the `AGENTS.md` row "TODO: name the validation library once chosen", and the implementation PR fills that row in.

Conventions: dates are ISO `YYYY-MM-DD`, times are ISO `HH:MM` local wall-clock with **no** timezone (see Edge Cases), unknown request fields are rejected, and errors are `{"error": {"code": "<stable_code>", "field": "<name|null>"}}` — a **stable machine-readable code**, never a prose message.

**The error codes are an enum, not a convention.** They live in `backend/trip_planner/errors.py` as a Python enum, are emitted as a generated TypeScript union the SPA imports, and a test asserts that **every member resolves to a non-empty key in both `en.json` and `pl.json`**. `scripts/check_locales.py` checks that the two locales agree with each other; it cannot check that a key the code needs actually exists, so a forgotten mapping would ship as a blank message in both languages and pass the gate green. That test is the missing half of R01 for backend-originated errors, and it is why this milestone needs no `backend/trip_planner/locales/` root at all.

### Authentication

| Method | Path | Body / Response | Notes |
|---|---|---|---|
| `POST` | `/auth/login` | `{email, password}` → `204` + `Set-Cookie: session=…` + CSRF cookie | `401 invalid_credentials` for both a wrong password and an unknown e-mail — identical status, body and headers, no user enumeration |
| `POST` | `/auth/logout` | → `204` | deletes the session row; idempotent |
| `GET` | `/auth/me` | → `{id, email, locale}` | `401` when there is no valid session |
| `PATCH` | `/auth/me` | `{locale}` → `{id, email, locale}` | the only mutable field. Cost stated plainly: at one user with one browser, `localStorage` alone would do, and this endpoint plus its CSRF path and tests is roughly half a day. It is kept because a locale that resets on every new browser is exactly the kind of paper cut that makes an owner stop using his own tool |

No registration, no password reset, no invitations. The single owner account is created by a management command:

```
uv run trip-planner create-owner --email <address>     # password read from stdin, never from argv
```

The recovery path for a forgotten password is re-running that command on the server. That is honest at one user and must not be quietly relied on at two.

### Trips

| Method | Path | Notes |
|---|---|---|
| `GET` | `/trips` | the owner's trips: `{id, title, start_date, end_date, departure_place, return_place, readiness:{arranged,tracked}}` |
| `POST` | `/trips` | `{title, start_date, end_date, departure_place, return_place?, stages:[{place, start_date?, end_date?}]}` → `201` with the full trip **and its generated days**. This single call is the design export's "Utwórz pustą oś czasu do ręcznego planowania". At least one stage is required (R03) |
| `GET` | `/trips/{tripId}` | the timeline payload: trip, ordered stages, ordered days each with its derived `stage_ids` and its items, and `readiness`. The `items` array arrives in Phase 3; in Phase 2 the field is present and always empty |
| `PATCH` | `/trips/{tripId}` | title, dates, departure/return place, subject to the mode-stability rule and the range rules below |
| `DELETE` | `/trips/{tripId}` | cascades to stages, days and items |

### Stages, days, items

| Method | Path | Notes |
|---|---|---|
| `POST` / `PATCH` / `DELETE` | `/trips/{tripId}/stages[/{stageId}]` | `position` is reassigned server-side to stay dense, in a single statement under the deferred unique constraint |
| `GET` | `/trips/{tripId}/days/{date}` | the day detail payload: the day, its derived stages, its ordered items, and prev/next dates for the day navigator |
| `POST` | `/trips/{tripId}/days/{date}/items` | `{kind, status?, start_time?, end_time?, end_date?, title, notes?}` → `201`; `status` defaults to `to_plan`, `position` is assigned server-side |
| `PATCH` | `/trips/{tripId}/items/{itemId}` | any item field, plus `date` to move the item to another day **of the same trip** |
| `DELETE` | `/trips/{tripId}/items/{itemId}` | |

Every path is nested under `/trips/{tripId}` and every handler takes the `get_owned_trip` dependency; the nesting is for readability, the dependency is the enforcement. A trip belonging to a different owner answers **`404`, not `403`** — a `403` would confirm the resource exists.

There are **no filter query parameters**. The timeline payload is complete and the SPA filters it (A11).

## 📝 UI/UX

Four routes. The design export is the visual reference for three of them; each is listed with what is adapted and what is dropped, because the export was drawn for a product with an assistant, prices and documents in it.

Mockups of the proposed screens live beside this spec and are attached to this spec's PR. They are illustrative statics — layout and flow, not pixel-perfect design — rendered from self-contained HTML with no application code behind them. There are **no current-state screenshots**: the repository contains no product code yet, so there is no running application to photograph.

| Screen | Mockup |
|---|---|
| `/trips/new` — the multi-stop creator, Polish locale | [`assets/walking-skeleton/mockup-01-trip-creator.png`](assets/walking-skeleton/mockup-01-trip-creator.png) |
| `/trips/:id` — the timeline, the counter and the filter bar, Polish locale | [`assets/walking-skeleton/mockup-02-timeline.png`](assets/walking-skeleton/mockup-02-timeline.png) |
| `/trips/:id/days/:date` — the day detail and the item editor, **English locale** | [`assets/walking-skeleton/mockup-03-day-detail.png`](assets/walking-skeleton/mockup-03-day-detail.png) |

Two of the three are rendered in Polish and one in English on purpose: R01 makes both locales first-class, and a spec that only ever pictures one of them is not showing the product it describes. `/login` has no mockup — it is a two-field form, and standard CRUD does not earn a picture.

### `/login`

E-mail, password, submit, a locale switch, and nothing else. No "remember me", no "forgot password", no sign-up link — none of those exist behind the API. On `401` the form shows one generic message in the active locale. This is the only unauthenticated route; every other route redirects here, preserving the intended path so that login lands the user where they were going.

### `/trips` — trip list

A list of the owner's trips, each row showing the title, the date range, the route summary (`Warszawa → Kuala Lumpur → Katowice`) and the readiness counter with its zero state. A "New trip" action, and an empty state for a first-time account. This screen is not in the design export; it is the smallest thing that makes more than one trip navigable, and it is otherwise standard CRUD.

### `/trips/new` — the multi-stop creator

Adapted from `kreator_podr_y_manualny_i_wieloodcinkowy`:

- **Kept:** the route-mode toggle (*W obie strony* / *Inne miasto powrotu (Open-jaw)* / *W jedną stronę*), which writes exactly the three `return_place` states in the data model; the trip date range; the ordered list of stages, each with a place and an **optional** date range, add and remove; the live summary panel ("15 dni / 14 n. · 3 bazy"); and the primary action **"Utwórz pustą oś czasu do ręcznego planowania"** — the button this whole screen exists to deliver.
- **Dropped:** the "Kreator manualny / Tryb sugestii AI / Import rezerwacji" mode tabs and "Wypełnij pusty harmonogram z sugestiami AI" (A05 cut — chat and the assistant go first); the "Odcinki podróży (Loty / Transfery)" leg editor with its flight numbers (a leg is a transport item, and the item now carries a time span so it fits); the PNR / e-ticket dropzone (attachments, A05 cut); the "Budżet i koszty manualne" panel (downstream of attachments); the "Potrzebujesz pomocy AI?" card.
- **States:** the primary action is disabled until the trip has a title, a valid range and at least one stage; validation errors appear against the field that caused them; a stage range outside the trip range is refused inline before the request is sent, and again by the server.

### `/trips/:id` — the timeline

Adapted from `g_wny_pulpit_i_o_czasu`, which is the screen the counter lives on:

- **Kept:** the trip header with title, date range and route summary; the **readiness counter** occupying the export's "STATUS LOGISTYKI" tile; the filter bar as *All* / *Only outstanding* / one chip per item type, in the position of "Wszystko (11) · Noclegi (3) · Transport (4) · Atrakcje i Jedzenie (4) · Tylko do zrobienia (3)"; the vertical day-by-day timeline with a date chip per day and a card per item; the per-item status chip; the item's time, type icon, title and notes.
- **The tile's layout is adopted; its arithmetic is not.** The export's own numbers give it away: its filter bar sums to 3+4+4 = 11 and its counter reads "7 z 11", so the export's denominator is the *all-items* count — which includes *do zaplanowania* and therefore contradicts R02. Its "Tylko do zrobienia (3)" is likewise inconsistent with the outstanding filter defined below. We take the shape and not the sums.
- **Dropped:** the entire "VoyageAI Concierge" drawer and every AI card in it (A05 cut, chat first); the PLN/EUR toggle, the "SZACOWANY BUDŻET" tile and all per-item prices (downstream of attachments; brief Q04 open); "Eksportuj PDF" (D12, *Later*) and "Udostępnij" (A05 cut — the link's shape is fixed by D08/D09 for a later spec); reservation codes, "Opłacono z góry", "Zarezerwuj przez AI" and "Kup bilety online" (D04, R07 — a real exclusion); ticket-PDF pills and photo cards (attachments); the per-day weather strip (D12).
- **The filter's exact meaning:** *Only outstanding* is `status ≠ done` — both *do zaplanowania* and *do zarezerwowania* — because it answers "what do I still have to touch", a different and equally useful question from the one the counter answers. It is applied in the browser and reflected in the URL; the counter never changes when it is applied.
- **Empty states:** a trip whose days are all empty shows the days with an invitation to add the first item, not a blank page; that empty timeline is the deliverable of Phase 2 and must look deliberate.

### `/trips/:id/days/:date` — the day detail

Adapted from `szczeg_y_dnia_i_aktywno_ci`:

- **Kept:** the breadcrumb (Trips → trip → day), the day heading with its derived stage or stages, prev/next day navigation, the numbered ordered list of the day's items, and the item editor — type, start time, optional end time and end date, title, notes, status — as a dialog opened from an item or from "Add item", with save and delete.
- **Dropped:** the "Podgląd trasy" map with "Otwórz GPS" (D12); "Załączniki i dokumenty dnia" and "Dodaj plik / zdjęcie / bilet" (attachments, A05 cut); "Zadania & Przygotowanie" (brief Q02 undecided); the "Inteligentny Asystent Dnia" panel and "Sugerowana optymalizacja czasowa" (A05 cut); "Eksportuj do Google Calendar" and "Optymalizuj trasę z AI" (D12); per-item photos, ratings, prices, ticket numbers and vendor comparisons.
- **The status control is the point of this screen.** Moving an item to *gotowe* here is the action the counter on the timeline reacts to, and it is the brief's "arranging one item" flow with its attachment step removed.

### Cross-cutting UI rules

- **Bilingual, both first-class (R01).** Every string goes through i18next; the `<html lang>` attribute follows the active locale; dates, times and numbers are formatted through `Intl` with the active locale, never concatenated.
- **Status is never colour alone.** Each status chip renders its translated text node **and** a `data-status` attribute driving a distinct icon, so the three statuses are distinguishable to a colour-blind reader and assertable in a test. A chip that conveys status only through a CSS class fails that test.
- **Keyboard and focus.** The item editor is a focus-trapped dialog that returns focus to its trigger; the filter bar is a real radio group; day headings are real headings, so the page is navigable by landmark.
- **Unsaved input on session expiry.** When a `401` arrives while the item dialog is open, the draft is written to a module-scoped store keyed by item id before the router navigates to `/login`, and restored when the user returns; it is cleared on a successful save and on sign-out. Component state does not survive an unmount, so this needs a real mechanism or no promise at all.
- **Design tokens.** `modern_premium_travel_companion/DESIGN.md` supplies the palette, the Plus Jakarta Sans type scale, radii and spacing; those become CSS custom properties. The brand is **Smart Trip Planner** — the export's "VoyageAI" is dropped (D01).

## 📝 Edge Cases & Failure Scenarios

| Case | Behaviour |
|---|---|
| `end_date < start_date` on a trip or stage | `422 invalid_date_range`, refused client-side first |
| A stage range not contained in the trip range | `422 stage_outside_trip` naming the stage |
| A trip created with zero stages | `422 stages_required` — R03 says one or more |
| A stage with no dates | allowed; it labels no day |
| Trip range shortened so a day carrying items falls outside it | `409 days_have_items` listing the offending dates; **no item is ever destroyed by a date edit**. Days without items are removed silently |
| Trip range shortened so an existing stage falls outside it | `409 stages_outside_new_range` naming the stages — symmetric with the row above, and the case the first draft of this spec missed |
| Trip range extended | new `trip_day` rows are inserted; existing days and items untouched |
| Trip range longer than 366 days | `422 trip_too_long`. A bound exists so one bad date entry cannot generate unbounded rows |
| `departure_place` edited while the trip is in round-trip mode | `return_place` is rewritten to match, in the same transaction |
| Two or more stages covering the same day | allowed; label is the `→`-joined chain, truncated after two with `+n` |
| A day covered by no stage | allowed; rendered without a stage label — a day in transit |
| Item with no time | sorted after all timed items of that day, ordered among itself by `position`; rendered as "all day" |
| Item spanning into a later day | rendered once, on its start day, with an "→ dd.MM" marker; counted once |
| `end_date` beyond the trip's end, or `end_time` before `start_time` on a same-day item | `422 invalid_time_span` |
| Item `PATCH` with a `date` outside the trip's range or on a non-existent day | `422 date_outside_trip`. A cross-*trip* move is unreachable by construction — the trip id is in the path — so it is not a case, it is a `404` |
| `tracked = 0` for the counter | "nothing arranged yet"; no fraction, no percentage, no bar |
| Deleting a stage | days and items survive — days belong to the trip, not the stage. Only the derived label changes |
| Deleting a trip | cascades; a confirmation dialog naming the trip, since there is no undo in this milestone |
| Session expires mid-edit | `401`; the SPA saves the dialog draft to the module-scoped store and routes to `/login` with the return path |
| Repeated failed logins | rate-limited per normalised e-mail and per source address over a fixed window, counted in `login_attempt`. The response is byte-identical to an ordinary failure |
| Timing side channel on login | a fixed response floor (the handler waits until `t0 + 400 ms` before answering) rather than an attempt to equalise real work. Tested through an injected clock; wall-clock equality is not assertable without flakiness |
| A trip id belonging to nobody, or to another owner | `404`, identically |
| CSRF | unsafe methods require a double-submit token header matching a non-`HttpOnly` cookie; `SameSite=Lax` is the first line and this is the second (D14) |
| Database unavailable | `503 service_unavailable`; the SPA shows a retry state rather than an empty timeline — an empty timeline is indistinguishable from a real empty trip and would be a lie about the plan |

**Documented, not built in this milestone.** Two rows above describe behaviour that has no implementation step and must not be mistaken for one: **concurrent edits from two tabs** are last-write-wins (`updated_at` is returned but not enforced — at one user, D15, optimistic locking is machinery without a failure to prevent), and there is **no scheduled cleanup** of expired sessions or old login attempts (both are pruned lazily on access). Both are named here so the next agent finds a decision rather than a gap.

**Times and dates carry no timezone, deliberately.** A trip's days are calendar dates and an item's times are wall-clock at the place they happen; storing them as `DATE` and `TIME` and never converting is correct for a plan a human reads, and it removes any dependency on timezone data for places we do not resolve (D04). The cost is that the app cannot say "your flight leaves in 3 hours" — nothing in scope asks it to.

## 📝 Deployment (D14, and A05's "deployed")

A05's test says *deployed*, so a plan that ends at a passing test suite has not met it. The milestone ships:

- **One container image** built from `deploy/Dockerfile`: the SPA is built in a first stage and its static bundle is served by the FastAPI app from a single origin, which removes CORS, a second certificate and a second host.
- **A managed Postgres instance**, reachable only from the application, with `alembic upgrade head` run as a release step **before** the new image takes traffic.
- **TLS terminated at the platform's proxy**, HTTP redirected, HSTS on; the session cookie is `Secure`, which means it does not work over plain HTTP even by accident.
- **Environment variables, each required at startup with a fatal error naming it** — the `BACKWARD_COMPATIBILITY.md` §5 rule:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `SESSION_SECRET` | keys the session-token hash and the CSRF token |
| `APP_BASE_URL` | absolute URL, used for cookie domain and redirect validation |
| `ENVIRONMENT` | `production` / `development`; `production` refuses to start without TLS-implying config |

No secret is ever committed, logged, or echoed by the `create-owner` command. The verification for this phase is not a unit test: it is a real URL where `/api/v1/trips` answers `401` unauthenticated and `/login` answers `200`.

## 📝 Risks & Impact Review

- **Blast radius: none, and that is the point.** The repository has no product code, so this spec breaks nothing. It *creates* the surfaces `BACKWARD_COMPATIBILITY.md` lists as "not yet created" — the HTTP API and the database schema — and every one of its inventory rows starts applying the moment Phase 1 merges. The file's `Versioning: TODO` is resolved above; its §5 environment-variable rule is satisfied by the deployment section.
- **Three migration-class risks, all designed for the cheaper failure**: the multi-stop shape (text places rather than a guessed place entity; derived rather than stored day-to-stage links), the status (a check constraint rather than a native enum), and the item time span (nullable columns present from the first `item` migration rather than a later backfill across split-in-two flights). The first is gated on human confirmation (A2).
- **Rollback story.** Each phase is one Alembic revision with a working `downgrade`, and each leaves the application running. Rolling back Phase 4 leaves a usable timeline whose filter is gone; Phase 3, an empty timeline; Phase 2, a deployed login screen with nothing behind it. No phase alters a column another phase shipped, so no rollback leaves a half-migrated database.
- **Product-decision compliance, stated precisely.** This spec covers a **strict subset** of the brief's *Now* list. Chat (D03), the read-only magic link (D08, D09) and attachments (*Now* bullet 5, with cost data downstream of them under R04) **remain in scope for the first version** and are cut from *this milestone* under A05's own cut authority, to be covered by later specs. Nothing here contradicts an active Non-goal, Business rule or Decision, so no superseding row is required — but the difference between "deferred by A05" and "excluded by a decision" is exactly the difference `SDLC.md` treats as a review blocker, and the Scope table above keeps them apart.
- **Calendar risk is the real risk (A05)**, and the Slippable tail section names the cut line rather than leaving it to be discovered on 2026-09-14. The counter is deliberately *not* in that tail.
- **Security posture (D14).** Argon2id hashing, opaque server-side sessions with real revocation, `HttpOnly` + `Secure` + `SameSite=Lax` cookies, a CSRF double-submit token, database-backed login rate limiting that survives multiple workers, no user enumeration, a fixed response floor against timing analysis, `404` rather than `403` for other owners' resources, an ownership dependency every trip-scoped route takes, and no secret in any log line or error body.
- **What this spec does not protect against.** A03 — that a hand-maintained plan stays current enough to be trusted — is untestable before the app exists and is not addressed by any decision here. The counter is only as true as the statuses the owner sets.

## 📝 Internationalisation — the library, chosen and justified

**The choice is `react-i18next` (with `i18next` and `i18next-icu`), and the deciding factor is how it interacts with `scripts/check_locales.py`.** That gate flattens every locale file to dotted leaf keys and fails when Polish carries a key English does not define — which is exactly what i18next's *default* suffix pluralisation produces, because Polish resolves to four CLDR plural categories (`one`, `few`, `many`, `other`) against English's two: a pluralised string ships as `key_one`/`key_other` in `en.json` and `key_one`/`key_few`/`key_many`/`key_other` in `pl.json`, and the gate's `extra`-key branch turns red on the first one. Adding `i18next-icu` moves the plural selection *inside* a single key's value as an ICU `{count, plural, …}` expression, so both files keep identical key sets and the gate passes unmodified. Everything else follows: plain JSON in exactly the `en.json` / `pl.json` layout the gate already supports, no extraction or compile step between adding a key and running the gate, a `Trans` component for strings with markup in the middle, `Intl`-backed date and number formatting through the same formatter so R01's extension to dates and numbers is satisfied by one mechanism, and language detection with persistence. The alternatives lose on the same axis: **FormatJS / react-intl** has first-class ICU but keeps messages in compiled, id-keyed build artifacts, which is friction against a gate that reads the source JSON; **Lingui** is also ICU-based and excellent, but its macro-and-compile pipeline is more machinery than a two-locale personal application needs before 2026-09-15; and a **hand-rolled context** is the smallest thing that works right up to the first Polish plural and the first locale-formatted date.

Two honest qualifications, so the argument is not overstated. ICU is not the *only* way to keep the two files key-identical — one could carry the four suffixed keys in `en.json` unused, or format plurals through `Intl.PluralRules` in a custom formatter, or write copy that avoids counted nouns. And editing the gate is not forbidden: R01's own **Required path to change** is "Change `AGENTS.md` and the gate in the same PR". ICU wins on merit — one key per string, plural rules that live with the translation rather than in the key namespace, and date/number formatting through the same formatter — not on necessity.

**The proving string is a counted noun that actually inflects.** The counter's own copy (`"{arranged} z {tracked} załatwionych"`) has no counted noun in it, and "pozycji" happens to be invariant in the genitive plural, so neither would exercise the problem. The stage and night counts do: *1 etap / 2 etapy / 5 etapów*, *1 noc / 2 noce / 5 nocy*. Phase 0's proving key is therefore the stage count on the creator's summary panel — `{count, plural, one {# etap} few {# etapy} many {# etapów} other {# etapu}}` — with a test asserting the `few` and `many` forms render.

The implementation PR replaces the `i18n | TODO — library not yet chosen` row in `AGENTS.md` with this decision, in the same PR that introduces the dependency.

## 📝 Decisions in play

| Id | How this spec relies on it |
|---|---|
| R01 / R09 | Both locales first-class from the first commit; ICU pluralisation so the parity gate passes unmodified; an error-code enum test closing the gap the gate cannot see; code, spec and PR bodies English |
| R02 / D05 | Exactly three statuses; `arranged = done`, `tracked = to_book + done`; `to_plan` outside the arithmetic; the constraint makes it structural |
| R03 / D06 | Multi-stop and a differing return point in the first migration; stage dates optional, as R03's "dates" are the trip's |
| D04 / R07 | No external calls, no live prices, no booking — a genuine exclusion from the first version |
| R04 / D07 | Cost data is *kept when it arrives with an attachment*; attachments are cut from this milestone under A05, so cost data has nothing to attach to yet — **not a deferral of R04** |
| R08 / D11 / D14 | E-mail-and-password owner login; nothing showing a plan reachable without a session; deployed publicly with the security posture above |
| R06 / D09 | One editor per trip — no co-editing, no permissions model |
| D08 / D09 | Fix the *shape* of sharing for the later spec; the feature itself is cut here under A05, not deferred by these rows |
| D03 | Fixes chat's role as an editing surface for the later spec; chat is cut here by A05, which names it first |
| D01 | The product is Smart Trip Planner; the export's "VoyageAI" brand is dropped |
| D15 | One owner; a real `owner` table but no registration, roles or invitations |
| D12 / N01 | Everything above is deferred, never excluded |
| A05 | **The authority for every cut in this milestone**, and the source of the Slippable tail |
| Brief Q05 | Answered by this spec (the brief assigns it to the first frontend PR) |
| Brief Q01, Q02, Q03, Q04 | Left open; the features they concern are out of this milestone |

**Nothing in this spec proposes to supersede an active entry.** The approval it needs is on its autonomous assumptions below.

## ⚠️ Resolved assumptions (autonomous defaults)

This spec was written in `--autonomous` mode. Each question below was resolved by the most reversible, smallest-scope answer available, and each is open to override before merge.

| # | Question | Resolved as | Rationale |
|---|---|---|---|
| A1 | Should this milestone be one spec or several? | **One spec, five phases** | The phases *are* sequentially deployable — Phase 0+1 alone is a shippable artifact — so this is not a claim that they cannot be split. It is a claim that they are one milestone with one approval decision: A05 names them as a single test, and reviewing the data model, the auth model and the counter against each other is the point. The cost is real and stated: the one gated decision (A2) arrives inside a long document, which is why the assumptions comment on the PR carries it separately |
| A2 | How is the multi-stop shape stored, so that R03 and D06 are satisfied from the first migration? | **`trip.departure_place` + nullable `trip.return_place` + an ordered `trip_stage` table with optional dates; day-to-stage derived by date containment, never stored; places as free text** — ⚠ **NEEDS HUMAN CONFIRMATION** | The three route modes fall out with no discriminator column, boundary-sharing travel days are expressible, and every deferred refinement (a place entity, a stored `stage_id`) is an addition. Marked for confirmation because the owner named this the one thing that would be a migration if wrong, and no brief decision fixes the shape below the level of R03 |
| A3 | Native `ENUM` or a `CHECK`-constrained `TEXT` column for `item.status`, and in which language are the values stored? | **`CHECK`-constrained `TEXT`, values `to_plan` / `to_book` / `done`** | R09 puts code in English and only the UI in Polish; a check constraint is an ordinary migration to change, a native enum type is not |
| A4 | Can an item span more than one day? | **Yes — nullable `end_time` and `end_date` in the first `item` migration** — ⚠ **NEEDS HUMAN CONFIRMATION** | Without a span, an overnight flight must be split in two and then counts twice in the readiness arithmetic, so the item's shape changes the number the product exists to show. Marked for confirmation because it is the same migration class as A2: nullable columns are free now, a backfill across already-split items later is not |
| A5 | What exactly does "filter down to what is still left" show? | **`status ≠ done` — both *do zaplanowania* and *do zarezerwowania*** | The counter answers "how much of what I decided is booked"; the filter answers the different question "what do I still have to touch" |
| A6 | Which i18n library? (brief Q05) | **`react-i18next` + `i18next-icu`** | One key per string across Polish's four plural categories, so the parity gate passes unmodified; see the internationalisation section, including its two qualifications |
| A7 | Which backend framework, ORM and database? | **FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic + PostgreSQL** | Mainstream, `uv`-installable, and Pydantic fills the `AGENTS.md` "validation library — TODO" row. Postgres over SQLite because D14 deploys publicly from day one, and the rate limiter, the deferrable constraint and the functional index all want it |
| A8 | How is the owner session carried? | **Opaque server-side session token in an `HttpOnly` + `Secure` + `SameSite=Lax` cookie, with a CSRF double-submit token** | Logout must genuinely revoke; there is no second service to federate to |
| A9 | How does the owner account come to exist? | **Provisioned by a `create-owner` command; no registration, no password reset** | D15 says one user, and a public sign-up form on an internet-facing app is attack surface serving nobody. Adding registration later is an endpoint; removing one after it has been reachable is not |
| A10 | What happens to items and stages on days a shortened trip range would delete? | **`409` naming them; the owner moves or deletes them first. A date edit never destroys data** | Data loss is a blocker finding under `BACKWARD_COMPATIBILITY.md` |
| A11 | Server-side or client-side filtering of the timeline? | **Client-side; no filter query parameters** | The payload is already fully in the browser. Server-side filtering would add parameters, a `422` path and an API test, and would turn "the counter must not move with the filter" into a server invariant instead of a non-issue |
| A12 | What does "deployed" in A05 concretely mean? | **One container image serving API + SPA from one origin, managed Postgres, migrations as a release step, TLS at the proxy, four required environment variables** | The smallest thing that satisfies D14 and `BACKWARD_COMPATIBILITY.md` §5. Splitting into two deployables is an addition later; merging two into one after the fact is not |
| A13 | API versioning strategy (the `BACKWARD_COMPATIBILITY.md` TODO) | **`/api/v1` prefix, additive-only within a version** | One path component, and the only mechanism that lets an error or status code change later without the expand/contract dance |

## 📋 Phasing

Each phase is independently shippable and leaves the application working and deployed.

- **Phase 0 — Foundation and a green gate.** The repository builds, tests and lints itself, in both locales.
- **Phase 1 — Owner authentication and deployment.** The application is *actually deployed* to the public internet with nothing reachable behind the login (R08, D14). This is the phase that makes every later phase safe to ship, and A05's "deployed" is met here rather than assumed.
- **Phase 2 — Trip creation and the empty timeline.** A multi-stop trip exists, with its days (R03, D06).
- **Phase 3 — Items, statuses and the readiness counter.** The plan can be filled in by hand and the product answers its central question (D05, R02, P1). The counter ships here, not last, because it is the main object of the product.
- **Phase 4 — The filter and the trip-management tail.** The outstanding filter, the per-type chips, trip edit and delete, stage editing. This is the slippable phase.

## 📋 Implementation Plan

Every step is testable and leaves the application working. This structure is what `om-auto-implement-spec` hands to `om-auto-create-pr`.

### Phase 0 — Foundation and a green gate

1. Scaffold `backend/` as a `uv` project: `pyproject.toml`, `uv.lock`, `ruff` config, a `pytest` suite with one passing smoke test, and a FastAPI app exposing `GET /api/v1/health`. Verify: `(cd backend && uv run ruff check .)` and `(cd backend && uv run pytest)` pass.
2. Scaffold `frontend/` as a Vite + React + TypeScript project with strict mode, Vitest, and one passing smoke test. Verify: `npm run typecheck`, `npm run test -- --run` and `npm run build` pass.
3. Add `react-i18next`, `i18next` and `i18next-icu`; create `frontend/src/locales/en.json` and `pl.json`; wire the provider, the `<html lang>` binding and the locale switch. Include the stage-count ICU plural key as the proving string. Verify: `python3 scripts/check_locales.py` reports both locales in sync, and a test asserts the Polish `few` (2 etapy) and `many` (5 etapów) forms render.
4. Add PostgreSQL, SQLAlchemy 2.0 and Alembic with an empty baseline revision, plus a pytest fixture that migrates a throwaway database per session. Verify: `alembic upgrade head` and `downgrade base` both succeed in a test.
5. Replace the resolved TODOs in `AGENTS.md` and `BACKWARD_COMPATIBILITY.md`. Verify: a test asserts the exact strings `i18n | TODO`, `TODO: name the validation library` and `**Versioning:** TODO` are absent from those files.
6. Add the GitHub Actions workflow running the six validation-gate commands in the order `.ai/agentic.config.json` lists them. Verify: the workflow is green on the PR.

### Phase 1 — Owner authentication and deployment (R08, D11, D14)

1. Migration and models for `owner`, `session` and `login_attempt`, including the `lower(email)` unique index. Verify: upgrade/downgrade round-trip test, and a test that two e-mails differing only in case collide.
2. `security/`: Argon2id hash and verify via `argon2-cffi`; opaque 256-bit token generation; constant-time comparison against the stored hash. Verify: unit tests, including that the hash never appears in the model's `repr` or in a response model.
3. `errors.py` with the `ErrorCode` enum and its generated TypeScript union. Verify: the test that every member resolves to a non-empty key in both `en.json` and `pl.json` — the check `check_locales.py` structurally cannot make.
4. `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/me` with the cookie and CSRF handling. Verify: tests for success; for wrong password and unknown e-mail returning **identical status, body and headers**; for a missing CSRF token on an unsafe method; and for logout actually invalidating the token.
5. Database-backed login rate limiting plus the fixed response floor. Verify: a test that the limiter engages after the configured attempts, that its response is byte-identical to an ordinary failure, and — through an injected clock, not wall-clock measurement — that the handler waits until the floor before answering.
6. The `get_current_session` dependency applied to every non-auth route by default rather than opted into per route, and `get_owned_trip` for trip-scoped routes. Verify: a test that enumerates the application's routes and asserts each is either in the public allow-list or carries `get_current_session`, and that every `/trips/…` route carries `get_owned_trip`. This is the test that keeps R08 true as routes are added.
7. `trip-planner create-owner` reading the password from stdin. Verify: a test that the password appears in neither `sys.argv` nor the command's output.
8. The `/login` screen, the session context, the route guard, the redirect-with-return-path and the module-scoped draft store. Verify: component tests for the guard redirecting, for the error message rendering in both locales, and for a draft surviving a `401` round trip.
9. `deploy/Dockerfile` (SPA build stage → FastAPI serving the bundle), the compose file, the startup check that fails fatally naming any missing environment variable, and the release step running `alembic upgrade head` before traffic. Verify: a test that startup aborts with the variable's name when it is unset; then the **deployment itself** — a real URL where `/api/v1/trips` answers `401` and `/login` answers `200` over TLS, recorded on the PR.

### Phase 2 — Trip creation and the empty timeline (R03, D06)

1. Migration and models for `trip`, `trip_stage` and `trip_day` with every `CHECK` and `UNIQUE` constraint, including the deferrable one. Verify: tests that the database itself rejects an inverted date range and a duplicate `(trip_id, date)`.
2. `domain/days.py`: `generate_days(start, end)`, inclusive, bounded at 366. Verify: unit tests for a one-day trip, a leap-day span, and the bound.
3. `domain/stages.py`: `stages_for_day(stages, date)` returning a list of any length ordered by `position`, and the `→`-joined label truncated after two with `+n`. Verify: unit tests for a travel day shared by two stages, three stages sharing a date, a stage with no dates, and a day in no stage.
4. `POST /trips` creating trip, stages and days in one transaction; `GET /trips`; `GET /trips/{id}` returning the timeline payload with derived `stage_ids` and an always-empty `items` array. Verify: tests for the three route modes, for `stages_required`, for `stage_outside_trip`, for stages without dates, and that another owner's trip answers `404`.
5. The `/trips` list screen and the `/trips/new` creator, including the route-mode toggle and inline validation. Verify: component tests for each route mode producing the right request body, and for the primary action staying disabled until the form is valid.
6. The `/trips/:id` timeline rendering days with their stage labels and a deliberate empty state. Verify: a component test that a trip with no items renders every day and the empty-state copy in both locales.

### Phase 3 — Items, statuses and the readiness counter (D05, R02, P1)

1. Migration and model for `item` with both `CHECK` constraints and the nullable span columns. Verify: a test that the database rejects a fourth status value — the constraint that makes R02 structural rather than conventional.
2. `domain/items.py` span validation, and `domain/readiness.py`: `readiness(items) -> (arranged, tracked)` with `to_plan` excluded from both. Verify: unit tests for all-`to_plan` returning `(0, 0)`, the mixed case, the empty case, and a spanning item counted once.
3. `GET /trips/{id}/days/{date}` with prev/next dates. Verify: tests for the first and last day of a trip, and for a date outside the trip answering `404`.
4. Item `POST`, `PATCH` (including `date` to move between days) and `DELETE`, with server-assigned `position` and the ordering rule. Verify: tests for the default status, untimed items sorting last, `invalid_time_span`, and `422 date_outside_trip`.
5. `readiness` on the `GET /trips` and `GET /trips/{id}` payloads, as `{arranged, tracked}`. Verify: an API test that the figure matches the domain function.
6. The `/trips/:id/days/:date` screen: the ordered item list, day navigation, and the item editor dialog with type, times, title, notes and status. Verify: component tests for creating, editing and deleting an item, and for focus returning to the trigger when the dialog closes.
7. Status chips rendering a translated text node and a `data-status` attribute. Verify: a test asserting the three translated labels exist in both locale files and that no status is conveyed by a CSS class alone.
8. Items on the timeline's day cards, spanning items marked "→ dd.MM", and the counter tile with its `tracked = 0` copy on both the timeline and the trip list. Verify: component tests for the fraction, for the zero state in both locales, and that an item created in the day detail appears on the timeline.

### Phase 4 — The filter and the trip-management tail (the slippable phase)

1. The filter bar as a radio group — *All* / *Only outstanding* — filtering client-side and reflected in the URL. Verify: component tests that switching the filter changes the item list and leaves the counter untouched.
2. The per-type chips with their counts. Verify: a component test that the counts sum to the item total.
3. `PATCH /trips/{id}` with the date-range regeneration rules and the round-trip mode-stability rule. Verify: tests that extending adds days; that shortening past a day with items answers `409 days_have_items` and changes nothing; that shortening past a stage answers `409 stages_outside_new_range`; that shortening past an empty day removes it; and that editing `departure_place` in round-trip mode rewrites `return_place`.
4. `DELETE /trips/{id}` and its confirmation dialog. Verify: a test that the cascade removes stages, days and items, and none of another trip's.
5. Stage `POST`/`PATCH`/`DELETE` with dense `position` reassignment in a single statement. Verify: tests that positions stay dense after a delete from the middle and that the deferred constraint is not violated mid-transaction.
6. End-to-end verification of the brief's own success flow: log in, create a three-stage open-jaw trip, add items across several days including one overnight flight, set statuses, read the counter, filter to what is outstanding. Verify: an integration test walking that path against the deployed instance, with screenshots on the implementation PR.
