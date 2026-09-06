# Read-only trip sharing — one magic link per trip

- Date: 2026-09-05 · Revised 2026-09-06 against the merged codebase · Author: `om-auto-write-spec` (autonomous) · Status: draft, gated on the assumptions below and on the proposed decision row **D16**
- Source brief: `.ai/specs/product-brief.md` (signed 2026-09-05)
- **Builds on code that now exists.** `.ai/specs/2026-09-05-walking-skeleton.md` is merged and *implemented* (PRs #2, #6), and `.ai/specs/2026-09-06-design-system-adoption.md` is merged and implemented (PRs #10, #11). This document was first written against an empty repository; it has been revised to name the modules, components, tokens and tests that are actually there. Every cross-cutting rule those two specs establish — focus traps, `Intl` formatting, `<html lang>`, status chips as translated text plus `data-status`, the `503` retry state, spanning items rendered once, the design system's token vocabulary — applies unchanged and is **not** restated here
- Adjacent, in flight: `.ai/specs/2026-09-05-attachments-and-reservation-data.md` (PR #4, still a draft). This spec does not wait for it; it defines the tripwire (below) that forces its new fields and routes to get an explicit sharing decision
- **The share surface was deliberately left unbuilt for this spec.** The design-system spec's workstream B would have stood up an inert State A share dialog; the owner cut its Phase 5 at the safety checkpoint ("Skip 5, do 6"), and `frontend/src/styles/screens.css` carries a comment reserving the `Shared` chip's place and naming PR #3 — this document — as its owner. So there is no preview to replace: this spec builds the surface for real, in its reserved slot
- Visual reference: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/g_wny_pulpit_i_o_czasu` for the "Udostępnij" button's position, and the **running application** for everything else. The guest view has no mockup in the export; it is designed here, in the adopted design system
- Mode: `om-spec-writing --autonomous`. Every question this spec answered on its own is listed under **Resolved assumptions (autonomous defaults)** and is open to override before merge.

## 📝 TLDR

The owner presses "Udostępnij" on a trip's timeline and gets one link. Anyone holding that link opens the same timeline and the same readiness counter in a browser, in Polish or English, without an account, without a cookie, and without the ability to change one character of the plan. The owner can see the link again, copy it again, and revoke it; revoking is permanent for that link and a new one can be generated afterwards.

This is the third slice of the brief's *Now* scope and it is mandated, not optional: D08 fixes the shape ("jeden dla projektu, read only w v1") and D09 fixes the permission model (one editor, guests read). **Nothing this document builds is cut, and nothing D08 or D09 mandate is deferred here.**

It deserves a careful spec rather than a CRUD ticket because it opens the product's first unauthenticated surface on the public internet (D14). R08 is written in two halves — *no screen showing a plan is reachable without either an owner session or a trip's magic link*. The walking skeleton built the first half; this spec builds the second. A guessable link, a leaked link, or a link that quietly carries more than the owner thinks it carries is a published plan.

## 📝 Problem Statement

P2, in the brief's own words: *there is no good way to share the state of the plans with other people*. A plan held in someone's head, their mailbox and a partial spreadsheet cannot be shown to a companion without retelling it. The brief's Key flows section describes the whole interaction in one line — *the owner sends the trip's link to a companion → the companion opens the same timeline and counter, read-only → any reaction happens outside the app* — and notes that it is **not in the design export**, which shows only an "Udostępnij" button.

**Why this ships now, and what it is not justified by.** The brief's Definition of Ready addendum is explicit: *every ticket whose justification is "so that other people can use it" is out of scope until A01 is tested — the sharing link in Now is there because the owner wants to show his own plan, not because a second user was found*. This feature's justification is therefore **P2 and D08**, not A01. A01 is accepted untested by D15 and nothing here depends on it: the guest is not a user of the product, has no account, and the product gains no second user by shipping this. A06 ("a read-only link is enough for travel companions") is likewise untested — and this feature is the *instrument* of A06's own smallest test (*send the Malaysia link to whoever travels along and count how many ask to change something*), which is a further reason to build read-only first and hear the requests rather than design comments (D09, D12) against a guess.

Evidence and its limits, carried forward honestly: P2 is an `[INTERVIEW]` claim from one session with one person who is also the builder, with no frequency and no cost attached. There is no benchmark data at all (brief Q01, still open).

## 📝 Scope

### In scope

| # | Capability | Contract it serves |
|---|---|---|
| S1 | Exactly one **active** magic link per trip, minted by the owner, enforced structurally rather than by convention | D08, R05 |
| S2 | The link grants **read-only** access to the trip's timeline and its readiness counter, to a recipient with no account and no session | D08, R05, R06, D09 |
| S3 | The **guest view** — designed here, since the export has none — reusing the owner's timeline components read-only rather than building a second timeline | brief Key flows, "Future state — sharing" |
| S4 | The **owner's side**: generating the link, seeing it again later, copying it, and knowing at a glance that a trip is shared | the brief's "Udostępnij" affordance |
| S5 | **Revocation** — the owner can end a link's life, and an ended link says so rather than disappearing | R05 (undecided → decided by D16 below); `BACKWARD_COMPATIBILITY.md` §3 |
| S6 | The **security boundary**: exactly one new unauthenticated route family, enumerable, with an explicit payload projection deciding what a guest may see | R08, D14 |
| S7 | Polish and English, both first-class, for a guest who never chose a language in this product; `scripts/check_locales.py` green | R01, R09 |

### Out of scope — and the honest authority for each cut

**No row in this table is authorised by A05.** A05 is the brief's mechanism for sequencing the *Now* list under calendar pressure, and this milestone uses it for nothing: everything D08 and D09 mandate is built here. Every cut below is decision-backed, which is a different thing and is kept a different thing deliberately.

| Not built here | Authority |
|---|---|
| Guest comments and suggestions on a shared plan | **D09**, which settled it: said first as an optional extra ("z **ew.** możliwością skomentowania") and then closed with "read only w v1". **D12** puts it on the *Later* list by name |
| Several people editing one trip; a permissions or roles model; invitations | **R06 / D09** — a trip has exactly one editor, its owner |
| Public plans as inspiration; discovery; anything indexable | **D12**, *Later*. This spec actively works against it — the guest page is `noindex` |
| The assistant and its suggestions on the shared view | It does not exist yet in any surface, so there is nothing to expose. When it ships, D04 / R07 bound it |
| A second owner login path; "sign in with this link"; converting a guest into an account | **R08**, explicit that the magic link is *for guests rather than a second owner login path*. The guest endpoint sets no cookie and creates no session |
| Link expiry as a policy | Decided against by **D16** below, with revocation as the control. R05 records expiry as undecided, so this is a decision being taken, not a mandate being deferred |
| Per-link passwords, per-recipient links, access logs, "who opened it" | Nothing in the brief asks for them, and each is an addition to a shape D08 fixes at *one link per trip*. See Research |
| Export to PDF / Calendar / Wallet, "Eksportuj PDF" beside the export's share button | **D12**, *Later* |

Nothing here is *excluded*: N01 and D12 say the product excludes nothing permanently.

### The slippable tail

A05 decides the month, so this spec names its own cut line rather than discovering it on 2026-09-14. In priority order, the **last things built and the first things to drop** are: the `is_shared` chip on the trip-list rows (the trip banner keeps its own), and the guest's per-item-type filter chips — `FilterBar` renders *All* / *Only outstanding* and the type chips together, so dropping the guest's chips means passing it a reduced item set rather than deleting anything.

**Revocation is explicitly not slippable.** A sharing feature that cannot be turned off is a privacy hole, and since D16 sets no automatic expiry, revocation is the **only** control that exists. If the calendar forces a choice between the `is_shared` chip and the revoke action, the chip goes.

## 📝 Proposed Solution

Four decisions carry the design, and each is about a boundary rather than a screen:

1. **A separate route namespace for guests, not a widened owner route.** The guest reads `GET /api/v1/shared/{token}`. The owner's `GET /api/v1/trips/{tripId}` is not taught to accept a token. This keeps the walking skeleton's invariant — *every `/trips/…` route carries `get_owned_trip`* — literally true and machine-checked, and puts the product's entire unauthenticated surface in one auditable module.
2. **The guest payload is a different model, not a filtered one**, produced by an explicit projection in `domain/sharing.py` and frozen by a serialized-payload snapshot test. A field or a route added on the owner's side does not reach a guest; it makes a test fail. This is the mechanism the document is built around, and its exact shape and known limits are specified under **The projection tripwire**.
3. **One timeline, rendered twice — and the pieces already exist.** The first draft of this spec proposed extracting the timeline into presentational components. That extraction has since happened on its own: `ItemRow`, `StatusChip`, `ReadinessTile` and `FilterBar` are already separate components in `frontend/src/features/trips/`, and `ItemRow` **already** renders as a plain `<div>` rather than a button when no `onOpen` is passed, and **already** omits its notes paragraph when `notes` is null. The guest screen is therefore a new route component composing existing pieces with fewer props, not a refactor. There is deliberately **no `isGuest` boolean threaded through the tree**: a mode flag is exactly how an edit affordance leaks into a read-only view six months later, and the read-only shape falls out of *not passing a callback* instead.
4. **The link is a bearer credential and is treated like one everywhere except at rest**, where it is stored as issued so that S4 — the owner seeing and re-copying his own link — remains possible. The full argument, its rejected alternatives and its residual exposure paths are in **Data Model**, stated once.

**Alternatives considered and why they lost:**

- **A signed, stateless token (JWT / itsdangerous) carrying the trip id and an expiry.** No table, no lookup. Rejected on the one requirement that matters: it cannot be revoked. Revocation would need a denylist table — the table we avoided, plus an extra moving part — and with no expiry it would grow for ever.
- **The token in the URL fragment (`/s#<token>`) instead of the path.** The fragment never reaches the server, so it cannot reach an access log. Rejected because the page then cannot be opened without JavaScript, the token must be moved into a header by client code, and link previewers handle fragments unevenly. The logging problem is solved directly instead (see Security).
- **Reusing `GET /trips/{tripId}` with an optional `?token=`.** Fewer endpoints. Rejected: it makes the one enforceable statement about owner routes conditional, and it puts the decision about what a guest sees inside a handler that also serves the owner — the exact place where a future field gets forgotten.
- **A per-recipient link ("send to Kasia").** Rejected by D08: *one link per trip* is what gets pasted into a group chat, and the owner said so.
- **A server-rendered public HTML page instead of an SPA route.** Would not need JavaScript. Rejected: it is a second implementation of the timeline — precisely what the brief's "reuse the owner's timeline read-only" rules out — and it would duplicate the i18n layer server-side.

## 📝 Research — what the market leaders do, and what we skip

**Epistemic warning.** Brief Q01 records that nothing has ever been checked and that *"a competitor described from memory would be a guess wearing the clothes of a fact"*. This run had no network access, so what follows is **from knowledge, not from a check**, and is `[ASSUMPTION]`-grade. Q01 stays open; no design decision below rests on it.

The document-sharing pattern (Google Docs, Notion, Dropbox) and the trip-specific one (Wanderlog, TripIt) converge on four things and we take all four: an **unguessable link rather than an obscure id**; a **copy button as the primary action**, because the link's whole purpose is to be pasted somewhere else; a **plain sentence in the dialog naming who can see the plan** rather than an icon; and **`noindex` on the shared page**. The sentence is worth singling out — Google Docs writes "Anyone on the internet with the link can view", and that phrasing is the only thing standing between an owner and a wrong mental model of what he just created. The share dialog copies it deliberately.

What they carry that we skip: **link roles** (view / comment / edit) — D09 gives us exactly one role; **per-person invitations** — D08 gives us one link per trip; **password-protected links and expiry pickers** — a second control to explain and a second failure mode for an audience of one owner and his companions; **access logs / "who viewed this"** — a privacy surface of its own that nothing in the brief asks for. Each is an addition later; none is foreclosed here.

The one place we are plausibly *behind* them and accept it: they let the sharer choose what the recipient sees. We decide it once, globally, in the projection — and D16 plus Q3 record that as a decision for the owner to take rather than a settled truth.

## 📝 Architecture

Additions only. No existing module moves, and no existing component changes behaviour.

```
backend/trip_planner/
  api/sharing.py          NEW  owner endpoints, mounted on the AUTHENTICATED router list
  api/shared.py           NEW  the guest endpoint — the whole public API surface, one module
  api/schemas.py               + GuestTripRead / GuestDayRead / GuestItemRead
  domain/sharing.py       NEW  pure: mint_token(), project_trip_for_guest(), the allow-lists
  db/models.py                 + TripShareLink
  errors.py                    + SHARE_LINK_NOT_FOUND / _REVOKED / _GONE
  app.py                       + one PUBLIC_PATHS entry; + the guest response headers
  spa.py                       + the guest document's headers on the index fallback
  logging.py              NEW  the access-log filter that redacts tokens
migrations/versions/           one Alembic revision: trip_share_link

frontend/
  public/robots.txt       NEW  (spa.py's public_file() already anticipates this file)
  src/api/sharing.ts      NEW  typed client for both sides
  src/features/sharing/ShareDialog.tsx  NEW  owner: create / view / copy / revoke
  src/features/sharing/GuestTripPage.tsx NEW the /s/:token route and its dead-link states
  src/features/sharing/GuestShell.tsx    NEW guest chrome — AppShell without the account
  src/features/trips/{ItemRow,StatusChip,ReadinessTile,FilterBar}.tsx   REUSED unchanged
  src/features/trips/TimelinePage.tsx    + "Udostępnij" in the existing AppShell `actions`
                                           slot, + the reserved `Shared` chip
  src/App.tsx                            + /s/:token, outside RequireSession
  src/assets/icons.svg                   + the `share` glyph
  src/styles/{components,screens}.css    + the share dialog and guest recipes
  src/locales/{en,pl}.json               + the new keys, in both
```

Boundaries that matter:

- **`domain/sharing.py` is pure**, like every other module under `domain/`: token minting is a function over `secrets`, and the projection is a function from owner-shaped values to guest-shaped values with no database access. Both are unit-testable without fixtures.
- **`api/shared.py` is the entire unauthenticated API surface** apart from the health check and the two auth routes already on `PUBLIC_PATHS`. One module, so that "what can the internet reach" is answerable by reading one file — and one `PUBLIC_PATHS` entry, so it is also answerable by reading one frozenset.
- **The guest document needs no new routing.** `spa.py`'s index fallback already serves the app shell for every non-API path, so `/s/<token>` reaches the SPA the moment `App.tsx` declares the route. What `spa.py` gains is headers, not a route.
- **The frontend never computes readiness** — unchanged rule. The guest payload carries `{arranged, tracked}` from the same `domain/readiness.py`, so R02 keeps exactly one implementation and the guest cannot be shown a different number from the owner's.
- **Filtering stays in the browser** — unchanged rule (walking-skeleton A11). The guest payload is complete, and the guest's filter bar is `FilterBar` over the guest's own items.
- **No external subresources, still** — on this screen a security control rather than a scope statement, and now genuinely true: `main.tsx` self-hosts Plus Jakarta Sans through `@fontsource-variable/plus-jakarta-sans/wght.css`, and the icon sprite is a hashed local asset (`icons.svg?no-inline`). CSP is what keeps it true (see Security).
- **The design system is the visual vocabulary, not a suggestion.** Every new rule uses tokens from `styles/tokens.css`, because `scripts/check_css_tokens.py` is now a validation-gate command and a raw hex literal fails the build. Any new colour pair goes into `scripts/check_contrast.py`'s table — which is why the guest surface introduces no new colour and reuses the existing chip, card, modal and button recipes.

## 📝 Data Model

One new table. No column is added to `trip`, `trip_day` or `item`.

### `trip_share_link`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_id` | UUID **NULL**, FK → `trip.id` `ON DELETE SET NULL`, indexed | NULL means *the trip it pointed at has been deleted* — the state the `410 share_link_gone` branch reports |
| `token` | TEXT NOT NULL, `UNIQUE` | 256 bits from `secrets.token_urlsafe(32)` → 43 URL-safe characters. Stored as issued; see below |
| `created_at` | TIMESTAMPTZ NOT NULL | shown to the owner in the share dialog |
| `revoked_at` | TIMESTAMPTZ NULL | NULL means active. Set, never unset; a row is never deleted |

```sql
CREATE UNIQUE INDEX ux_share_link_active ON trip_share_link (trip_id) WHERE revoked_at IS NULL;
```

That partial index is **D08 and R05 made structural**, the same way the status `CHECK` constraint makes R02 structural rather than conventional: "exactly one link per trip" is enforced by the database, not by a handler remembering to check. Postgres treats NULLs as distinct in a unique index, so any number of orphaned rows (deleted trips) coexist without contending for it.

**Why `ON DELETE SET NULL` rather than `CASCADE`.** `BACKWARD_COMPATIBILITY.md` §3 requires a shared-itinerary link to *"keep resolving, or resolve to an explicit 'this plan is no longer available', never to a wrong plan"*. A cascade would delete the row and the link would answer `404` — a message about the *link* when the truth is about the *plan* — and it would also falsify two claims this design depends on: that tokens are unique across the table for all time, and that a row is never deleted. Keeping the orphaned row costs one nullable column and buys the third guest state below.

**Why the token is stored as issued, argued once.** The walking skeleton hashes session tokens because a database dump would otherwise yield working sessions, and a session grants *write* access to the owner's account and every trip he will ever have. A share token grants **read** access to exactly one trip whose entire contents sit in the same dump, so hashing protects nothing an attacker with that dump does not already hold — while costing the capability S4 requires. The alternative, show-once, makes the owner revoke and regenerate whenever he loses the message, minting more live links than he needs: a worse privacy outcome than the one hashing was meant to buy.

**Encryption at rest under `SESSION_SECRET` was considered and rejected — narrowly.** It would preserve S4 exactly and would defend the case the argument above does not cover: a *partial* leak, such as a logical backup of this table alone, a misconfigured read replica, or a SQLAlchemy `StatementError` whose message includes bound parameters. It lost on the grounds that it adds a key-rotation problem and a decrypt path to every request for a threat that is strictly narrower than the full-dump case already conceded, at one owner on one host. **If the owner overrides Q3 to widen what a guest sees, this trade-off deserves revisiting in the same breath.**

That argument holds only if the token is disciplined everywhere else:

- excluded from every response model except the owner's own share endpoints;
- `TripShareLink.__repr__` overridden so it cannot reach a log line, exactly as `owner.password_hash` is — and, because `__repr__` is not the only path from an ORM to a log, database exceptions are caught at the boundary and re-raised without bound parameters;
- never written to an application log, an error body, an exception message or a metric label;
- kept out of the reverse proxy's logs by the request-path and `Referer` redaction in Security.

**No `expires_at` column.** D16 sets no automatic expiry, and the walking skeleton set the precedent against shipping columns nothing can populate. Should expiry ever be decided, it is one nullable column and one clause in one query — an addition, and safe under §2.

**No `last_accessed_at`, no view counter** (Q8): they are a privacy surface of their own pointed at the owner's friends, and nothing in the brief asks for them. The retained revoked rows are not an audit trail of *access* — nothing records who opened a link — they exist only so a dead token can answer honestly.

### Relationship summary

```
owner 1─n trip 1─0..n trip_share_link     (at most ONE row with revoked_at IS NULL per trip)
                        deleting the trip orphans its links (trip_id → NULL), never deletes them
```

### Migration

One Alembic revision creating `trip_share_link` and its partial unique index, with a working `downgrade`. It creates a table that did not exist, so §2's "safe against rows that already exist" rule is vacuous for it.

## 📝 API Contracts

Conventions are the walking skeleton's, unchanged: JSON under `/api/v1`, ISO dates and wall-clock times, unknown request fields rejected, errors as `{"error": {"code": "<stable_code>", "field": "<name|null>"}}` with the code drawn from the `ErrorCode` enum, resolving to a non-empty key in **both** locale files. Unsafe methods carry the skeleton's CSRF double-submit token — inherited, and asserted for the two new ones.

### Owner side — session-authenticated, `get_owned_trip`, under `/trips/{tripId}`

| Method | Path | Response | Notes |
|---|---|---|---|
| `GET` | `/trips/{tripId}/share-link` | `200 {"link": null}` or `200 {"link": {"token", "url", "created_at"}}` | "Not shared" is a normal state, not a `404`. Called when the share dialog opens, never as part of the timeline payload, so the secret is fetched only when it is about to be shown |
| `POST` | `/trips/{tripId}/share-link` | `201 {"link": {...}}` on create; **`200` with the existing link when one is already active** | Deliberately idempotent: a double-click, a retry or a second tab must never silently rotate a link already sitting in a group chat. There is no `409` because "already shared" is the desired end state. **The `201`/`200` split is contract, not incidental** — §1 lists a status-code change for an existing condition as breaking |
| `DELETE` | `/trips/{tripId}/share-link` | `204` | Sets `revoked_at`; never deletes the row. Idempotent: `204` even when nothing is active |

`TripSummary` in `api/schemas.py` gains one additive response boolean, `is_shared` — never the token — which `TripDetail` inherits, so `GET /trips` and `GET /trips/{tripId}` both carry it from one edit. It is **always present**, never omitted when false: changing that later would be a §1 field change. Adding a response field is explicitly non-breaking under §1.

A trip belonging to another owner answers `404` on all three, identically to every other trip-scoped route.

### Guest side — the entire unauthenticated surface

| Method | Path | Response |
|---|---|---|
| `GET` | `/shared/{token}` | `200` guest payload · `404 share_link_not_found` (unknown or malformed) · `410 share_link_revoked` (the owner turned it off) · `410 share_link_gone` (the trip was deleted) |

- **No cookie is read and none is set.** A session cookie that happens to be present is ignored, so an owner opening his own link sees exactly what his companion sees — the honest preview, asserted by a test.
- **`GET` only.** There is no guest write path to defend because there is no guest write endpoint (R06, D09).
- The token is validated against `^[A-Za-z0-9_-]{43}$` **before** any query, so malformed input is a `404` that never touches the database.

The payload:

```jsonc
{
  "trip":   { "title", "start_date", "end_date", "departure_place", "return_place" },
  "stages": [ { "id", "position", "place", "start_date", "end_date" } ],
  "days":   [ { "date", "stage_ids": [...], "items": [
                  { "id", "kind", "status", "start_time", "end_time", "end_date", "title" } ] } ],
  "readiness": { "arranged", "tracked" }
}
```

Absent by construction: `item.notes`; attachments, confirmation numbers, cost and currency when they exist; the owner's e-mail, id and locale; the trip's id; any URL reaching an owner route. The `id` fields that remain are opaque UUIDs used as React keys and unlock nothing, because every owner route requires a session *and* ownership.

### The projection tripwire

The guest payload is frozen by **three** assertions in CI, because one was not enough. All three attach to code that exists: the owner's response models are `ItemRead`, `StageRead`, `DayRead`, `TripSummary`, `TripDetail` and `ReadinessRead` in `backend/trip_planner/api/schemas.py`.

1. **A serialized snapshot.** A fixture trip with notes, several stages and a spanning item is rendered through `project_trip_for_guest`, and the **full recursive key set** of the resulting JSON is compared against a frozen constant. This is the assertion that survives refactors: it does not care whether a field arrives as a model attribute, a computed property, a serializer alias or a nested relation.
2. **Per-model owner-only allow-lists**, for `ItemRead`, `TripSummary`, `StageRead` and `DayRead` alike — not for items only. Today `ItemRead`'s owner-only set is exactly `{notes, position}`; `TripSummary`'s is `{id, readiness, is_shared}` (the guest gets its own readiness object, not the owner's field, and must never be told whether the trip is shared); `StageRead` and `DayRead` are projected whole apart from `DayRead.items`. A future `trip.budget` or `stage.notes` must be classified before the suite goes green.
3. **A route-inventory assertion**, which already exists and is stronger than the first draft of this spec assumed. `backend/tests/test_route_protection.py` asserts that every registered route is on `app.PUBLIC_PATHS` or carries `get_current_session`, that no allow-list entry is stale, and — in `test_the_public_allow_list_stays_small` — that `PUBLIC_PATHS` equals a literal frozenset written out in the test. Adding the guest route is therefore a **deliberate two-place edit**: `app.py` and that literal. A route added silently fails; an allow-list grown silently fails too.

**The known limit, stated because the earlier draft of this spec overstated the mechanism.** Attachments will most likely arrive as a *relation and a download route* (`GET /files/{attachmentId}` or similar) rather than as a key on the owner's item payload. Assertion 1 catches the payload case and assertion 3 catches the route case — a new public download route fails the enumeration test, and an authenticated one is simply unreachable for a guest — but **neither can decide the sharing question for a route the attachments spec designs as owner-authenticated and then wishes to open**. That decision belongs in the attachments spec, and this document's ask of it is one line: *any route serving item-derived content is either owner-authenticated or added to the public allow-list with a stated privacy decision; there is no third option.*

### Error codes added

| Code | Status | Meaning |
|---|---|---|
| `share_link_not_found` | `404` | Unknown or malformed token |
| `share_link_revoked` | `410` | The owner turned this link off |
| `share_link_gone` | `410` | The link was valid; the trip it pointed at has been deleted |

The `404` / `410` split tells the holder of a token that the token once existed. At 256 bits nobody reaches those branches by guessing — the only party who can present a dead token is somebody the owner sent it to, and that person deserves the true answer. §3 requires it in so many words.

## 📝 UI/UX

Mockups live beside this spec and are attached to its PR. They are illustrative statics with no application code behind them — but they are **not** hand-rolled: they render through `assets/design-system-adoption/_mockup.css`, the adopted design system's own mockup stylesheet, referenced from the sibling directory rather than copied. One vocabulary, one file, and a mockup that cannot drift from the system it depicts. The typeface is the real Plus Jakarta Sans from that directory's `fonts/`, with no network request.

| Screen | Mockup |
|---|---|
| The owner's share dialog in **State B** over the timeline, with the `Shared` chip on the banner and "Udostępnij" in the action row — Polish | [`assets/trip-sharing-magic-link/mockup-01-share-dialog.png`](assets/trip-sharing-magic-link/mockup-01-share-dialog.png) |
| `/s/:token` — the guest view: `GuestShell` chrome, the banner, `ReadinessTile`, `FilterBar`, the rail, and item cards **without notes** — Polish | [`assets/trip-sharing-magic-link/mockup-02-guest-view.png`](assets/trip-sharing-magic-link/mockup-02-guest-view.png) |
| `/s/:token` — the three dead-link states, **English** | [`assets/trip-sharing-magic-link/mockup-03-guest-dead-links.png`](assets/trip-sharing-magic-link/mockup-03-guest-dead-links.png) |

Two are Polish and one English on purpose: R01 makes both locales first-class, and a spec that only ever pictures one is not showing the product it describes.

**Current state.** The application runs now, so "before" is a real screen rather than an absence — but no fresh capture was taken in this revision, because it would mean booting Postgres and the stack to photograph screens this feature has not touched yet. The timeline as it looks today, in both locales, is committed at `.ai/runs/2026-09-06-design-system-adoption/final-gate-artifacts/04-timeline-{pl,en}.png` (and at 360px beside them). Mockup 01 is that screen plus two controls; mockup 02 is that screen with the account taken out of it.

Nothing in these mockups is fabricated beyond the plan data: the share token is invented and marked as such, and there is no view count, no example guest, and no progress figure the payload does not carry.

### The owner's share dialog

Opened from **"Udostępnij"**, a `.button-quiet` in the `actions` slot `TimelinePage` already passes to `AppShell` — where the "Delete trip" button lives today, and the adopted equivalent of the export's own position for it beside "Eksportuj PDF" (dropped, D12). The dialog reuses the design system's existing modal recipe and `ConfirmDialog` for the revoke confirmation; it introduces no new overlay treatment and no new token.

**State A — not shared yet.** One sentence naming the consequence, then one primary action:

> *Każdy, kto ma ten link, zobaczy ten plan — bez konta i bez logowania. Nie zobaczy Twoich notatek, załączników, numerów rezerwacji ani kosztów.*
> *Anyone with this link can see this plan — no account, no sign-in. They will not see your notes, attachments, confirmation numbers or costs.*

Primary action: **"Utwórz link" / "Create link"**. The sentence is the Google-Docs pattern from Research and the only place the owner's mental model gets corrected before the link exists. It also states D16's projection in words, so an owner who disagrees finds out while he can still say so.

**State B — shared.** The URL in a read-only, selectable field; **"Kopiuj" / "Copy"** as the primary action with a transient confirmation announced through an `aria-live="polite"` region (a purely visual "✓" is invisible to a screen reader); the creation date; the same sentence about who can see it; and a destructive **"Odwołaj link" / "Revoke link"**, visually secondary, behind a confirmation:

> *Wszyscy, którym wysłałeś ten link, stracą dostęp. Tego nie da się cofnąć — możesz później utworzyć nowy link.*
> *Everyone you sent this link to will lose access. This cannot be undone — you can create a new link afterwards.*

Copying uses `navigator.clipboard.writeText`, falling back to selecting the field's text where it is unavailable, because a copy button that silently does nothing is worse than no button.

After a successful revoke the dialog returns to **State A** in place. "Revoke" and "create a new link" stay two deliberate actions rather than one *Regenerate* click, so an owner who wants to stop sharing does not have to mint a new secret to do it.

**The `is_shared` indicator, in the slot the design system reserved for it.** `frontend/src/styles/screens.css` carries this comment in its `/trips` block:

> *Deliberately NOT here: a `Shared` chip. PR #3 specifies one, but it is only true when a share token exists, none can exist yet, and a chip that is never true is a fabrication rather than a preview.*

A token can exist now, so the chip lands and that comment is replaced by the rule. It is the existing chip recipe with the `share` glyph, on the trip banner of `/trips/:id` and on the trip's row in `/trips` (the latter is the slippable half). Without it there is no way to tell from the plan itself that it is currently readable by anyone holding a link, and R08's whole subject is knowing what is reachable.

**The sprite gains one glyph.** Phase 6.1 of the design-system run dropped the `share` symbol from `frontend/src/assets/icons.svg` on the grounds that "a glyph with no consumer is dead weight" — this spec is the consumer, so it adds it back, in the same style as the seven that are there, and `Icon`'s `IconName` union picks it up.

### `/s/:token` — the guest view

One route, one screen. **There is no guest day-detail screen**: everything the owner's `/trips/:id/days/:date` adds is the editor, and every item is already on the timeline. One page is also the right shape for a link opened once, on a phone, from a chat message.

- **Chrome: `GuestShell`, not `AppShell`.** `AppShell` calls `useSession()` and always renders sign-out and a wordmark linking to `/trips`; a guest has neither a session nor anywhere to go. `GuestShell` is a sibling component reusing the same `chrome.css` classes — the frosted sticky header, the page grid, `<main>` as the landmark — with the wordmark as plain text, the `LocaleSwitch` with no `persistLocale` callback, and **no** sign-out, no account menu, no dock. It does not call `useSession`, so the guest view renders identically whether or not the session probe has answered.
- **A one-line banner** under the header: *Widok tylko do odczytu, udostępniony przez autora planu* / *Read-only view shared by the trip's owner* — it answers "can I change this?" before the guest tries.
- **Banner, readiness tile and filter bar** are the owner's components unchanged: the trip banner treatment from `screens.css`, `ReadinessTile` with its progress ring and its `tracked = 0` suppression, and `FilterBar` over the guest's own items. The counter is half of what D08 promises the guest and must not be a reduced version of the owner's number.
- **The timeline** is the same rail, day anchors, `ItemRow` and `StatusChip`. Read-only falls out of the existing props rather than from a new mode: `ItemRow` already renders a plain `<div>` instead of a `<button>` when `onOpen` is not passed, so the guest simply does not pass it. No "Add item", and an empty day reads *Nic jeszcze nie zaplanowane* / *Nothing planned yet* rather than the owner's invitation to add the first item.
- **Item cards carry no notes line, with no component change.** `ItemRow` already renders its notes paragraph only when `item.notes` is non-null. The only edit it needs is to its prop *type* — the fields it reads, with `notes` optional — so a guest item satisfies it structurally. Behaviour is untouched and the existing tests stand. Stated plainly because this is the visible face of Q3 and the owner should see the cost of the default before merging it.
- **Dead links are pages, not toasts:** *Ten link nie działa* / *This link does not work* (`404`), *Ten plan nie jest już udostępniony* / *This plan is no longer shared* (`410 revoked`), and *Ten plan już nie istnieje* / *This plan no longer exists* (`410 gone`). Full pages with the same chrome and the locale switch, because the recipient has nowhere else to go in this application.
- **Page metadata stays generic, which is a requirement rather than a change.** `frontend/index.html` already sets a static `<title>Smart Trip Planner</title>` and carries no Open Graph or Twitter card tags, and nothing on the guest route may add either. Every chat client fetches a pasted URL server-side to build a preview; a title carrying the trip name would publish the plan's name into channels the owner did not choose. The requirement therefore gets a test rather than an implementation. See Security for the part that cannot be mitigated.

### Locale for a person with no account

Nothing new is built here, and that is the finding. `detectInitialLocale()` in `frontend/src/i18n/index.ts` already resolves *stored choice → browser language → `pl`*, and `applyLocale()` already writes `<html lang>` and the `trip-planner.locale` key. The guest gets exactly that, with the header switch calling `applyLocale` and **not** `persistLocale` — there is no owner row to write to.

An earlier draft of this spec proposed an `en` fallback and a separate `guestLocale` key. Both are dropped: a second locale-detection path on the same origin is worse than a terminal fallback that the switch corrects in one click, and the owner-collision the scoped key was meant to prevent is already handled — `SessionContext` applies the server-side `owner.locale` on sign-in, so an owner who previews his own link in English and returns to `/trips` gets his account's language back.

### The SPA route

`RequireSession` is not an allow-list — it is a layout route wrapping the four owner screens in `App.tsx`. So the guest route is declared as a **sibling outside that wrapper**, and it must be declared *before* the existing `<Route path="*" element={<Navigate to="/trips" replace />} />`, which would otherwise send every guest to `/trips` and from there to `/login` — a login form for an account they do not have. That catch-all is the real trap this spec has to step around, and the test that catches it is an unauthenticated render of `/s/:token` asserting no redirect.

`SessionProvider` still wraps everything and still probes `GET /auth/me`, which answers `401` for a guest. That is harmless — `GuestShell` does not read the session and the guest endpoint never returns `401`, so the global unauthenticated handler is never triggered from the guest page — but the guest view must render at `status: 'loading'` as well as at `'anonymous'`, which is exactly what not calling `useSession` guarantees.

## 📝 Edge Cases & Failure Scenarios

Rows already fully specified in API Contracts or Security are not repeated here.

| Case | Behaviour |
|---|---|
| Trailing punctuation added by a chat client (`…/s/abc.`) | Fails the pattern check → `404`. Not defended further: stripping punctuation would risk resolving a *near* token, and the copy button copies a clean URL |
| Trip deleted after sharing | `trip_id` → NULL; the link answers `410 share_link_gone`, "this plan no longer exists". Distinct from *revoked*, which would attribute to the owner a sharing decision he did not make |
| Revoke, then create a new link | A fresh token; the old row answers `410 share_link_revoked` for ever. The two are never confused, because `token` is unique across the whole table for all time |
| Revocation racing an in-flight guest request | Last-write-wins on one row; the worst case is one already-issued response for a link revoked in the same millisecond. No locking, and none needed |
| The plan changes while a guest has the page open | The link always resolves to the **live** plan; the guest sees the change on reload. This is the feature, and it is §3's "never to a wrong plan" |
| The trip's date range shrinks after sharing | Nothing special — the guest sees the current days; day and item deletion rules are the owner-side rules the walking skeleton already specifies |
| A trip with no items at all | Every day renders its "nothing planned yet" state, and the counter shows its `tracked = 0` copy |
| Guest browser prefers neither Polish nor English | English, with the switch one click away |
| A guest presents the token as a cookie or header to an owner route | `401`. The token is not a session and no code path turns it into one (R08) |
| Backend unavailable | The walking skeleton's `503` retry state, never an empty timeline |

## 📝 Security

D14 makes this section non-optional: it is the first time anything in this product answers a request from a stranger.

**R08's second half, made enumerable.** `backend/tests/test_route_protection.py` already asserts that every registered route is on `app.PUBLIC_PATHS` or carries `get_current_session`, that the allow-list has no stale entries, and that it equals a literal frozenset spelled out in the test. This spec adds **exactly one** entry, in two places, in the same commit as the route. A future public route is therefore a deliberate edit to a test rather than an omission nobody notices.

**Where the headers come from, corrected.** The first draft of this spec put the security headers and the log redaction in a reverse-proxy configuration under `deploy/proxy/`. **That directory does not exist and neither does the proxy**: `deploy/` holds a `Dockerfile`, two compose files and an entrypoint, and `trip_planner/spa.py` serves the built SPA from the same origin as the API. TLS is terminated by whatever platform the image runs on, which is not a file in this repository. So every control below is implemented **in the application** — a Starlette middleware for the response headers, `spa.py`'s index fallback for the guest document, and a logging filter for the access log. That is strictly better than the proxy version: it is committed, diffable, reviewable, and asserted by `pytest` rather than by a deployment checklist nobody runs.

| Control | What it is, and what it is for |
|---|---|
| **Token entropy** | 256 bits from `secrets.token_urlsafe(32)`. Never derived from the trip id, never sequential, and deliberately **not a UUID** — a UUIDv4 carries 122 bits and, worse, *looks like an identifier*, which invites treating it as non-secret |
| **No brute-force limiter, deliberately** | At an implausible million guesses per second against a 2^256 space, the expected time to find a live token exceeds the age of the universe by many orders of magnitude. A limiter here would be theatre plus a table — and the existing `security/rate_limit.py` is built around `login_attempt`'s non-null e-mail, so reusing it would mean migrating a table for a threat that does not exist. What the endpoint needs is ordinary **DoS** protection, which is a platform concern (see Deployment), never presented as protection against guessing |
| **Content-Security-Policy** | `default-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'`, set by application middleware on the SPA document. This is what actually enforces "the guest page makes no external request" — a promise otherwise kept only by reviewer memory until the first analytics SDK or icon font is installed. `frame-ancestors 'none'` additionally stops a shared plan being framed silently inside a third-party page. It is safe to apply to the whole document surface, not just `/s/`: the app already loads every asset from its own origin |
| **No third-party subresources** | Already true and now enforced. `main.tsx` imports `@fontsource-variable/plus-jakarta-sans/wght.css`, so the typeface is served from `/assets` as hashed woff2 files rather than from a font CDN, and the icon sprite is imported `?no-inline` as a local hashed asset. That matters concretely here: a Google Fonts request issued from `/s/<token>` would hand the complete share URL to a third party in a `Referer` header. The CSP makes a future regression fail the build rather than leak |
| **Referrer policy** | `Referrer-Policy: no-referrer`, set by the same middleware on the guest document |
| **Log redaction, on both fields** | A logging filter on uvicorn's access logger redacts the request path for `/s/…` and `/api/v1/shared/…` — **and the `Referer` field globally**. The second is the one that matters: the guest page's own same-origin subresource requests (`/assets/index-*.js`, the woff2 files, the sprite, the API call) do not match either path prefix, so a path-only redaction would log the complete share URL as their referrer on every one of them. A token in a log line is a live link in a log line |
| **Not indexable** | `X-Robots-Tag: noindex, nofollow` on the guest document, and the `<meta name="robots">` equivalent. `/s/` is deliberately **not** `Disallow`ed in the new `frontend/public/robots.txt`: a crawler that obeys `Disallow` never fetches the page and therefore never reads the `noindex`, and a disallowed URL discovered from an external link can still be indexed URL-only — which would publish the token itself, the one thing this design cannot survive. Allowing the crawl so it can read the `noindex` is the correct configuration. `spa.py`'s `public_file()` already anticipates this exact file, so it is served rather than swallowed by the index fallback |
| **Not cached** | `Cache-Control: private, no-store` on the guest payload — a correctness control as much as a privacy one, since a cached payload would keep serving a plan after revocation, and revocation is the only kill switch this design has. The document itself is already `no-store` in `spa.py` |
| **No cookie, no session, ever** | The guest endpoint reads no cookie and sets none. R08 in code |
| **No guest write path** | An absence, not a permission check: the guest surface is one `GET` |
| **Owner endpoints still owned** | The three share endpoints take `get_owned_trip`, so no owner can mint, read or revoke a link for a trip that is not his. Both unsafe methods carry the skeleton's CSRF double-submit token — a forged `DELETE` would otherwise let a third-party page silently un-share an owner's plan |
| **Immediate revocation** | One indexed lookup per guest request, no in-process token cache, no CDN caching |
| **Field-level exposure decided once** | The projection tripwire and its three assertions, with their limit stated |

**What this design does not protect against, plainly.**

- **Forwarding.** The link *is* the credential and it is bearer-only: the magic link's security model is that of the group chat it gets pasted into. Nothing in D08's shape can change that, and an expiry date would be a comfort rather than a control. **Revocation is the only real control, which is why it is in v1 and not in the slippable tail.**
- **Link unfurling.** D08's own rationale is that the link "gets pasted into a group chat" — and every major chat client (Slack, WhatsApp, Messenger, iMessage, Discord) fetches a pasted URL server-side to build a preview. **The token is therefore transmitted to, and logged by, a third party on the feature's very first use, by design.** The generic `<title>` and the absent Open Graph tags keep the *trip's name* out of those previews; they cannot keep the *URL* out of the chat provider's infrastructure. This is inherent to sharing a bearer link over a messaging platform and is the strongest practical argument for revisiting expiry if D16's Q3 answer is ever widened.

## 📝 Deployment

No new deployable, no new container, no new environment variable. The guest share URL is built from `APP_BASE_URL`, which the walking skeleton already requires at startup and `config.py` already validates.

Everything the Security section names is **in the application**, for the reason the walking skeleton put login rate limiting in Postgres rather than in a worker: a control that lives only in a checklist is not a control. The headers ship as middleware, the redaction as a logging filter, `robots.txt` as a file in `frontend/public/` — all three diffable and asserted by tests.

The **one** genuinely platform-level item is the per-IP request cap on `/s/` and `/api/v1/shared/`, as denial-of-service protection only. There is no reverse-proxy configuration in this repository to put it in, so it is recorded here as a deployment note and explicitly **not** claimed as a control the codebase provides. If the deployment platform offers no such cap, the honest consequence is that the guest endpoint is as exposed to flooding as `/login` already is — a pre-existing property of the deployment, not something this feature introduces.

## 📝 Risks & Impact Review

- **Blast radius: additive throughout.** One new table, one new public route, three new owner endpoints, three new error codes, one added `TripSummary` field, one new SPA route, one new sprite glyph, new locale keys, response-header middleware and an access-log filter. The only edit to an existing component is `ItemRow`'s prop *type*, widened to what it already reads. Under §1, adding endpoints and response fields is non-breaking; under §2 the migration creates a table that did not exist. **Nothing changes meaning** — §1's worst and quietest class of break. The one thing to watch on review is the middleware: a CSP applied to the whole document surface touches four screens this feature does not otherwise change, which is why Phase 1 step 9 asserts the headers rather than assuming them.
- **§3 is the section this spec answers directly**, and it needed a design change to answer honestly: a link resolves to the live plan, a revoked one says so, a deleted one says *that* instead, and a token never comes to mean a different trip because rows are orphaned rather than deleted.
- **§4 applies to the dialog copy.** If Q3 is overridden and guests do come to see notes, the State A sentence must ship under a **new** translation key rather than a rewritten one: changing a key's meaning while keeping its name is a §4 break.
- **The one risk that cannot be rolled back is exposure.** Every other decision here is reversible in a PR. What a link has already shown to a group chat cannot be unshown. That asymmetry is the whole justification for defaulting the projection to the minimum and for gating Q3 on human confirmation.
- **The dependency that will actually bite: the attachments spec**, and the tripwire's stated limit is the honest version of how far this document can protect against it. Its one ask of that spec is in **The projection tripwire**.
- **Rollback story.** One migration with a working `downgrade`; dropping the table removes every link, which is the safe direction for a privacy feature — a rollback closes access rather than opening it. A frontend rollback turns every live link into a dead page. Neither can leak.
- **Product-decision compliance.** This spec builds what D08 and D09 mandate, in the shape they mandate, and cuts nothing under A05. It **does** decide four points R05 records as undecided, and R05's *Required path to change* names a superseding decision row and a distinct privacy decision — so it proposes **D16** below rather than claiming none is needed.
- **A06's test ships with the feature**, and building read-only first is what makes that test possible.
- **Calendar risk (A05).** This is the smallest of the three *Now* slices — one table, four endpoints, one new screen, one dialog — and it got smaller when the design system landed: the components the guest view needs already exist and already behave read-only, so Phase 2 composes rather than builds. Its slippable tail is named above.

## 📝 Decisions in play

| Id | How this spec relies on it |
|---|---|
| D08 / R05 | One magic link per trip, read-only, no account for the recipient — enforced by the partial unique index. R05's undecided points are decided by the proposed D16 |
| D09 / R06 | One editor, guests read only — realised as the absence of a guest write endpoint. Comments and suggestions stay in *Later* by these rows and D12 |
| R08 / D14 | The second half of R08: one unauthenticated route family, enumerable, cookie-less, session-less. The magic link is not a login |
| R02 / D05 | The guest's readiness counter is the owner's, from the same `domain/readiness.py` |
| R01 / R09 | Both locales first-class for a guest who never chose one; `check_locales.py` green; spec, code and PR body English |
| R04 / D07 | Cost and reservation data are *stored* when they arrive — R04 says nothing about who may see them, so withholding them from guests contradicts nothing. The projection makes that an explicit decision rather than an oversight |
| R03 / D06 | The guest sees the multi-stop structure as the owner does: ordered stages, derived day labels, an open-jaw route summary |
| D04 / R07 | No external calls — on this screen a security control, enforced by CSP |
| D12 / N01 | Guest comments, public plans, exports: deferred, never excluded |
| D15 / A01 | **Not relied upon.** This feature is justified by P2 and D08; the Definition of Ready addendum bars anything justified by "so other people can use it" until A01 is tested, and this is not that |
| A06 | Untested, and this feature is the instrument of its own smallest test |
| A05 | **Cited for nothing.** No capability is cut under it; it shapes only the slippable-tail ordering |
| Brief Q03 | Closed in the sharing direction by D16; the storage half (where attachments live, sizes, formats) remains open and belongs to the attachments spec |
| Brief Q01 | Still open; the Research section is explicitly from knowledge and no decision rests on it |

### Proposed superseding decision row — D16

R05's *Required path to change* is **"A superseding decision row; any public-link feature needs its own privacy decision."** This spec decides expiry, revocation and guest visibility, so it must supply that row rather than assert none is needed — otherwise R05's own text would still read "still undecided" the moment code shipped that decided it, which is exactly the silent divergence `BACKWARD_COMPATIBILITY.md` names as the worst kind of break.

> **D16 — 2026-09-05 — Read-only sharing is decided as follows.** A trip's magic link **does not expire**; the owner's revocation is the only control, it disables the link permanently, and creating a new link is a separate action. A guest sees the trip title, dates, departure and return places, its stages and days, each item's kind, status, times and title, and the readiness counter — **and nothing else**: not notes, not attachments, not confirmation numbers, not costs. *Why:* exposure is one-way and a timer nobody set is not a control. *Owner:* Michal Klosinski. *Status:* **proposed — approval required before merge.** *Review by:* 2026-12-31.

D16 supersedes the undecided clause of R05 and closes the sharing half of brief Q03. **The edit adding D16 to `product-brief.md`, amending R05's text and annotating Q03 is not made by this PR** — it lands once the owner confirms Q3, because the row would otherwise record a decision he has not taken. This is the single reason this PR is a draft.

## ⚠️ Resolved assumptions (autonomous defaults)

This spec was written in `--autonomous` mode. Each question was resolved by the most reversible, smallest-scope answer available, and each is open to override before merge.

| # | Question | Resolved as | Rationale |
|---|---|---|---|
| Q1 | Does the link expire, and after how long? (R05) | **No automatic expiry. Revocation is the control.** No `expires_at` column | A link that dies on its own dies at the worst moment — mid-trip, in an airport, exactly when the companion opens it (A03, D10). The privacy case for expiry is real but is answered better by a control the owner operates deliberately than by a timer he will not remember setting. Adding expiry later is one nullable column and one query clause. Coupled to Q3: this default is defensible **because** exposure is minimal; widening Q3 should reopen it in the same breath |
| Q2 | Can the owner kill a link, and does that regenerate or disable? (R05) | **Yes. Revocation *disables*; creating a new link is a separate second action.** The row is kept and answers `410` for ever | Conflating "stop sharing" with "share differently" in one *Regenerate* button means an owner who simply wants access to end must mint a new secret to do it. Keeping the row is what satisfies §3 |
| Q3 | Does the guest see an item's **notes** (the free-text field)? (brief Q03) | **No** — ⚠ **NEEDS HUMAN CONFIRMATION** | The one place a reasonable owner could reasonably disagree, and a privacy decision rather than a UI one. Notes are free text written for an audience of one and can hold anything from "confirm the exact address" to a door code or a remark about a fellow traveller; a group-chat link is as public as the group chat. The cost is real and visible in mockup 02 — the guest's card is a line lighter, and some of that line is genuinely useful to a companion. Defaulted closed because **exposure is one-way**: adding a field to the guest payload is a one-line PR, but a note already read in a group chat cannot be unread. The smallest override, deliberately not built pending confirmation, is a single `share_notes` boolean on `trip_share_link` |
| Q4 | Does the guest see **attachments** and **confirmation numbers**? (brief Q03, R05) | **No** | A confirmation number plus a surname is frequently enough to view, change or cancel a booking on the airline's or hotel's own site — a credential, not a detail. An attachment is a boarding pass with a scannable barcode. The attachments spec has not merged, so there is no field to expose yet; the tripwire makes its arrival a decision rather than a default |
| Q5 | Does the guest see **cost and currency data**? (R04, brief Q04) | **No** | R04 says the data is *stored*; it says nothing about who sees it. Cost is the most sensitive thing on a plan shared with the people it is being split with — and D12 puts cost splitting in *Later*, so no flow here needs the number |
| Q6 | Where does the token live in the URL, and how is it stored? | **In the path (`/s/{token}`), 256 bits, stored as issued** | The path keeps the link openable without JavaScript and pasteable anywhere, at the cost of appearing in logs — answered by an application logging filter that redacts the path *and* the `Referer` field. Stored as issued because seeing and re-copying the link is in scope (S4); the full argument, including why encryption at rest lost narrowly, is in Data Model |
| Q7 | How does a guest with no account get Polish or English? (R01) | **Reuse `detectInitialLocale()` exactly as it is** — stored choice, then browser language, then `pl` — with the existing header switch calling `applyLocale` and not `persistLocale` | Revised against the code: this function already exists and already does the detection. An earlier draft proposed an `en` fallback under a separate `guestLocale` key; both are dropped, because a second locale-detection path on one origin is worse than a terminal fallback the switch corrects in one click, and `SessionContext` already restores the owner's server-side locale on sign-in |
| Q8 | Does the owner learn that the link was opened? | **No** | Nothing in the brief asks for it, and it is a privacy surface pointed at the owner's friends. `created_at` is the only timestamp shown |
| Q9 | Does the guest get a day-detail screen, or only the timeline? | **Only the timeline — one route, one page** | Everything the owner's day detail adds is the editor, and every item is already on the timeline. D08 promises the guest the timeline and the counter, and one page delivers exactly that |
| Q10 | Is this one spec or several? (the mandatory split check) | **One spec, two phases** | There is exactly one independently deployable capability here — "share a trip read-only". The API without the UI ships nothing usable and the UI cannot exist without the API, so splitting would create two half-features and two approval decisions for one product decision |
| Q11 | Filtered owner models, or a separate guest model? | **A separate guest model, frozen by a serialized-payload snapshot plus per-model owner-only allow-lists and the route inventory** | Filtering at runtime means the next field ships to guests unless somebody remembers. A frozen snapshot means it does not ship until somebody decides. Its limit against attachments-as-a-route is stated, not glossed |
| Q12 | Is there a brute-force rate limit on the guest endpoint? | **No — a malformed-token pattern check in the handler; DoS capping left to the platform and not claimed as a repository control** | A 2^256 keyspace has no brute-force story to defend, and reusing `security/rate_limit.py` would mean migrating `login_attempt`'s non-null e-mail column for a threat that does not exist. There is no reverse-proxy config in this repository, so the DoS cap is named as a deployment note rather than pretended into the codebase |
| Q13 | What does a link to a **deleted** trip say? | **`410 share_link_gone` — "this plan no longer exists"**, via `ON DELETE SET NULL` rather than a cascade | §3 legislates this case by name. A `404` would talk about the link when the truth is about the plan, and reusing "no longer shared" would attribute to the owner a decision he did not take |

## 📋 Phasing

Two phases, sequenced rather than independent: Phase 1 is deployable but deliberately invisible, and Phase 2 cannot ship without it. Both land against a repository that already builds, tests and deploys, so every step below names real files.

- **Phase 1 — The link and the guest payload (server).** Migration, token minting, the projection and its three assertions, the three owner endpoints, the guest endpoint, its headers and its log redaction, and the `PUBLIC_PATHS` edit. Deployable on its own and user-invisible: no UI references it, so nothing is half-promised.
- **Phase 2 — The owner's dialog and the guest screen (client).** The share dialog, the `Shared` chip in its reserved slot, the `share` glyph, the `/s/:token` route, the guest shell and its dead-link pages, `robots.txt`, both locales, and the end-to-end walk.

The component extraction the first draft planned is **gone from this plan**: `ItemRow`, `StatusChip`, `ReadinessTile` and `FilterBar` already exist and already behave read-only when no callback is passed, so there is nothing to extract and no refactor to sequence around the attachments spec.

## 📋 Implementation Plan

Every step is testable and leaves the application working. The full eight-command validation gate — `check_locales.py`, `check_css_tokens.py`, `check_contrast.py`, `ruff`, `pytest`, `typecheck`, `vitest`, `build` — runs at each phase boundary. This structure is what `om-auto-implement-spec` hands to `om-auto-create-pr`.

### Phase 1 — The link and the guest payload (server)

1. Alembic revision and the `TripShareLink` model in `db/models.py`: the columns above, `trip_id` nullable with `ON DELETE SET NULL`, `UNIQUE` on `token`, the partial unique index, and an overridden `__repr__`. Verify: an upgrade/downgrade round-trip test; a test that the **database itself** rejects a second active link for one trip while accepting any number of revoked and any number of orphaned ones; a test that deleting a trip sets `trip_id` to NULL and leaves the row; and a test that the token appears in neither `repr()` nor `str()`.
2. `domain/sharing.py`: `mint_token()` over `secrets.token_urlsafe(32)` and `TOKEN_PATTERN`. Verify: unit tests for length, charset, and that 1000 mints are distinct.
3. `domain/sharing.py`: `project_trip_for_guest(...)`, the `GuestTripRead` / `GuestDayRead` / `GuestItemRead` models in `api/schemas.py`, and the owner-only allow-lists for `ItemRead`, `TripSummary`, `StageRead` and `DayRead`. Verify: **the tripwire** — (a) the full recursive key set of a guest payload rendered from a fixture trip (notes, several stages, a spanning item) equals a frozen constant; (b) each owner model's field set equals its guest set plus its declared owner-only set, so `ItemRead` gaining a field fails until it is classified; (c) a projected payload built from an item that has notes contains no `notes` key.
4. `errors.py`: `SHARE_LINK_NOT_FOUND`, `SHARE_LINK_REVOKED`, `SHARE_LINK_GONE`. Verify: the existing enum test — every member resolves to a non-empty key in both `en.json` and `pl.json` — now covers all three, and `check_locales.py` stays green.
5. `api/sharing.py`, included on the `AUTHENTICATED` dependency list: `GET`, `POST` and `DELETE /trips/{trip_id}/share-link`, all taking `get_owned_trip`. Verify: `{"link": null}` before sharing; `201` then `200`-with-the-same-token on a repeated `POST`; `204` on `DELETE` and `204` again when nothing is active; that `DELETE` sets `revoked_at` rather than removing the row; that **both unsafe methods reject a missing or mismatched CSRF token**; that another owner's trip answers `404` on all three; and that `test_every_trip_scoped_route_resolves_ownership_through_the_shared_dependency` still passes with the new `{trip_id}` routes registered.
6. `is_shared` on `TripSummary`, inherited by `TripDetail`. Verify: an API test that it flips with create and revoke on both `GET /trips` and `GET /trips/{trip_id}`, and that **no response body from any `/trips` route contains the token**, asserted by scanning the serialized payloads for it.
7. `api/shared.py`: `GET /api/v1/shared/{token}` with the pattern pre-check, the `404` / `410 revoked` / `410 gone` branches, and `Cache-Control: private, no-store`. Verify: a valid token returns the projected payload; unknown and malformed tokens return `404`, the malformed one without touching the database (asserted through the session); a revoked token returns `410 share_link_revoked`; an orphaned one returns `410 share_link_gone`; **no `Set-Cookie` header is present**; and a request carrying a valid owner session cookie receives the byte-identical guest response.
8. Add `f"{API_PREFIX}/shared/{{token}}"` to `PUBLIC_PATHS` in `app.py` **and** to the literal frozenset in `test_the_public_allow_list_stays_small`. Verify: the four route-protection tests pass with exactly one new entry, and adding a route without an entry still fails.
9. Response-header middleware (CSP, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex, nofollow`, `X-Content-Type-Options`) applied to the SPA document in `spa.py`'s fallback, and a `logging.py` filter on uvicorn's access logger redacting the `/s/…` and `/api/v1/shared/…` request paths and the `Referer` field globally. Verify: header assertions on a `/s/:token` document response and on the guest API response; and a logging test that a record whose path or referrer carries a token is emitted with the token replaced.

### Phase 2 — The owner's dialog and the guest screen (client)

1. `api/sharing.ts` and `features/sharing/ShareDialog.tsx`: State A, State B, copy with its clipboard fallback and `aria-live` confirmation, revoke through the existing `ConfirmDialog`. Reuses the modal recipe; adds no token to `tokens.css`. Verify: component tests for both states, the copy fallback path, revoke returning the dialog to State A, and focus returning to the "Udostępnij" trigger on close.
2. `TimelinePage`: the "Udostępnij" `.button-quiet` in the `AppShell` `actions` slot beside "Delete trip". Verify: a component test that the dialog opens from it and that the delete flow is unaffected.
3. The `share` glyph in `assets/icons.svg` and `IconName`; the `Shared` chip on the trip banner and on the `/trips` row, replacing the reserving comment in `screens.css`. Verify: a component test that the chip renders only when `is_shared` is true, `check_css_tokens.py` green, and `check_contrast.py` green with no new pair (the chip reuses an existing recipe).
4. `App.tsx`: `/s/:token` declared **outside** `RequireSession` and **before** the `*` catch-all. Verify: a test that an unauthenticated render of `/s/:token` shows the guest view and does **not** navigate, and a test that it still renders while the session probe is in flight.
5. `features/sharing/GuestShell.tsx` and `GuestTripPage.tsx`, composing `ReadinessTile`, `FilterBar`, `ItemRow` and `StatusChip`; `ItemRow`'s prop type widened to the fields it reads with `notes` optional. Verify: component tests that the guest screen renders banner, counter, filter bar and days; that it contains **no** link to any `/trips` route, no sign-out, no editing control and no notes paragraph; that item rows render as `div` rather than `button`; and that the existing `ItemRow` and day-detail tests still pass unchanged.
6. The three dead-link pages and the `503` retry state in `GuestTripPage`. Verify: component tests for all four, each asserting its copy in **both** locales.
7. All new keys in `en.json` and `pl.json`, and the guest locale switch wired to `applyLocale` without `persistLocale`. Verify: `check_locales.py` green; a test that the switch changes the guest view's language and writes no request.
8. `frontend/public/robots.txt` **without** a `/s/` disallow, and a test that `index.html` still carries a static title and no `og:` or `twitter:` meta tag. Verify: a build-artifact scan asserting the emitted `index.html` and bundles reference no external `https://` origin — a real assertion over `dist/`, not a jsdom one, which cannot observe subresource fetches.
9. End-to-end verification of the brief's own sharing flow: the owner signs in, opens the Malaysia trip, creates a link and copies it; a **clean browser context with no cookies** opens the link and sees the timeline, the counter and the status chips but no notes, no sign-out and no editing control; the owner revokes; the same link reloads to "this plan is no longer shared". Verify: an integration test walking that path, with screenshots in both locales on the implementation PR, following the capture discipline the design-system run established (wait on `document.fonts.ready`, assert an element per screen, fail loudly on a locale mismatch).
