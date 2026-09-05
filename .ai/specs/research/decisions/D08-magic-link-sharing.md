# D08 — Sharing works through one magic link per trip, read-only
- Date, owner: 2026-09-05, Michal Klosinski
- Context and the options weighed: Sharing the state of a plan is one of the two problems in the brief. Three ways in were offered for the person receiving it: a public read-only URL, accounts with named invitations, or a magic link.
- Decision and why: "Wchodzi przez magic linka", refined in the fourth round to "jeden dla projektu, read only w v1" — one link per trip, read-only.
- Consequences, and what would make us revisit it: R05 in the brief. One link per trip is what gets pasted into a group chat, which means anyone holding it can read the plan; expiry, revocation and whether attachments and confirmation numbers are exposed through it are left open as Q03 and must be settled before the link ships.
- Required path to change: A superseding record; a per-person link or a public catalogue of plans would each need their own privacy decision.
- Status: active
- Source: `.ai/specs/research/interviews/2026-09-05-owner-session.md`
