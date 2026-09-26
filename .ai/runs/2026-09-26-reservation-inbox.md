# Execution plan — the reservation inbox, Phase 1 (the inbox spine)

- Date: 2026-09-26 · Engine: `om-auto-create-pr` · Branch: `feat/reservation-inbox`
- Source doc: `.ai/specs/2026-09-26-reservation-inbox.md`
- Base: `main`

## Goal

Ship **Phase 1 of the reservation inbox — the inbox spine, with no model and no
model egress**. The owner forwards a confirmation to the account's inbound
address; AWS SES stores the raw MIME in a private S3 bucket and notifies one
signed HTTPS endpoint through SNS; the app ingests it, stores its text and its
PDF/JPEG/PNG parts on the shipped `attachment` table, applies the sender policy
with its quarantine and recovery actions, and shows it all on a new `/inbox`
screen where the owner can place an unrouted message on a trip by hand.

## Scope

**In** — the spec's `## 📋 Implementation Plan` → *Phase 1 — The inbox spine (no
model)*, all thirteen numbered steps, verbatim.

**Out, and why** — Phases 2, 3 and 4 of the same spec. This is **not** a scope
cut made by this run: the spec itself declares

> **Human gate before Phase 2, not a step inside it.** The brief's smallest test
> for **A07/A08** … needs material only he has, so no implementation engine can
> execute it. It is a precondition on starting the phase, and its result belongs
> back in this document. If the rule places poorly, the rule changes here before
> any code is written.

so writing Phase 2 code now would violate the spec being implemented. Phase 1 is
described by the spec as *"independently deployable without model egress"* and
*"independently implementable"*. Phases 3 and 4 depend on Phase 2's routing and
extraction, so they follow the same gate.

**Non-goals** (nothing here is touched): the model adapters and
`inbound_model_egress`, `inbound_action_item` and the approval/undo path, the
action-item sheet, `read-document` egress, the share link, the preview surfaces,
chat, and any change to the shipped trip/stage/day/item endpoints beyond the one
widened `attachment` `CHECK`.

## Risks

- **One widened `CHECK` on a shipped table.** `num_nonnulls(item_id,
  trip_day_id, inbound_message_id) = 1` is a widening — every existing row
  satisfies it — so it is safe against existing data with no backfill. The risk
  is the `downgrade`, which must **refuse** rather than delete while any
  attachment is parented to an inbound message. Step 1.1 tests exactly that.
- **One new public route.** `POST /api/v1/inbox/receipts/sns` is the single
  permission R10 grants. `PUBLIC_PATHS` and `test_route_protection.py`'s
  `test_the_public_allow_list_stays_small` must widen by exactly this path and
  nothing else — step 3.4 is that deliberate act, with forged-traffic tests.
- **The shipped installation byte cap.** `_installation_bytes` sums *every*
  attachment row, so inbox documents would crowd out the owner's own uploads the
  moment `inbound_message_id` exists. Step 2.4 excludes them and gives the inbox
  its own cap; a test fills one budget and proves the other still works.
- **No AWS is reachable from the suite.** Every SES/SNS/S3 interaction is tested
  against captured event fixtures and a stubbed S3 client. No test makes a
  network call, and the feature being unconfigured is a supported, tested state.
- **A07/A08 remain untested** — unchanged by this run, and the reason Phase 2 is
  gated rather than built.

## Implementation Plan

Phases group the spec's thirteen steps for commit hygiene; step numbering follows
the spec so a resume can be traced back to it. Each step is testable and leaves
the application working.

### Phase 1: Schema and configuration

1.1 (spec 1) The Alembic revision: `inbound_message`, `inbound_delivery_status`,
`inbound_trusted_sender`, `attachment.inbound_message_id` +
`attachment.sent_externally_at`, and the replaced three-parent `CHECK`. Models in
`db/models.py`. Tests: upgrade/downgrade round-trip against a database holding
both existing attachment parents; zero and two parents still rejected; the new
third parent accepted; `UNIQUE (owner_id, ses_message_id)` rejects duplicates;
`downgrade` refuses while inbox attachments remain.

1.2 (spec 2) Optional inbox configuration in `config.py` — unset means the
feature is off. README + `.ai/qa/test-env.env` documentation of the SES receipt
rule, MX, private encrypted S3 bucket, SNS HTTPS subscription, SQS dead-letter
queue, lifecycle and alarms. Fill `AGENTS.md`'s external-APIs row with the
inbound integration actually built and move that row from `STILL_OPEN` to
`RESOLVED` in `tests/test_docs_todos_resolved.py`. Tests: startup with nothing
set, no AWS call, `inbox_enabled=false`, documented names match `config.py`, no
credentials in logs.

### Phase 2: Domain, transport and ingestion

2.1 (spec 3) `domain/inbound.py` — pure: MIME part selection, HTML→text
reduction, filename/subject normalisation, the sender policy over SES verdicts,
truncation. Fixtures: plain text, HTML, PDF, unknown sender, failed and missing
DMARC, failed scan, a 40 MB message, eleven parts, `.ics`, script and tracking
pixel.

2.2 (spec 4) `uv add` the AWS SDK (lockfile in the same commit), then
`inbound/transport.py` + `inbound/ses.py` + the public SNS endpoint. Tests:
certificate-URL allow-list, signature, topic/region, subscription confirmation,
recipient, action type, bucket/prefix/key, bounded JSON, idempotent SES id;
invalid events touch neither S3 nor the database; transient DB failure is a
retryable 5xx.

2.3 (spec 5) Background S3 ingestion and the trip-less
`store_inbound_attachment`. Tests: duplicate SNS deliveries insert once; the RFC
`Message-ID` is never the key; S3 failure retries; accepted ingestion survives a
crash before the S3 delete; a rejected sender causes no GET; an unsupported part
is dropped while the text survives.

2.4 (spec 7) `security/quota.py` extended: inbound message and byte windows
separate from browser uploads, `_installation_bytes` excluding inbound rows, and
an inbox storage cap over exactly those rows. Tests: each boundary; an exhausted
window persists a `deferred` record without a GET and retries later; browser
uploads are never blocked.

2.5 (spec 8) `scheduler.py` — the ingestion/retry loop on its own thread and
`sessionmaker` under `pg_advisory_lock`, with clean shutdown and an S3-expiry
alarm. Tests: concurrent workers process once; a transient S3 failure records
`last_error`; the loop stays off when unconfigured; a hung S3 call delays neither
`GET /health` nor the SNS acknowledgement.

### Phase 3: The API, the gates and the boundary

3.1 (spec 6) `GET /inbox/messages/{id}/attachments/{attachmentId}/content` — the
owner-scoped content route reusing the shipped `_serving_headers`. Tests: its
response headers are **byte-identical** to the shipped trip-scoped route's for
the same file; `404` for another owner's message and for an attachment not on
this message; a conditional request answers `304`.

3.2 (spec 9) `api/inbox.py` — the owner inbox routes and the quarantine recovery
routes. Hand placement changes only `inbound_message.trip_id`. Tests: owner-only
access and CSRF; *Trust this sender* and *Release this message* use only the
recorded SES id and S3 key, re-check metadata, update the quarantined row in
place, and answer explicitly when the S3 object expired.

3.3 (spec 10) The three error-code gates: `STATUS_FOR_CODE`, non-empty keys in
both `en.json` and `pl.json`, and a regenerated `frontend/src/api/errorCodes.ts`.
Tests: those three plus `check_locales.py`, green.

3.4 (spec 11) The boundary assertions as their own step: `PUBLIC_PATHS` and
`test_route_protection.py` widen by exactly `POST /api/v1/inbox/receipts/sns`;
every other new route resolves `get_current_session` through `get_current_owner`.
Tests: forged SNS traffic creates no delivery row, triggers no S3 GET and changes
no plan; no guest serializer carries an inbox field.

3.5 (spec 12) The quarantine's 30-day purge and S3 cleanup. Tests: expired
quarantine rows and their private MIME objects are removed; accepted objects are
deleted after commit; deferred objects are alarmed before expiry; a released
message survives as a normal accepted message.

### Phase 4: The `/inbox` screen

4.1 (spec 13) The screen — the three regions including quarantine *Show*, *Trust
this sender* and *Release this message*, the empty state naming the address, SES
delivery/ingestion status, hand placement, and the `AppShell` badge as one
optional prop. Tests: a component test per region, the unconfigured state,
release from S3, both locales, the ICU plural's Polish `few`/`many` forms, and
`check_css_tokens.py` + `check_contrast.py` green.

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Schema and configuration

- [ ] 1.1 The Alembic revision and the five new/extended models
- [ ] 1.2 Optional inbox configuration, its documentation and the AGENTS.md row

### Phase 2: Domain, transport and ingestion

- [ ] 2.1 `domain/inbound.py` — the pure MIME, text and sender-policy rules
- [ ] 2.2 The AWS SDK, `inbound/transport.py`, `inbound/ses.py` and the SNS endpoint
- [ ] 2.3 Background S3 ingestion and `store_inbound_attachment`
- [ ] 2.4 Inbound windows and the separated installation byte cap
- [ ] 2.5 `scheduler.py` — the ingestion and retry loop

### Phase 3: The API, the gates and the boundary

- [ ] 3.1 The owner-scoped inbox attachment content route
- [ ] 3.2 `api/inbox.py` — the owner inbox and quarantine recovery routes
- [ ] 3.3 The three error-code gates
- [ ] 3.4 The `PUBLIC_PATHS` widening and the boundary assertions
- [ ] 3.5 The quarantine purge and S3 cleanup

### Phase 4: The `/inbox` screen

- [ ] 4.1 The `/inbox` screen, its three regions and the `AppShell` badge
