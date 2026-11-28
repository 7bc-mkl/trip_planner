# Capability: http-delivery

Lets a browser load the app and its assets safely and quickly, on every deployment target.

## Requirement: Security headers on every response
The system SHALL set `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: strict-origin-when-cross-origin` on every response, plus `Strict-Transport-Security` when `ENVIRONMENT=production`, from the application itself rather than from the reverse proxy, without weakening a stricter header a route sets.

### Scenario: The Lambda target, with no proxy in front
- WHEN a browser requests `/login` through the Function URL
- THEN the response carries all four headers

### Scenario: A route with its own stricter policy
- WHEN an attachment's content is served
- THEN its sandbox CSP and its own headers are unchanged

Frozen by: `backend/tests/test_security.py` (characterization added in Phase 1 step 10)

Source: .ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md

## Requirement: Hashed assets are cached as immutable
The system SHALL serve files under `/assets` with `Cache-Control: public, max-age=31536000, immutable`, and SHALL keep serving `index.html` with `Cache-Control: no-store`.

### Scenario: A returning visit
- WHEN the owner opens the app a second time after the same build
- THEN the browser loads the bundles from its cache and requests only `index.html` and API calls

### Scenario: A new build
- WHEN a new image is deployed
- THEN the next page load fetches the new `index.html`, which names the new hashed bundles

Frozen by: `backend/tests/test_spa.py` (characterization added in Phase 1 step 10)

Source: .ai/specs/2026-11-27-scale-to-zero-deployment-lambda-neon.md
