"""Startup configuration and SPA delivery.

`BACKWARD_COMPATIBILITY.md` §5 requires a new required variable to fail loudly at
startup naming itself. The failure mode this prevents is the quiet one: an app
that starts with a default, serves wrongly, and is diagnosed hours later.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trip_planner.app import API_PREFIX, create_app
from trip_planner.config import (
    REQUIRED_ENVIRONMENT_VARIABLES,
    MissingConfiguration,
    require_settings,
)
from trip_planner.spa import mount_spa, static_dir


class TestStartupRefusesIncompleteConfiguration:
    @pytest.mark.parametrize("missing", sorted(REQUIRED_ENVIRONMENT_VARIABLES))
    def test_startup_aborts_naming_the_unset_variable(
        self, missing: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        complete = {
            "DATABASE_URL": "postgresql://u:p@h/d",
            "SESSION_SECRET": "x" * 48,
            "APP_BASE_URL": "https://planner.example.com",
            "ENVIRONMENT": "production",
        }
        del complete[missing]

        for name in REQUIRED_ENVIRONMENT_VARIABLES:
            monkeypatch.delenv(name, raising=False)
        for name, value in complete.items():
            monkeypatch.setenv(name, value)

        with pytest.raises(MissingConfiguration) as caught:
            create_app()

        assert caught.value.missing == [missing]
        assert missing in str(caught.value), "the operator must not have to read the source"

    def test_the_message_explains_what_the_variable_is_for(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in REQUIRED_ENVIRONMENT_VARIABLES:
            monkeypatch.delenv(name, raising=False)

        with pytest.raises(MissingConfiguration) as caught:
            require_settings()

        message = str(caught.value)
        for name, purpose in REQUIRED_ENVIRONMENT_VARIABLES.items():
            assert name in message
            assert purpose.split(",")[0][:20] in message

    def test_every_required_variable_is_documented_in_the_compose_file(self) -> None:
        """A variable the app requires but the deployment never sets is a crash."""
        compose = (Path(__file__).resolve().parents[2] / "deploy" / "compose.yml").read_text()

        for name in REQUIRED_ENVIRONMENT_VARIABLES:
            assert name in compose, f"deploy/compose.yml never sets {name}"


class TestSpaDelivery:
    @pytest.fixture
    def bundle(self, tmp_path: Path) -> Path:
        (tmp_path / "index.html").write_text("<!doctype html><title>Smart Trip Planner</title>")
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "index-abc123.js").write_text("console.log('bundle')")
        return tmp_path

    def test_no_bundle_present_still_starts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Development and CI have no built bundle; the API must still run."""
        monkeypatch.setenv("STATIC_DIR", "/nonexistent/path")
        assert static_dir() is None

    def test_the_index_is_served_for_a_client_side_route(self, bundle: Path) -> None:
        """A reload on /trips/123 must get the app shell, not a 404."""
        app = create_app(check_configuration=False)
        mount_spa(app, API_PREFIX, bundle)

        with TestClient(app) as client:
            response = client.get("/trips/123")

        assert response.status_code == 200
        assert "Smart Trip Planner" in response.text

    def test_the_index_is_not_cached(self, bundle: Path) -> None:
        """It names hashed bundles; a stale copy pins the browser to a dead build."""
        app = create_app(check_configuration=False)
        mount_spa(app, API_PREFIX, bundle)

        with TestClient(app) as client:
            response = client.get("/trips")

        assert response.headers["cache-control"] == "no-store"

    def test_assets_are_served(self, bundle: Path) -> None:
        app = create_app(check_configuration=False)
        mount_spa(app, API_PREFIX, bundle)

        with TestClient(app) as client:
            response = client.get("/assets/index-abc123.js")

        assert response.status_code == 200
        assert "bundle" in response.text

    def test_an_unknown_api_path_stays_a_404_and_does_not_fall_back_to_html(
        self, bundle: Path
    ) -> None:
        """Serving HTML here would make a fetch caller fail with a parse error."""
        app = create_app(check_configuration=False)
        mount_spa(app, API_PREFIX, bundle)

        with TestClient(app) as client:
            response = client.get(f"{API_PREFIX}/nope")

        assert response.status_code == 404
        assert "<!doctype html>" not in response.text.lower()
        # And in the API's own error shape, like every other API error.
        assert response.json() == {"error": {"code": "not_found", "field": None}}

    def test_the_api_still_answers_with_the_spa_mounted(self, bundle: Path) -> None:
        app = create_app(check_configuration=False)
        mount_spa(app, API_PREFIX, bundle)

        with TestClient(app) as client:
            response = client.get(f"{API_PREFIX}/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestDeploymentArtifacts:
    @pytest.fixture
    def deploy_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "deploy"

    def test_the_dockerfile_builds_the_spa_and_serves_it_from_the_api_image(
        self, deploy_dir: Path
    ) -> None:
        dockerfile = (deploy_dir / "Dockerfile").read_text()

        assert "AS frontend" in dockerfile, "the SPA needs its own build stage"
        assert "npm run build" in dockerfile
        assert "COPY --from=frontend" in dockerfile, "one image must carry both"
        assert "USER planner" in dockerfile, "the runtime must not be root"

    def test_the_entrypoint_offers_a_migrate_release_step(self, deploy_dir: Path) -> None:
        """Migrations run before the new image takes traffic, so they need a hook."""
        entrypoint = (deploy_dir / "entrypoint.sh").read_text()

        assert "alembic upgrade head" in entrypoint
        assert "--factory" in entrypoint, "startup must validate configuration first"

    def test_the_compose_file_runs_migrations_before_the_app(self, deploy_dir: Path) -> None:
        compose = (deploy_dir / "compose.yml").read_text()

        assert "service_completed_successfully" in compose, (
            "the app must wait for the migrate step, not merely for it to start"
        )

    def test_no_secret_is_committed_in_a_deployment_file(self, deploy_dir: Path) -> None:
        """The one thing that must never be in the repository."""
        for path in deploy_dir.iterdir():
            if not path.is_file():
                continue
            text = path.read_text()
            assert "SESSION_SECRET:" not in text or "${SESSION_SECRET" in text, (
                f"{path.name} appears to hard-code SESSION_SECRET"
            )


def test_the_gate_and_the_ci_workflow_run_the_same_commands() -> None:
    """AGENTS.md requires the workflow to mirror validation.commands, in order."""
    root = Path(__file__).resolve().parents[2]
    commands = json.loads((root / ".ai" / "agentic.config.json").read_text())["validation"][
        "commands"
    ]
    workflow = (root / ".github" / "workflows" / "validation-gate.yml").read_text()

    for command in commands:
        assert command in workflow, f"the CI workflow does not run: {command}"
