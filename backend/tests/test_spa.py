"""Serving the built SPA from the same origin as the API.

The interesting cases are all about what the catch-all route must *not* swallow:
an unknown API path (which must stay a JSON error), a file the build put in the
bundle root (which must be itself, not the app shell), and anything reached
through `..` (which must not be served at all).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trip_planner.spa import mount_spa, public_file

API_PREFIX = "/api/v1"


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """A bundle shaped like the one `npm run build` produces."""
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg id='favicon'/>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(bundle: Path) -> Iterator[TestClient]:
    app = FastAPI()
    mount_spa(app, API_PREFIX, bundle)
    with TestClient(app) as test_client:
        yield test_client


class TestPublicFiles:
    def test_a_file_in_the_bundle_root_is_served_as_itself(self, client: TestClient) -> None:
        """The bundler copies `public/` to the root, not under /assets.

        Without this the favicon answers 200 with the app shell — an HTML body
        where an image was asked for, which fails silently in every browser.
        """
        response = client.get("/favicon.svg")

        assert response.status_code == 200
        assert "svg" in response.headers["content-type"]
        assert response.text == "<svg id='favicon'/>"

    def test_hashed_assets_are_still_served(self, client: TestClient) -> None:
        response = client.get("/assets/index-abc123.js")

        assert response.status_code == 200
        assert "console.log(1)" in response.text

    def test_a_traversal_attempt_never_leaves_the_bundle(self, bundle: Path) -> None:
        """`..` must resolve to nothing, not to a file next to the bundle."""
        secret = bundle.parent / "outside.txt"
        secret.write_text("not yours", encoding="utf-8")

        assert public_file(bundle, "/../outside.txt") is None
        assert public_file(bundle, "/assets/../../outside.txt") is None

    def test_the_index_is_not_treated_as_a_public_file(self, bundle: Path) -> None:
        """It goes through the fallback instead, which is where no-store is set."""
        assert public_file(bundle, "/index.html") is None


class TestTheClientRoutingFallback:
    def test_an_unknown_path_gets_the_app_shell(self, client: TestClient) -> None:
        """A reload on /trips/123 must reach the app, not a 404."""
        response = client.get("/trips/123")

        assert response.status_code == 200
        assert "<div id=root>" in response.text

    def test_the_shell_is_never_cached(self, client: TestClient) -> None:
        """index.html names the hashed bundles; a stale copy pins a dead build."""
        assert client.get("/trips").headers["cache-control"] == "no-store"

    def test_an_unknown_api_path_stays_a_json_error(self, client: TestClient) -> None:
        response = client.get(f"{API_PREFIX}/nope")

        assert response.status_code == 404
        assert response.json() == {"error": {"code": "not_found", "field": None}}
