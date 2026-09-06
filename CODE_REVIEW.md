# Code review rules — trip_planner

The repo-local review checklist. `om-code-review` (and therefore `om-auto-review-pr`) applies this file automatically, in addition to its built-in checklist. Humans reviewing by hand should use it too.

> **Greenfield note.** This repository had no source code when these rules were written, so they are derived from the agreed stack (uv + Python backend, React frontend, PL/EN multilingual) rather than from observed code. As real conventions establish themselves — the validation library, the error-response shape, the i18n library — replace the **TODO** markers here with what the code actually does. A rule nobody can point at in the codebase is a rule that will not be followed.

## Review priorities, in order

Findings are ranked by severity, and severity is decided by consequence, not by how much code changed.

| Severity | Meaning | Verdict impact |
|---|---|---|
| **Blocker** | Ships a security hole, loses or corrupts user data, breaks a documented contract surface, or leaves the validation gate red. | `changes-requested`, always. |
| **Major** | A real correctness bug on a realistic path, a missing regression test for a fixed bug, or an untranslated user-facing string. | `changes-requested` unless the author has a stated reason. |
| **Minor** | Clarity, naming, duplication, a missing edge-case test. | Note it; does not block on its own. |
| **Nit** | Style preference the tooling does not enforce. | Optional; prefer filing a follow-up over blocking. |

Do not report a finding the tooling already catches — `ruff` and `npm run typecheck` are in the gate, so formatting and type errors are not review findings.

## 1. Correctness

- **Every bug fix has a regression test that fails without the fix.** This is the single most-skipped rule; check that the test actually exercises the fixed path rather than passing vacuously.
- Error paths are as reviewed as happy paths. What does the user see when the call fails, when the input is malformed, when the third party times out?
- Timezones and dates are a trip planner's sharpest edge. An itinerary spans days, often across timezones. Reject naive `datetime` in domain logic — everything is timezone-aware, and "the day a traveller is in Lisbon" is not the same as "the day in the server's timezone".
- Money and distances carry units. No bare floats representing currency; no ambiguity between km and miles.
- Concurrency and ordering: if a change introduces background work, retries, or caching, what happens when it runs twice?

## 2. Security

- **No secrets in the diff.** API keys, tokens, connection strings, and `.env` content never land in the repository. A credential-looking string in a diff is a blocker, and rotating it is part of the fix — deleting the line is not enough once it is pushed.
- Every external input is validated at the boundary before it reaches domain logic. The library is **Pydantic v2**, and the shared pattern is a request model per endpoint with `model_config = ConfigDict(extra="forbid")`, so an unknown field is a `422` rather than a silently dropped typo. Domain functions take already-validated values; a handler that passes raw request data into `domain/` is a finding.
- Authorization is checked per resource, not per route. A trip belongs to a user; reading, editing, or sharing it must verify that ownership at the point of access.
- User-supplied content rendered in React must not use `dangerouslySetInnerHTML` without an explicit, reviewed sanitization step.
- Outbound calls to third-party APIs (maps, places, weather, LLM providers) must not forward more user data than the feature needs. Flag anything that sends personal data to a new destination — that is a product decision, not an implementation detail.
- LLM-driven planning is untrusted output: never execute, eval, or interpolate a model response into a query, path, or shell command without validation. Model output is data.

## 3. Contracts

- Check the change against `BACKWARD_COMPATIBILITY.md`. A breaking change to a protected surface without the required migration path is a blocker, and the reviewer quotes the specific surface.
- HTTP response shapes, error codes, and field names are contracts the frontend depends on. A rename is a breaking change even when both sides land in the same PR — say so, and check the deprecation path.
- Database migrations are reviewed for reversibility and for what happens to rows that already exist.

## 4. Multilingual — repo-specific

This is where a trip planner quietly rots, so it gets its own section.

- **No hardcoded user-visible strings.** Every string a user reads goes through the i18n layer. A literal in JSX or in a backend error message that reaches the UI is a **major** finding.
- Every new key exists, non-empty, in both `en` and `pl`. The gate (`scripts/check_locales.py`) catches missing and empty keys — but it cannot catch a Polish value that is just the English text copied over. Reviewers check that.
- Polish is not English with different words: it has grammatical cases and complex plural rules (1 / 2–4 / 5+). Any string with a count in it must use the i18n library's plural mechanism, not `n === 1 ? "day" : "days"` logic.
- Dates, times, numbers, currencies, and distances are formatted through the locale, never concatenated by hand.
- Layout must survive longer Polish strings. A button sized to fit "Save" will break on "Zapisz zmiany" — flag fixed-width containers around translated text.

## 5. Frontend quality

- TypeScript `strict`; an `any` needs a comment explaining why. A cast that silences the compiler without changing runtime behavior hides a bug rather than fixing one.
- Loading, empty, and error states exist for every screen that fetches data. A trip planner shows a lot of remote data; "it works when the API is fast and returns results" is not a finished screen.
- Accessibility on interactive elements: real `<button>`/`<a>` semantics, labels on form controls, keyboard reachability, visible focus. The repo already carries an `accessibility` label — use it.
- No new dependency without a reason in the PR description. Check bundle impact for anything large.

## 6. Backend quality

- Dependencies are added with `uv add`, and `uv.lock` is committed in the same commit.
- I/O-bound work does not block; long-running planning work does not run inside a request handler without a stated reason.
- Log lines never contain credentials, tokens, or full request bodies with personal data.
- Domain logic is testable without the network. If a change makes a unit test require a live third-party API, that is a design finding.

## 7. Tests

- Tests assert behavior, not implementation. A test that breaks on every refactor is a maintenance cost, not a safety net.
- Reject tests that cannot fail: no assertion, an assertion on a mock's own return value, or a `try/except` that swallows the failure.
- Frontend tests exercise what the user does (render, click, read), not component internals.

## Review conduct

- Every finding names a file and line, states the consequence, and proposes a concrete fix. "This is wrong" is not a finding.
- Approve when the change is correct and safe, not when it is perfect. Minors and nits become follow-up issues (`om-followup-issue-from-pr`), not another review round.
- Say what you checked and could not verify — an honest "I did not exercise the booking flow" is worth more than silent approval.
- The validation gate is evidence, not a substitute for reading the diff. Green CI on an unreviewed design change means nothing.
