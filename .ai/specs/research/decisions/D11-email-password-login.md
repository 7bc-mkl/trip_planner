# D11 — The owner logs in with e-mail and password
- Date, owner: 2026-09-05, Michal Klosinski
- Context and the options weighed: Options were magic-link login (the same mechanism as for guests), no login at all in the first version, or a classic account.
- Decision and why: E-mail and password.
- Consequences, and what would make us revisit it: R08 in the brief. Two authentication paths exist by design: sessions for the owner, magic links for guests. Password reset and session handling are part of the first version's cost.
- Required path to change: A superseding record.
- Status: active
- Source: `.ai/specs/research/interviews/2026-09-05-owner-session.md`
