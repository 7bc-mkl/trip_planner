# Read-only trip sharing — one magic link per trip

- Date: 2026-09-05 · Author: `om-auto-write-spec` (autonomous) · Status: draft, gated on the assumptions below
- Source brief: `.ai/specs/product-brief.md` (signed 2026-09-05)
- Depends on: `.ai/specs/2026-09-05-walking-skeleton.md` — its stack, `/api/v1` conventions, error-code enum, `get_owned_trip` ownership dependency and route-enumeration test are settled and reused here, never re-derived
- Adjacent, in flight: the attachments and reservation-data spec. This spec does **not** wait for it; it defines the mechanism (the projection allow-list and its test) that forces that spec's new fields to get an explicit sharing decision instead of leaking by default
- Visual reference: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/g_wny_pulpit_i_o_czasu` — the timeline the guest sees, and its "Udostępnij" button. The guest view itself has no mockup in the export; it is designed here
- Mode: `om-spec-writing --autonomous`. Every question this spec answered on its own is listed under **Resolved assumptions (autonomous defaults)** and is open to override before merge.

## 📝 TLDR

The owner presses "Udostępnij" on a trip's timeline and gets one link. Anyone holding that link opens the same timeline and the same readiness counter in a browser, in Polish or English, without an account, without a cookie, and without the ability to change one character of the plan. The owner can see the link again, copy it again, and revoke it; revoking it is permanent for that link and a new one can be generated afterwards.

This is the third slice of the brief's *Now* scope and it is mandated, not optional: D08 fixes the shape ("jeden dla projektu, read only w v1") and D09 fixes the permission model (one editor, guests read). **Nothing this document builds is cut, and nothing D08 or D09 mandates is deferred here.**

The reason it deserves a careful spec rather than a CRUD ticket is that it opens the product's first unauthenticated surface on the public internet (D14). R08 is written in two halves — *no screen showing a plan is reachable without either an owner session or a trip's magic link*. The walking skeleton built the first half. This spec builds the second, and a guessable link, a leaked link, or a link that quietly carries more than the owner thinks it carries is a published plan.

## 📝 Problem Statement

P2, in the brief's own words: *there is no good way to share the state of the plans with other people*. A plan held in someone's head, their mailbox and a partial spreadsheet cannot be shown to a companion without retelling it. The Key flows section describes the whole intended interaction in one line — *the owner sends the trip's link to a companion → the companion opens the same timeline and counter, read-only → any reaction happens outside the app* — and notes that it is **not in the design export**, which shows only an "Udostępnij" button.

**Why this ships now, and what it is not justified by.** The brief's Definition of Ready addendum is explicit: *every ticket whose justification is "so that other people can use it" is out of scope until A01 is tested — the sharing link in Now is there because the owner wants to show his own plan, not because a second user was found*. This feature's justification is therefore **P2 and D08**, not A01. A01 ("people other than the owner have problems P1 and P2") is accepted untested by D15 and nothing here depends on it: the guest is not a user of the product, has no account, and the product gains no second user by shipping this. A06 ("a read-only link is enough for travel companions") is likewise untested — and this feature is the *instrument* of A06's own smallest test (*send the Malaysia link to whoever travels along and count how many ask to change something*), which is one more reason to build it read-only first and hear the requests, rather than to design comments (D09, D12) against a guess.

Evidence and its limits, carried forward honestly: P2 is an `[INTERVIEW]` claim from one session with one person who is also the builder, with no frequency and no cost attached. There is no benchmark data at all (brief Q01, still open — see Research below, which is explicitly from knowledge rather than from a check).

## 📝 Scope

### In scope

| # | Capability | Contract it serves |
|---|---|---|
| S1 | Exactly one **active** magic link per trip, minted by the owner, structurally enforced rather than merely intended | D08, R05 |
| S2 | The link grants **read-only** access to the trip's timeline and its readiness counter, to a recipient with no account and no session | D08, R05, R06, D09 |
| S3 | The **guest view** — designed here, since the export has none — reusing the owner's timeline components read-only rather than building a second timeline | brief Key flows, "Future state — sharing" |
| S4 | The **owner's side**: generating the link, seeing it again later, copying it, and knowing at a glance that a trip is shared | the brief's "Udostępnij" affordance |
| S5 | **Revocation** — the owner can end a link's life, and an ended link says so rather than disappearing | R05 (undecided → resolved below); `BACKWARD_COMPATIBILITY.md` §3 |
| S6 | The **security boundary**: exactly one new unauthenticated route family, enumerable, with an explicit field projection deciding what a guest may see | R08, D14 |
| S7 | Polish and English, both first-class, for a guest who never chose a language in this product; `scripts/check_locales.py` green | R01, R09 |

### Out of scope — and the honest authority for each cut

**No row in this table is authorised by A05.** A05 is the brief's mechanism for sequencing the *Now* list under calendar pressure, and this milestone uses it for nothing: everything D08 and D09 mandate is built here. The cuts below are all decision-backed deferrals to *Later*, which is a different thing and is kept a different thing deliberately.

| Not built here | Authority — and it is never A05 |
|---|---|
| Guest comments and suggestions on a shared plan | **D09**, which settled it: said first as an optional extra ("z **ew.** możliwością skomentowania") and then closed with "read only w v1". **D12** puts it on the *Later* list by name. This is a real decision, not a deferral of something this spec was asked to build |
| Several people editing one trip; a permissions or roles model; invitations | **R06 / D09** — a trip has exactly one editor, its owner |
| Public plans as inspiration; discovery; anything indexable | **D12**, *Later*. This spec actively works against it: the guest page is `noindex` |
| Chat, the assistant, AI suggestions on the shared view | **A05** cut it from the walking skeleton, naming chat first; it remains in *Now* for a later spec. Not shown to guests for the simpler reason that it does not exist yet |
| A second owner login path; "sign in with this link"; converting a guest into an account | **R08**, which is explicit that the magic link is *for guests rather than a second owner login path*. The guest endpoint therefore sets no cookie and creates no session — see Security |
| Link expiry as a policy | Resolved below (Q1) as *no automatic expiry in v1*, with revocation as the control. Not a deferral of anything a decision row mandates: R05 records expiry as **undecided**, and this spec decides it |
| Per-link passwords, per-recipient links, access logs, "who opened it" | Nothing in the brief asks for them, and each is an addition to a shape D08 fixes at *one link per trip*. See Research for why the market leaders carry them and we do not |
| Export to PDF / Calendar / Wallet, "Eksportuj PDF" beside the export's share button | **D12**, *Later* |

Nothing here is *excluded*: N01 and D12 say the product excludes nothing permanently.

### The slippable tail

A05 decides the month, so this spec names its own cut line rather than discovering it on 2026-09-14. In priority order, the **last things built and the first things to drop** are: the `is_shared` chip on the trip-list rows (the timeline header keeps its own), and the guest's per-item-type filter chips (which do not exist for the guest if the owner's Phase 4 slipped, because it is the same component).

**Revocation is explicitly not slippable.** A sharing feature that cannot be turned off is a privacy hole, and since Q1 resolves to *no automatic expiry*, revocation is the **only** control that exists. If the calendar forces a choice between the `is_shared` chip and the revoke action, the chip goes.

## 📝 Proposed Solution

Four decisions carry the whole design, and each of them is about a boundary rather than a screen:

1. **A separate route namespace for guests, not a widened owner route.** The guest reads `GET /api/v1/shared/{token}`. The owner's `GET /api/v1/trips/{tripId}` is not taught to accept a token. This keeps the walking skeleton's invariant — *every `/trips/…` route carries `get_owned_trip`* — literally true and machine-checked, and it puts the entire unauthenticated surface of the product in one auditable handler.
2. **The guest payload is a different model, not a filtered one.** A `GuestItem` Pydantic model with its own declared field set, produced by an explicit projection function in `domain/sharing.py`. A field added to the owner's item model does **not** appear on the guest's; it makes a test fail. This is the mechanism, not a convention, and it is the reason the in-flight attachments spec cannot leak a boarding pass into a group chat by accident.
3. **One timeline, rendered twice.** The timeline's presentational pieces — trip hero, readiness counter, filter bar, day row, item card — are extracted into components that take data and no editing callbacks. The owner screen and the guest screen are two thin route components composing the same pieces. There is deliberately **no `isGuest` boolean threaded through the tree**: a mode flag is exactly how an edit affordance leaks into a read-only view six months later.
4. **The link is a bearer credential and is treated like one everywhere except at rest.** 256 bits of entropy, never logged, never sent in a `Referer`, never indexed, never cached — but stored in plaintext, because the owner's ability to *see and copy the link again* is in scope (S4), and hashing it would protect a database dump that already contains every plan the link could reveal. That reasoning is set out in full under Data Model.

**Alternatives considered and why they lost:**

- **A signed, stateless token (JWT / itsdangerous) with the trip id and an expiry inside it.** No table, no lookup. Rejected on the one requirement that matters: it cannot be revoked. Revocation would need a denylist table, which is the table we avoided plus an extra moving part — and with no expiry (Q1) the denylist would grow forever. Statelessness buys nothing at one owner.
- **The token in the URL fragment (`/s#<token>`) instead of the path.** The fragment is never sent to the server, so it cannot reach an access log. Rejected because the token then must be read by JavaScript and moved into a header, the page cannot be opened without JS, and some link previewers and chat clients handle fragments unevenly. The logging problem is solved directly instead — the access-log format redacts the path for `/s/` and `/api/v1/shared/` — and the `Referer` problem is solved by policy plus the guest page making no external requests at all.
- **Reusing `GET /trips/{tripId}` with an optional `?token=`.** Fewer endpoints. Rejected: it makes the one enforceable statement about owner routes conditional, and it puts the decision about which fields a guest sees inside a handler that also serves the owner — the exact place where a future `notes` field gets forgotten.
- **A per-recipient link ("send to Kasia").** Rejected by D08: *one link per trip* is what gets pasted into a group chat, and the owner said so.
- **Hashing the token at rest, showing it once.** Rejected because it removes S4 — the owner could never see the link again and would have to revoke and regenerate to re-copy it, which is a worse privacy outcome (more links minted) for a security benefit that is nil in this threat model. Argued in full below.
- **A rendered public HTML page instead of the SPA route.** Marginally faster and would not need JS. Rejected: it is a second implementation of the timeline, which is precisely what the brief's "reuse the owner's timeline read-only" instruction rules out, and it would duplicate the i18n layer server-side.

## 📝 Research — what the market leaders do, and what we skip

**Epistemic warning, stated up front.** Brief Q01 records that nothing has ever been checked and *"a competitor described from memory would be a guess wearing the clothes of a fact"*. This run had no network access, so the paragraph below is **from knowledge, not from a check**, and it is `[ASSUMPTION]`-grade for the same reason the brief's benchmark table is empty. Q01 stays open; nothing in this spec's design depends on a claim in this section.

The document-sharing pattern (Google Docs, Notion, Dropbox) and the trip-specific one (Wanderlog, TripIt) converge on the same four things, and we take all four: an **unguessable link rather than an obscure id**, a **copy button as the primary action** because the link's whole purpose is to be pasted somewhere else, a **plain sentence in the dialog naming who can see the plan** rather than an icon, and **`noindex` on the shared page** so a link pasted into a public forum does not become a search result. The sentence is worth singling out: Google Docs writes "Anyone on the internet with the link can view", and that phrasing is the only thing standing between an owner and a wrong mental model of what he just created. The share dialog below copies that pattern deliberately.

What they carry that we skip, and why each is right to skip **here** rather than wrong in general: **link roles** (view / comment / edit) — D09 says one editor and read-only, so there is exactly one role; **per-person invitations and per-recipient links** — D08 says one link per trip; **password-protected links and expiry pickers** — a second control to explain and a second failure mode, for an audience of one owner and his travel companions; **access logs / "who viewed this"** — a privacy surface of its own that tells the owner when a friend looked at the plan, which nothing in the brief asks for. Each of these is an addition later; none of them is a shape this document forecloses.

The one place we are plausibly *behind* the leaders and accept it: they let the sharer choose what the recipient sees. We decide it once, globally, in the projection below — and Q3/Q4/Q5 record that as an assumption for the owner to override rather than as a settled truth.

## 📝 Architecture

Additions only. Nothing in the walking skeleton's layout moves.

```
backend/trip_planner/
  api/sharing.py          NEW  owner endpoints (session + get_owned_trip)
  api/shared.py           NEW  the guest endpoint — the whole public surface, one file
  domain/sharing.py       NEW  pure: mint_token(), project_trip_for_guest()
  db/models.py                 + TripShareLink
  errors.py                    + share_link_not_found, share_link_revoked, share_link_gone
migrations/                    one revision: trip_share_link

frontend/src/
  features/timeline/components/   NEW  extracted presentational pieces (hero, counter,
                                       filter bar, day row, item card) — no callbacks
  features/timeline/OwnerTimeline.tsx   composes them, adds editing affordances
  features/sharing/ShareDialog.tsx  NEW owner: generate / view / copy / revoke
  features/sharing/GuestTrip.tsx    NEW the /s/:token route
  api/sharing.ts              NEW  typed client for both sides
```

Boundaries that matter:

- **`domain/sharing.py` is pure**, like every other `domain/` module: token minting is a function over `secrets`, and the projection is a function from owner-shaped values to guest-shaped values with no database access. Both are unit-testable without fixtures.
- **`api/shared.py` is the entire unauthenticated surface of the product** apart from `POST /auth/login` and the health check. It is one file so that "what can the internet reach" is answerable by reading one file, and the route-enumeration test's public allow-list names its one route explicitly.
- **The frontend never computes readiness** — unchanged rule. The guest payload carries `{arranged, tracked}` from the same `domain/readiness.py`, so R02 keeps exactly one implementation and the guest cannot be shown a different number from the owner.
- **Filtering stays in the browser** — unchanged rule (walking-skeleton A11). The guest payload is complete; the guest's filter bar is the owner's component over the owner's data.
- **No external calls, still.** This matters more here than anywhere else: see Security, where a single web-font request from a CDN would hand the full share URL to a third party in a `Referer` header.

## 📝 Data Model

One new table. No column is added to `trip`, `trip_day` or `item`.

### `trip_share_link`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `trip_id` | UUID FK → `trip.id`, `ON DELETE CASCADE`, indexed | |
| `token` | TEXT NOT NULL, `UNIQUE` | 256 bits from `secrets.token_urlsafe(32)` → 43 URL-safe characters. Stored as issued; see the plaintext argument below |
| `created_at` | TIMESTAMPTZ NOT NULL | shown to the owner in the share dialog |
| `revoked_at` | TIMESTAMPTZ NULL | NULL means active. Set, never unset; a revoked row is never deleted |

```sql
CREATE UNIQUE INDEX ux_share_link_active ON trip_share_link (trip_id) WHERE revoked_at IS NULL;
```

**That partial index is D08 and R05 made structural**, the same way the status `CHECK` constraint makes R02 structural rather than conventional: "exactly one magic link per trip" is enforced by the database, not by a handler remembering to check. Revoked rows accumulate freely and carry no uniqueness, which is what lets an old link keep answering *"this plan is no longer shared"* forever.

**Why the token is stored in plaintext, and why that is not the walking skeleton's session mistake repeated.** The walking skeleton hashes session tokens because a database dump would otherwise yield working sessions — and a session grants *write* access to the owner's account, every trip he has, and every trip he will ever have. A share token grants **read** access to exactly one trip, whose entire contents sit in the same dump. Hashing it would protect nothing an attacker with that dump does not already hold, and it would cost the capability S4 explicitly requires: the owner seeing and re-copying his link. The alternative — show-once — makes the owner revoke and regenerate every time he loses the message, minting more live links than he needs, which is a worse privacy outcome than the one hashing was supposed to buy.

That argument holds only if the token is disciplined everywhere else, so:

- excluded from every response model except the owner's own share endpoints;
- `TripShareLink.__repr__` is overridden so it cannot reach a log line, exactly as `owner.password_hash` is;
- never written to an application log, an error body, an exception message or a metric label;
- the access-log format redacts the path for `/s/…` and `/api/v1/shared/…` (see Deployment notes).

**No `expires_at` column.** Q1 resolves to no automatic expiry, and the walking skeleton set the precedent for not shipping columns nothing can populate (it refused `cost` and `confirmation_number` for exactly that reason). Should expiry ever be decided, it is **one nullable column and one clause in one query** — an addition, the cheapest change in this document, and safe under `BACKWARD_COMPATIBILITY.md` §2.

**No `last_accessed_at`, no view counter.** Q8 resolves against them: they are a privacy surface of their own — they tell the owner when a friend looked at his plan — and nothing in the brief asks for them.

### Relationship summary

```
owner 1─n trip 1─0..n trip_share_link      (at most ONE row with revoked_at IS NULL — partial unique index)
                        deleting the trip cascades its links away
```

### Migration

One Alembic revision creating `trip_share_link` and its partial unique index, with a working `downgrade`. It creates a table that did not exist, so the `BACKWARD_COMPATIBILITY.md` "safe against rows that already exist" rule is vacuous for it.

## 📝 API Contracts

Conventions are the walking skeleton's, unchanged: JSON under `/api/v1`, ISO dates and wall-clock times with no timezone, unknown request fields rejected, errors as `{"error": {"code": "<stable_code>", "field": "<name|null>"}}` with the code drawn from the `ErrorCode` enum in `backend/trip_planner/errors.py` and resolving to a non-empty key in **both** locale files (the enum test, not `check_locales.py`, is what catches a missing mapping).

### Owner side — session-authenticated, `get_owned_trip`, under `/trips/{tripId}`

| Method | Path | Body / Response | Notes |
|---|---|---|---|
| `GET` | `/trips/{tripId}/share-link` | → `200 {"link": null}` or `200 {"link": {"token", "url", "created_at"}}` | "not shared" is a normal state, not a `404`. Called when the share dialog opens, never as part of the timeline payload, so the secret is fetched only when it is about to be shown |
| `POST` | `/trips/{tripId}/share-link` | → `201 {"link": {...}}` on create; **`200` with the existing link when one is already active** | Deliberately idempotent. A double-click, a retried request or a second browser tab must never silently rotate a link that is already sitting in a group chat. There is no `409` here because "already shared" is the desired end state, not an error |
| `DELETE` | `/trips/{tripId}/share-link` | → `204` | Sets `revoked_at`; never deletes the row. Idempotent: `204` even when there is no active link |

`GET /trips` and `GET /trips/{tripId}` gain **one additive optional boolean**, `is_shared` — never the token. It is what lets the timeline header and the trip-list row show that a plan is currently reachable by anyone holding a link. Adding an optional response field is explicitly non-breaking under `BACKWARD_COMPATIBILITY.md` §1.

A trip belonging to another owner answers `404` on all three, identically to every other trip-scoped route — the `403` would confirm the trip exists.

### Guest side — the entire unauthenticated surface

| Method | Path | Response |
|---|---|---|
| `GET` | `/shared/{token}` | `200` guest payload · `404 share_link_not_found` (unknown, malformed, or the trip is gone) · `410 share_link_revoked` |

- **No cookie is read and none is set.** A session cookie that happens to be present is ignored: an owner who opens his own link sees exactly what his companion sees, which is the honest preview and is asserted by a test.
- **`GET` only.** There is no guest write path to defend, because there is no guest write endpoint — an absence, not a permission check (R06, D09).
- The token is validated against `^[A-Za-z0-9_-]{43}$` **before** any query, so malformed input is a `404` that never touches the database.

The guest payload:

```jsonc
{
  "trip":   { "title", "start_date", "end_date", "departure_place", "return_place" },
  "stages": [ { "id", "position", "place", "start_date", "end_date" } ],
  "days":   [ { "date", "stage_ids": [...], "items": [
                  { "id", "kind", "status", "start_time", "end_time", "end_date", "title" } ] } ],
  "readiness": { "arranged", "tracked" }
}
```

**What is structurally absent, and why the word "structurally" is load-bearing:** `item.notes`, and — when the attachments spec lands them on the owner's model — attachments, confirmation numbers, cost and currency. Also absent: the owner's e-mail, id and locale; the trip's id; any URL that reaches an owner route. The `id` fields that remain are opaque UUIDs used as React keys; they unlock nothing, because every owner route still requires a session *and* ownership.

**The projection test — the one test this spec exists to add.** In `domain/sharing.py`:

```python
GUEST_ITEM_FIELDS = frozenset({"id", "kind", "status", "start_time", "end_time", "end_date", "title"})
OWNER_ONLY_ITEM_FIELDS = frozenset({"notes", "position", "trip_day_id", "created_at", "updated_at"})
```

Two assertions, run in CI:

1. `set(GuestItem.model_fields) == GUEST_ITEM_FIELDS` — nothing enters the guest payload without editing this constant.
2. `set(OwnerItem.model_fields) == GUEST_ITEM_FIELDS | OWNER_ONLY_ITEM_FIELDS` — **the important one.** The day the attachments spec adds `attachments` or `confirmation_number` to the owner's item model, this test goes red, and the only ways to make it green are to put the field in the guest allow-list or to declare it owner-only. Either way a human makes a privacy decision. Without this test the default is "the new field ships to everyone holding the link", which is the failure mode this whole document is written against.

### Error codes added to the enum

| Code | Status | Meaning |
|---|---|---|
| `share_link_not_found` | `404` | Unknown or malformed token, or the trip no longer exists |
| `share_link_revoked` | `410` | The token was issued for a real trip and the owner revoked it |

**On the `404` / `410` distinction being an oracle:** it tells the holder of a token that the token once existed. With 256 bits of entropy nobody reaches this branch by guessing — the only party who can present a revoked token is somebody the owner sent it to, and that person is exactly who deserves the true answer. `BACKWARD_COMPATIBILITY.md` §3 demands it in so many words: a shared itinerary link *"must keep resolving, or resolve to an explicit 'this plan is no longer available', never to a wrong plan"*. A `404` for a revoked link would fail that sentence.

## 📝 UI/UX

Mockups of the proposed screens live beside this spec and are attached to this spec's PR. They are illustrative statics — layout and flow, not pixel-perfect design — rendered from self-contained HTML with no application code behind them. There are **no current-state screenshots**: the walking skeleton has not merged, so there is no running application to photograph.

| Screen | Mockup |
|---|---|
| The owner's share dialog over the timeline, active-link state, Polish locale | [`assets/trip-sharing-magic-link/mockup-01-share-dialog.png`](assets/trip-sharing-magic-link/mockup-01-share-dialog.png) |
| `/s/:token` — the guest view, Polish locale | [`assets/trip-sharing-magic-link/mockup-02-guest-view.png`](assets/trip-sharing-magic-link/mockup-02-guest-view.png) |
| `/s/:token` — the revoked-link state, **English locale** | [`assets/trip-sharing-magic-link/mockup-03-guest-revoked.png`](assets/trip-sharing-magic-link/mockup-03-guest-revoked.png) |

Two mockups are in Polish and one in English on purpose: R01 makes both locales first-class, and a spec that only ever pictures one of them is not showing the product it describes.

### The owner's share dialog

Opened from **"Udostępnij"** in the timeline's action row — the design export's own position for it in `g_wny_pulpit_i_o_czasu`, where it sits beside "Eksportuj PDF" (dropped, D12). It is a focus-trapped dialog that returns focus to its trigger, per the walking skeleton's cross-cutting rules.

**State A — not shared yet.** One sentence of plain copy naming the consequence, then one primary action:

> *Każdy, kto ma ten link, zobaczy ten plan — bez konta i bez logowania. Nie zobaczy Twoich notatek, załączników, numerów rezerwacji ani kosztów.*
> *Anyone with this link can see this plan — no account, no sign-in. They will not see your notes, attachments, confirmation numbers or costs.*

Primary action: **"Utwórz link" / "Create link"**. The sentence is not decoration; it is the Google-Docs pattern from Research and the only place the owner's mental model gets corrected before the link exists. It also states the Q3/Q4/Q5 projection in words, so an owner who disagrees with it finds out at the moment he can still say so.

**State B — shared.** The URL in a read-only, full-width, selectable text field; a **"Kopiuj" / "Copy"** button as the primary action with a transient "Skopiowano ✓" confirmation; the creation date formatted through `Intl`; the same sentence about who can see it; and a destructive **"Odwołaj link" / "Revoke link"** action, visually secondary, behind a confirmation step:

> *Wszyscy, którym wysłałeś ten link, stracą dostęp. Tego nie da się cofnąć — możesz później utworzyć nowy link.*
> *Everyone you sent this link to will lose access. This cannot be undone — you can create a new link afterwards.*

Copying uses `navigator.clipboard.writeText`; where it is unavailable the field's text is selected instead and the button label becomes "Zaznacz / Select", because a copy button that silently does nothing is worse than no button.

After a successful revoke the dialog returns to **State A** in place, so "revoke" and "create a new link" are two deliberate actions rather than one "regenerate" click that conflates *stop sharing* with *share differently*. An owner who wants to stop must not have to mint a new secret to do it.

**The `is_shared` indicator.** When a trip has an active link the timeline header carries a small chip — 🔗 *Udostępniona* / *Shared* — and, in the non-slippable case, so does the trip's row in `/trips`. Without it there is no way to tell from the plan itself that it is currently readable by anyone holding a link, and R08's whole subject is knowing what is reachable.

### `/s/:token` — the guest view

One route, one screen. **There is no guest day-detail screen**: everything the owner's `/trips/:id/days/:date` adds is the editor, and every item is already on the timeline. One page is also the right shape for the medium — the link is opened once, on a phone, from a chat message.

- **Chrome:** the brand, the PL/EN switch, and nothing else. No account menu, no "sign in", no navigation to `/trips`, no route by which a guest can discover that owner screens exist.
- **A one-line banner under the header:** *Widok tylko do odczytu, udostępniony przez autora planu* / *Read-only view shared by the trip's owner*. It answers the guest's first question — "can I change this?" — before he tries.
- **The trip hero:** title, date range, route summary — identical component to the owner's.
- **The readiness counter:** identical component, identical arithmetic, identical `tracked = 0` copy (*"nic jeszcze nie załatwione"* / *"nothing arranged yet"*, no fraction, no percentage, no bar). This is half of what D08 promises the guest and it must not be a reduced version of the owner's number.
- **The filter bar:** the owner's component, unchanged, client-side over the same payload. *Only outstanding* is genuinely the guest's question too. If the owner's Phase 4 slipped and the chips do not exist, the guest has no chips either — one component, one fate.
- **The timeline:** the same day rows, date chips, item cards and status chips. Item cards are **not** interactive: no link, no dialog, no hover affordance suggesting one, no "Add item", and an empty day reads *Nic jeszcze nie zaplanowane* / *Nothing planned yet* rather than the owner's invitation to add the first item.
- **Item cards carry no notes line.** The card component takes `notes?: string` and renders the paragraph only when it is present — one component, not two, and the guest's card is simply lighter. Stated plainly because it is the visible face of Q3 and the owner should see the cost of the default before merging it.
- **Errors are pages, not toasts:** an unknown token renders *Ten link nie działa* / *This link does not work*; a revoked one renders *Ten plan nie jest już udostępniony* / *This plan is no longer shared*, with a line suggesting the recipient ask the owner for a new link. Both are full pages with the same chrome and the locale switch, because the recipient has nowhere else to go in this application.
- **A failed request is not an empty timeline.** `503` renders a retry state, per the walking skeleton's rule that an empty timeline is indistinguishable from a real empty trip and would be a lie about the plan.

### Locale for a person with no account

The guest never chose a language here, so i18next language detection reads the browser's preference: **Polish when the browser prefers Polish, English otherwise**, with the switch overriding it and persisting to `localStorage` for that browser. English rather than Polish is the fallback because `AGENTS.md` names English the reference locale and it is the better guess for anyone who is not a Polish speaker; the owner's own default stays `'pl'` on his account, which is a different population and a different setting. `<html lang>` follows the active locale, and every date and number goes through `Intl`.

### Accessibility

The dialog is a real `role="dialog"` with a focus trap and an ESC path. The copy confirmation is announced through an `aria-live="polite"` region, since a purely visual "✓" is invisible to a screen reader. Status chips on the guest view keep the owner view's rule — a translated **text node** plus a `data-status` attribute, never colour alone. The guest page has one `<h1>` (the trip title) and real day headings, so it is navigable by landmark on a phone screen reader.

## 📝 Edge Cases & Failure Scenarios

| Case | Behaviour |
|---|---|
| Unknown token | `404 share_link_not_found`; the "this link does not work" page |
| Malformed token (wrong length or charset) | `404`, rejected by the pattern check **before** any database query |
| Trailing punctuation added by a chat client (`…/s/abc.`) | Fails the pattern check → `404`. Not defended against further; the copy button copies a clean URL and guessing at punctuation stripping would risk resolving a *near* token |
| Revoked token | `410 share_link_revoked`; the "no longer shared" page. Permanent — the row is never reactivated |
| Trip deleted after sharing | The link row cascades away → `404`, the same page as an unknown link. Deliberately **not** `410`: a deleted plan has no state to report, and calling it "no longer shared" would attribute to the owner a sharing decision he did not make |
| Owner opens his own link while signed in | Sees the guest view. The endpoint ignores the session cookie and sets none — the honest preview, and asserted by a test |
| Two `POST /share-link` in a row (double click, retry, second tab) | The second answers `200` with the **same** link. A live link is never silently rotated |
| `DELETE /share-link` when nothing is shared | `204`, idempotent |
| Revoke, then create a new link | A fresh token; the old row keeps answering `410` for ever. The two are never confused, because the token is unique across the whole table |
| A guest calls an owner route with the token as a cookie or header | `401`. The token is not a session and no code path turns it into one (R08) |
| The plan changes while a guest has the page open | The link always resolves to the **live** plan; the guest sees the change on reload. This is the feature, and it is `BACKWARD_COMPATIBILITY.md` §3's "never to a wrong plan" |
| The trip's date range shrinks after sharing | Nothing special: the guest sees the current days. Day and item deletion rules are the owner-side rules already specified in the walking skeleton |
| A trip with no items at all | The guest sees every day, each with the "nothing planned yet" state, and the counter's `tracked = 0` copy |
| An item spanning into a later day | Rendered once on its start day with the "→ dd.MM" marker and counted once — the owner's rule, reused, not re-specified |
| Guest browser prefers neither Polish nor English | English, with the switch one click away |
| Backend unavailable | `503`; the retry state, never an empty timeline |
| A crawler follows a link pasted in a public forum | `X-Robots-Tag: noindex, nofollow`, the `<meta name="robots">` equivalent, and `Disallow: /s/` in `robots.txt`. All three are advisory against a hostile crawler — the honest control is that the URL is unguessable and the owner can revoke it |

**Documented, not built.** Concurrent revocation while a guest request is in flight is last-write-wins on a single row and needs no locking: the worst case is one already-issued response for a link revoked in the same millisecond. There is no cleanup job for revoked rows; they are the audit trail and they are tiny.

## 📝 Security

This is the section D14 makes non-optional, because it is the first time anything in this product answers a request from a stranger.

**R08's second half, made enumerable.** The walking skeleton's route-enumeration test asserts every route is either in an explicit public allow-list or carries `get_current_session`. This spec adds **exactly one** entry to that allow-list, `GET /api/v1/shared/{token}`, in the same commit as the route. Every future public route is therefore a deliberate edit to a test rather than an omission nobody notices — and "what can the internet reach" stays a question with a checked answer.

| Control | What it is, and what it is for |
|---|---|
| **Token entropy** | 256 bits from `secrets.token_urlsafe(32)`. Never derived from the trip id, never sequential, and deliberately **not a UUID** — a UUIDv4 carries 122 bits and, worse, *looks like an identifier*, which invites treating it as non-secret |
| **No brute-force control, and why that is the rigorous answer** | At an implausible one million guesses per second against a 2^256 space, the expected time to find any live token exceeds the age of the universe by many orders of magnitude. A rate limiter here would be security theatre and a table nobody needs. What the endpoint *does* need is ordinary **DoS** protection, which belongs at the platform proxy as a per-IP request cap, noted under Deployment |
| **No `Referer` leakage** | `Referrer-Policy: no-referrer` on the guest page, **and no external requests from it at all** — no CDN fonts, no analytics, no map tiles, no third-party icons. This is concrete, not theoretical: the design tokens name *Plus Jakarta Sans*, and a Google Fonts request from `/s/<token>` would hand the complete share URL to a third party under the default referrer policy. The font is self-hosted |
| **Not indexable** | `X-Robots-Tag: noindex, nofollow` on the guest HTML and the guest API response, the `<meta name="robots">` equivalent for crawlers that read only the body, and `Disallow: /s/` in `robots.txt`. Listing the path in `robots.txt` is safe: the path is not the secret, the token is |
| **Not cached** | `Cache-Control: private, no-store` on the guest payload. This is a correctness control as much as a privacy one — a CDN-cached payload would keep serving a plan after revocation, and revocation is the only kill switch this design has |
| **Not logged** | The access-log format redacts the path for `/s/…` and `/api/v1/shared/…`; the model's `__repr__` is overridden; the token appears in no error body, exception message or metric label. A token in a log line is a live link in a log line |
| **No cookie, no session, ever** | The guest endpoint reads no cookie and sets none. R08 is explicit that the magic link is for guests rather than a second owner login path, and this is that sentence in code |
| **No guest write path** | Not a permission check — an absence. The guest surface is one `GET` |
| **Owner endpoints still owned** | The three share endpoints take `get_owned_trip`, so no owner can mint, read or revoke a link for a trip that is not his; another owner's trip answers `404` |
| **Immediate revocation** | One indexed lookup per guest request, no in-process token cache, no CDN caching. Revocation takes effect on the next request, always |
| **Field-level exposure decided once, in code** | The projection allow-list and its two tests, above. This is the control that survives the next six specs |

**What this design does not protect against, stated plainly.** A guest can forward the link to anyone. The link *is* the credential and it is bearer-only: the magic link's security model is that of the group chat it gets pasted into — whoever can read the message can read the plan. Nothing in D08's shape can change that, and pretending otherwise with an expiry date would be a comfort rather than a control. **Revocation is the only real control, which is exactly why it is in v1 and why it is not in the slippable tail.**

## 📝 Deployment notes

No new deployable, no new environment variable. Three configuration facts belong in the release checklist rather than in code:

- the guest share URL is built from `APP_BASE_URL`, which the walking skeleton already requires at startup;
- the reverse proxy's access-log format redacts `/s/…` and `/api/v1/shared/…` paths, and its response-header block adds `X-Robots-Tag` for those paths;
- a per-IP request cap on `/s/` and `/api/v1/shared/` at the proxy, as DoS protection only — never presented as protection against guessing.

## 📝 Risks & Impact Review

- **Blast radius: additive throughout.** One new table, one new public route family, three new owner endpoints, two new error codes, one additive optional response field (`is_shared`), new locale keys, and a pure refactor extracting timeline components. Under `BACKWARD_COMPATIBILITY.md` §1, adding endpoints and optional response fields is explicitly non-breaking; under §2 the migration creates a table that did not exist. **Nothing changes meaning**, which §1 calls the worst and quietest class of break.
- **§3 is the section this spec answers directly.** *"Shared or exported itineraries (public links, exports) are external contracts: an old link must keep resolving, or resolve to an explicit 'this plan is no longer available', never to a wrong plan."* Satisfied three ways: tokens are unique across the table for all time so a token can never come to mean a different trip; a revoked link answers `410` with exactly that message rather than vanishing; and a live link always resolves to the current plan.
- **The one risk that cannot be rolled back is exposure.** Every other decision here is reversible in a PR. What a link has already shown to a group chat cannot be unshown — you cannot un-send. That asymmetry is the entire justification for defaulting the projection to the minimum and for marking Q3 as needing human confirmation rather than quietly shipping the owner's private notes.
- **The dependency that will actually bite: the attachments spec.** It adds fields to the owner's item model — attachments, and under R04 confirmation numbers and cost. The projection test above is designed to fail the moment it does, forcing a decision. This spec does not block on it and it does not block this spec: attachments are simply not in the allow-list, and if the attachments PR merges first, the failing test is the conversation.
- **Rollback story.** One migration with a working `downgrade`; dropping the table removes every link, which is the safe direction for a privacy feature — a rollback closes access rather than opening it. The frontend rollback loses the guest route, which turns every live link into a `404` page. Both are recoverable and neither can leak.
- **Product-decision compliance.** This spec builds what D08 and D09 mandate, in the shape they mandate, and cuts nothing under A05. It answers the sharing half of brief Q03 (does the magic link expose attachments — no, in v1) and hands the storage half to the attachments spec. It contradicts no active Non-goal, Business rule or Decision, so **no superseding row is required**. R05 records expiry and revocation as undecided and this spec decides them; that is R05 being satisfied, not overridden — but the owner is the decider, which is why they are in the assumptions table.
- **A06's test ships with the feature.** A06 ("a read-only link is enough for travel companions") is untested, and its smallest test is to send the Malaysia link and count how many people ask to change something. Building read-only first is what makes that test possible; designing comments now (D09, D12) would answer the question by assuming it.
- **Calendar risk (A05).** This is the smallest of the three *Now* slices — one table, four endpoints, one new screen and a refactor — and its slippable tail is named above. The counter and the guest timeline are not in it.

## 📝 Decisions in play

| Id | How this spec relies on it |
|---|---|
| D08 / R05 | One magic link per trip, read-only, no account for the recipient — the feature itself, with "exactly one active" enforced by a partial unique index. R05's undecided points (expiry, revocation, what the guest sees) are decided in the assumptions table |
| D09 / R06 | One editor, guests read only. Realised as the *absence* of a guest write endpoint, not as a permission check. Comments and suggestions stay in *Later* by these rows and D12 — a decision, not an A05 cut |
| R08 / D14 | The second half of R08: the one unauthenticated route family, enumerable in the route test's allow-list, cookie-less, session-less. The magic link is not a login |
| R02 / D05 | The guest's readiness counter is the owner's, from the same `domain/readiness.py` — one implementation of R02, including its `tracked = 0` copy |
| R01 / R09 | Both locales first-class for a guest who never chose one; browser detection with an override; `check_locales.py` green; spec, code and PR body in English |
| R04 / D07 | Cost and reservation data are *stored* when they arrive — R04 says nothing about who may see them, so not showing them to guests does not contradict it. The projection makes that an explicit decision rather than an oversight |
| R03 / D06 | The guest sees the multi-stop structure as the owner does: ordered stages, derived day labels, an open-jaw route summary |
| D04 / R07 | No external calls, which on this screen is a security control rather than a scope statement — see the `Referer` row in Security |
| D12 / N01 | Guest comments, public plans as inspiration, exports: deferred, never excluded |
| D15 / A01 | Not relied upon. This feature is justified by **P2 and D08**; the brief's Definition of Ready addendum bars anything justified by "so other people can use it" until A01 is tested, and this is not that |
| A06 | Untested, and this feature is the instrument of its own smallest test |
| A05 | **Cited for nothing here.** No capability is cut under it; the only thing it shapes is the slippable-tail ordering |
| Brief Q03 | Answered in the sharing direction (the link exposes no attachments, confirmation numbers or costs in v1); the storage half belongs to the attachments spec |
| Brief Q01 | Still open. The Research section is explicitly from knowledge, not from a check, and no design decision rests on it |

**Nothing in this spec proposes to supersede an active entry.** The approval it needs is on its autonomous assumptions below.

## ⚠️ Resolved assumptions (autonomous defaults)

This spec was written in `--autonomous` mode. Each question below was resolved by the most reversible, smallest-scope answer available, and each is open to override before merge.

| # | Question | Resolved as | Rationale |
|---|---|---|---|
| Q1 | Does the link expire, and after how long? (R05, undecided) | **No automatic expiry in v1. Revocation is the control.** No `expires_at` column | A link that dies on its own dies at the worst possible moment — mid-trip, in an airport, which is precisely when the companion opens it (A03, D10). The privacy argument for expiry is real but is answered better by a control the owner operates deliberately than by a timer he will not remember setting. Adding expiry later is one nullable column and one clause in one query — the cheapest change in this document. Note the coupling: this default is only defensible **because** Q3–Q5 keep the exposure minimal; if the owner widens what the guest sees, expiry deserves revisiting in the same breath |
| Q2 | Can the owner kill a link, and does that regenerate or disable? (R05, undecided) | **Yes. Revocation *disables*; creating a new link is a separate second action.** The revoked row is kept and answers `410 "this plan is no longer shared"` for ever | Conflating "stop sharing" with "share differently" in one *Regenerate* button means an owner who simply wants access to end must mint a new secret to do it. Keeping the row is what satisfies `BACKWARD_COMPATIBILITY.md` §3's requirement that an old link resolve to an explicit "no longer available" rather than vanish into a `404` |
| Q3 | Does the guest see an item's **notes** (the free-text field)? (brief Q03) | **No** — ⚠ **NEEDS HUMAN CONFIRMATION** | This is a privacy decision, not a UI one, and it is the one place a reasonable owner could reasonably disagree. Notes are free text written for an audience of one and can hold anything from "confirm the exact address" to a door code or a remark about a fellow traveller; a group-chat link is as public as the group chat. The cost is real and visible in the mockup — the guest's card is a line lighter, and some of that line is genuinely useful to a companion ("2h 05m layover in Doha"). Defaulted closed because **exposure is one-way**: a field can be added to the guest payload in a one-line PR, but a note already read in a group chat cannot be unread. The smallest override, deliberately **not** built pending this confirmation, is a single `share_notes` boolean on `trip_share_link` |
| Q4 | Does the guest see **attachments** and **confirmation numbers**? (brief Q03, R05) | **No** | A confirmation number plus a surname is frequently enough to view, change or cancel a booking on the airline's or hotel's own site — it is a credential, not a detail. An attachment is a boarding pass with a scannable barcode. Additionally, the attachments spec has not merged, so there is no field to expose yet; the projection test makes its arrival a decision rather than a default |
| Q5 | Does the guest see **cost and currency data**? (R04, brief Q04) | **No** | R04 says this data is *stored*; it says nothing about who sees it, so withholding it contradicts nothing. Cost is the most sensitive thing on a plan shared with the people it is being split with — and D12 puts splitting costs between participants in *Later*, so there is no flow here that needs the number |
| Q6 | Where does the token live in the URL, and how is it stored? | **In the path (`/s/{token}`), 256 bits, stored in plaintext** | The path keeps the link openable without JavaScript and pasteable anywhere, at the cost of appearing in access logs — solved directly by redacting those two path prefixes. Plaintext at rest because seeing and re-copying the link is in scope (S4) and hashing would protect a database dump that already contains every plan the token could reveal; the full argument is in Data Model |
| Q7 | How does a guest with no account get Polish or English? (R01) | **Browser language detection: Polish when the browser prefers Polish, English otherwise, with a switch in the guest header** | English is the reference locale per `AGENTS.md` and the better guess for a non-Polish speaker; the owner's own `'pl'` default is a different setting for a different population. The switch makes a wrong guess one click expensive |
| Q8 | Does the owner learn that the link was opened — a view count or "last opened"? | **No** | Nothing in the brief asks for it, and it is a privacy surface of its own pointed at the owner's friends. `created_at` is the only timestamp the dialog shows |
| Q9 | Does the guest get a day-detail screen, or only the timeline? | **Only the timeline — one route, one page** | Everything the owner's day detail adds is the editor, and every item is already visible on the timeline. D08 promises the guest the timeline and the counter, and that is what one page delivers — which is also the right shape for a link opened once on a phone |
| Q10 | Is this one spec or several? (the mandatory split check) | **One spec, two phases** | The server phase and the client phase are sequenced, not independent: the API without the UI ships nothing a person can use, and the UI without the API cannot exist. There is exactly one independently deployable capability here — "share a trip read-only" — so splitting would create two half-features and two approval decisions for one product decision |
| Q11 | Does the guest payload reuse the owner's models with fields filtered out, or a separate model? | **A separate `GuestItem` model built by an explicit projection, with two allow-list tests** | Filtering at runtime means the next field added to the owner's model ships to guests unless somebody remembers. A frozen allow-list means it does not ship until somebody decides. This is the mechanism the whole spec is built around |
| Q12 | Is there a brute-force rate limit on the guest endpoint? | **No — a malformed-token pattern check and a proxy-level DoS cap instead** | A 2^256 keyspace has no brute-force story to defend; a limiter would be theatre plus a table. The genuine concern at this endpoint is denial of service, and that belongs at the proxy |

## 📋 Phasing

Two phases. Each is independently shippable and leaves the application working and deployed.

- **Phase 1 — The link and the guest payload (server).** The migration, token minting, the projection and its tests, the three owner endpoints, the guest endpoint, and the route-allow-list entry. Deployable on its own and deliberately invisible: no UI references it, so nothing is half-promised to a user.
- **Phase 2 — The owner's dialog and the guest screen (client).** The timeline component extraction, the share dialog, the `is_shared` indicator, the `/s/:token` route and its error pages, both locales, and the end-to-end walk. The feature is live at the end of it.

## 📋 Implementation Plan

Every step is testable and leaves the application working. This structure is what `om-auto-implement-spec` hands to `om-auto-create-pr`.

### Phase 1 — The link and the guest payload (server)

1. Alembic revision and the `TripShareLink` model: the columns above, the FK cascade, the `UNIQUE` on `token`, and the partial unique index on `(trip_id) WHERE revoked_at IS NULL`, with an overridden `__repr__`. Verify: an upgrade/downgrade round-trip test; a test that the **database itself** rejects a second active link for one trip while accepting any number of revoked ones — the constraint that makes D08 structural; and a test that the token does not appear in `repr()`.
2. `domain/sharing.py`: `mint_token()` over `secrets.token_urlsafe(32)`, and `TOKEN_PATTERN`. Verify: unit tests for length, charset, and that 1000 mints are distinct.
3. `domain/sharing.py`: `project_trip_for_guest(...)` and the `GuestItem` / guest payload models, plus `GUEST_ITEM_FIELDS` and `OWNER_ONLY_ITEM_FIELDS`. Verify: **the two projection tests** — the guest model's field set equals the allow-list, and the owner model's field set equals the union — plus a test asserting `notes` is absent from a projected payload containing an item that has notes.
4. `errors.py`: `share_link_not_found` and `share_link_revoked`. Verify: the existing enum test — every member resolves to a non-empty key in both `en.json` and `pl.json` — now covers them.
5. `api/sharing.py`: `GET`, `POST` and `DELETE /trips/{tripId}/share-link`, all through `get_owned_trip`. Verify: tests for `{"link": null}` before sharing; `201` then `200`-with-the-same-token on a repeated `POST`; `204` on `DELETE` and `204` again when nothing is active; that `DELETE` sets `revoked_at` rather than removing the row; and that another owner's trip answers `404` on all three.
6. `is_shared` on the `GET /trips` and `GET /trips/{tripId}` payloads. Verify: an API test that it flips with create and revoke, and that **no response body from any `/trips` route ever contains the token** — asserted by scanning the serialized payloads for it.
7. `api/shared.py`: `GET /shared/{token}` with the pattern pre-check, the `404` / `410` branches, and the `Cache-Control: private, no-store` and `X-Robots-Tag` headers. Verify: tests for a valid token returning the projected payload; an unknown token and a malformed token returning `404` (the malformed one without a query, asserted through the session); a revoked token returning `410`; that **no `Set-Cookie` header is present**; and that a request carrying a valid owner session cookie gets the identical guest response.
8. Add `GET /api/v1/shared/{token}` to the route-enumeration test's public allow-list, in this commit. Verify: the existing test passes with exactly one new allow-list entry and still fails when a route is added without one.

### Phase 2 — The owner's dialog and the guest screen (client)

1. Extract the timeline's presentational components — `TripHero`, `ReadinessCounter`, `FilterBar`, `DayRow`, `ItemCard` — taking data and no editing callbacks, with `ItemCard` rendering its notes paragraph only when `notes` is present. Pure refactor. Verify: the walking skeleton's existing timeline tests pass unchanged.
2. `api/sharing.ts` and the share dialog: State A, State B, copy with its clipboard fallback and `aria-live` confirmation, and revoke behind its confirmation. Verify: component tests for both states, for the copy fallback path, for revoke returning the dialog to State A, and for focus returning to the "Udostępnij" trigger on close.
3. The `is_shared` chip on the timeline header (and the trip-list row — the slippable part). Verify: a component test that the chip appears only when `is_shared` is true.
4. The `/s/:token` route and `GuestTrip.tsx` composing the extracted components. Verify: component tests that the guest screen renders the hero, counter, filter bar and days; that it contains **no** link to any `/trips` route, no editing control and no notes paragraph; and that item cards are not interactive.
5. The guest error pages for `404` and `410`, and the `503` retry state. Verify: component tests for all three, each asserting its copy in **both** locales.
6. Guest locale detection and the header switch, plus all new keys in `en.json` and `pl.json`. Verify: `python3 scripts/check_locales.py` green; a test that a Polish browser preference yields Polish, a German one yields English, and the switch overrides both.
7. `robots.txt` with `Disallow: /s/`, the `noindex` meta on the guest route, `Referrer-Policy: no-referrer`, and self-hosting the display font so the guest page issues no third-party request. Verify: a test asserting the guest route's document requests no external origin, and one asserting the meta tag is present.
8. End-to-end verification of the brief's own sharing flow: the owner signs in, opens the Malaysia trip, creates a link, copies it; a **clean browser context with no cookies** opens the link and sees the timeline, the counter and the status chips but no notes and no editing control; the owner revokes; the same link reloads to "this plan is no longer shared". Verify: an integration test walking that path against the deployed instance, with screenshots on the implementation PR.
