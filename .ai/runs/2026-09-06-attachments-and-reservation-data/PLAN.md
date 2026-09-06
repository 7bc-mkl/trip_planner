# Execution plan — attachments and reservation data

- Run: `2026-09-06-attachments-and-reservation-data`
- Branch: `feat/attachments-and-reservation-data`
- Base: `main` (at `4ef73d9`)
- Engine: `om-auto-create-pr-loop` (steps: 28, `--loop`: no — routed by the 20-Step threshold)
- Source spec: `.ai/specs/2026-09-05-attachments-and-reservation-data.md`
- Started: 2026-09-06T16:27Z

## Tasks

> Authoritative status table. `Status` is one of `todo` or `done`. On landing a Step, flip `Status` to `done` and fill the `Commit` column with the short SHA. The first row whose `Status` is not `done` is the resume point for `om-auto-continue-pr-loop`. Step ids and `Exec` cells are immutable once the plan is committed — per-Step commits touch only `Status` and `Commit`.

| Phase | Step | Title | Exec | Status | Commit |
|-------|------|-------|------|--------|--------|
| 1 | 1.1 | Attachment, AttachmentBlob and UploadEvent models with their Alembic revision | dispatch:capable | done | `a76361d` |
| 1 | 1.2 | `domain/uploads.py` — byte sniffing, structural checks, dimensions, filename normalisation | dispatch:capable | done | `223399b` |
| 1 | 1.3 | `domain/money.py` — amount/currency pairing and ISO-4217 validation | dispatch:cheap | done | `17215fb` |
| 1 | 1.4 | `security/quota.py` — per-owner rate/volume windows and locked byte quotas | dispatch:capable | done | `8cc3dc2` |
| 1 | 1.5 | Nine new `ErrorCode` members with both locales' keys | dispatch:cheap | done | `da84350` |
| 1 | 1.6 | The two upload endpoints, in the fixed check order | dispatch:capable | done | `9c47672` |
| 1 | 1.7 | Attachment metadata, content download and delete routes | dispatch:capable | done | `c4d5f2a` |
| 1 | 1.8 | `attachment_count`, day/item `attachments` and the three reservation fields on the serialisers and `PATCH` | dispatch:capable | done | `0f1cb4e` |
| 1 | 1.9 | Cascade behaviour end to end | dispatch:cheap | done | `6a820b4` |
| 1 | 1.10 | The `days_have_attachments` guard on the shipped `PATCH /trips/{tripId}` | dispatch:capable | done | `763a459` |
| 2 | 2.1 | `src/api/attachments.ts` — typed client with upload progress and abort | dispatch | todo | — |
| 2 | 2.2 | `UploadDropzone` — labelled file input, pre-check, state machine, `aria-live` | dispatch:capable | todo | — |
| 2 | 2.3 | The day documents panel on `/trips/:id/days/:date` | dispatch | todo | — |
| 2 | 2.4 | The item attachment strip inside the item editor | dispatch | todo | — |
| 2 | 2.5 | Download and delete, with a confirmation dialog naming the file | dispatch | todo | — |
| 2 | 2.6 | The attachment-count ICU plural key in both locales | dispatch:cheap | todo | — |
| 2 | 2.7 | The paperclip badge on the timeline's item cards | dispatch:cheap | todo | — |
| 2 | 2.8 | Preview-surface reconciliation (no-op unless `features/preview/` exists) | inline | todo | — |
| 3 | 3.1 | The `item` reservation columns on their own Alembic revision | dispatch:capable | todo | — |
| 3 | 3.2 | The `ReservationPanel` disclosure inside the item editor | dispatch | todo | — |
| 3 | 3.3 | The disclosure's placement and its never-auto-expanded guarantee | dispatch | todo | — |
| 3 | 3.4 | Currency defaulting to `PLN` and `Intl.NumberFormat` rendering | dispatch:cheap | todo | — |
| 3 | 3.5 | The status control's path to *done* left untouched and unconditioned | dispatch:cheap | todo | — |
| 3 | 3.6 | Assert the absence of nagging | dispatch:cheap | todo | — |
| 3 | 3.7 | End-to-end verification of the brief's own flow | inline | todo | — |
| 4 | 4.1 | Drag-and-drop layered on the existing input | dispatch | todo | — |
| 4 | 4.2 | The image lightbox — focus-trapped, `Escape` to close | dispatch | todo | — |
| 4 | 4.3 | The non-blocking duplicate hint | dispatch:cheap | todo | — |

## Goal

Implement `.ai/specs/2026-09-05-attachments-and-reservation-data.md` in full: the owner can attach
PDFs, JPEGs and PNGs to a day or to an item, download and delete them, and record a reservation's
confirmation number and cost on the item itself — completing *Now* bullet 5 and R04. Everything is
additive to the shipped walking skeleton except one deliberate narrowing of `PATCH /trips/{tripId}`.

## Scope

- **Backend** — `db/models.py` (three new models), two Alembic revisions, `domain/uploads.py`,
  `domain/money.py`, `security/quota.py`, `api/attachments.py`, and extensions to `api/items.py`,
  `api/trips.py`, `api/schemas.py`, `errors.py`.
- **Frontend** — `src/api/attachments.ts`, five new components under `src/features/trips/`,
  extensions to `ItemDialog.tsx`, `DayDetailPage.tsx`, `ItemRow.tsx`, `src/styles/components.css`
  and both locale files.
- **Tooling** — `scripts/check_contrast.py` gains a declared pair only if a new text-on-colour pair
  is actually introduced (the spec expects the shipped `--danger-surface` pair to suffice).
- **Dependencies** — `python-multipart` is required for FastAPI's `UploadFile`/`Form` support and is
  not currently in `backend/pyproject.toml`. It is added via `uv add` in Step 1.6, with `uv.lock`
  updated in the same commit (AGENTS.md, Dependencies row).

## Non-goals

Explicitly not touched by this run, each because the spec says so:

- Guest/magic-link access to attachments (A8) — no unauthenticated read path is added.
- Malware scanning (A11), EXIF stripping and any server-side image decoding (A12).
- Inline PDF preview (A10) — download only.
- Deduplication or refusal of duplicate uploads (A14) — only the non-blocking hint in 4.3.
- A trip-level "Reservations & documents" hub screen (A13).
- Cost totals, sums, currency conversion or any budget surface (D12, A7).
- Attachment rename or `PATCH`; attachment undo.
- Optimistic locking — concurrent edits stay last-write-wins (D15).

## Risks

- **The upload surface is the feature's own new risk.** Mitigated exactly as the spec's Security
  section specifies: derived content types, no server-side decoding, the full response-header set,
  `Content-Disposition: attachment` universally, and limits enforced before the body is read.
- **Two migration-class decisions** (A2 bytes in `BYTEA`; A6 reservation data on `item`) are both
  owner-confirmed on 2026-09-06, so neither is an open assumption this run must gate on.
- **Step 1.10 edits shipped code.** The existing `days_have_items` suite is its regression guard and
  must keep passing unmodified.
- **`pytest` skips silently without a reachable PostgreSQL.** A local server is running on
  `localhost:55432` (`deploy/compose.dev.yml`); every gate run must be read for skips, not just for
  a green exit code.
- **The dispatch safety checkpoint fires after ~20 consecutive successful Steps.** If it fires, the
  run halts with `Status: in-progress`, the PR stays a draft, and the user resumes with
  `om-auto-continue-pr-loop`.

## External References

None — no `--skill-url` was passed.

## Implementation Plan

Every Step is exactly one commit. Step titles match the Tasks table verbatim. Where the spec's own
Implementation Plan states verification, that verification is part of the Step.

### Phase 1 — Storage, validation and the API

**1.1 Attachment, AttachmentBlob and UploadEvent models with their Alembic revision.**
Add `Attachment`, `AttachmentBlob` and `UploadEvent` to `backend/trip_planner/db/models.py` in the
house style (docstrings that argue the shape, `PgUUID`, `CheckConstraint` names prefixed `ck_`), and
one Alembic revision `0005_attachment.py` on top of `0004_item`. `attachment` carries the
exactly-one-parent `CHECK ((item_id IS NULL) <> (trip_day_id IS NULL))`, both cascading FKs indexed,
the `content_type IN ('application/pdf','image/jpeg','image/png')` check, the
`byte_size > 0 AND byte_size <= 10485760` check and a non-unique `sha256` index. `attachment_blob`
is `attachment_id` UUID pk/fk cascade plus `data BYTEA NOT NULL`. `upload_event` mirrors
`login_attempt`: `BIGSERIAL` pk, indexed `owner_id` FK cascade, indexed `occurred_at`, `byte_size`.
**The `item` reservation columns are deliberately not in this revision** — they are Phase 3's, so
that phase rolls back alone. Verify: extend `tests/test_migrations.py` with an upgrade/downgrade
round trip; add `tests/test_models_attachment.py` asserting the database itself rejects an
attachment with two parents, one with none, and a fourth content type.

**1.2 `domain/uploads.py` — byte sniffing, structural checks, dimensions, filename normalisation.**
A pure module, no database and no I/O: `sniff_type(head: bytes)` returning the derived content type
or `None`; the per-format structural checks (PDF `%PDF-` with version `1.0`–`2.0` and an `%%EOF`
within the last 1024 bytes and length ≥ 100; JPEG `FF D8 FF` with the marker chain walked in stdlib
code to the first `SOF0`–`SOF3` and a trailing `FF D9`; PNG signature with a first `IHDR` chunk
whose CRC verifies); `png_dimensions` / `jpeg_dimensions` reading the header integers only; the
25 MPx bound; and `normalise_filename` implementing the six numbered steps of the spec's Filenames
section, including the separate ASCII `Content-Disposition` fallback restricted to `[A-Za-z0-9._-]`.
**No image library is added to `pyproject.toml`.** Verify: `tests/test_domain_uploads.py` over a
fixture corpus — a real minimal PDF, JPEG and PNG; a JPEG named `.pdf`; an HTML page named `.jpg`;
an SVG; a PKPASS/ZIP; a truncated PDF with no `%%EOF`; a PNG whose `IHDR` claims 60 000 × 60 000; a
zero-byte file; and filenames containing `../`, a newline, 4 000 emoji, only dots, and `a";x=".pdf`.
A test asserts no image library is a declared dependency.

**1.3 `domain/money.py` — amount/currency pairing and ISO-4217 validation.**
Pure functions over `Decimal | None` and `str | None`: the paired-nullability rule, the non-negative
rule, at most two decimal places, and the `^[A-Z]{3}$` shape. Verify:
`tests/test_domain_money.py` including `0`, three decimals, a negative, an amount alone, a currency
alone, and lower-case `"pln"`.

**1.4 `security/quota.py` — per-owner rate/volume windows and locked byte quotas.**
Modelled on `security/rate_limit.py`. Two callables usable **before** the body is read
(30 uploads / 10 min and 200 MB / hour per owner, counted over `upload_event`, pruning rows outside
the window) and the in-transaction checks: attachments per parent (20), bytes per trip (250 MB) and
bytes per installation (2 GB), each taken under `pg_advisory_xact_lock` — `hashtext(trip_id)` for
the trip key and a fixed key for the installation. Verify: `tests/test_quota.py` — each limit
engages at its boundary; old rows are pruned; the rate window refuses without reading a body; and
two genuinely concurrent transactions cannot both consume the last of a trip's quota (a test that
fails against an unlocked `SUM`).

**1.5 Nine new `ErrorCode` members with both locales' keys.**
`attachment_too_large` (413), `unsupported_file_type` (415), `malformed_upload` (422),
`attachment_limit_reached` (409), `trip_storage_quota_exceeded` (409), `rate_limited` (429),
`invalid_cost` (422), `invalid_reservation_field` (422), `days_have_attachments` (409) — each with
its `STATUS_FOR_CODE` entry, its `error.<code>` key in `en.json` and `pl.json`, and the regenerated
`frontend/src/api/errorCodes.ts`. Verify: the existing `tests/test_errors.py` now covers them, and
`python3 scripts/check_locales.py` is green.

**1.6 The two upload endpoints, in the fixed check order.**
`POST /trips/{tripId}/days/{date}/attachments` and `POST /trips/{tripId}/items/{itemId}/attachments`
in a new `api/attachments.py`, both under `get_owned_trip`. Add `python-multipart` via `uv add` and
commit `uv.lock` in the same commit. The order is fixed and is the security control: authenticate →
check the rate window → reject on `Content-Length` → read and count the body → exactly one part
named `file` → sniff → structural check → open the transaction → advisory lock → re-check the window
and the byte quotas → insert metadata and blob. The stored `content_type` is always the derived one.
Verify: `tests/test_attachments_api.py` — a successful upload of each accepted type; each refusal
from 1.2's corpus; a lying/absent `Content-Length` (chunked, oversized body); two file parts; a
missing CSRF token; another owner's trip answering `404`; and the derived type winning over a false
client header.

**1.7 Attachment metadata, content download and delete routes.**
`GET /trips/{tripId}/attachments/{id}`, `GET …/content` and `DELETE …/{id}` (204). The content route
serves the full header set from the spec's Security section verbatim, including
`Content-Disposition: attachment; filename="<ascii>"; filename*=UTF-8''<rfc5987>`, `nosniff`, the
`default-src 'none'; sandbox` CSP, `Cross-Origin-Resource-Policy: same-origin`,
`Referrer-Policy: no-referrer`, `Cache-Control: private, no-cache` and the strong `ETag`. Verify:
tests asserting **every** header with its exact value; a conditional request with the `ETag`
answering `304`; the delete removing the blob row; and all three answering `404` for an attachment
belonging to another trip.

**1.8 `attachment_count`, day/item `attachments` and the three reservation fields on the serialisers
and `PATCH`.** `attachment_count` per item on the timeline payload; `attachments` arrays on the day
and on each item of the day-detail payload. Counts are aggregated in one query, never per item.
Verify: API tests that the count matches for zero, one and several files, that an item move carries
its attachments, that a day attachment does not move, and that neither payload issues a query per
item or reads `attachment_blob`.

**The reservation half of this Step landed in 3.1, not here** (decision recorded in `NOTIFY.md`,
2026-09-06). `confirmation_number`, `cost_amount` and `cost_currency` are serialised from `item`
columns that Step 3.1 adds on its own Alembic revision — deliberately, so Phase 3 rolls back alone
(A1). Adding them to `ItemRead`/`ItemUpdate` here would have required either pulling that migration
forward into Phase 1 or serialising columns that do not exist. So the contract half moved to the
Step that owns the columns rather than the phase split being broken for it.

**1.9 Cascade behaviour end to end.** Verify: tests that deleting an item, a day's parent trip, and
a trip each remove the attachment rows **and** the blob rows in one transaction, and that no other
trip's rows are touched. Test-only Step unless a cascade proves missing.

**1.10 The `days_have_attachments` guard on the shipped `PATCH /trips/{tripId}`.**
`_refuse_if_days_would_be_lost` in `backend/trip_planner/api/trips.py` currently drops a day with no
items silently; narrow that to "no items **and** no attachments" by adding a sibling refusal raising
`409 days_have_attachments` with the dates named. Verify: shortening a range past a day holding a
voucher and no items answers `409` and changes nothing; shortening past a genuinely empty day still
removes it; and the existing `days_have_items` tests pass **unchanged**.

### Phase 2 — The day detail attachment UI (*Now* bullet 5)

**2.1 `src/api/attachments.ts` — typed client with upload progress and abort.**
`fetch` cannot report upload progress, so this one client uses `XMLHttpRequest` while keeping
`ApiError` and the CSRF header contract of `src/api/client.ts` — the error envelope is parsed
through the same shape so a caller sees one error type. Typed `Attachment`, upload for both parents,
metadata, content URL, delete. Verify: unit tests for the progress callback and for abort producing
no row.

**2.2 `UploadDropzone` — labelled file input, pre-check, state machine, `aria-live`.**
A real `<label>` over a real `<input type="file">` with `accept=".pdf,.jpg,.jpeg,.png"`, the
client-side extension and size pre-check (a convenience, never the reason a file is refused), the
state machine idle → selected → uploading → done / failed, per-file independence, and an
`aria-live="polite"` region announcing progress and completion. CSS in `src/styles/components.css`
uses only `--hairline-strong` (dashed outline), `--surface-sunken` (drag-over fill) and
`--radius-lg`; the failure pill reuses the shipped `--danger-surface` / `--on-danger-surface` pair.
Verify: component tests for each state, for a refused pre-check never issuing a request, for the
translated message of each server error code, and for retry — plus
`python3 scripts/check_css_tokens.py` and `python3 scripts/check_contrast.py` green, adding a
declared pair to the contrast table in this same Step if one is genuinely new.

**2.3 The day documents panel on `/trips/:id/days/:date`.**
`DayAttachments.tsx`, below the item list, headed "Załączniki i dokumenty dnia" / "Day files and
documents", with the shipped `.empty-state` recipe for its empty state and the dropzone's action
labelled "Dodaj plik / zdjęcie / bilet" / "Add file, photo or ticket". An attachment renders as a
card row at `--radius-lg`: a lazy-loaded original-image preview or the `<Icon>` document glyph, the
filename, the size through an ICU key with the unit as an argument. Verify: component tests for the
list, the empty state, and both locales.

**2.4 The item attachment strip inside the item editor.**
`ItemAttachments.tsx` hosted by `ItemDialog.tsx`, plus the paperclip and count on the item row.
Verify: component tests for an item with none, with one, and with several.

**2.5 Download and delete, with a confirmation dialog naming the file.**
Reuse the shipped `ConfirmDialog` / `.dialog--confirm` treatment; the download action is
`.button-quiet` and says "Pobierz" / "Download", never "Preview"; delete is `.button-danger`.
Verify: component tests for the confirmation copy in both locales and for focus returning to the
trigger.

**2.6 The attachment-count ICU plural key in both locales.**
`{count, plural, one {# plik} few {# pliki} many {# plików} other {# pliku}}` and its English
counterpart. Verify: a test asserting the Polish `few` (2 pliki) and `many` (5 plików) forms render,
and `check_locales.py` green.

**2.7 The paperclip badge on the timeline's item cards.**
`ItemRow` gains one **optional** prop, `attachmentCount?`. Verify: a component test that it appears
only when `attachment_count > 0`, and that `ItemRow`'s existing callers that pass no count render
exactly as before.

**2.8 Preview-surface reconciliation (no-op unless `features/preview/` exists).**
If `frontend/src/features/preview/` exists when this Step runs, delete this feature's two preview
surfaces and update the design-system spec's `data-preview` census from four surfaces to two. It
does not exist today, so this Step is expected to be **recorded as a no-op** rather than deleted —
a later reader must find the decision, not a gap. Verify: a `grep` for `data-preview` and the
recorded outcome in `NOTIFY.md`.

### Phase 3 — Reservation data (R04, D07)

**3.1 The `item` reservation columns on their own Alembic revision.**
`0006_item_reservation.py` adding `confirmation_number TEXT NULL`, `cost_amount NUMERIC(12,2) NULL`
and `cost_currency CHAR(3) NULL` with the length, non-negative, ISO-4217 and paired-nullability
`CHECK`s, and the matching columns on `Item`. Nullable, no default, no backfill. Verify: an
upgrade/downgrade round trip against a database already holding items and attachments; tests that
the database itself rejects a cost amount without a currency, a negative amount, and a
501-character confirmation number.

**This Step also carries the API half moved out of 1.8**, in the same commit as the columns it
depends on: `confirmation_number`, `cost_amount` (a `Decimal` on the wire, never a `float`) and
`cost_currency` on `ItemRead` — on **both** payloads, so the timeline's item and the day detail's
item stay one shape — and as three optional fields on `ItemUpdate`, cleared with an explicit `null`
and left alone when omitted through the existing `model_fields_set` / `NULLABLE_FIELDS` mechanism.
The cost halves must be supplied and cleared together or `422 invalid_cost`, routed through
`domain/money.py`; a confirmation number over 500 characters is `422 invalid_reservation_field`;
`""` means clear, because the database `CHECK` rejects it. No `reservation_start`/`reservation_end`
of any kind — the reservation's dates are the item's existing span. Verify, in addition to the
migration tests above: that clearing a cost requires clearing both halves, that one half alone is
`422 invalid_cost`, and that omitting a reservation field leaves it unchanged.

**3.2 The `ReservationPanel` disclosure inside the item editor.**
Confirmation number, amount, currency; collapsed by default; nothing required. Verify: component
tests that an item saves with every field empty, that the panel is collapsed on first render, and
that no validation error can originate from an empty reservation field.

**3.3 The disclosure's placement and its never-auto-expanded guarantee.**
Directly beneath the item's attachment list, its label and the word *optional* visible while
collapsed. Verify: component tests that it is collapsed on every render including immediately after
an upload, that **nothing** in the application ever opens it programmatically, and that it does not
exist at all for a day-level attachment list.

**3.4 Currency defaulting to `PLN` and `Intl.NumberFormat` rendering.**
Verify: tests asserting `1 250,00 zł` under `pl` and `PLN 1,250.00` under `en` from one call.

**3.5 The status control's path to *done* left untouched and unconditioned.**
Verify: a test that moving an item to `done` issues no reservation-related request, shows no prompt,
and changes the counter — and a test that the counter is identical for two `done` items, one with
reservation data and one without. This is R04's "never demanded" expressed as a test.

**3.6 Assert the absence of nagging.**
Verify: tests that no "incomplete", "missing" or "complete your details" string exists in either
locale file, and that neither the timeline nor the day detail renders any marker keyed on an empty
reservation field.

**3.7 End-to-end verification of the brief's own flow.**
Open a day → open an item → set its details → attach a voucher PDF → save the confirmation number
and cost → move the status to *gotowe* → the readiness counter changes. Verify: an integration test
walking that path via `om-integration-tests`, with screenshots posted on the implementation PR.

### Phase 4 — Polish (the slippable phase)

**4.1 Drag-and-drop layered on the existing input.** Verify: a component test that a drop and a
picker selection produce the identical request.

**4.2 The image lightbox — focus-trapped, `Escape` to close.** Verify: component tests for focus
management and keyboard dismissal.

**4.3 The non-blocking duplicate hint.** Shown when an upload's `sha256` matches an existing
attachment on the same parent. Verify: a component test that the hint appears and that the upload
still succeeds.
