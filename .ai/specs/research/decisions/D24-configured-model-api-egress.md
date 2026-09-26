# D24 — Forwarded confirmations may use one configured model API

- Date, owner: 2026-09-26, Michal Klosinski
- Context and options weighed: Q11 asked whether confirmation content may leave the deployment for a model. The reservation inbox spec proposes three supported API providers, an explicit provider and model selector, no default, and no automatic fallback. Keeping all content local would leave the Phase 1 manual inbox usable but remove model routing and extraction.
- Decision and why: the owner chose **“Allow configured API.”** Message text, `From`/`Subject`/`Date`, and limited candidate-trip summaries may go to one explicitly configured Anthropic, Google Gemini, or OpenAI API at a time. Document bytes require a separate owner action for the named document. With no complete provider configuration, no model content leaves the deployment.
- Consequences, and what would make us revisit it: this closes Q11 and permits Phases 2–4 of the reservation inbox spec. The selected provider's terms remain an operator check before enabling its credential. Egress is recorded with provider and model identity; a provider change requires an explicit configuration change. Revisit if the privacy terms or observed extraction quality make the convenience unacceptable.
- Status: active
