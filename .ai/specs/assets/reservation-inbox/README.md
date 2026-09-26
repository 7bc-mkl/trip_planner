# Visual evidence — reservation-inbox

Referenced from `.ai/specs/2026-09-26-reservation-inbox.md` and attached to its PR.

## Proposed — illustrative mockups

Self-contained static HTML with no application code behind it, rendered to PNG by the configured
browser provider (`agent-browser` v0.34.0). They communicate layout, hierarchy and copy — not
pixel-perfect design, and not a promise about markup.

They deliberately **share `../design-system-adoption/_mockup.css`** rather than carrying a stylesheet
of their own, exactly as the sharing spec's mockups do. That file is the adopted design system's
mockup vocabulary, and its `@font-face` rules resolve `fonts/` relative to itself, so these pages
render in the real Plus Jakarta Sans with no network request. One stylesheet means these mockups
cannot drift from the system they depict; the cost is that they must be rendered from this
directory, with that sibling present.

| File | Shows |
|---|---|
| `mockup-01-inbox.*` | `/inbox` — the three regions in the order attention should go: **Do zatwierdzenia** (an `update_item` proposal targeted at an existing hotel item, and a `create_item` proposal for a flight with no matching item), **Nieprzypisane** with the router's reason in plain language, and **Kwarantanna** as a count with *Pokaż* revealing sender and subject only — never a body or an attachment — and *Zwolnij tę wiadomość* beside a DMARC-failing auto-forward, which is the policy's one predictable false positive. The nav badge, the forwarding address, and the honest "last checked" line. Polish |
| `mockup-02-action-item-sheet.*` | The action-item review sheet — the feature's whole argument in one screen. The two-column diff (*now in your plan* / *in the message*) with per-field ticks: empty fields ticked, **the non-empty `Cost` unticked by default with both values shown**, the un-proposed `Notes` untouched, the forward status move ticked, the document its own row. The source message beside it as plain text, with the extracted values marked. English |
| `mockup-03-states.*` | Four states: **A** trip classification from the unrouted queue, with the document retained in the inbox until approval, **B** the normal empty state naming the address, **C** the inbox not configured (an explanation, not an error), **D** a failed poll with the honest "messages are not lost" line. Polish |

Two locales across the set, for the reason R01 gives: both are first-class, and a spec that only ever
pictures one is not showing the product it describes.

All data is fabricated plan data — the addresses, booking references and PDF names are invented and
belong to no real reservation. No credential, token or real confirmation appears anywhere.

## Current state

Not captured. The screens this feature proposes **do not exist yet** — there is no `/inbox` route, no
nav badge and no review sheet in the running application, so there is nothing to photograph that
would tell a reviewer anything the mockups do not. Capturing the surrounding app again would mean
booting Postgres and the stack to re-photograph screens this feature does not change; the timeline
and day detail as they look today are already committed under
`.ai/runs/2026-09-06-design-system-adoption/final-gate-artifacts/` and in the sibling asset
directories.
