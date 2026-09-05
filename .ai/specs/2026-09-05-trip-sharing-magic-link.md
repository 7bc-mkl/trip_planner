# Read-only trip sharing — one magic link per trip

- Date: 2026-09-05 · Author: `om-auto-write-spec` (autonomous) · Status: draft, gated on the assumptions below and on the proposed decision row **D16**
- Source brief: `.ai/specs/product-brief.md` (signed 2026-09-05)
- Depends on: `.ai/specs/2026-09-05-walking-skeleton.md` — its stack, `/api/v1` conventions, error-code enum, `get_owned_trip` dependency, SPA route guard and route-enumeration test are settled and reused here. Cross-cutting rules it already states (focus traps, `Intl` formatting, `<html lang>`, status chips as text-node-plus-`data-status`, the `503` retry state, spanning items rendered once) apply unchanged and are **not** restated in this document
- Adjacent, in flight: the attachments and reservation-data spec. This spec does not wait for it; it defines the tripwire (below) that forces its new fields and routes to get an explicit sharing decision
- Visual reference: `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/g_wny_pulpit_i_o_czasu` — the timeline the guest sees, and its "Udostępnij" button. The guest view itself has no mockup in the export; it is designed here
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

A05 decides the month, so this spec names its own cut line rather than discovering it on 2026-09-14. In priority order, the **last things built and the first things to drop** are: the `is_shared` chip on the trip-list rows (the timeline header keeps its own), and the guest's per-item-type filter chips (which do not exist for the guest if the owner's Phase 4 slipped, because it is the same component).

**Revocation is explicitly not slippable.** A sharing feature that cannot be turned off is a privacy hole, and since D16 sets no automatic expiry, revocation is the **only** control that exists. If the calendar forces a choice between the `is_shared` chip and the revoke action, the chip goes.

## 📝 Proposed Solution

Four decisions carry the design, and each is about a boundary rather than a screen:

1. **A separate route namespace for guests, not a widened owner route.** The guest reads `GET /api/v1/shared/{token}`. The owner's `GET /api/v1/trips/{tripId}` is not taught to accept a token. This keeps the walking skeleton's invariant — *every `/trips/…` route carries `get_owned_trip`* — literally true and machine-checked, and puts the product's entire unauthenticated surface in one auditable module.
2. **The guest payload is a different model, not a filtered one**, produced by an explicit projection in `domain/sharing.py` and frozen by a serialized-payload snapshot test. A field or a route added on the owner's side does not reach a guest; it makes a test fail. This is the mechanism the document is built around, and its exact shape and known limits are specified under **The projection tripwire**.
3. **One timeline, rendered twice.** The timeline's presentational pieces — trip hero, readiness counter, filter bar, day row, item card — are extracted into components that take data and no editing callbacks. The owner screen and the guest screen are two thin route components composing the same pieces. There is deliberately **no `isGuest` boolean threaded through the tree**: a mode flag is exactly how an edit affordance leaks into a read-only view six months later.
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

Additions only. Nothing in the walking skeleton's layout moves.

```
backend/trip_planner/
  api/sharing.py          NEW  owner endpoints (session + get_owned_trip)
  api/shared.py           NEW  the guest endpoint — the whole public surface, one module
  domain/sharing.py       NEW  pure: mint_token(), project_trip_for_guest(), the allow-lists
  db/models.py                 + TripShareLink
  errors.py                    + share_link_not_found, share_link_revoked, share_link_gone
migrations/                    one revision: trip_share_link
deploy/proxy/                NEW  committed reverse-proxy config (headers + log redaction)

frontend/src/
  features/timeline/components/  NEW  extracted presentational pieces — no callbacks
  features/timeline/OwnerTimeline.tsx  composes them, adds editing affordances
  features/sharing/ShareDialog.tsx NEW owner: generate / view / copy / revoke
  features/sharing/GuestTrip.tsx   NEW the /s/:token route and its error states
  api/sharing.ts                   NEW typed client for both sides
```

Boundaries that matter:

- **`domain/sharing.py` is pure**, like every other `domain/` module: token minting is a function over `secrets`, and the projection is a function from owner-shaped values to guest-shaped values with no database access. Both are unit-testable without fixtures.
- **`api/shared.py` is the entire unauthenticated surface** apart from `POST /auth/login` and the health check. One module, so that "what can the internet reach" is answerable by reading one file.
- **The frontend never computes readiness** — unchanged rule. The guest payload carries `{arranged, tracked}` from the same `domain/readiness.py`, so R02 keeps exactly one implementation and the guest cannot be shown a different number from the owner's.
- **Filtering stays in the browser** — unchanged rule (walking-skeleton A11). The guest payload is complete; the guest's filter bar is the owner's component over the owner's data.
- **No external calls, still** — which on this screen is a security control rather than a scope statement, and is enforced by CSP rather than by intent (see Security).

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

`GET /trips` and `GET /trips/{tripId}` gain one additive response boolean, `is_shared` — never the token. It is **always present**, never omitted when false: changing that later would be a §1 field change. Adding an optional response field is explicitly non-breaking under §1.

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

The guest payload is frozen by **three** assertions in CI, because one was not enough:

1. **A serialized snapshot.** A fixture trip with notes, several stages and a spanning item is rendered through `project_trip_for_guest`, and the **full recursive key set** of the resulting JSON is compared against a frozen constant. This is the assertion that survives refactors: it does not care whether a field arrives as a model attribute, a computed property, a serializer alias or a nested relation.
2. **Per-model owner-only allow-lists**, for `item`, `trip`, `trip_stage` and `trip_day` alike — not for items only. A future `trip.budget` or `stage.notes` must be classified before it compiles green.
3. **A route-inventory assertion.** Every route in the application is either in the route-enumeration test's public allow-list or carries `get_current_session`. This spec adds exactly one allow-list entry, `GET /api/v1/shared/{token}`.

**The known limit, stated because the earlier draft of this spec overstated the mechanism.** Attachments will most likely arrive as a *relation and a download route* (`GET /files/{attachmentId}` or similar) rather than as a key on the owner's item payload. Assertion 1 catches the payload case and assertion 3 catches the route case — a new public download route fails the enumeration test, and an authenticated one is simply unreachable for a guest — but **neither can decide the sharing question for a route the attachments spec designs as owner-authenticated and then wishes to open**. That decision belongs in the attachments spec, and this document's ask of it is one line: *any route serving item-derived content is either owner-authenticated or added to the public allow-list with a stated privacy decision; there is no third option.*

### Error codes added

| Code | Status | Meaning |
|---|---|---|
| `share_link_not_found` | `404` | Unknown or malformed token |
| `share_link_revoked` | `410` | The owner turned this link off |
| `share_link_gone` | `410` | The link was valid; the trip it pointed at has been deleted |

The `404` / `410` split tells the holder of a token that the token once existed. At 256 bits nobody reaches those branches by guessing — the only party who can present a dead token is somebody the owner sent it to, and that person deserves the true answer. §3 requires it in so many words.

## 📝 UI/UX

Mockups live beside this spec and are attached to its PR. They are illustrative statics rendered from self-contained HTML with no application code behind them. There are **no current-state screenshots**: the walking skeleton has not merged, so there is no running application to photograph.

| Screen | Mockup |
|---|---|
| The owner's share dialog over the timeline, active-link state, Polish | [`assets/trip-sharing-magic-link/mockup-01-share-dialog.png`](assets/trip-sharing-magic-link/mockup-01-share-dialog.png) |
| `/s/:token` — the guest view, Polish | [`assets/trip-sharing-magic-link/mockup-02-guest-view.png`](assets/trip-sharing-magic-link/mockup-02-guest-view.png) |
| `/s/:token` — the three dead-link states, **English** | [`assets/trip-sharing-magic-link/mockup-03-guest-revoked.png`](assets/trip-sharing-magic-link/mockup-03-guest-revoked.png) |

Two are Polish and one English on purpose: R01 makes both locales first-class, and a spec that only ever pictures one is not showing the product it describes.

### The owner's share dialog

Opened from **"Udostępnij"** in the timeline's action row — the design export's own position for it, beside "Eksportuj PDF" (dropped, D12).

**State A — not shared yet.** One sentence naming the consequence, then one primary action:

> *Każdy, kto ma ten link, zobaczy ten plan — bez konta i bez logowania. Nie zobaczy Twoich notatek, załączników, numerów rezerwacji ani kosztów.*
> *Anyone with this link can see this plan — no account, no sign-in. They will not see your notes, attachments, confirmation numbers or costs.*

Primary action: **"Utwórz link" / "Create link"**. The sentence is the Google-Docs pattern from Research and the only place the owner's mental model gets corrected before the link exists. It also states D16's projection in words, so an owner who disagrees finds out while he can still say so.

**State B — shared.** The URL in a read-only, selectable field; **"Kopiuj" / "Copy"** as the primary action with a transient confirmation announced through an `aria-live="polite"` region (a purely visual "✓" is invisible to a screen reader); the creation date; the same sentence about who can see it; and a destructive **"Odwołaj link" / "Revoke link"**, visually secondary, behind a confirmation:

> *Wszyscy, którym wysłałeś ten link, stracą dostęp. Tego nie da się cofnąć — możesz później utworzyć nowy link.*
> *Everyone you sent this link to will lose access. This cannot be undone — you can create a new link afterwards.*

Copying uses `navigator.clipboard.writeText`, falling back to selecting the field's text where it is unavailable, because a copy button that silently does nothing is worse than no button.

After a successful revoke the dialog returns to **State A** in place. "Revoke" and "create a new link" stay two deliberate actions rather than one *Regenerate* click, so an owner who wants to stop sharing does not have to mint a new secret to do it.

**The `is_shared` indicator.** When a trip has an active link the timeline header carries a chip — 🔗 *Udostępniona* / *Shared* — and, when not cut by the slippable tail, so does the trip's row in `/trips`. Without it there is no way to tell from the plan itself that it is currently readable by anyone holding a link, and R08's whole subject is knowing what is reachable.

### `/s/:token` — the guest view

One route, one screen. **There is no guest day-detail screen**: everything the owner's `/trips/:id/days/:date` adds is the editor, and every item is already on the timeline. One page is also the right shape for a link opened once, on a phone, from a chat message.

- **Chrome:** the brand, the PL/EN switch, nothing else. No account menu, no "sign in", no route by which a guest discovers that owner screens exist.
- **A one-line banner:** *Widok tylko do odczytu, udostępniony przez autora planu* / *Read-only view shared by the trip's owner* — it answers "can I change this?" before the guest tries.
- **Hero, readiness counter and filter bar** are the owner's components unchanged, including the counter's `tracked = 0` copy. The counter is half of what D08 promises the guest and must not be a reduced version of the owner's number. If the owner's Phase 4 slipped and the type chips do not exist, the guest has no chips either — one component, one fate.
- **The timeline:** the same day rows, date chips, item cards and status chips, but item cards are **not** interactive — no link, no dialog, no hover affordance suggesting one, no "Add item". An empty day reads *Nic jeszcze nie zaplanowane* / *Nothing planned yet* rather than the owner's invitation to add the first item.
- **Item cards carry no notes line.** The card renders its notes paragraph only when `notes` is present — one component, not two. Stated plainly because it is the visible face of Q3 and the owner should see the cost of the default before merging it.
- **Dead links are pages, not toasts:** *Ten link nie działa* / *This link does not work* (`404`), *Ten plan nie jest już udostępniony* / *This plan is no longer shared* (`410 revoked`), and *Ten plan już nie istnieje* / *This plan no longer exists* (`410 gone`). Full pages with the same chrome and the locale switch, because the recipient has nowhere else to go in this application.
- **Page metadata is deliberately generic.** The document `<title>` is the product name, and there are **no Open Graph or Twitter card tags** on `/s/:token`. Every chat client fetches a pasted URL server-side to build a preview; a title carrying the trip name would publish the plan's name into channels the owner did not choose. See Security for the part of this that cannot be mitigated.

### Locale for a person with no account

The guest never chose a language here, so i18next detection reads the browser preference: **Polish when the browser prefers Polish, English otherwise**, with the header switch overriding it. English is the fallback because `AGENTS.md` names it the reference locale and it is the better guess for a non-Polish speaker; the owner's own `'pl'` default is a different setting for a different population.

The override persists to a **scoped** `localStorage` key, `guestLocale`, read only by `/s/*`. The owner's locale remains the server-side `owner.locale` and always wins on owner routes — otherwise an owner who previews his own link in English and returns to `/trips` would find his account's language quietly changed.

### The SPA route guard

The walking skeleton states that `/login` is *the only unauthenticated route; every other route redirects here*. This spec makes it two. The guard's public list gains exactly one entry, `/s/:token`, in the same commit as the route — and it is verified by an explicit test, because without that edit every guest is bounced to a login form for an account they do not have, and every component test of the guest screen would still pass.

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

**R08's second half, made enumerable.** The route-enumeration test asserts every route is either in an explicit public allow-list or carries `get_current_session`. This spec adds **exactly one** entry, in the same commit as the route. Every future public route is therefore a deliberate edit to a test rather than an omission nobody notices.

| Control | What it is, and what it is for |
|---|---|
| **Token entropy** | 256 bits from `secrets.token_urlsafe(32)`. Never derived from the trip id, never sequential, and deliberately **not a UUID** — a UUIDv4 carries 122 bits and, worse, *looks like an identifier*, which invites treating it as non-secret |
| **No brute-force limiter, deliberately** | At an implausible million guesses per second against a 2^256 space, the expected time to find a live token exceeds the age of the universe by many orders of magnitude. A limiter here would be theatre plus a table. What the endpoint needs is ordinary **DoS** protection — a per-IP cap in the committed proxy config, never presented as protection against guessing |
| **Content-Security-Policy** | `default-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'`. This is what actually enforces "the guest page makes no external request" — a promise otherwise kept only by reviewer memory until the first analytics SDK or icon font is installed. `frame-ancestors 'none'` additionally stops a shared plan being framed silently inside a third-party page |
| **No third-party subresources** | No CDN fonts, no analytics, no map tiles, no third-party icons. Concrete, not theoretical: the design tokens name *Plus Jakarta Sans*, and a Google Fonts request from `/s/<token>` would hand the complete share URL to a third party in a `Referer` header. The font is self-hosted, and the CSP makes a regression fail rather than leak |
| **Referrer policy** | `Referrer-Policy: no-referrer`, served as a header on the guest **document**, not merely intended in a component |
| **Log redaction, on both fields** | The proxy redacts the request path for `/s/…` and `/api/v1/shared/…` — **and the `Referer` field globally**. The second is the one that matters: the guest page's own same-origin subresource requests (`/assets/index-*.js`, the font, the API call) do not match either path prefix, so a path-only redaction would log the complete share URL in `$http_referer` on every one of them. A token in a log line is a live link in a log line |
| **Not indexable** | `X-Robots-Tag: noindex, nofollow` on the guest document, and the `<meta name="robots">` equivalent. `/s/` is deliberately **not** `Disallow`ed in `robots.txt`: a crawler that obeys `Disallow` never fetches the page and therefore never reads the `noindex`, and a disallowed URL discovered from an external link can still be indexed URL-only — which would publish the token itself, the one thing this design cannot survive. Allowing the crawl so it can read the `noindex` is the correct configuration |
| **Not cached** | `Cache-Control: private, no-store` on the guest payload — a correctness control as much as a privacy one, since a CDN-cached payload would keep serving a plan after revocation, and revocation is the only kill switch this design has |
| **No cookie, no session, ever** | The guest endpoint reads no cookie and sets none. R08 in code |
| **No guest write path** | An absence, not a permission check: the guest surface is one `GET` |
| **Owner endpoints still owned** | The three share endpoints take `get_owned_trip`, so no owner can mint, read or revoke a link for a trip that is not his. Both unsafe methods carry the skeleton's CSRF double-submit token — a forged `DELETE` would otherwise let a third-party page silently un-share an owner's plan |
| **Immediate revocation** | One indexed lookup per guest request, no in-process token cache, no CDN caching |
| **Field-level exposure decided once** | The projection tripwire and its three assertions, with their limit stated |

**What this design does not protect against, plainly.**

- **Forwarding.** The link *is* the credential and it is bearer-only: the magic link's security model is that of the group chat it gets pasted into. Nothing in D08's shape can change that, and an expiry date would be a comfort rather than a control. **Revocation is the only real control, which is why it is in v1 and not in the slippable tail.**
- **Link unfurling.** D08's own rationale is that the link "gets pasted into a group chat" — and every major chat client (Slack, WhatsApp, Messenger, iMessage, Discord) fetches a pasted URL server-side to build a preview. **The token is therefore transmitted to, and logged by, a third party on the feature's very first use, by design.** The generic `<title>` and the absent Open Graph tags keep the *trip's name* out of those previews; they cannot keep the *URL* out of the chat provider's infrastructure. This is inherent to sharing a bearer link over a messaging platform and is the strongest practical argument for revisiting expiry if D16's Q3 answer is ever widened.

## 📝 Deployment

No new deployable and no new environment variable. The guest share URL is built from `APP_BASE_URL`, which the walking skeleton already requires at startup.

Three security controls above are proxy configuration, and the walking skeleton's own precedent — putting login rate limiting in Postgres rather than in a worker, because a checklist and a decorative counter are not controls — applies here too. They are therefore **committed configuration in `deploy/proxy/`, not release-checklist prose**: the response-header block (CSP, `X-Robots-Tag`, `Referrer-Policy`, `Cache-Control`), the log-format redaction of the request path and the `Referer` field, and the per-IP request cap on `/s/` and `/api/v1/shared/`. A file in the repository can be reviewed, diffed and tested; a checklist item cannot.

## 📝 Risks & Impact Review

- **Blast radius: additive throughout.** One new table, one new public route family, three new owner endpoints, three new error codes, one additive response field, new locale keys, committed proxy config, and a pure refactor extracting timeline components. Under §1, adding endpoints and response fields is non-breaking; under §2 the migration creates a table that did not exist. **Nothing changes meaning** — §1's worst and quietest class of break.
- **§3 is the section this spec answers directly**, and it needed a design change to answer honestly: a link resolves to the live plan, a revoked one says so, a deleted one says *that* instead, and a token never comes to mean a different trip because rows are orphaned rather than deleted.
- **§4 applies to the dialog copy.** If Q3 is overridden and guests do come to see notes, the State A sentence must ship under a **new** translation key rather than a rewritten one: changing a key's meaning while keeping its name is a §4 break.
- **The one risk that cannot be rolled back is exposure.** Every other decision here is reversible in a PR. What a link has already shown to a group chat cannot be unshown. That asymmetry is the whole justification for defaulting the projection to the minimum and for gating Q3 on human confirmation.
- **The dependency that will actually bite: the attachments spec**, and the tripwire's stated limit is the honest version of how far this document can protect against it. Its one ask of that spec is in **The projection tripwire**.
- **Rollback story.** One migration with a working `downgrade`; dropping the table removes every link, which is the safe direction for a privacy feature — a rollback closes access rather than opening it. A frontend rollback turns every live link into a dead page. Neither can leak.
- **Product-decision compliance.** This spec builds what D08 and D09 mandate, in the shape they mandate, and cuts nothing under A05. It **does** decide four points R05 records as undecided, and R05's *Required path to change* names a superseding decision row and a distinct privacy decision — so it proposes **D16** below rather than claiming none is needed.
- **A06's test ships with the feature**, and building read-only first is what makes that test possible.
- **Calendar risk (A05).** This is the smallest of the three *Now* slices — one table, four endpoints, one new screen, a refactor and a proxy config — and its slippable tail is named above.

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
| Q6 | Where does the token live in the URL, and how is it stored? | **In the path (`/s/{token}`), 256 bits, stored as issued** | The path keeps the link openable without JavaScript and pasteable anywhere, at the cost of appearing in logs — answered by redacting the path *and* the `Referer` field at the proxy. Stored as issued because seeing and re-copying the link is in scope (S4); the full argument, including why encryption at rest lost narrowly, is in Data Model |
| Q7 | How does a guest with no account get Polish or English? (R01) | **Browser detection — Polish if preferred, English otherwise — with a switch, persisted under a `guestLocale` key scoped to `/s/*`** | English is the reference locale per `AGENTS.md` and the better guess for a non-Polish speaker. The scoped key prevents an owner previewing his own link from changing his account's language |
| Q8 | Does the owner learn that the link was opened? | **No** | Nothing in the brief asks for it, and it is a privacy surface pointed at the owner's friends. `created_at` is the only timestamp shown |
| Q9 | Does the guest get a day-detail screen, or only the timeline? | **Only the timeline — one route, one page** | Everything the owner's day detail adds is the editor, and every item is already on the timeline. D08 promises the guest the timeline and the counter, and one page delivers exactly that |
| Q10 | Is this one spec or several? (the mandatory split check) | **One spec, two phases** | There is exactly one independently deployable capability here — "share a trip read-only". The API without the UI ships nothing usable and the UI cannot exist without the API, so splitting would create two half-features and two approval decisions for one product decision |
| Q11 | Filtered owner models, or a separate guest model? | **A separate guest model, frozen by a serialized-payload snapshot plus per-model owner-only allow-lists and the route inventory** | Filtering at runtime means the next field ships to guests unless somebody remembers. A frozen snapshot means it does not ship until somebody decides. Its limit against attachments-as-a-route is stated, not glossed |
| Q12 | Is there a brute-force rate limit on the guest endpoint? | **No — a malformed-token pattern check, plus a proxy-level DoS cap in committed config** | A 2^256 keyspace has no brute-force story to defend. The genuine concern is denial of service, and it lives in `deploy/proxy/` where it can be reviewed |
| Q13 | What does a link to a **deleted** trip say? | **`410 share_link_gone` — "this plan no longer exists"**, via `ON DELETE SET NULL` rather than a cascade | §3 legislates this case by name. A `404` would talk about the link when the truth is about the plan, and reusing "no longer shared" would attribute to the owner a decision he did not take |

## 📋 Phasing

Two phases, sequenced rather than independent: Phase 1 is deployable but deliberately invisible, and Phase 2 cannot ship without it.

- **Phase 1 — The link and the guest payload (server).** Migration, token minting, the projection and its three assertions, the three owner endpoints, the guest endpoint, and the public allow-list entry. Deployable on its own; no UI references it, so nothing is half-promised to a user.
- **Phase 2 — The owner's dialog and the guest screen (client), plus the proxy config.** The component extraction, the share dialog, the `is_shared` indicator, the `/s/:token` route and its error pages, the route-guard amendment, both locales, the committed headers, and the end-to-end walk.

**Step 2.1 (the component extraction) is a natural standalone PR** and should be landed as one: it is the only part of Phase 2 that is not guest-specific, it touches the files the attachments spec is most likely to be editing concurrently, and it cannot start before the walking skeleton has merged.

## 📋 Implementation Plan

Every step is testable and leaves the application working. This structure is what `om-auto-implement-spec` hands to `om-auto-create-pr`.

### Phase 1 — The link and the guest payload (server)

1. Alembic revision and the `TripShareLink` model: the columns above, `trip_id` nullable with `ON DELETE SET NULL`, `UNIQUE` on `token`, the partial unique index, and an overridden `__repr__`. Verify: an upgrade/downgrade round-trip test; a test that the **database itself** rejects a second active link for one trip while accepting any number of revoked and any number of orphaned ones; a test that deleting a trip sets `trip_id` to NULL and leaves the row; and a test that the token does not appear in `repr()`.
2. `domain/sharing.py`: `mint_token()` over `secrets.token_urlsafe(32)` and `TOKEN_PATTERN`. Verify: unit tests for length, charset, and that 1000 mints are distinct.
3. `domain/sharing.py`: `project_trip_for_guest(...)`, the guest response models, and the owner-only allow-lists for `item`, `trip`, `trip_stage` and `trip_day`. Verify: **the tripwire** — (a) the full recursive key set of a guest payload rendered from a fixture trip (notes, several stages, a spanning item) equals a frozen constant; (b) each owner model's field set equals its guest set plus its declared owner-only set; (c) a test asserting `notes` is absent from a projected payload built from an item that has notes.
4. `errors.py`: `share_link_not_found`, `share_link_revoked`, `share_link_gone`. Verify: the existing enum test — every member resolves to a non-empty key in both `en.json` and `pl.json` — now covers all three.
5. `api/sharing.py`: `GET`, `POST` and `DELETE /trips/{tripId}/share-link`, all through `get_owned_trip`. Verify: `{"link": null}` before sharing; `201` then `200`-with-the-same-token on a repeated `POST`; `204` on `DELETE` and `204` again when nothing is active; that `DELETE` sets `revoked_at` rather than removing the row; that **both unsafe methods reject a request with a missing or mismatched CSRF token**; and that another owner's trip answers `404` on all three.
6. `is_shared` on the `GET /trips` and `GET /trips/{tripId}` payloads, always present. Verify: an API test that it flips with create and revoke, and that **no response body from any `/trips` route ever contains the token**, asserted by scanning the serialized payloads for it.
7. `api/shared.py`: `GET /shared/{token}` with the pattern pre-check, the `404` / `410 revoked` / `410 gone` branches, and the `Cache-Control: private, no-store` header. Verify: a valid token returns the projected payload; unknown and malformed tokens return `404`, the malformed one without touching the database (asserted through the session); a revoked token returns `410 share_link_revoked`; an orphaned one returns `410 share_link_gone`; **no `Set-Cookie` header is present**; and a request carrying a valid owner session cookie receives the identical guest response.
8. Add `GET /api/v1/shared/{token}` to the route-enumeration test's public allow-list. Verify: the test passes with exactly one new entry, still fails when a route is added without one, and asserts the allow-list's length so a silent third entry cannot appear.

### Phase 2 — The owner's dialog, the guest screen and the proxy config (client)

1. Extract `TripHero`, `ReadinessCounter`, `FilterBar`, `DayRow` and `ItemCard` — data in, no editing callbacks, `ItemCard` rendering its notes paragraph only when `notes` is present. Pure refactor; land it as its own PR. Verify: the walking skeleton's existing timeline tests pass unchanged.
2. `api/sharing.ts` and the share dialog: State A, State B, copy with its fallback and `aria-live` confirmation, revoke behind its confirmation. Verify: component tests for both states, the copy fallback path, revoke returning the dialog to State A, and focus returning to the "Udostępnij" trigger on close.
3. The `is_shared` chip on the timeline header (and the trip-list row — the slippable part). Verify: a component test that the chip appears only when `is_shared` is true.
4. **Amend the SPA route guard's public route list** to `/login` and `/s/:token`. Verify: a test that an unauthenticated visit to `/s/:token` renders the guest view and does **not** redirect, and a test asserting the guard's public list has exactly those two entries.
5. `GuestTrip.tsx` composing the extracted components, plus the three dead-link pages and the `503` retry state. Verify: component tests that the guest screen renders hero, counter, filter bar and days; that it contains **no** link to any `/trips` route, no editing control and no notes paragraph; that item cards are not interactive; and that each dead-link page renders its copy in **both** locales.
6. Guest locale detection, the header switch, the `guestLocale` scoped key, and all new keys in `en.json` and `pl.json`. Verify: `python3 scripts/check_locales.py` green; tests that a Polish browser preference yields Polish, a German one English, that the switch overrides both, and that setting `guestLocale` does not change the locale on an owner route.
7. The guest document's generic `<title>` with no Open Graph or Twitter tags, and self-hosting the display font. Verify: **a build-artifact scan** — the emitted `index.html` and JS/CSS bundles contain no external `https://` origin — rather than a jsdom assertion, which cannot observe subresource fetches; plus a test that the guest route renders no `og:` meta tag.
8. `deploy/proxy/` config committed: the CSP, `X-Robots-Tag`, `Referrer-Policy` and `Cache-Control` header block; the log format redacting the request path for `/s/` and `/api/v1/shared/` **and the `Referer` field globally**; the per-IP cap; and no `Disallow: /s/` in `robots.txt`. Verify: an integration test against the running stack asserting each header on a `/s/:token` response, and a log-format test that a request whose `Referer` carries a token produces a log line that does not.
9. End-to-end verification of the brief's own sharing flow: the owner signs in, opens the Malaysia trip, creates a link and copies it; a **clean browser context with no cookies** opens the link and sees the timeline, the counter and the status chips but no notes and no editing control; the owner revokes; the same link reloads to "this plan is no longer shared". Verify: an integration test walking that path against the deployed instance, with screenshots on the implementation PR.
