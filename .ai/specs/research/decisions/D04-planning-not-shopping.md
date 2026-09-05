# D04 — Planning first: no live search, no prices, no booking
- Date, owner: 2026-09-05, Michal Klosinski
- Context and the options weighed: The design export contains prices, budget figures, "Zarezerwuj przez AI", "Kup teraz przez AI" and external purchase links, which would mean live integrations with inventory and payment providers. The owner was asked whether the first version searches the real world or is a place where a plan is kept.
- Decision and why: "Przede wszystkim planowanie; cała reszta to dodatek — nie musi sam szukać; może sugerować pewne rzeczy ze swojej wiedzy albo przez web search."
- Consequences, and what would make us revisit it: R07 in the brief: no booking, no payment, no live price or inventory lookup in the first version. Assistant suggestions come from the model's own knowledge, which makes assumption A04 (are they accurate enough to be trusted) load-bearing.
- Required path to change: A superseding record; the first integration with live data would need one.
- Status: active
- Source: `.ai/specs/research/interviews/2026-09-05-owner-session.md`
