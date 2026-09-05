# D05 — Exactly three item statuses, and the counter counts the last two
- Date, owner: 2026-09-05, Michal Klosinski
- Context and the options weighed: The owner's first description had two states ("do zrobienia/zarezerwowania" and "zaplanowane"); the design export scatters nine different status labels across its screens. The counter built on these statuses is the product's main value, so the vocabulary had to be settled.
- Decision and why: Three statuses: *do zaplanowania*, *do zarezerwowania*, *gotowe*. The readiness counter counts the last two. The count of three was proposed by the agent and accepted with a single "3"; the names and the arithmetic are the owner's own, given in the fourth round after the agent's invented names were removed from the draft.
- Consequences, and what would make us revisit it: R02 in the brief. An item still *do zaplanowania* is outside the counter's arithmetic, so the counter answers "how much of what I have decided on is arranged", not "how much of the trip is figured out".
- Required path to change: A superseding record; the design export's richer vocabulary would come back as a data migration.
- Status: active
- Source: `.ai/specs/research/interviews/2026-09-05-owner-session.md`
