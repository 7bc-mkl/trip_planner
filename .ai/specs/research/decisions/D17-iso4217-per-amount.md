# D17 — Every stored amount carries its own ISO-4217 currency code; no conversion, no totals

- Date, owner: 2026-09-26, Michal Klosinski
- Context and the options weighed: proposed on 2026-09-06 by the attachments spec as an autonomous default (its A7) and shipped in PR #12, where a CHECK constraint pairs `cost_amount` with `cost_currency` so an amount never exists without its unit. The design export shows a PLN/EUR toggle and a per-trip budget figure; neither was built, because a total across currencies needs a conversion rate and a date nobody has decided.
- Decision and why: as in the title. Confirmed by the owner on 2026-09-26 ("Confirm").
- Consequences, and what would make us revisit it: closes brief Q04 and the "undecided" clause inside R04. Cost accounting and splitting between participants stay in *Later* under D12; when either arrives it brings the conversion decision with it.
- Status: active
