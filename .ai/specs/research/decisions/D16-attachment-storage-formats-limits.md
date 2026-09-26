# D16 — Attachments live in the app's own PostgreSQL database; PDF, JPEG and PNG only; 10 MB per file

- Date, owner: 2026-09-26, Michal Klosinski
- Context and the options weighed: proposed on 2026-09-06 by `.ai/specs/2026-09-05-attachments-and-reservation-data.md` as an autonomous default (its A2, A3, A4) and shipped in PR #12. The alternatives weighed there were an object store (one more credential, one more failure mode, a bucket to provision) and Postgres large objects (streaming bought nothing at a 10 MB cap and reintroduced orphan bookkeeping). PKPASS, SVG, HEIC, WEBP, GIF, TIFF, archives and Office documents were refused: each is another parser family, and PKPASS renders as nothing without the Wallet export D12 defers.
- Decision and why: as in the title. Confirmed by the owner on 2026-09-26 when the rows the spec had asked for were put to him — he answered "Confirm". The spec marked A2 as migration-class, which is why it wanted an owner's row behind it rather than a default.
- Consequences, and what would make us revisit it: closes the storage half of brief Q03 and retires that clause of R05's ancestor question. Moving to an object store stays additive — a `storage_backend` column, an `object_key` column, a copy job. A format nobody can identify from its bytes does not get added.
- Status: active
