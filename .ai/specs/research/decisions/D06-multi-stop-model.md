# D06 — Multi-stop trips are in the data model from the first migration
- Date, owner: 2026-09-05, Michal Klosinski
- Context and the options weighed: The owner's opening description was one destination and a return. The design export assumes open-jaw routes (out to one airport, back from another) and several bases inside one trip. The two imply different schemas.
- Decision and why: "Zdecydowanie wieloprzystankowość."
- Consequences, and what would make us revisit it: R03 in the brief: trip → stages → days → items, and a return point that may differ from the departure point, from the first migration onwards. The creation form asks for dates, a starting point and one or more destinations.
- Required path to change: A superseding record; simplifying to a single destination later would be a migration, not a settings change.
- Status: active
- Source: `.ai/specs/research/interviews/2026-09-05-owner-session.md`
