"""Serving the built SPA from the same origin as the API (spec A12).

One origin removes CORS, a second TLS certificate and a second host, and makes
the cookie and CSRF story trivial. At one user there is no scaling argument on
the other side.

The bundle is absent in development and in the test suite — the Vite dev server
serves it there — so mounting is conditional. A missing bundle must not stop the
API from starting.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from trip_planner.errors import ErrorCode, error_body

#: Where the Docker build stage puts the built SPA.
DEFAULT_STATIC_DIR = Path("/srv/static")


def static_dir() -> Path | None:
    """The directory holding the built SPA, or None when it is not present."""
    configured = os.environ.get("STATIC_DIR")
    candidate = Path(configured) if configured else DEFAULT_STATIC_DIR

    return candidate if (candidate / "index.html").is_file() else None


def public_file(directory: Path, url_path: str) -> Path | None:
    """A file the build put in the bundle root, or None.

    The bundler copies everything in `public/` (favicon.svg, icons.svg, a future
    robots.txt) to the root of the bundle rather than under `/assets`, so without
    this they fall through to the index fallback and answer with the app shell:
    a 200 of `text/html` where an image was asked for, which fails silently.

    `index.html` is deliberately excluded so it keeps going through the fallback
    that sets `Cache-Control: no-store`.
    """
    relative = url_path.lstrip("/")
    if not relative or relative == "index.html":
        return None

    root = directory.resolve()
    candidate = (root / relative).resolve()

    # `..` in a path must not reach outside the bundle. Resolving first and then
    # requiring the root to be an ancestor is the check that survives symlinks
    # and encoded separators alike.
    if root not in candidate.parents or not candidate.is_file():
        return None

    return candidate


def mount_spa(app: FastAPI, api_prefix: str, directory: Path) -> None:
    """Serve the SPA's assets, and its index for every non-API path.

    The fallback is what makes client-side routing survive a reload: a browser
    asking for /trips/123 directly must get the app shell, not a 404.

    Paths under the API prefix are deliberately excluded — an unknown API path
    must stay a JSON 404, not silently return HTML that a fetch caller would then
    fail to parse with a confusing error.
    """
    index = directory / "index.html"

    assets = directory / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    async def serve_index(request: Request) -> Response:
        if request.url.path.startswith(api_prefix):
            # Answer in the API's own error shape, not an empty body and not
            # HTML: a fetch caller parses this, and an unknown API path must look
            # like every other API error.
            return JSONResponse(status_code=404, content=error_body(ErrorCode.NOT_FOUND))

        asset = public_file(directory, request.url.path)
        if asset is not None:
            return FileResponse(asset)

        # index.html must never be cached: it names the hashed asset bundles, so
        # a stale copy pins the browser to a deleted build.
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    # Registered as a Starlette route rather than an APIRoute: it is static
    # delivery, not API surface, and the route-protection enumeration is about
    # the latter.
    app.router.routes.append(Route("/{full_path:path}", serve_index, methods=["GET", "HEAD"]))
