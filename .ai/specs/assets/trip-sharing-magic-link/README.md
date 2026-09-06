# Visual evidence — trip-sharing-magic-link

Attached to PR #3 and referenced from `.ai/specs/2026-09-05-trip-sharing-magic-link.md`.

## Proposed — illustrative mockups

Self-contained static HTML with no application code behind it, rendered to PNG by the configured
browser provider (`agent-browser`). They communicate layout, hierarchy and copy — not pixel-perfect
design, and not a promise about markup.

They deliberately **share `../design-system-adoption/_mockup.css`** rather than carrying a stylesheet
of their own. That file is the adopted design system's mockup vocabulary, and its `@font-face` rules
resolve `fonts/` relative to itself, so these pages render in the real Plus Jakarta Sans with no
network request. One stylesheet means these mockups cannot drift from the system they depict; the
cost is that they must be rendered from this directory, with that sibling present.

| File | Shows |
|---|---|
| `mockup-01-share-dialog.*` | The owner's share dialog in **State B** (an active link): the URL, the copy affordance with its `aria-live` confirmation, the creation date, and the revoke action with its consequence sentence. Behind it, the `Udostępniona` chip on the trip banner and "Udostępnij" beside "Usuń podróż" in the `actions` slot `TimelinePage` already passes to `AppShell`. Polish |
| `mockup-02-guest-view.*` | `/s/:token` — `GuestShell` (no sign-out, no account, no dock, the wordmark not a link), the read-only banner, `ReadinessTile` with its ring, `FilterBar`, and the timeline rail with `ItemRow` in its non-interactive form. **Item cards carry no notes line** — the visible face of Q3. Polish |
| `mockup-03-guest-dead-links.*` | `/s/:token` — the three dead-link pages side by side: revoked (`410`), trip deleted (`410`), unknown or malformed (`404`). English, because R01 makes both locales first-class |

Fabricated data is plan data only: the share token in mockup 01 is invented and labelled as such.
There is no example guest, no view count and no progress figure the guest payload does not carry.

## Current state

Not re-captured in this revision. The application runs, and the timeline as it looks today — the
screen mockups 01 and 02 are both derived from — is committed in both locales and at 360px at
`.ai/runs/2026-09-06-design-system-adoption/final-gate-artifacts/`. Photographing it again here
would mean booting Postgres and the stack to show screens this feature has not changed yet.
