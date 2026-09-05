# Backward compatibility — protected contract surfaces

What this project treats as a **contract**: something another party depends on, where a unilateral change breaks them. Review skills check every change against this file; implementation skills warn when a change violates it.

> **Greenfield note.** This repository had no source code when this file was written, so the inventory below is derived from the agreed architecture (a Python backend serving a React SPA, PL/EN multilingual) rather than from surfaces that exist today. Each surface is marked with its current state. As real surfaces appear, replace the placeholder with the concrete path, route prefix, or table name — and delete any surface this project turns out not to have. **An inventory nobody updates protects nothing.**

## The general rule

A change to a protected surface is **breaking** when an existing, correct consumer stops working after it — without that consumer changing anything. Adding is usually safe; removing, renaming, narrowing, and changing meaning are not.

Three things are always breaking, whatever the surface:

1. **Removing** something a consumer can currently use.
2. **Renaming** it (a rename is a removal plus an addition).
3. **Changing what it means** while keeping its name — the silent one, and the worst, because nothing fails loudly.

## Inventory

### 1. HTTP API — the backend/frontend contract

*State: not yet created. Expected under `backend/`, served to `frontend/`.*

The frontend is a real consumer even though it lives in the same repository. Landing both sides of a rename in one PR does not make it non-breaking: deployed clients, open browser tabs, and any cached bundle still speak the old shape.

| Change | Breaking? | Required path |
|---|---|---|
| Adding a new endpoint | No | Ship it. |
| Adding an **optional** response field | No | Ship it. Consumers must tolerate unknown fields. |
| Adding a **required** request field | **Yes** | Make it optional with a default first, migrate callers, then require it in a later release. |
| Removing or renaming a response field | **Yes** | Serve both old and new for one release, mark the old one deprecated in the PR body and in the API docs, then remove. |
| Changing a field's type or units | **Yes** | Never in place. Add the new field alongside, migrate, remove the old one. Changing a duration from minutes to seconds under the same name is the textbook silent break. |
| Changing an HTTP status code or error code for an existing condition | **Yes** | Frontends branch on these. Same deprecation path as a field rename. |
| Tightening validation on an existing endpoint | **Yes** | Input that used to be accepted now 4xx's. Log-and-allow first, measure, then enforce. |
| Changing pagination, sorting, or default limits | **Yes** | Treat as a field change; defaults are contract. |

**Versioning:** TODO — decide the strategy (URL prefix such as `/api/v1`, or additive-only evolution) in the first API spec, and record the decision here.

### 2. Persisted data — database schema and migrations

*State: not yet created.*

- Every schema change ships as a migration, in the same PR as the code that needs it.
- A migration must be **safe against rows that already exist**: adding a `NOT NULL` column requires a default or a backfill, never a bare `ALTER`.
- Destructive migrations (dropping a column or table) follow expand/contract: stop writing → stop reading → deploy → drop in a **later** release. Never in the same PR as the code change.
- Data loss is a **blocker** finding, always. There is no "it's only a dev database" exception in a reviewed PR.

### 3. Stored trip and itinerary documents

*State: not yet created. This is the surface most specific to this product.*

A saved trip is a user's own data and may sit untouched for months between the moment it is planned and the moment it is travelled. Whatever shape a trip is persisted in, old records must keep loading.

- A stored trip/itinerary must be readable by any later version of the code. Changing the stored shape requires either a version field with an upgrade path, or a migration that rewrites existing records.
- **A user's saved plan must never silently change meaning.** If a field's interpretation changes, existing records are migrated — not reinterpreted.
- Shared or exported itineraries (public links, exports) are external contracts: an old link must keep resolving, or resolve to an explicit "this plan is no longer available", never to a wrong plan.

### 4. Translation keys

*State: `scripts/check_locales.py` is in place; locale roots not yet created.*

Locale keys are an internal contract between the code and the locale files, enforced by the validation gate.

- Removing or renaming a key without updating every call site breaks the UI at runtime, not at build time. Rename in one commit across code and **all** locales.
- Every key exists non-empty in `en` and `pl`. Adding a language is additive and safe; **removing a required language is breaking** — update `REQUIRED_LOCALES` in `scripts/check_locales.py` and say why in the PR.
- Changing a key's meaning while keeping its name is breaking: other call sites now show the wrong text. Introduce a new key instead.

### 5. Configuration and environment variables

*State: not yet created.*

- Adding an **optional** variable with a sensible default: safe.
- Adding a **required** variable: breaking for every deployment — call it out in the PR body, document it, and provide a clear startup error naming the missing variable.
- Removing or renaming a variable: read both names for one release, warn on the old one, then drop it.
- Never commit a real value. Document the variable's name, purpose, and format; keep the value in the environment.

### 6. External integrations

*State: not yet created (maps, places, weather, booking, LLM providers).*

We are the consumer here, not the provider — but our users depend on the behavior these produce.

- A provider swap that changes user-visible results (different places, different routes, different prices) is a product decision, not a refactor. It needs a spec and a stated migration for saved trips built on the old provider's data.
- Every integration has a defined failure mode. Changing that failure mode — from "show cached results" to "show an error", say — is a user-visible behavior change and belongs in the PR description.

### 7. Pipeline configuration

*State: in place.*

`.ai/agentic.config.json`, `SDLC.md`, `.ai/trackers/github.md`, and `.ai/browsers/agent-browser.md` are the agent pipeline's contract. Changing `validation.commands`, the label taxonomy, or the QA gate changes how every skill behaves — update the config and `SDLC.md` in the same PR, and re-run `om-setup-agent-pipeline` when the toolchain or label taxonomy changes.

## What is *not* protected

To keep this list meaningful, these are explicitly free to change without ceremony:

- Internal module structure, function names, and file layout not exported across a boundary above.
- Private helpers, test fixtures, and test names.
- Anything documented as experimental **in the code**, with a comment naming the surface as unstable.
- The wording of English or Polish copy (the *key* is the contract, the *text* is not).

## Before merging a change to a protected surface

1. Say in the PR body which surface changed and whether it is breaking.
2. Provide the required path from the table (deprecation window, migration, or both).
3. Add a test proving the old behavior still works during the deprecation window.
4. If the change is breaking and the path cannot be followed, it needs an explicit maintainer decision on the PR — recorded there, not in chat.
