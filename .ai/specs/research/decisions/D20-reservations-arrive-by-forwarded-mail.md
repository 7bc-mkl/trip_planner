# D20 — Reservations enter the app by forwarding the confirmation to one account-level address

- Date, owner: 2026-09-26, Michal Klosinski
- Context and the options weighed: the alternatives put to the owner were a forwarding address the app owns and dropping the PDF into the app the way an attachment is uploaded today. The second needs no new trust boundary and keeps the manual step that the feature exists to remove. Within the first, a per-trip address makes routing trivial and means a new address every trip; one account-level address is permanent and has to work out the trip itself.
- Decision and why: "Definitely for account. Some LLM or other mechanism to route to the trip. If missed then generic queue for user intervention." One address for the account; a model routes the message to a trip; a message it cannot place waits in a queue the owner clears by hand.
- Consequences, and what would make us revisit it: moves the "automatic parsing of reservation PDFs and e-mails; a private per-trip e-mail address" line out of D12's *Later* list into *Now*. It creates the app's first inbound path that is not an owner session (R10, which widens R08), and it makes routing accuracy a product risk (A07). If the unrouted queue turns out to hold most messages, the inbox saves nothing and the decision is worth reopening.
- Status: active
