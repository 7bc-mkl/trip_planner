# Smart Trip Planner — product brief

- Date: 2026-09-05 · Mode: own · Owner: Michal Klosinski
- How the count below works: one tagged line of the body is one claim, counted under its strongest tag; the header, Hypotheses, the Definition of Ready addendum and the collection plan are not counted. Read the `[DOCUMENT]` figure with care: 26 of those claims cite decision records D01-D15, and all of them come from one session with one respondent — the owner, who is also the person building the product. Nothing here rests on written material that existed before today, except the design export and the repository's own conventions.
- Coverage: 47 claims — 39 sourced (interview 9, data 0, document 26, product 4, benchmark 0), 0 synthetic, 8 assumed; 2 entries on the collection plan
- Definition of Ready signed by: the team — Michal Klosinski, 2026-09-05 — with the riskiest assumption A01 ("people other than the owner have this problem") **accepted untested** (D15): the first version is built for the owner alone, and a wider group is a maybe, not a plan
- Sources:
  - `.ai/specs/research/interviews/2026-09-05-owner-session.md` — discovery session with the owner (four question rounds, 2026-09-05)
  - `.ai/specs/research/decisions/D01…D15` — decisions taken in that session
  - `.ai/specs/research/design/stitch_inteligentny_planer_podr_y/` — Stitch design export supplied by the owner on 2026-09-05: five screens plus `modern_premium_travel_companion/DESIGN.md`; labelled by the owner "wstępny design, do dostosowania w trakcie prac"
  - `AGENTS.md`, `SDLC.md`, `scripts/check_locales.py`, `.ai/agentic.config.json` — repository conventions for a greenfield project

## Vision

For a traveller who plans their own multi-stop trips, Smart Trip Planner holds the whole trip on one timeline, shows at a glance what is already arranged and what still needs booking, and can show that same picture to the people travelling along. `[INTERVIEW]` owner session, opening statement and Q2

## Target group and stakeholders

- Customer (pays): nobody. A personal tool, not a commercial product; no revenue goal. `[DOCUMENT]` D02
- User (uses): the owner. Friends were named in the first round ("ja i znajomi") and demoted in the fourth: "na początek dla mnie, jak mi się spodoba może dla większej ilości osób". The first version has exactly one intended user, and he is also the builder. `[INTERVIEW]` owner session, Q1 and Q5
- Stakeholders (decides, blocks, operates): the owner alone. `[DOCUMENT]` D02
- Decider for scope decisions: Michal Klosinski

## Problems, with evidence

- P1 — While a trip is being planned there is no clear overview of what has already been arranged and what is still left to do. The plan lives "w głowie, na mailu, trochę w excelu" — in the owner's head, in his mailbox, partly in a spreadsheet — so the list of what is still unbooked exists nowhere in one piece. `[INTERVIEW]` owner session, Q2 and Q6
- P2 — There is no good way to share the state of the plans with other people. A plan held in someone's head, their mailbox and a partial spreadsheet cannot be shown to a companion without retelling it. `[INTERVIEW]` owner session, Q2 and Q6
- How often this happens and what it costs is not established: a single respondent, who is also the person building the tool, no specific trip walked through, no record of trips per year or time lost. `[ASSUMPTION]` see A01
- The design export treats P1 as the product's centre rather than a detail: the timeline carries a "Status logistyki: 7 z 11 pozycji" counter, a "Tylko do zrobienia" filter and a "Status gotowości 80%" tile. `[DOCUMENT]` design export, `g_wny_pulpit_i_o_czasu`, `centrum_rezerwacji_i_dokument_w`

## Product and how it stands out

- What it is: a planner where a trip is entered by form or by chat, laid out as a timeline of days, and filled in by hand with items — accommodation, transport, activities, meals — each carrying a status and optional attachments. `[INTERVIEW]` owner session, opening statement and Q4
- Built as a Python backend serving a React single-page app; that choice predates this session and belongs to the repository, not to the discovery. `[PRODUCT]` `AGENTS.md`, Stack
- The first version plans; it does not shop. The assistant may suggest from what the model already knows, but the app does not search live inventory, fetch prices or book anything. `[DOCUMENT]` D04
- What makes it different, as the owner sees it: the readiness counter is the main object of the product, not a badge in a corner — the first question the app answers is "what is still not arranged". `[INTERVIEW]` owner session, Q2, read together with D05
- Chat is an editing surface at every stage, not an onboarding wizard: the user writes what to change, add or check, and the plan changes. `[INTERVIEW]` owner session, opening statement
- Benchmark: | reference | what it does well | where it falls short for our users | checked on | link | — empty. Nothing was checked, because this session had no network access; a competitor described from memory would be a guess wearing the clothes of a fact. On the collection plan.

## Goals and success criteria

- Business goal: none. Success is the owner's own use. `[DOCUMENT]` D02
- User outcome: the Malaysia trip is planned end to end inside the app — every day filled, every item carrying a status — and the app is what he opens during the trip. `[DOCUMENT]` D10
- Primary metric, baseline today, threshold, date: trips planned end to end in the app; baseline 0; threshold 1 (the Malaysia trip of October 2026); checked **2026-09-30**, a date the owner confirmed when it was put back to him as invented — twenty-five days after this brief. `[DOCUMENT]` D10
- What must not get worse: nothing exists yet to protect, with one exception — the Polish/English locale parity gate must stay green from the first commit, because it is a product requirement enforced by the pipeline, not a style rule. `[PRODUCT]` `AGENTS.md`, `scripts/check_locales.py`

## Scope

- **Now** — one traveller takes one real multi-stop trip from empty to fully planned:
  - create a trip from dates, a starting point and one or more destinations, by form or in chat; `[DOCUMENT]` D03
  - stages (bases) inside the trip, days generated from the dates, and an empty timeline to fill by hand; `[DOCUMENT]` D06
  - items on a day with a type, a time, free text, and one of three statuses — *do zaplanowania*, *do zarezerwowania*, *gotowe*; `[DOCUMENT]` D05
  - a readiness counter over the items that are *do zarezerwowania* or *gotowe*, and a filter down to what is still left; `[DOCUMENT]` D05
  - a day detail view for editing an item properly, with file and image attachments; `[INTERVIEW]` owner session, opening statement
  - chat that adds and changes items, and answers questions about the plan from the model's own knowledge; `[DOCUMENT]` D03
  - owner login with e-mail and password — a must-have rather than a convenience, because the app is deployed to the public internet from day one; `[DOCUMENT]` D11, D14
  - sharing a trip by one magic link per trip, read-only: the recipient sees the plan and can neither edit nor comment. `[DOCUMENT]` D08, D09
- **Later** — nothing here is closed, it is simply outside the first version: booking and payment in the app; live prices from external APIs; automatic parsing of reservation PDFs and e-mails; guest comments and suggestions on a shared plan; a private per-trip e-mail address; export to Google Calendar, Apple Wallet and PDF; route optimisation and maps; weather; splitting costs between participants; an offline mode on the phone; public plans as inspiration; several people editing one trip; cost accounting as a real feature. `[DOCUMENT]` D12
- **Not doing:** see Non-goals — deliberately empty.
- Open: whether the *Now* list is buildable by 2026-09-30, the date the owner set. The brief does not assume it is; A05 carries that risk and its test. `[ASSUMPTION]` A05

## Domain glossary

| Term | Meaning | Owned by | Visible to |
|---|---|---|---|
| Trip (podróż) | One journey with a date range, a starting point and one or more destinations; the unit that gets shared | Owner | Owner, guests |
| Stage / stop (etap, baza) | A place the traveller is based in for a stretch of the trip; a trip has one or more, and may return from a different place than it departed | Owner | Owner, guests |
| Day (dzień) | One calendar day of the trip, generated from its date range; the row of the timeline | System | Owner, guests |
| Item (pozycja) | Something planned on a day — accommodation, transport, activity, meal, other — with a time, a description, a status and optional attachments | Owner | Owner, guests |
| Status | One of exactly three values: *do zaplanowania* (still to be worked out), *do zarezerwowania* (decided, needs booking or buying), *gotowe* (arranged, optionally with an attachment) | Owner | Owner, guests |
| Readiness counter | "x of y arranged", over the items that are *do zarezerwowania* or *gotowe*; items still *do zaplanowania* stay out of the arithmetic | System | Owner, guests |
| Attachment (załącznik) | A file or image pinned to an item or a day — a ticket, a voucher, a screenshot | Owner | Owner, guests |
| Reservation data | Confirmation number, dates, cost — kept when it arrives with an attachment, never demanded from the user | Owner | Owner, guests |
| Task (zadanie) | A preparation to-do that is not an item on the timeline ("download offline maps") — in the design export, not yet decided for v1 (Q02) | Owner | Owner |
| Magic link | One link per trip that opens it read-only, without the recipient having an account | Owner | The recipients |
| Guest (gość) | A person holding a trip's magic link: reads the plan, and nothing else in the first version | Owner | Owner |

## Key flows

- Current state — planning a trip: the plan lives in three places at once — the owner's head, his mailbox, and "trochę w excelu", a partial spreadsheet. Nothing holds the whole picture, so what is still unbooked is recalled rather than read, and showing it to someone means retelling it. Thin: given in one sentence, without a specific trip, a frequency or a cost. `[INTERVIEW]` owner session, Q6
- Future state — first plan: enter dates, starting point and destinations (form or chat) → the app generates a trip with stages and empty days → the traveller fills days with items by hand, each with a status → the counter shows how much is left → filter down to what still needs booking. Steps 1 to 3 follow the design export, including its "Utwórz pustą oś czasu do ręcznego planowania" action; the rest is intended behaviour not yet walked in a prototype. `[DOCUMENT]` design export; `[ASSUMPTION]` beyond step 3
- Future state — arranging one item: open the day → open the item → set time and details → attach the ticket or voucher → move the status to *gotowe*; the counter changes. Follows `szczeg_y_dnia_i_aktywno_ci` and `centrum_rezerwacji_i_dokument_w`, whose reservation figures come from parsing that is not in the first version. `[DOCUMENT]` design export
- Future state — changing the plan by chat: at any point the user writes what to change, add or check; the assistant edits items and answers from its own knowledge, without searching live inventory. `[DOCUMENT]` D03, D04
- Future state — sharing: the owner sends the trip's link to a companion → the companion opens the same timeline and counter, read-only → any reaction happens outside the app. Not in the design export, which shows only an "Udostępnij" button. `[DOCUMENT]` D08, D09

## Business rules

| Id | Rule | Applies to | Source | Owner | Status | Review by | Required path to change |
|---|---|---|---|---|---|---|---|
| R01 | Every user-visible string exists in both Polish and English; the locale parity gate fails the build otherwise | Whole product | `[PRODUCT]` `AGENTS.md`, `scripts/check_locales.py` | Michal Klosinski | active | 2027-09-05 | Change `AGENTS.md` and the gate in the same PR |
| R02 | An item has exactly three statuses — *do zaplanowania*, *do zarezerwowania*, *gotowe* — and the readiness counter counts the last two; an item still *do zaplanowania* is out of the arithmetic | Items, counter | `[DOCUMENT]` D05 | Michal Klosinski | active | 2026-12-31 | A superseding decision row |
| R03 | A trip may have several stages and may return from a different place than it departed; the data model carries this from the first migration, and the creation form asks for dates, a starting point and one or more destinations | Trip, stages | `[DOCUMENT]` D06 | Michal Klosinski | active | 2026-12-31 | A superseding decision row |
| R04 | Cost and reservation data are stored when they arrive with material the user already has, and the app never requires the user to type them. Whether the first version handles more than one currency is undecided — the owner said nothing about it and the design carries a PLN/EUR toggle and a budget figure | Items, attachments | `[DOCUMENT]` D07 | Michal Klosinski | active | 2026-12-31 | A superseding decision row |
| R05 | A trip is shared by exactly one magic link per trip, granting read-only access. Expiry, revocation, and whether the guest sees attachments and confirmation numbers are still undecided (Q03) | Sharing | `[DOCUMENT]` D08 | Michal Klosinski | active | 2026-12-31 | A superseding decision row; any public-link feature needs its own privacy decision |
| R06 | A trip has exactly one editor — its owner. A guest reads and nothing more; comments and suggestions are deferred, not designed | Sharing, permissions | `[DOCUMENT]` D09 | Michal Klosinski | active | 2026-12-31 | A superseding decision row |
| R07 | The first version performs no booking, no payment and no live price or inventory lookup; assistant suggestions come from the model's own knowledge | Assistant, items | `[DOCUMENT]` D04 | Michal Klosinski | active | 2026-12-31 | A superseding decision row |
| R08 | The owner authenticates with e-mail and password, and the magic link is for guests rather than a second owner login path. Because the application is on the public internet from its first deployment, no screen showing a plan may be reachable without either an owner session or a trip's magic link | Authentication | `[DOCUMENT]` D11, D14 | Michal Klosinski | active | 2026-12-31 | A superseding decision row |
| R09 | Specifications, code, comments and PR bodies are English; only the user interface is bilingual | Repository | `[PRODUCT]` `AGENTS.md` | Michal Klosinski | active | 2027-09-05 | Change `AGENTS.md` |

## Non-goals

| Id | We are not building | Why | Owner | Status | Review by | Required path to change |
|---|---|---|---|---|---|---|
| N01 | Nothing is permanently excluded | The owner decided explicitly that every candidate feature — booking, live prices, PDF parsing, cost splitting, offline mode, public plans and the rest — is deferred rather than ruled out; the boundary of the first version is the *Now* list in Scope, not a list of prohibitions | Michal Klosinski | active | 2026-12-31 | A superseding row naming the feature actually being ruled out, and why |

This section is deliberately empty of exclusions, and that has a cost worth stating: reviewers cannot lean on non-goals to stop scope creep here. The only defence is the *Now* list and D12.

## Decisions

| Id | Date | Decision | Why | Owner | Status | Review by |
|---|---|---|---|---|---|---|
| D01 | 2026-09-05 | The product is called **Smart Trip Planner**; "VoyageAI" from the design export is dropped | The owner chose it over the mockups' generated brand name | Michal Klosinski | active | — |
| D02 | 2026-09-05 | A personal tool, no paying customer, no revenue goal | Answer to "who is this for" in round one | Michal Klosinski | active | 2026-12-31 |
| D03 | 2026-09-05 | The first version is a manual timeline; chat adds and changes items rather than generating whole trips | The owner picked option (a) over an AI-generated draft plan | Michal Klosinski | active | 2026-12-31 |
| D04 | 2026-09-05 | Planning first: no live search, no prices, no booking; the assistant suggests from its own knowledge or, later, the web | "Przede wszystkim planowanie; cała reszta to dodatek" | Michal Klosinski | active | 2026-12-31 |
| D05 | 2026-09-05 | Exactly three item statuses — *do zaplanowania*, *do zarezerwowania*, *gotowe* — and the counter counts the last two | The count of three was proposed by the agent and accepted with a single "3"; the names and the arithmetic are the owner's own, given in the fourth round. The design export scatters nine different status labels; the owner's first description had two | Michal Klosinski | active | 2026-12-31 |
| D06 | 2026-09-05 | Multi-stop trips are in the data model from the first migration | "Zdecydowanie wieloprzystankowość" — retrofitting this would be a rewrite, not an addition | Michal Klosinski | active | 2026-12-31 |
| D07 | 2026-09-05 | Costs are stored when they arrive with material the user has; accounting between participants is a future feature | The owner wants the data kept but not the data entry | Michal Klosinski | active | 2026-12-31 |
| D08 | 2026-09-05 | Sharing works through one magic link per trip, granting read-only access | "Wchodzi przez magic linka", then "jeden dla projektu, read only w v1" — one link per trip is what gets pasted into a group chat; read-only keeps the first version out of permissions work | Michal Klosinski | active | 2026-12-31 |
| D09 | 2026-09-05 | One editor per trip; a guest reads only. Comments and suggestions move to *Later* | Said first as an optional extra ("z **ew.** możliwością skomentowania"), then settled: "read only w v1" | Michal Klosinski | active | 2026-12-31 |
| D10 | 2026-09-05 | Success for the first version: the Malaysia trip of October 2026 planned end to end in the app, checked 2026-09-30 | The owner's own upcoming trip is the test, and he confirmed the check date when it was put back to him as invented | Michal Klosinski | active | 2026-09-30 |
| D11 | 2026-09-05 | The owner logs in with e-mail and password | Chosen over magic-link login and over no login at all | Michal Klosinski | active | 2026-12-31 |
| D12 | 2026-09-05 | No feature is permanently excluded; everything outside the first version is "later" | Asked twice. First: "wszystkie opcje można dodać potem, żadnej nie wykluczam". Then the owner accepted an agent-proposed list with four hard exclusions, and when the contradiction was put back to him he chose "nic nie wykluczam" — this row supersedes that acceptance | Michal Klosinski | active | 2026-12-31 |
| D13 | 2026-09-05 | There are no kill criteria, deliberately | "Jak będę dłubał to moja sprawa" — the owner accepts that this project has no stop condition | Michal Klosinski | active | — |
| D14 | 2026-09-05 | The application is deployed to the public internet from day one, which makes authentication a first-version must-have rather than a feature serving future users | "To będzie stało w internecie od dnia 1 — autoryzacja to must have". This answers the objection that login exists only to serve the untested A01: it does not, it exists because the thing is reachable by anyone | Michal Klosinski | active | 2026-12-31 |
| D15 | 2026-09-05 | A01 is accepted untested: the first version is built for the owner alone, and a wider group of users is a maybe conditional on him liking it | "Na początek dla mnie, jak mi się spodoba może dla większej ilości osób". This is what lets the Definition of Ready be signed with a high-importance assumption carrying no evidence — knowingly, not by oversight | Michal Klosinski | active | after the Malaysia trip |

## Riskiest assumptions

| Id | Assumption | Importance | Evidence today | If false | Smallest test | Owner | By when | Result |
|---|---|---|---|---|---|---|---|---|
| A01 | People other than the owner — the "friends" of the first round — have problems P1 and P2 | high | none `[ASSUMPTION]`; the only respondent is the owner, who is also the builder | Nothing breaks in the first version, which is now explicitly built for one person; what breaks is any later investment made *because* other people are expected | Ask three friends who travelled this year how they kept track of what was still unbooked, and whether anyone asked them for the plan | Michal Klosinski | before any work aimed at users beyond the owner | accepted untested (D15) |
| A02 | Changing a plan through chat is faster or nicer than editing the timeline directly | high | none `[ASSUMPTION]` | Chat becomes the most expensive feature and the least used; the manual timeline is the whole product | Plan one Malaysia day entirely through chat and one entirely by hand, then compare | Michal Klosinski | with the first working timeline | untested |
| A03 | A manually maintained plan stays current enough to be trusted during the trip itself | high | none `[ASSUMPTION]` | The readiness counter lies, and lying once is enough to send the owner back to his mailbox and spreadsheet | Use the app as the only plan for the Malaysia trip and note every divergence from reality | Michal Klosinski | October 2026 | untested |
| A04 | Assistant suggestions drawn from model knowledge alone are accurate enough to be trusted | high | none `[ASSUMPTION]` | Confident suggestions about closed museums and non-existent restaurants destroy trust after one incident — the strongest argument for the deferred live-data work | Ask for ten concrete Malaysia suggestions and check each against reality | Michal Klosinski | before chat suggestions ship | untested |
| A05 | The *Now* scope — timeline, statuses, counter, attachments, chat, login and a read-only share link — can be built and be usable by 2026-09-30, twenty-five days from this brief, in a repository holding no product code | high | none `[ASSUMPTION]`; public deployment and authentication (D14) are inside the first version rather than after it | The primary metric fails for a reason that says nothing about the product idea; the Malaysia trip gets planned in e-mail and a spreadsheet after all | A walking skeleton by 2026-09-15 — one trip, its days, items with the three statuses, the counter, deployed and behind a login; whatever is not standing by then gets cut, chat first | Michal Klosinski | 2026-09-15 | untested |
| A06 | A read-only link is enough for travel companions — they want to see where things stand, not to write | medium | none `[ASSUMPTION]`; P2 as reported is about showing state, not co-editing | Comments, suggestions or co-editing move from *Later* into the first thing anyone asks for, and the one-editor model has to be reworked | Send the Malaysia link to whoever travels along and count how many ask to change something | Michal Klosinski | October 2026 | untested |

Importance and evidence together are the assumption map: every high-importance row has no evidence yet, which is normal for a brief written before anything exists. A05 is now the one that decides the month, because A01 has been settled by decision rather than by evidence.

## Kill criteria

None, deliberately. The owner decided this project has no stop condition: "brak, świadomie", and, when asked a second time, "jak będę dłubał to moja sprawa; jak nie będę używał to pewnie zostawię". Recorded as D13, not as an omission.

The practical consequence is worth stating once for the whole document: nothing in this brief can say no. There are no kill criteria (D13), no exclusions (N01), no evidence from outside the team, and the primary metric on 2026-09-30 reports a result without triggering anything. The only brakes are the *Now* list in Scope and D12, both revisable at will by the one person who is also the only user and the only respondent. That is a legitimate way to run a personal project; it does mean a future disagreement about scope has nothing in here to appeal to.

## Hypotheses to test

None. No persona walkthroughs or simulated interviews were run, so there is nothing `[SYNTHETIC]` to keep here.

## Open questions

| Id | Question | Blocking | Who can answer | Status |
|---|---|---|---|---|
| Q01 | Benchmark: what do Wanderlog, TripIt, Mindtrip and Google Travel do about "what is still unbooked", and where do they fall short for this traveller? Nothing was checked; this session had no network access | no | Michal Klosinski, or an agent session with network access | open |
| Q02 | The design export has a "Zadania & Przygotowanie" checklist separate from timeline items. Is a preparation task a first-version concept or a later one? | no | Michal Klosinski | open |
| Q03 | Where do attachments live, what size and formats are accepted, does a trip's magic link expose them, and can the link be revoked? The design says PDF, PKPASS, JPG up to 25 MB; nothing in this session confirmed it | no | Michal Klosinski | open |
| Q04 | Does the first version handle more than one currency? The owner said nothing about it; the design carries a PLN/EUR toggle and a budget figure | no | Michal Klosinski | open |
| Q05 | The i18n library is still `TODO` in `AGENTS.md`, and locale files must land where `scripts/check_locales.py` looks; the choice belongs to the first frontend PR | no | Michal Klosinski | open |

## Definition of Ready addendum (own)

The riskiest assumption A01 is untested, and the owner recorded the decision to build without testing it (D15): the first version serves him alone, and a wider audience is conditional on his own satisfaction. The brief is therefore **signed** — knowingly, with the assumption open.

Two things follow for anyone filing tickets from this brief. First, P1 and P2 rest on a single respondent who is also the builder, with no frequency and no cost attached; `om-prepare-issue` should say so in any ticket justified by them. Second, every ticket whose justification is "so that other people can use it" is out of scope until A01 is tested — the sharing link in *Now* is there because the owner wants to show his own plan, not because a second user was found.

## Collection plan

### Product and how it stands out — benchmark

- **What we need to know:** what existing planners already do about "what is still unbooked", and where they fall short for a traveller who plans multi-stop trips by hand
- **Who can answer it:** the owner, or an agent session with network access
- **How:** benchmark check — Wanderlog, TripIt, Mindtrip, Google Travel: how each shows unresolved parts of a plan, how each shares a plan with a companion, what it costs
- **Owner and by when:** Michal Klosinski, before any work aimed at users beyond the owner
- **Template:** `.ai/specs/research/templates/benchmark-check.md`

### Problems, with evidence — users other than the owner

- **What we need to know:** whether P1 and P2 exist for anyone besides the owner, how often, and what they cost
- **Who can answer it:** three people from the owner's circle who travelled in the last year
- **How:** interview — three short conversations: what they used, where the state of the plan lived, what they did when someone asked to see it
- **Owner and by when:** Michal Klosinski, before any work aimed at users beyond the owner
- **Template:** `.ai/specs/research/templates/interview-note.md`
