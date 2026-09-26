# D18 — A trip's magic link exposes no attachments, notes, confirmation numbers or costs

- Date, owner: 2026-09-26, Michal Klosinski
- Context and the options weighed: proposed by the attachments spec (its A8/A9) and matched independently by the sharing spec's guest projection, which lists what a guest sees — title, dates, places, stages, days, each item's kind, status, times and title, and the counter — and states the rest is "absent by construction". The alternative, letting the sharer choose per link what a guest sees, is what the larger planners do; it was rejected as permissions work the first version does not want.
- Decision and why: as in the title. Confirmed by the owner on 2026-09-26 ("Confirm").
- Consequences, and what would make us revisit it: settles R05's visibility clause and closes the attachment half of brief Q03. It also keeps the attachments design's threat model intact — nobody but the owner can fetch a stored byte — which is the condition under which malware scanning and EXIF stripping were cut. Widening guest visibility reopens both.
- Status: active
