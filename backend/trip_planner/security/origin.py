"""The origin lock: only requests that came through CloudFront are served.

On the Lambda target the Function URL is `AuthType: NONE` and publicly
reachable. CloudFront adds a custom origin header, `X-Origin-Verify`, carrying
`ORIGIN_VERIFY_SECRET`; a request without the matching value did not come
through CloudFront and is answered `403 forbidden_origin` before any route runs.

The one exemption is `GET /api/v1/health`: the Lambda Web Adapter's readiness
probe comes from localhost without the header, and the route says nothing.

A verified request is marked in the ASGI scope (`ORIGIN_VERIFIED_SCOPE_KEY`), and
`security.rate_limit` trusts `CloudFront-Viewer-Address` only on such a request
— without this check anyone calling the raw Function URL could set it.

Installed only when the secret is set, so compose behind Caddy runs no check at
all. Pure ASGI, like `security.headers`: nothing here buffers a body.
"""

from __future__ import annotations

import hmac

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from trip_planner.errors import STATUS_FOR_CODE, ErrorCode, error_body

ORIGIN_VERIFY_HEADER = b"x-origin-verify"

#: Set to `True` in the scope of a request that carried the matching header.
#: A scope key rather than a header, so a caller cannot forge it.
ORIGIN_VERIFIED_SCOPE_KEY = "trip_planner.origin_verified"

#: (method, path) pairs served without the header.
EXEMPT: frozenset[tuple[str, str]] = frozenset({("GET", "/api/v1/health")})


def is_origin_verified(scope: Scope) -> bool:
    return scope.get(ORIGIN_VERIFIED_SCOPE_KEY) is True


class OriginVerifyMiddleware:
    def __init__(self, app: ASGIApp, *, secret: str) -> None:
        if not secret:
            raise ValueError("OriginVerifyMiddleware needs a non-empty secret")
        self.app = app
        self.secret = secret.encode("utf-8")

    def _matches(self, scope: Scope) -> bool:
        presented = [value for name, value in scope["headers"] if name == ORIGIN_VERIFY_HEADER]
        # Exactly one: two copies means something other than CloudFront set one.
        return len(presented) == 1 and hmac.compare_digest(presented[0], self.secret)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if self._matches(scope):
            scope[ORIGIN_VERIFIED_SCOPE_KEY] = True
            await self.app(scope, receive, send)
            return

        if (scope.get("method"), scope["path"]) in EXEMPT:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return

        code = ErrorCode.FORBIDDEN_ORIGIN
        response = JSONResponse(status_code=STATUS_FOR_CODE[code], content=error_body(code))
        await response(scope, receive, send)
