# D21 — Every forwarded reservation becomes an action item the owner approves

- Date, owner: 2026-09-26, Michal Klosinski
- Context and the options weighed: the owner's first description separated the two cases — populate a matching item, and raise something approval-gated only when nothing matched. Asked directly whether populating an existing item could happen silently, he closed the gap: "Leave it for now as action item as well, just better targeted."
- Decision and why: a forwarded message never changes a plan by itself. It produces an action item: aimed at the matching item when the router found one, proposing a new item when it did not. The owner approves it, and only then does the plan change.
- Consequences, and what would make us revisit it: this is what keeps A07 and A08 — routing and extraction errors — annoyances rather than a plan that is quietly wrong while the readiness counter still says "arranged". It also means the inbox never reduces the number of decisions the owner makes, only the amount he types, which is the honest measure of whether it met P3.
- Status: active
