# Attachments and reservation data — the day detail completed

- Date: 2026-09-05 · Author: `om-auto-write-spec` (autonomous) · Status: draft, gated on the two ⚠ assumptions below
- Source brief: `.ai/specs/product-brief.md` (signed 2026-09-05)
- Foundation spec: `.ai/specs/2026-09-05-walking-skeleton.md` — **settled and not reopened here.** Its stack, `/api/v1` conventions, `ErrorCode` enum, `get_owned_trip` dependency and the `trip` / `trip_stage` / `trip_day` / `item` tables are the ground this spec builds on. Its assumptions **A2** (the multi-stop shape) and **A4** (the item time span) are owner-confirmed and this spec relies on both.
- Visual reference: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/`, chiefly `szczeg_y_dnia_i_aktywno_ci` and `centrum_rezerwacji_i_dokument_w` — a preliminary mockup labelled by the owner "wstępny design, do dostosowania w trakcie prac", not a contract
- Mode: `om-spec-writing --autonomous`. Every question this spec answered on its own is listed under **Resolved assumptions (autonomous defaults)** and is open to override before merge.

## 📝 TLDR

Build the second slice of the *Now* scope: **file and image attachments** pinned to an item or to a day, and the **reservation data** R04 describes — confirmation number, dates, cost — kept when it arrives alongside that material and never demanded from the user. With it, the day detail screen the walking skeleton left half-built is finished, and the brief's own "arranging one item" flow can run end to end: open the day → open the item → set the details → **attach the ticket or voucher** → move the status to *gotowe* → the counter changes.

Three decisions carry this document, and each would be a migration rather than an addition if it is wrong: **where the bytes live** (Postgres `BYTEA`, in a blob table separate from the metadata), **what an attachment hangs off** (one `attachment` table with exactly one of `item_id` / `trip_day_id` set), and **where reservation data hangs** (nullable columns on `item`, with the reservation's *dates* being the item's existing time span rather than a second copy of it). Everything else — screens, endpoints, limits, formats — is addition-shaped and a later PR can revise it cheaply.

This is also the first feature in the product that accepts bytes from a browser, on an installation that D14 puts on the public internet from day one. The Security section is therefore not a checklist at the end; it is a first-class part of the design, and two things it could not make safe — inline PDF preview and malware scanning — are **cut and named** rather than promised.

## 📝 Problem Statement

The brief's central problem P1 is that the state of a plan — *what is arranged and what is not* — exists nowhere in one piece: it lives in the owner's head, in his mailbox and "trochę w excelu". The walking skeleton moved the *statuses* out of his head and onto a timeline. It did not move the **evidence**. The booking confirmation for the Kuala Lumpur hotel is still an e-mail; the Pena palace ticket is still a PDF in a downloads folder; the car-hire voucher is still a screenshot on a phone. An item marked *gotowe* with no document behind it is a claim the owner has to trust his own memory for, which is exactly the state the product exists to replace — and A03 ("a manually maintained plan stays current enough to be trusted during the trip itself") is the assumption most damaged by it.

Two things follow, and they are the two halves of this spec:

1. **Attachments are the evidence layer.** The brief's *Now* list, bullet 5, is "a day detail view for editing an item properly, **with file and image attachments**", and the glossary defines an attachment as "a file or image pinned to **an item or a day** — a ticket, a voucher, a screenshot". The "arranging one item" flow in Key flows ends on the attach step. This is not a nice-to-have inside the milestone; it is the step the flow terminates on.
2. **Reservation data arrives with that evidence, and only then.** R04 is explicit and it is a mandate, not a deferral: "Cost and reservation data **are stored** when they arrive with material the user already has, and the app **never requires** the user to type them." D07 records the owner's own words: *"Jeżeli informacja będzie dostępna (np. z uploadu rezerwacji) to warto ją trzymać"*. The design work here is therefore not a reservation form. It is designing a place for data to land at the one moment the user is already holding it — with the voucher open in front of him because he is attaching it — and designing the app so that it never asks again.

Evidence and its limits, carried forward honestly. P1 and P2 are `[INTERVIEW]` claims from one session with one respondent who is also the builder. The design export is `[DOCUMENT]` evidence of an intended shape and nothing more — in particular its "PDF, PKPASS, PNG, JPG (do 25 MB)" dropzone caption is an artefact of a generated mockup, not a requirement anyone stated, which is precisely why brief **Q03** is open. There is no benchmark data (brief Q01, still open — this session, like the discovery session, had no network access, so the comparisons in *Proposed Solution* are labelled as recalled rather than checked).

## 📝 Scope

### In scope

| # | Capability | Contract it serves |
|---|---|---|
| S1 | Upload a file or image and pin it to an **item** | *Now* bullet 5; glossary, *Attachment* |
| S2 | Upload a file or image and pin it to a **day** | *Now* bullet 5; glossary, *Attachment* ("an item **or a day**"); design export, "Załączniki i dokumenty dnia" |
| S3 | List, download and delete attachments, for both parents | the same |
| S4 | **Reservation data on an item** — confirmation number and cost — stored when it arrives, never required, never nagged | **R04**, D07 |
| S5 | The reservation's **dates** carried by the item's existing time span, not duplicated | R04 ("dates"), and walking-skeleton A4 (owner-confirmed) |
| S6 | The **day detail screen completed**: the attach step and the terminating move to *gotowe* | brief Key flows, "arranging one item"; *Now* bullet 5 |
| S7 | An upload path that is safe on a public deployment: derived content types, structural path-traversal immunity, size, count, quota and rate limits, safe serving | **D14**, R08 |
| S8 | Polish and English both first-class; `scripts/check_locales.py` green | R01, R09 |

### Out of scope — and the honest authority for each cut

Same discipline as the foundation spec, because it is easy to get this wrong: **several things below are inside the brief's *Now* list, mandated by active rows, and no row is ever cited as the authority for deferring the thing that row mandates.** Where an item is cut from *this* slice while remaining in the first version, the authority is **A05** — the riskiest-assumption row whose smallest test is *"a walking skeleton by 2026-09-15 … whatever is not standing by then gets cut, chat first"* — read as the brief's own mechanism for **sequencing** *Now*, not for shrinking it.

| Deferred | Authority for cutting it *here* | What the design export shows, and what we do with it |
|---|---|---|
| Chat, the assistant, any AI suggestion | **A05**, which names chat first | "Inteligentny Asystent Dnia", "Sugerowana optymalizacja czasowa", "Kup teraz przez AI" — **not designed here** |
| The magic link and everything a guest sees | **A05** (this is the next spec's subject). This spec fixes one **binding precondition** on it: see A8/A9 below | the "Udostępnij" button — **not designed here** |
| Automatic parsing of reservation PDFs and e-mails; a private per-trip e-mail address | **D12** (*Later* list) — a genuine deferral, and the reason S4 is a manual capture surface rather than an inbox | "Inteligentny Skaner AI", "Automatyczne parsowanie", "PNR: #9842103", `trip-pt2025@my.voyageai.com` — **not designed here** |
| Live prices, booking, buying, vendor comparison | **D04 / R07** — a real decision-backed exclusion from the first version | "Sixt 185 PLN/dzień vs Europcar 210 PLN/dzień", "Zarezerwuj przez AI", "Kup 2 bilety" — **not designed here** |
| Splitting costs between participants; any cost total, budget figure, or per-trip sum | **D12** (*Later*: "splitting costs between participants", "cost accounting as a real feature"). R04 mandates *storing* cost, and this spec stores it; it does not mandate arithmetic over it | "Wydatki potwierdzone 4 250 PLN", "78% łącznego budżetu", "Szacowany budżet", "Suma cząstkowa" — **not designed here** |
| A trip-level "Rezerwacje i Dokumenty" hub screen | **A05** — *Now* bullet 5 names the **day detail** view. It is a pure query over data this spec already stores, so it is an addition later, never a migration (see A13) | the whole `centrum_rezerwacji_i_dokument_w` screen — its *rows* informed the attachment metadata below; its screen is **not designed here** |
| Apple Wallet / Google Pass export, PDF and Calendar export | **D12** — and the reason PKPASS is not an accepted format (A3) | "Zsynchronizuj z Apple Wallet & Google Pass", "Eksportuj portfel" | 
| Preparation tasks separate from timeline items | brief **Q02** is open — undecided for v1, so there is nothing to build to | "Zadania & Przygotowanie" — **not designed here** |
| Insurance policies, passports and other trip-level documents as a *typed* concept | **A05**; nothing stops the owner attaching a policy PDF to the day he flies, which is what the data model already allows | "Ubezpieczenie i Paszporty (1)" — the *filter category* is **not designed here** |
| Maps, GPS, weather, route optimisation | **D12** | "Podgląd trasy", "Otwórz GPS", the weather strip — **not designed here** |

Nothing here is *excluded*: N01 and D12 say the product excludes nothing permanently.

### The slippable tail

A05 is still the risk that decides the month, and a plan that does not name its own cut line is not managing it. In priority order, **the last things built and the first things to drop are**: drag-and-drop onto the drop zone (a plain file-picker button does the same job), the image lightbox (a download link does the same job), the paperclip badge on the timeline's item cards, and the duplicate-file hint. Everything else — the upload endpoint with its full validation, the two parents, download, delete, the reservation fields, the quotas and limits — is load-bearing.

Two things are explicitly **not** in the tail, and it matters to say which:

- **Day-level attachments (S2) are not slippable.** The glossary defines an attachment as pinned to "an item **or** a day", and shipping only one half means the `attachment` table's parent shape gets decided by what ran out of time rather than by design — the one decision here that would be a migration.
- **No security control in S7 is slippable.** Cutting a limit or a check to make a date is how a personal tool on the public internet becomes someone else's file host. If the calendar bites hard enough to threaten S7, the correct cut is the whole feature, not its safety.

## 📝 Proposed Solution

Nothing clever, for the same reason the foundation spec gave: the risk here is calendar risk (A05) plus a genuinely new attack surface, not technical difficulty.

- **The bytes live in PostgreSQL**, in an `attachment_blob` table holding one `BYTEA` per attachment, separate from the `attachment` metadata row so that listing a day never reads a megabyte. The deployment (walking-skeleton A12) has exactly one durable store, one backup, one credential and one failure mode; an object store would add a bucket to provision, a credential to manage, a signed-URL scheme to design, an orphaned-object reaper to write, and a second thing that can be down — before 2026-09-30. See A2 for the full argument and the additive path out.
- **One `attachment` table with two nullable parent columns and a `CHECK` that exactly one is set.** An attachment belongs to an item or to a day, never to both, never to neither. `ON DELETE CASCADE` on both, which — because the bytes are in the same database — means deleting a trip removes its files in the same transaction, with no orphan-sweeping job anywhere in the system.
- **Reservation data is three nullable columns on `item`**, plus the rule that the reservation's *dates* are the item's existing `start_time` / `end_time` / `end_date` span rather than a second pair of date columns. There is exactly one answer in the system to "when is the hotel booked for", and it is the one the timeline already renders.
- **Uploads are validated by what the bytes actually are**, never by the client's `Content-Type` header and never by the filename's extension. Three formats pass — PDF, JPEG, PNG — each identified by magic bytes and then by a small amount of pure-stdlib structural checking; nothing else is stored. **No image library ever decodes an uploaded image on the server.**
- **Files are served back only to the owner's session**, always as `Content-Disposition: attachment`, always with `X-Content-Type-Options: nosniff` and a locking-down `Content-Security-Policy`, from a route that goes through the settled `get_owned_trip` dependency and answers `404` — never `403` — for anyone else.

### Alternatives considered, and why they lost

- **An object store (S3 / R2 / MinIO) with pre-signed URLs.** The textbook answer, and the right one at scale. It loses *here* on three counts: it puts a second stateful dependency and a second credential into a deployment A12 deliberately made a single image plus one managed database; pre-signed URLs are bearer tokens that bypass `get_owned_trip` entirely, so the one place ownership is enforced would suddenly have a second, weaker path around it; and deleting a trip would stop being a cascade and start being a distributed delete with an orphan reaper behind it. The move is **additive when it is justified**: a `storage_backend` column defaulting to `'db'`, an `object_key` column, and a copy job — see A2.
- **The filesystem of the application container.** Cheapest to write, and wrong: A12's deployment is a single container image on a platform where the filesystem is ephemeral, so this is a data-loss design wearing a simple one's clothes. A mounted volume brings back a second stateful thing without bringing the object store's benefits.
- **Postgres large objects (`lo`) instead of `BYTEA`.** They stream, which `BYTEA` does not, and at a 10 MB cap that buys nothing but a second access API, `lo_unlink` bookkeeping that is *not* covered by `ON DELETE CASCADE`, and exactly the orphan problem this design just avoided.
- **A separate `reservation` table, one-to-one with `item`.** Rejected: five nullable fields with no cardinality above one, bought with a join on every timeline read and a second entity in the glossary. When cost splitting arrives (D12) it will want a *participant* dimension, and that is a new table with its own shape either way — nothing is saved by guessing at it now.
- **Hanging reservation data on the `attachment` row instead of the item.** Superficially attractive, because that is literally where the data comes from. Rejected on two hard grounds: deleting a voucher PDF during a tidy-up would silently delete the confirmation number with it — data loss from a file-management action, a blocker class under `BACKWARD_COMPATIBILITY.md` §2 — and two documents evidencing one booking (a voucher and a receipt) would give one hotel stay two costs with no rule for which one the item shows.
- **Storing an amount without a currency code.** Rejected outright, whatever Q04 turns out to be. A column of bare numbers whose unit lives in someone's head is `BACKWARD_COMPATIBILITY.md`'s named worst case — "changing what it means while keeping its name" — pre-installed on day one. See A7: carrying the code costs three characters and no feature.
- **Server-side thumbnailing, EXIF stripping, or PDF text extraction.** Each requires *decoding attacker-supplied bytes with a parser*, which is the single largest source of remote-code-execution CVEs in this problem space. All three are cut; the browser renders images in its own sandbox, which is what it is good at. The costs are stated in A12 and in Security.

### Benchmark, recalled rather than checked

Brief **Q01** is open and this session had no network access, so what follows is recollection, labelled as such, and does not close it. **TripIt**'s answer to "never demand the data" is a forwarding address that parses confirmation e-mails — the genuinely better product answer, and precisely what D12 defers; our optional capture panel is the honest manual stand-in until that lands, and the data it writes is the same shape a parser would later fill. **Wanderlog** attaches files per plan item and carries an expense ledger with currency conversion — the attachment half matches this design, the ledger half is D12's "cost accounting as a real feature". **Google Travel** derives everything from Gmail and stores nothing the user pins by hand, which is a different product. The complexity all three carry and this spec skips: OCR, currency conversion, per-traveller expense splitting, and a document hub as a first-class screen. The thing they get right that this spec accepts as a real gap: an attachment the user has to remember to upload is an attachment that sometimes does not get uploaded — which is A03's risk, and it is not solved here.

## 📝 Architecture

Additive throughout. No module the foundation spec created changes shape; four are extended and two are new.

```
backend/
  trip_planner/
    api/attachments.py         NEW  upload, download, metadata, delete
    api/items.py               EXTENDED  three reservation fields on the existing PATCH
    api/trips.py               EXTENDED  attachment_count on the timeline payload
    domain/uploads.py          NEW  pure: sniff type, structural check, dimension bound,
                                    filename normalisation, limit arithmetic
    domain/money.py            NEW  pure: amount/currency validation and pairing
    db/models.py               EXTENDED  Attachment, AttachmentBlob, UploadEvent
    security/quota.py          NEW  DB-backed per-owner upload rate + volume limiter
    errors.py                  EXTENDED  eight new ErrorCode members
frontend/
  src/api/attachments.ts       NEW  typed client, upload with progress
  src/features/day/            EXTENDED  DayAttachments, ItemAttachments, ReservationPanel,
                                         UploadDropzone, Lightbox
  src/features/timeline/       EXTENDED  the paperclip badge on item cards
  src/locales/{en,pl}.json     EXTENDED  new keys, both locales, ICU plurals
migrations/                    NEW  one revision (see Migrations)
```

Boundaries that matter, in the same spirit as the foundation spec:

- **`domain/uploads.py` is pure and it is where the security decisions live.** Type sniffing, the structural check, the dimension bound, filename normalisation and the limit arithmetic are functions over `bytes` and plain values with no database and no I/O. That is what makes the malicious-input cases *unit-testable without a server*, and it means there is exactly one implementation of "is this file acceptable" rather than one in the endpoint and a forgotten second one anywhere else.
- **`get_owned_trip` remains the only fence, and nothing routes around it.** Every attachment route is nested under `/trips/{tripId}/…` and takes the settled dependency. Crucially, this is *the reason pre-signed URLs were rejected*: the moment a URL grants access without passing that dependency, the foundation spec's Phase 1 route-enumeration test stops being able to prove R08.
- **The attachment content route is the one place authorisation will later become pluggable.** It resolves its caller through a single `resolve_trip_access(trip_id, request)` seam that today has exactly one implementation — the owner session. The sharing spec adds the guest-grant implementation *there*, in one function with one test, rather than by threading a second auth path through the handler. This is the entirety of what this spec does for the magic link, and it is deliberately a seam and not a feature.
- **The server never renders, transforms, re-encodes or parses an uploaded file.** It reads bytes, checks them, stores them, and later hands the identical bytes back. Everything that looks at the *content* of an attachment runs in the browser's sandbox.
- **No external calls, still.** Nothing is fetched by URL, no antivirus service is contacted, no CDN is involved. "Attach from a link" is deliberately not an endpoint — it would be a server-side request forgery primitive delivered as a feature.
- **The frontend never decides what is acceptable.** It pre-checks extension and size purely so the user gets an instant message instead of a wasted 10 MB upload; the server repeats every check and the server's answer is the only one that matters.

## 📝 Data Model

The section this slice turns on. Three shapes, each argued.

### `attachment` — metadata, one row per file

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | also the storage identity: it is what the blob row keys on, and nothing derived from user input ever is |
| `item_id` | UUID FK → `item.id`, `ON DELETE CASCADE`, NULL, indexed | set when the attachment is pinned to an item |
| `trip_day_id` | UUID FK → `trip_day.id`, `ON DELETE CASCADE`, NULL, indexed | set when it is pinned to a day |
| `filename` | TEXT NOT NULL | the **display name only**, normalised on write (see below). It never reaches a filesystem, a path, a shell or a storage key |
| `content_type` | TEXT NOT NULL, `CHECK (content_type IN ('application/pdf','image/jpeg','image/png'))` | **derived from the bytes**, never copied from the request |
| `byte_size` | INTEGER NOT NULL, `CHECK (byte_size > 0 AND byte_size <= 10485760)` | the true length of what was stored, counted while reading |
| `sha256` | CHAR(64) NOT NULL, indexed (non-unique) | integrity, and the duplicate hint in A14. Deliberately **not** unique: two identical files on two different days are two attachments |
| `created_at` | TIMESTAMPTZ NOT NULL | |

```sql
CHECK ((item_id IS NULL) <> (trip_day_id IS NULL))   -- exactly one parent, always
```

**Why one table with two nullable parents, rather than two tables or a polymorphic key.** The glossary requires both parents; that is settled, not chosen here. What is chosen is the shape:

- *Two tables* (`item_attachment`, `day_attachment`) duplicates every column, every constraint, every index and every endpoint, and then requires a `UNION` the first time anything wants "this trip's documents" — which is exactly what the deferred hub screen (A13) will want.
- *A polymorphic `(parent_type, parent_id)` pair* gives up referential integrity: the database can no longer cascade, and a dangling `parent_id` becomes possible on the day someone deletes a row by hand. The two-nullable-FK shape keeps real foreign keys, real cascades, and a `CHECK` that makes "an attachment with no parent" and "an attachment with two parents" both unrepresentable.
- *An `attachable` supertype table* is the fully normalised answer and is more machinery than two nullable columns are worth at this size.

**There is deliberately no `trip_id` column.** It would be convenient for scoping and it would be a denormalisation that can drift. Ownership is already enforced one hop up by `get_owned_trip`, and the parent chain (`item → trip_day → trip`, or `trip_day → trip`) resolves it exactly. The "list a whole trip's attachments" query the hub screen would want is a two-hop join over indexed foreign keys on a personal-scale dataset.

**Relaxing the `CHECK` later is how a trip-level attachment arrives.** If the owner ever wants a document pinned to the *trip* rather than to a day (an insurance policy, a passport scan — the design export's "Ubezpieczenie i Paszporty" row), the change is: add a nullable `trip_id`, widen the `CHECK` to "exactly one of three". That is an ordinary additive migration. Guessing at it now is inventory nobody updates.

### `attachment_blob` — the bytes, on their own

| Column | Type | Notes |
|---|---|---|
| `attachment_id` | UUID pk, FK → `attachment.id`, `ON DELETE CASCADE` | one-to-one; the pk *is* the fk |
| `data` | BYTEA NOT NULL | the file, byte-exact as uploaded |

**Split from the metadata for one reason and it is not aesthetics.** SQLAlchemy will happily `SELECT *` a day's attachments; with the bytes in the same row, rendering a day with six photos reads sixty megabytes to display six filenames. A separate table makes that mistake impossible to make by accident rather than merely discouraged by a `deferred()` loader option someone can forget. Postgres TOASTs the column out of line regardless, so there is no storage cost to the split.

`ON DELETE CASCADE` from `attachment`, which itself cascades from `item` and `trip_day`, which cascade from `trip`. **Deleting a trip therefore deletes its files, transactionally, with no sweeper, no reaper and no eventual consistency** — the single strongest operational argument for A2's answer, and the one that disappears the moment the bytes move to a bucket.

### `item` — three additive nullable columns (R04, D07)

| Column | Type | Notes |
|---|---|---|
| `confirmation_number` | TEXT NULL, `CHECK (confirmation_number <> '')` | free text. Vendors use `SX-9912L`, `#9842103`, `TP1205/PNR` and worse; any format we imposed would be wrong for something the user is copying off a voucher |
| `cost_amount` | NUMERIC(12,2) NULL, `CHECK (cost_amount >= 0)` | `NUMERIC`, never a float — money |
| `cost_currency` | CHAR(3) NULL, `CHECK (cost_currency ~ '^[A-Z]{3}$')` | ISO 4217 |

```sql
CHECK ((cost_amount IS NULL) = (cost_currency IS NULL))   -- an amount never exists without its unit
```

Everything the foundation spec already shipped on `item` is untouched. These are three nullable columns and two check constraints on a table whose meaning does not change — an addition in the plainest sense, and exactly the addition the foundation spec anticipated when it wrote *"No `cost`, no `currency`, no `confirmation_number` … not because R04 forbids them — R04 says the opposite … but because it arrives with an attachment, and attachments are cut from this milestone."* Attachments now exist, so the data has something to arrive with, and the columns stop being inventory nobody updates.

**R04's "dates" are the item's existing time span, and are not stored a second time.** This is the sharpest modelling call in the document. A confirmation says "Memmo Alfama, 1–4 May"; the item that *is* that stay already carries its start day, `end_date` and optional times, in columns the owner confirmed as walking-skeleton A4. Adding `reservation_start` / `reservation_end` beside them would create two answers to "when is this booked for", and the foundation spec rejected precisely that duplication once already, for exactly this reason, when it refused to model transport legs separately from items. Capturing a reservation's dates therefore **writes the item's own span**, in the same request, through the same validation (`invalid_time_span`) — the user sees one date control on the screen and it means one thing.

**No `vendor`, no `booking_url`, no `paid` flag, no `payment_method`.** R04 names three things — confirmation number, dates, cost — and the item already has a `title` and free-text `notes` for "Sixt Rent-A-Car". The design export's "Opłacone / Potwierdzone", "Do opłacenia na miejscu" and "Rezerwacja potwierdzona" are nine more status labels for a product that has exactly three (R02, D05); the item's status already says whether it is arranged.

### `upload_event` — the rate and volume limiter's storage

| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL pk | |
| `owner_id` | UUID FK → `owner.id`, `ON DELETE CASCADE`, indexed | |
| `occurred_at` | TIMESTAMPTZ NOT NULL, indexed | |
| `byte_size` | INTEGER NOT NULL | counted for the volume window |

Deliberately modelled on the foundation spec's `login_attempt` — same pattern, same reasoning, a **separate table rather than a widened one**, because `login_attempt` is keyed on a normalised e-mail and a source address for an *unauthenticated* endpoint, while this is keyed on an authenticated owner. Merging them would mean nullable columns on both halves and a discriminator; the foundation spec's shape stays untouched. Rows outside the window are deleted on each check, as there.

### Relationship summary

```
trip 1─n trip_day 1─n item
                  1─n attachment (trip_day_id set)      ─┐
             item 1─n attachment (item_id set)          ─┴ exactly one parent, CHECK-enforced
       attachment 1─1 attachment_blob                     (bytes; cascades all the way up)
             item ·─· reservation data                    (three nullable columns on item itself;
                                                            the dates ARE the item's time span)
owner 1─n upload_event
```

### Migrations

**One Alembic revision**, in the same PR as the code that needs it, with a working `downgrade`: create `attachment`, `attachment_blob` and `upload_event`; add the three nullable columns and two check constraints to `item`. Against `BACKWARD_COMPATIBILITY.md` §2: the new tables did not exist, so "safe against rows that already exist" is vacuous for them; the `item` columns are **nullable with no default and no backfill**, which is the safe form of the rule. The `downgrade` drops the tables and the columns, and therefore destroys the data in them — which is what a downgrade of a feature migration means and is stated here so nobody discovers it at 02:00. It is not the expand/contract case §2 governs: nothing is being removed from a surface a consumer already depends on.

Storage growth is now a deployment property: the database backup carries the files. At the caps in A4 one trip is bounded at 250 MB and the whole installation at 2 GB, which is a manageable backup on any hosted Postgres plan and is the reason those caps exist as much as abuse is.

## 📝 API Contracts

All additive, all under `/api/v1`, all cookie-authenticated, all taking `get_owned_trip`, all answering `404` — never `403` — for a trip belonging to anyone else. Per `BACKWARD_COMPATIBILITY.md` §1: new endpoints and new *optional response fields* are non-breaking, and nothing existing is renamed, retyped or given a new meaning.

### Upload

| Method | Path | Notes |
|---|---|---|
| `POST` | `/trips/{tripId}/days/{date}/attachments` | `multipart/form-data`, **exactly one** part named `file` → `201` with the attachment metadata |
| `POST` | `/trips/{tripId}/items/{itemId}/attachments` | the same, pinned to the item → `201` |

Both require the CSRF double-submit token the foundation spec established for unsafe methods. Both accept exactly one file per request: one part means a two-line parser configuration instead of a loop with its own limit arithmetic, and a client uploading five files makes five requests with five independent progress bars and five independent failures — which is also the better UX.

Response body (identical wherever an attachment is serialised):

```json
{ "id": "…", "filename": "Voucher_Memmo_Alfama.pdf", "content_type": "application/pdf",
  "byte_size": 860160, "sha256": "…", "created_at": "2026-09-05T10:11:12Z",
  "item_id": "…", "trip_day_id": null }
```

### Read, download, delete

| Method | Path | Notes |
|---|---|---|
| `GET` | `/trips/{tripId}/attachments/{attachmentId}` | the metadata object above |
| `GET` | `/trips/{tripId}/attachments/{attachmentId}/content` | the bytes, with the header set in Security below |
| `DELETE` | `/trips/{tripId}/attachments/{attachmentId}` | `204`; cascades to the blob; permanent, no undo in this milestone |

There is **no `PATCH`** on an attachment. A file's bytes are immutable by construction — replacing one is a delete and an upload — and renaming the display filename is a feature nobody asked for. Immutability is also what lets the content route serve a strong `ETag`.

### Reservation data — no new endpoint

Reservation data is written through the **existing** `PATCH /trips/{tripId}/items/{itemId}`, which gains three optional fields: `confirmation_number`, `cost_amount`, `cost_currency`. Adding optional request fields is non-breaking; adding *required* ones would not be, and none is required — that is R04 expressed in the contract rather than only in the UI. Explicit `null` clears a field; omitting it leaves it alone. `cost_amount` and `cost_currency` must be supplied and cleared **together**: one without the other is `422 invalid_cost`, which is the API-level statement of the paired `CHECK`.

The reservation's dates are set through the item fields that already exist — `start_time`, `end_time`, `end_date` — with the validation the foundation spec already defined. There is no second date vocabulary.

### Existing payloads, extended

| Payload | Added field | Why not more |
|---|---|---|
| `GET /trips/{tripId}` (timeline) | `attachment_count` (integer) per item | one integer drives the paperclip badge; shipping the full list would put every filename on a trip-wide payload for a screen that shows none of them |
| `GET /trips/{tripId}/days/{date}` (day detail) | `attachments` (array) on the day, and `attachments` (array) on each item | this is the screen that renders them |
| both | `confirmation_number`, `cost_amount`, `cost_currency` on each item | the day detail edits them; the timeline does not display them, but omitting them from one item serialiser and not the other is how two shapes of the same object appear |

### New error codes

Added to the settled `ErrorCode` enum in `backend/trip_planner/errors.py`, which means each is automatically covered by the foundation spec's test that **every member resolves to a non-empty key in both `en.json` and `pl.json`** — the check `scripts/check_locales.py` structurally cannot make:

| Code | Status | Raised when |
|---|---|---|
| `attachment_too_large` | `413` | the body or the counted stream exceeds the per-file cap |
| `unsupported_file_type` | `415` | the bytes are not PDF, JPEG or PNG |
| `malformed_upload` | `422` | zero bytes, no `file` part, more than one part, a truncated or structurally invalid file |
| `attachment_limit_reached` | `409` | the parent already holds the maximum number of attachments |
| `trip_storage_quota_exceeded` | `409` | the trip's or the installation's byte quota would be exceeded |
| `rate_limited` | `429` | the per-owner upload rate or volume window is exhausted |
| `invalid_cost` | `422` | an amount without a currency, or the reverse; a negative amount; more than two decimals |
| `attachment_parent_missing` | `404` | the day or item in the path does not exist **within this trip** |

Adding an enum member is additive for the server. The SPA imports the generated TypeScript union, so an unhandled code is a compile error rather than a blank message — and a generic translated fallback exists regardless.

## 📝 Security

D14 puts this on the public internet and this is the first feature that accepts bytes from a browser, so this section is part of the design, not an appendix to it. The threat model is narrow and worth stating precisely: **there is no unauthenticated upload path** (R08 — nothing showing or touching a plan is reachable without an owner session, and the route-enumeration test from the foundation spec's Phase 1 keeps that true as these routes are added). The realistic adversaries are therefore a stolen or fixated session, a cross-site request from another origin, and the owner's own browser being tricked into rendering something hostile — plus straightforward resource exhaustion.

### Where the bytes live

Inside PostgreSQL, in a table reachable only by the application's own credential, on a database A12 already places on a private network. **No uploaded byte ever touches the application's filesystem** — the request body is read into memory, validated, and passed to the driver as a bind parameter. There is no temporary file, so there is no temporary-file race, no leftover on a crash, and no directory anyone can be tricked into writing outside of.

### Filenames

The client's filename is **display metadata and nothing else**, and it is structurally incapable of being anything else because the storage identity is the attachment's own UUID primary key. Path traversal is not filtered here; it is unrepresentable. On write the filename is nonetheless normalised, because it is echoed back into HTML and into a response header:

1. decoded as UTF-8, replacing invalid sequences; NFC-normalised;
2. reduced to its basename — everything up to and including the last `/` or `\` is discarded;
3. control characters, `\r`, `\n` and `\t` removed (a newline in a filename is a response-header injection primitive);
4. truncated to 200 characters, on a character boundary;
5. if the result is empty or consists only of dots, replaced with a generated name derived from the **detected** type (`attachment.pdf`, `image.jpg`, `image.png`).

The extension is *never* consulted when deciding what a file is. A file named `ticket.pdf` whose bytes are a JPEG is stored as a JPEG named `ticket.pdf`; a file named `x.pdf` whose bytes are an HTML page is refused.

### Content-type verification that does not trust the client

The request's `Content-Type` part header and the filename extension are both **discarded before any decision**. The type is derived from the bytes, in `domain/uploads.py`:

| Type | Magic bytes | Structural check that follows |
|---|---|---|
| PDF | `%PDF-` at offset 0, version `1.0`–`2.0` | an `%%EOF` marker within the last 1024 bytes; total length ≥ 100 bytes. **The PDF is not parsed** — no object graph is walked, so no PDF parser CVE is reachable |
| JPEG | `FF D8 FF` at offset 0 | the marker chain is walked with ~40 lines of stdlib code to the first `SOF0`–`SOF3` frame header, from which the declared dimensions are read; the stream must end with `FF D9` |
| PNG | `89 50 4E 47 0D 0A 1A 0A` | the first chunk must be `IHDR`; width and height are read from it; the CRC of `IHDR` is verified |

**No image library runs on the server.** Pillow was the obvious alternative and it lost: `Image.open()` plus `verify()` is a decoder touching attacker-controlled bytes, historically the richest CVE surface in this whole area, and it exists to give us something we do not need. Reading two 32-bit integers out of a PNG `IHDR` is not a decode. The declared pixel count is bounded at **50 megapixels** — a decompression bomb is a small file that expands catastrophically *when decoded*, and since the server never decodes, the bound exists to protect the **browser** that will. A file whose header claims 60 000 × 60 000 is refused as `unsupported_file_type`.

Nothing else is accepted, and each refusal has a reason:

- **SVG** — an XML document that executes script in the origin that renders it. Not an image for security purposes.
- **PKPASS** (the design export's suggestion) — a ZIP container. It cannot be verified without unzipping attacker-controlled archive bytes, it renders as nothing without the Wallet export that D12 defers, and it would be the only accepted format whose identity depends on trusting a filename. **Cut, and named in A3 as cut.**
- **HEIC / WEBP / GIF / TIFF** — each is another parser family for the browser and another magic-byte path for us, in exchange for formats no ticket vendor issues. A phone that shoots HEIC shares as JPEG.
- **Office documents, archives, e-mail files (`.eml`, `.msg`), anything else** — macro and parser surface, and nothing in the *Now* scope needs them.
- **HTML and plain text** — a saved confirmation page is the plausible use, and it is exactly the stored-XSS vector; a screenshot or a print-to-PDF is the safe form of the same thing.

### Limits (all enforced server-side, all with a translated error)

| Limit | Value | Enforced |
|---|---|---|
| Per file | 10 MB | reject on `Content-Length` **before reading**, and again by counting bytes while reading — a chunked request can lie about or omit the length |
| Parts per request | exactly one, named `file`; field values capped at 200 bytes | the multipart parser's own limits, not a post-hoc check |
| Attachments per parent | 20 per item, 20 per day | `409 attachment_limit_reached` |
| Bytes per trip | 250 MB | `409 trip_storage_quota_exceeded`, checked inside the upload transaction |
| Bytes per installation | 2 GB | the same code, the same error |
| Upload rate | 30 uploads / 10 min and 200 MB / hour, per owner | `429 rate_limited`, counted in `upload_event` in Postgres — **not** in a process-local dictionary, because A12's deployment runs more than one worker and an in-process counter would be decorative |

Quota checks happen **inside** the same transaction as the insert, so two concurrent uploads cannot each observe headroom that only one of them can have.

### Serving a file back, and to whom

Only to the owner's session, through `get_owned_trip`, from `GET …/attachments/{id}/content`, with every one of these headers:

```
Content-Type: <the derived type — never the client's>
Content-Disposition: attachment; filename="<ascii fallback>"; filename*=UTF-8''<rfc-5987>
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'none'; sandbox
Cross-Origin-Resource-Policy: same-origin
Referrer-Policy: no-referrer
Cache-Control: private, no-cache
ETag: "<attachment id>"
```

Two notes on that set. `Content-Disposition: attachment` is applied **universally, including to images** — an `<img src>` ignores the header entirely, so the gallery still renders, while a hostile file navigated to directly downloads instead of rendering in our origin. And `private, no-cache` with a strong `ETag` is deliberate rather than `no-store`: the content is immutable, so a conditional request answers `304` and the gallery does not re-download ten megabytes on every render, while every revalidation still passes through the session check.

**Inline PDF preview is cut, and this is the "cannot make it safe, so cut it" case.** The design export's "Pokaż PDF z kodem QR" would mean serving a PDF `inline`, where the browser's viewer executes the document's JavaScript **in this application's origin** — with the session cookie in scope. The standard mitigation is to serve user content from a separate sandbox origin, and A12 fixes the deployment at one origin, one image, one certificate. So the download path is what ships, the separate-origin upgrade is recorded as the precondition for ever changing that, and nothing pretends a sandboxed `<iframe>` on the same origin is a fix.

### What a malicious upload cannot do

| Attack | Why it fails |
|---|---|
| Stored XSS via an uploaded file | HTML, SVG and text are refused by magic-byte sniffing; the stored type is derived, never echoed from the request; `nosniff` stops content-type confusion; `Content-Disposition: attachment` and the `sandbox` CSP stop rendering in our origin |
| Path traversal (`../../etc/passwd` as a filename) | unrepresentable — the storage key is a UUID and the filename never reaches a path. The normalisation in step 2 above exists for the *displayed* string, not as the defence |
| Response-header injection via a filename | control characters stripped; the header is RFC 5987 percent-encoded, never interpolated raw |
| Remote code execution through an image parser | no image parser runs server-side; the dimension read is two integers out of a header |
| Decompression / pixel bomb | no archive format is accepted; declared pixel count bounded at 50 MPx before the browser ever sees it |
| Server-side request forgery | there is no "attach from URL" and the server fetches nothing, ever |
| Disk or memory exhaustion | `Content-Length` rejected before the read, bytes counted during it, and per-parent, per-trip, per-installation and per-window limits behind that |
| Cross-site upload from another origin | the CSRF double-submit token is required on every unsafe method (foundation spec); `SameSite=Lax` in front of it |
| IDOR — reading another trip's ticket | `get_owned_trip` on every route; `404` rather than `403`, so nothing is confirmed to exist |
| Enumerating attachments | UUID primary keys; no sequential identifier is exposed |
| Reading a ticket without an account | there is no unauthenticated read path at all in this spec — see the magic-link decision below |

### What this spec explicitly does **not** protect against, stated plainly

- **No malware scanning.** An uploaded file is stored and handed back byte-for-byte; if the owner uploads an infected PDF, he can download an infected PDF. This is acceptable at exactly one consumer who is also the uploader (D15), and it stops being acceptable the moment anyone else can fetch these bytes — which is why the magic-link answer below is "no", and why an AV step is listed there as a precondition rather than as a nice-to-have.
- **No EXIF stripping.** Photographs are stored byte-exact, GPS coordinates and all. Stripping requires re-encoding, which requires decoding, which is the one thing this design refuses to do server-side. For the owner reading his own photographs this is a non-issue; it becomes a real leak the moment a guest can fetch them, and it is the second precondition on the sharing spec.
- **No content inspection of any kind** — no OCR, no text extraction, no thumbnail generation. That is the whole point.
- **Downloaded bytes persist in the browser's own cache and downloads folder**, outside this application's control, as they do for every website.

## 📝 UI/UX

One screen is completed and one is lightly touched. Everything here is `szczeg_y_dnia_i_aktywno_ci` adapted, with the parts serving out-of-scope features dropped.

Mockups of the proposed screens live beside this spec and are attached to this spec's PR. They are illustrative statics — layout and flow, not pixel-perfect design — rendered from self-contained HTML with no application code behind them. **There are no current-state screenshots**: the walking skeleton's implementation is still on an open PR and nothing is deployed, so there is no running application to photograph.

| Screen | Mockup |
|---|---|
| `/trips/:id/days/:date` — the day detail with day-level documents and per-item attachments, Polish locale | [`assets/attachments-and-reservation-data/mockup-01-day-detail.png`](assets/attachments-and-reservation-data/mockup-01-day-detail.png) |
| The item editor: attachments, the optional reservation panel, and the move to *done*, **English locale** | [`assets/attachments-and-reservation-data/mockup-02-item-editor.png`](assets/attachments-and-reservation-data/mockup-02-item-editor.png) |
| Upload states — in progress, refused type, too large, quota — Polish locale | [`assets/attachments-and-reservation-data/mockup-03-upload-states.png`](assets/attachments-and-reservation-data/mockup-03-upload-states.png) |

Two locales across three mockups, for the same reason the foundation spec gave: R01 makes both first-class and a spec that only ever pictures one is not showing the product it describes.

### `/trips/:id/days/:date` — the day detail, completed

- **Day documents.** A panel headed "Załączniki i dokumenty dnia" / "Day files and documents", carrying the day's own attachments and one action, "Dodaj plik / zdjęcie / bilet" / "Add file, photo or ticket". Kept verbatim from the export because the export got this one right.
- **Item attachments.** Each item row gains a paperclip with a count when it has any; the attachments themselves live inside the item editor, next to the fields they evidence. This is the split the export implies with its per-item ticket pills and its separate day panel, and it is the split the data model enforces.
- **An attachment renders as**: a thumbnail for images, a document glyph for PDFs; the filename; the size, formatted through `Intl` and never concatenated; a download action; a delete action behind a confirmation that names the file. Images open in a lightbox; PDFs download (see the cut above — the button says "Pobierz" / "Download", not "Preview", because saying "Preview" and delivering a download is the kind of small lie that makes an owner stop trusting his own tool).
- **Dropped from the export, in this screen**: "Inteligentny Asystent Dnia" and "Sugerowana optymalizacja czasowa" (A05, chat first); "Zadania & Przygotowanie" (brief Q02 undecided); "Podgląd trasy" and "Otwórz GPS" (D12); "Eksportuj do Google Calendar" and "Optymalizuj trasę z AI" (D12); vendor comparison cards, per-item ratings and live prices (D04, R07).

### Uploading

- The drop zone is **a real `<label>` over a real `<input type="file">`**. Drag-and-drop is an enhancement layered on top and is the first thing in the slippable tail; the keyboard and file-picker path is the one that always exists.
- `accept=".pdf,.jpg,.jpeg,.png"` on the input is a **convenience for the picker dialog and nothing else** — the client-side extension and size pre-check exists so the user gets an instant answer instead of a wasted upload, and it is never the reason a file is refused. The server repeats every check.
- States: idle → selected → uploading with a determinate progress bar → done (the row appears in the list) → failed, showing the translated message for the server's error code with a retry action. Progress and completion are announced through an `aria-live="polite"` region.
- One file per request; selecting five files produces five rows, five progress bars, five independent outcomes. A failure of one never rolls back the others.
- Cancelling mid-upload aborts the request; nothing is stored, because the row and the bytes are written in one transaction only after the whole body has been read and validated.

### The reservation panel — data capture on the user's terms (R04, D07)

This is the part where a design can most easily betray a rule, so the rules are stated as invariants before the layout:

1. **No reservation field is ever required.** Not to save an item, not to attach a file, not to move a status.
2. **Moving an item to *gotowe* never asks for anything.** The status control is one click and stays one click. R02's counter counts statuses and is untouched by reservation data — a `done` item with no confirmation number is exactly as arranged as one with it, and no badge, tooltip, percentage or "incomplete" marker anywhere suggests otherwise.
3. **Nothing is ever a modal in the way, and nothing blocks.** The panel is inline, collapsed by default, and dismissible.
4. **No nagging, ever.** No empty-state prompt on the timeline, no "complete your reservation details" banner, no count of missing fields, no reminder. If the owner never fills one of these fields in his whole Malaysia trip, the app says nothing about it.

The panel itself: inside the item editor, below the notes field, a collapsed disclosure headed "Dane rezerwacji (opcjonalne)" / "Reservation details (optional)". Opened, it shows three controls — a free-text **confirmation number**; an **amount**; and a **currency** beside it. Nothing else.

The one moment it is offered rather than merely available: **the first time an attachment lands on an item, the panel auto-expands once**, with a single non-blocking line — "Masz przy sobie voucher? Możesz zapisać numer i koszt." / "Voucher in front of you? You can save the number and the cost." — because that is the one second in the whole product when the user is demonstrably looking at the data. Collapsing it records the dismissal for that item and it never auto-expands again. It stays reachable, permanently, from the same disclosure.

**Dates are not in this panel.** The reservation's dates are the item's own start day, times and `end_date`, edited in the controls that already exist a few rows above. The panel would otherwise offer a second, contradictory place to say when the hotel is booked for.

Day-level attachments get **no** reservation panel — a day is not booked; an item is.

### `/trips/:id` — the timeline, lightly touched

One addition only: a paperclip glyph with a count on any item card that has attachments, driven by `attachment_count`. **Costs, currencies and confirmation numbers are not shown on the timeline.** The export's PLN/EUR toggle, "SZACOWANY BUDŻET" tile and per-item prices all belong to totals and conversion, which are D12's, and putting a money column on the product's central screen would quietly make it a budget tracker, which D04 and the owner's own "przede wszystkim planowanie" say it is not.

### Cross-cutting

- **Bilingual, both first-class (R01, R09).** Every new string goes through i18next. Two new ICU plural keys, and the attachment count is a genuinely inflecting Polish counted noun — `{count, plural, one {# plik} few {# pliki} many {# plików} other {# pliku}}` — so it exercises the `few`/`many` split the foundation spec chose ICU for, and a test asserts both forms render.
- **File sizes and money go through `Intl`, never through concatenation.** Sizes render via a translated ICU key with the unit as an argument; amounts via `Intl.NumberFormat(locale, {style: 'currency', currency})`, so `1 250,00 zł` in Polish and `PLN 1,250.00` in English fall out of one call.
- **Accessibility.** The drop zone is a labelled file input; upload progress is `aria-live`; thumbnails carry the filename as alt text; the lightbox is a focus-trapped dialog returning focus to its trigger, closing on `Escape`; the delete confirmation names the file rather than saying "this item"; no state is conveyed by colour alone.
- **Session expiry mid-upload.** A `401` during an upload cannot be recovered the way the foundation spec's dialog draft is: a `File` handle cannot be restored across a navigation, and pretending otherwise would be a promise the browser will not keep. The app says so — the item's text draft is preserved by the existing mechanism, the file selection is not, and the message names which is which.

## 📝 Edge Cases & Failure Scenarios

| Case | Behaviour |
|---|---|
| A file over 10 MB | `413 attachment_too_large` before the body is read when `Content-Length` says so; while reading otherwise. The client pre-check catches the common case without a request |
| A zero-byte file | `422 malformed_upload` |
| A request with no `file` part, or with two | `422 malformed_upload` |
| Bytes that are not PDF, JPEG or PNG | `415 unsupported_file_type`, with a translated message naming the three accepted formats |
| `ticket.pdf` whose bytes are a JPEG | accepted, stored as `image/jpeg`, display name unchanged. The extension is never authoritative |
| `photo.jpg` whose bytes are an HTML page | `415 unsupported_file_type` |
| A PDF with no `%%EOF` in its last 1024 bytes (truncated upload) | `422 malformed_upload` |
| A PNG whose `IHDR` claims 60 000 × 60 000 | `415 unsupported_file_type` — the pixel bound, applied before any browser sees it |
| A filename containing `../`, a newline, or 4 000 emoji | normalised per the Security section: basename only, control characters stripped, truncated to 200 characters. Never a failure; the file is stored |
| A filename that normalises to empty | replaced with a generated name derived from the detected type |
| The same file uploaded twice to the same item | both are stored; `sha256` matches, so the UI may show a non-blocking "already attached" hint (slippable). **No deduplication and no refusal** — refcounted shared blobs are machinery, and refusing is wrong when a user genuinely wants two copies |
| The 21st attachment on one item | `409 attachment_limit_reached` |
| An upload that would push the trip past 250 MB | `409 trip_storage_quota_exceeded`, checked inside the insert's transaction |
| The 31st upload in ten minutes | `429 rate_limited`, counted in `upload_event` |
| Upload cancelled or the connection dropped mid-body | nothing is written; the row and the bytes are one transaction after full validation |
| Two tabs uploading to the same item at once | both succeed and both appear; there is no ordering claim beyond `created_at` |
| The item is deleted while its attachment list is open | the delete cascades; the next request answers `404` and the SPA returns to the day |
| An item is moved to another day of the same trip | its attachments move with it — they hang off `item_id`. Day attachments stay on the day, which is the point of having two parents |
| A trip is deleted | attachments and their bytes go with it, in the same transaction, no sweeper (see Data Model) |
| An attachment id from another trip in the path | `404`, identically to any other cross-owner access |
| A day or item id in the path that is not in this trip | `404 attachment_parent_missing` |
| `cost_amount` with no `cost_currency`, or the reverse | `422 invalid_cost` — and the UI defaults the currency so it does not arise |
| A negative cost, or one with three decimals | `422 invalid_cost` |
| A cost of exactly `0` | accepted. A free museum day is a real, arranged item with a real, arranged cost |
| A confirmation number of 4 000 characters | accepted and stored; it is free text, and the only thing a length rule could do is reject a real voucher code we did not anticipate. Rendered truncated with the full value available |
| An empty-string confirmation number | rejected by the `CHECK`; the API treats `""` as "clear the field" (`null`) |
| Session expires mid-upload | `401`; the text draft survives via the existing mechanism, the file selection does not, and the message says so |
| The database is unavailable | `503 service_unavailable`, as everywhere else; the attachment list shows a retry state, never an empty list — an empty list is indistinguishable from "you attached nothing" and would be a lie about the plan |
| A guest with a magic link requests attachment content | not reachable: no guest route exists in this spec. When the sharing spec adds one, it adds it at the `resolve_trip_access` seam, under the preconditions in A8 |

**Documented, not built.** Two behaviours are named so the next agent finds a decision rather than a gap. **Concurrent edits** remain last-write-wins, unchanged from the foundation spec — at one user (D15) optimistic locking is machinery without a failure to prevent. **There is no attachment undo**: delete is permanent, exactly as trip delete is, and the confirmation dialog is the whole safety net.

## 📝 Risks & Impact Review

- **Blast radius: one screen and one `PATCH`.** Every API change is additive under `BACKWARD_COMPATIBILITY.md` §1 — new endpoints, new *optional* response fields, new *optional* request fields, new error-code enum members. Nothing existing is removed, renamed, retyped, or given a new meaning; no status code changes for an existing condition; no validation is tightened on an existing input. §3 ("stored trip and itinerary documents") is respected in the strongest form: every existing stored trip keeps loading unchanged, because the columns added to `item` are nullable and mean nothing when absent.
- **Three migration-class decisions, all designed for the cheaper failure.** *Where the bytes live* — Postgres now, with the escape hatch designed as an additive `storage_backend` + `object_key` pair and a copy job rather than a rewrite (A2 ⚠). *What an attachment hangs off* — one table, two nullable FKs, a `CHECK`; widening to a third parent is additive, and this is the shape the deferred hub screen (A13) can query without a `UNION` (A5). *Where reservation data hangs* — on the item, with the dates being the item's existing span, so nothing in the system holds two answers to when a booking is (A6 ⚠).
- **Rollback story.** One Alembic revision with a working `downgrade`. Rolling it back leaves the walking skeleton exactly as it was — a timeline with statuses and a counter and no attachments — and destroys the attachments and reservation data, which is what rolling back this feature means. The frontend degrades in the same shape: the day detail without the attachment panels is the screen the foundation spec shipped.
- **The new risk this feature introduces is the upload surface itself**, and the Security section is the mitigation, in full, with two residual risks named rather than papered over: **no malware scanning** and **no EXIF stripping**. Both are tolerable at exactly one consumer who is also the uploader (D15) and both become preconditions the moment a guest can fetch a byte (A8).
- **Product-decision compliance, stated precisely.** This spec **implements** *Now* bullet 5 and **R04**; it does not defer either. It covers a strict subset of what remains of *Now* — chat (D03) and the magic link (D08, D09) are still in the first version and still cut from *this* slice under A05's sequencing authority. Nothing here contradicts an active Non-goal, Business rule or Decision, so no superseding row is required. Two places where the design export was followed *away* from a rule are worth naming: its nine reservation status labels lose to R02's three, and its budget totals lose to D12.
- **Calendar risk (A05) remains the real risk.** The slippable tail above names the cut line, and it deliberately does not include day-level attachments or any security control.
- **What this spec does not fix.** A03 — that a hand-maintained plan stays current enough to be trusted — is unchanged. An attachment the owner forgets to upload is still an attachment the app does not have, and the honest better answer to that is TripIt's forwarding address, which is D12's.

## 📝 Decisions in play

| Id | How this spec relies on it |
|---|---|
| **R04 / D07** | **Implemented, not deferred.** Confirmation number and cost are stored on the item; the dates are the item's existing span; every field is optional at every layer — schema, API and UI — and the UI never demands, blocks or nags |
| *Now* bullet 5 | **Implemented.** File and image attachments on the day detail view, for both parents the glossary names |
| Brief Key flows | The "arranging one item" flow now runs to its end: open day → open item → set details → attach → *gotowe* → the counter changes |
| R02 / D05 | Untouched, and defended: the counter counts statuses only, and reservation data never affects it. The export's nine reservation status labels are dropped |
| R08 / D14 | The whole Security section: no unauthenticated path, `get_owned_trip` on every route, CSRF on every unsafe method, derived content types, `404` over `403` |
| R01 / R09 | Both locales for every new string, including error codes via the enum test; ICU plurals for the attachment count; sizes and money through `Intl` |
| D04 / R07 | No live prices, no vendor comparison, no booking — a genuine exclusion, and the reason the export's price cards are dropped |
| R06 / D09 | One editor; attachments are the owner's, and no write path exists for anyone else |
| D12 / N01 | Parsing, Wallet export, cost totals and cost splitting are deferred, never excluded |
| D15 | One consumer, which is what makes "no malware scanning" and "no EXIF stripping" tolerable — and what makes them preconditions on the sharing spec |
| Walking-skeleton **A2**, **A4** | Owner-confirmed and relied on: the multi-stop shape is untouched, and the item time span is what carries R04's "dates" |
| A05 | The authority for every cut in the Scope table, and the source of the slippable tail |
| Brief **Q03** | **Answered here** — A2, A3, A4, A8, A9 |
| Brief **Q04** | **Answered here** — A7 |
| Brief Q01, Q02 | Left open; Q01 for want of network access, Q02 because nothing here builds to it |

**Nothing in this spec proposes to supersede an active entry.** The approval it needs is on its autonomous assumptions below.

## ⚠️ Resolved assumptions (autonomous defaults)

This spec was written in `--autonomous` mode. Each question below was resolved by the most reversible, smallest-scope answer available, and each is open to override before merge. **A2 and A6 carry `⚠ NEEDS HUMAN CONFIRMATION` and gate the merge.**

| # | Question | Resolved as | Rationale |
|---|---|---|---|
| A1 | One spec, or one for attachments and one for reservation data? | **One spec, four phases** | They are separable in principle — Phase 3 could ship alone — but R04 binds them at the requirement level ("stored when it arrives **with** material the user already has"), the capture surface lives inside the attach flow, and both land on the same screen. One milestone, one approval decision. The phases stay independently deployable so the split remains available |
| A2 | Where do the bytes live? (brief **Q03**) | **PostgreSQL `BYTEA`, in an `attachment_blob` table separate from the metadata** — ⚠ **NEEDS HUMAN CONFIRMATION** | One durable store, one backup, one credential, one failure mode; deleting a trip deletes its files transactionally with no orphan reaper; and no bucket to provision before 2026-09-30 (A05). The move to an object store is additive when it is justified — a `storage_backend` column, an `object_key` column, a copy job. Marked because the brief leaves Q03 explicitly open, because it is the one decision here that is a data migration rather than an addition, and because it is the choice a reviewer is most likely to disagree with |
| A3 | Which formats are accepted? (brief **Q03**) | **PDF, JPEG, PNG — and nothing else.** PKPASS, SVG, HEIC, WEBP, GIF, TIFF, archives, Office documents, HTML and plain text are all refused | Each accepted format must be identifiable from its bytes and safe for the browser to render. PKPASS — which the design export names — is a ZIP whose identity depends on trusting a filename and which renders as nothing without the Wallet export D12 defers, so it is **cut and said so**. SVG executes script. The rest are parser families bought for formats no ticket vendor issues. The design export's list is a generated mockup caption, not a requirement anyone stated |
| A4 | What size and quota limits? (brief **Q03**) | **10 MB per file**; 20 attachments per parent; 250 MB per trip; 2 GB per installation; 30 uploads / 10 min and 200 MB / hour per owner | Smaller than the export's 25 MB, and deliberately: a boarding pass is under 2 MB and a phone photograph under 8 MB, the bytes live in a database whose backup someone has to restore, and `BYTEA` is read whole into memory. Every number is a constant in code, changeable by a one-line PR — the *shape* is what matters, not the value |
| A5 | What does an attachment hang off — an item, a day, or either? | **Either: one `attachment` table with nullable `item_id` and `trip_day_id` and a `CHECK` that exactly one is set** | The glossary settles *that* both exist ("pinned to an item **or** a day"); this settles the shape. Real foreign keys and real cascades, which a polymorphic `(type, id)` pair gives up; no duplicated table, which two tables would cost; and widening to a trip-level parent later is one relaxed `CHECK`. Migration-class, but glossary-backed rather than invented, so it is not marked for confirmation — see Risks |
| A6 | Where does reservation data hang, and what exactly is stored? | **Three nullable columns on `item`** — `confirmation_number`, `cost_amount`, `cost_currency` — **and the reservation's *dates* are the item's existing time span, not new columns** — ⚠ **NEEDS HUMAN CONFIRMATION** | On the item, because hanging it on the attachment means deleting a voucher silently deletes the confirmation number, and two documents for one booking give one stay two costs. Dates on the item's span, because the foundation spec already refused to model the same journey twice and this is the same refusal. Marked because it is migration-class, because it is the shape any later cost-splitting feature (D12) builds on, and because only the owner knows whether he thinks of a reservation as a property of the plan item or of the document |
| A7 | Does the first version handle more than one currency? (brief **Q04**) | **Every stored amount carries an ISO-4217 code; there is no conversion, no total, no sum and no PLN/EUR toggle anywhere.** The input defaults to the trip's last-used currency, else `PLN` | This is the *smaller* thing, not the safer-bigger one. What makes multi-currency expensive is arithmetic — rates, a base currency, cross-currency sums — and none of that is in scope, because totals are D12's. What is left is a three-character column that costs nothing and an `Intl.NumberFormat` call. The alternative, a bare number whose unit lives in someone's head, is `BACKWARD_COMPATIBILITY.md`'s named worst case pre-installed. The export's toggle is dropped: it implies conversion. **Override note:** if the answer is "PLN only, forever", the change is to fix the column's `CHECK` — a one-line migration, not a redesign |
| A8 | Does a trip's magic link expose attachments? (brief **Q03**) | **No — not in the first version.** No unauthenticated read path exists in this spec. The content route resolves its caller through a single `resolve_trip_access` seam so the sharing spec can add guest access in one function | An unauthenticated bearer URL to a ticket PDF carrying a confirmation number is the highest-consequence thing this feature could leak, and this spec ships **no malware scanning** and **no EXIF stripping** — both tolerable for an owner reading his own files, neither tolerable for a link pasted into a group chat. Recorded as a **binding precondition on the sharing spec**: guest-visible attachments require, at minimum, revocable links, EXIF handling for images, and a decision on scanning |
| A9 | Can a magic link be revoked? (brief **Q03**) | **Out of this spec's surface — and recorded as a precondition rather than left open.** The sharing spec must ship revocation, and must ship it *before* any guest-visible attachment | Revocation is a property of the link, which this spec does not create; answering it here would be designing another spec's data model. Naming it as a precondition is the part that belongs here, because A8's answer is what makes it load-bearing |
| A10 | Is a PDF previewed inline in the app? | **No — download only.** The action says "Pobierz" / "Download" | Serving a PDF `inline` runs its JavaScript in this application's origin with the session cookie in scope. The real fix is a separate sandbox origin, and A12 fixes the deployment at one origin, one image, one certificate. This is the Security section's "cannot make it safe, so cut it" case, and it is named as a cut rather than dressed up as a same-origin sandboxed `<iframe>` |
| A11 | Is uploaded content scanned for malware? | **No.** Stated plainly in Security and in the PR body | At one consumer who is also the uploader (D15), scanning protects nobody from anybody. It becomes a precondition under A8. The alternative — wiring an AV service — adds an external call, a credential and a failure mode to a feature that currently makes none |
| A12 | Are images re-encoded, thumbnailed or EXIF-stripped server-side? | **No. The server never decodes an uploaded image.** Dimensions are read as two integers from the PNG `IHDR` / JPEG `SOF` header with stdlib code; no image library is installed | Decoding attacker-supplied bytes is the largest RCE surface in this problem space, and Pillow would be that decoder. The browser renders images in its own sandbox, which is what it is for. The cost is the retained EXIF, named as a residual risk and as a precondition under A8 |
| A13 | Is there a trip-level "Reservations & documents" hub screen? | **No — the day detail only** | *Now* bullet 5 names the day detail view, and A05 sequences the rest. The hub is a pure query over data this spec already stores — a two-hop join, no schema change — so it is an addition whenever it is wanted, never a migration. The export's `centrum_rezerwacji_i_dokument_w` informed the metadata this spec keeps; its screen is not built |
| A14 | Are duplicate uploads detected or deduplicated? | **`sha256` is stored; nothing is deduplicated and nothing is refused.** A non-blocking "already attached" hint is in the slippable tail | Refcounted shared blobs are real machinery for a saving measured in megabytes, and refusing a duplicate is wrong when the user wants two copies. The hash earns its column through integrity checking and through the hint |

## 📋 Phasing

Each phase is independently shippable and leaves the application working and deployed.

- **Phase 1 — Storage, validation and the API.** Backend only. Files can be uploaded, listed, downloaded and deleted through the API, with every security control in place. Nothing in the UI changes yet, and the phase is verifiable entirely by tests.
- **Phase 2 — The day detail attachment UI.** The day documents panel, the item attachment strip, upload with progress, download, delete, and the timeline paperclip badge. *Now* bullet 5 is met at the end of this phase.
- **Phase 3 — Reservation data (R04, D07).** The three item columns, the `PATCH` fields, the optional capture panel, and the "arranging one item" flow running to its end at *gotowe*. R04 is met at the end of this phase.
- **Phase 4 — The polish, and the slippable phase.** Drag-and-drop, the image lightbox, the duplicate hint.

## 📋 Implementation Plan

Every step is testable and leaves the application working. This structure is what `om-auto-implement-spec` hands to `om-auto-create-pr`.

### Phase 1 — Storage, validation and the API

1. One Alembic revision creating `attachment` (with the exactly-one-parent `CHECK`, both cascading FKs, the `content_type` and `byte_size` checks and the `sha256` index), `attachment_blob`, and `upload_event`; and adding `confirmation_number`, `cost_amount`, `cost_currency` plus the paired-nullability `CHECK` to `item`. Verify: an upgrade/downgrade round-trip test; a test that the database itself rejects an attachment with two parents, one with none, a fourth content type, and a cost amount without a currency.
2. `domain/uploads.py` — `sniff_type(head: bytes)`, the per-format structural checks, `png_dimensions` / `jpeg_dimensions` read from the header with stdlib code only, the 50 MPx bound, and `normalise_filename`. Verify: unit tests over a fixture corpus — a real minimal PDF, JPEG and PNG; a JPEG named `.pdf`; an HTML page named `.jpg`; an SVG; a PKPASS/ZIP; a truncated PDF with no `%%EOF`; a PNG whose `IHDR` claims 60 000 × 60 000; a zero-byte file; and filenames containing `../`, a newline, 4 000 emoji, and only dots. **No image library is added to `pyproject.toml`** — a test asserts that.
3. `domain/money.py` — amount/currency pairing, the non-negative and two-decimal rules, ISO-4217 shape. Verify: unit tests including `0`, three decimals, a negative, an amount alone, a currency alone, and `"pln"` lower-case.
4. `security/quota.py` — the per-owner rate and volume windows over `upload_event`, and the per-parent, per-trip and per-installation byte and count checks, all callable inside a transaction. Verify: tests that each limit engages at its boundary, that old rows are pruned, and that two concurrent uploads cannot both consume the last of a quota.
5. Eight new `ErrorCode` members with their `en.json` and `pl.json` keys. Verify: the foundation spec's existing enum test, which now covers them, plus `python3 scripts/check_locales.py` green.
6. `POST /trips/{tripId}/days/{date}/attachments` and `POST /trips/{tripId}/items/{itemId}/attachments`: `Content-Length` rejection before the read, byte counting during it, one part only, sniffing, structural check, quota inside the transaction, blob insert. Verify: API tests for a successful upload of each accepted type; for each refusal in step 2's corpus; for a `Content-Length` that lies (chunked, no length, oversized body); for two file parts; for a missing CSRF token; for another owner's trip answering `404`; and that the stored `content_type` is the derived one when the client sent a false header.
7. `GET …/attachments/{id}`, `GET …/attachments/{id}/content` with the full header set, and `DELETE …/attachments/{id}`. Verify: tests asserting **every** header in the Security section is present with its exact value; that a conditional request with the `ETag` answers `304`; that the delete removes the blob row; and that all three answer `404` for an attachment belonging to another trip.
8. `attachment_count` on the timeline payload, `attachments` on the day-detail payload, and the three reservation fields on the item serialiser and on `PATCH /items/{itemId}`. Verify: API tests that the count matches, that an item move carries its attachments, that a day attachment does not move, that clearing a cost requires clearing both halves, and that omitting a field leaves it unchanged.
9. Cascade behaviour end to end. Verify: tests that deleting an item, a day's parent trip, and a trip each remove the attachment rows **and** the blob rows in one transaction, and that no other trip's rows are touched.

### Phase 2 — The day detail attachment UI (*Now* bullet 5)

1. `src/api/attachments.ts` — the typed client with upload progress and abort. Verify: unit tests for the progress callback and for abort producing no row.
2. The `UploadDropzone` component: a labelled real file input, the client-side pre-check, the state machine (idle → selected → uploading → done / failed), the `aria-live` region, and per-file independence. Verify: component tests for each state, for a refused pre-check never issuing a request, for the translated message of each server error code, and for retry.
3. The day documents panel on `/trips/:id/days/:date`, with its empty state. Verify: component tests for the list, the empty state, and both locales.
4. The item attachment strip inside the item editor, plus the paperclip and count on the item row. Verify: component tests for an item with none, with one, and with several.
5. Download and delete, with a confirmation dialog naming the file. Verify: component tests for the confirmation copy in both locales and for focus returning to the trigger.
6. The attachment-count ICU plural key in both locales. Verify: a test asserting the Polish `few` (2 pliki) and `many` (5 plików) forms render, and `check_locales.py` green.
7. The paperclip badge on the timeline's item cards. Verify: a component test that it appears only when `attachment_count > 0`.

### Phase 3 — Reservation data (R04, D07)

1. The `ReservationPanel` disclosure inside the item editor — confirmation number, amount, currency; collapsed by default; nothing required. Verify: component tests that an item saves with every field empty, that the panel is collapsed on first render, and that no validation error can originate from an empty reservation field.
2. The one-time auto-expand after the first attachment lands on an item, with its dismissal remembered per item. Verify: component tests that it expands once, that collapsing it prevents a second expansion, and that it never appears for a day attachment.
3. Currency defaulting to the trip's last-used code, else `PLN`, and `Intl.NumberFormat` currency rendering in both locales. Verify: tests asserting `1 250,00 zł` under `pl` and `PLN 1,250.00` under `en` from one call, and that the default follows the last used value.
4. The status control's path to *gotowe* left untouched and unconditioned. Verify: a test that moving an item to `done` issues no reservation-related request, shows no prompt, and changes the counter — and a test that the counter is identical for two `done` items, one with reservation data and one without. **This is R04's "never demanded" expressed as a test.**
5. Assert the absence of nagging. Verify: tests that no "incomplete", "missing" or "complete your details" string exists in either locale file, and that neither the timeline nor the day detail renders any marker keyed on an empty reservation field.
6. End-to-end verification of the brief's own flow: open a day → open an item → set its details → attach a voucher PDF → save the confirmation number and cost → move the status to *gotowe* → the readiness counter changes. Verify: an integration test walking that path, with screenshots on the implementation PR.

### Phase 4 — Polish (the slippable phase)

1. Drag-and-drop over the drop zone, layered on the existing input. Verify: a component test that a drop and a picker selection produce the identical request.
2. The image lightbox — focus-trapped, `Escape` to close, focus returned. Verify: component tests for focus management and keyboard dismissal.
3. The non-blocking duplicate hint when an upload's `sha256` matches an existing attachment on the same parent. Verify: a component test that the hint appears and that the upload still succeeds.
