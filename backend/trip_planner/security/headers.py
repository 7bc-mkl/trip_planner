"""Response security headers, set by the app itself.

These four were Caddy's job (`deploy/Caddyfile`); the Lambda target has no Caddy,
so the app sets them. Caddy's `header` directive *replaces*, so the two together
do not duplicate a header and the Caddyfile stays as it is.

Pure ASGI rather than `BaseHTTPMiddleware`: that one buffers and re-streams the
body, which would defeat streamed attachment downloads.

A header a route already set is never overridden (the attachment content routes
carry their own `nosniff` and sandbox CSP). One limit: Starlette's outermost
`ServerErrorMiddleware` sits outside user middleware, so an unhandled-exception
500 does not pass through here.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Same value as the Caddyfile: two years, no `preload` (effectively irreversible).
HSTS_VALUE = "max-age=63072000; includeSubDomains"

BASE_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.headers = BASE_HEADERS + ((("Strict-Transport-Security", HSTS_VALUE),) if hsts else ())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers:
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
