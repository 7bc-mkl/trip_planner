"""Startup configuration and SPA delivery.

`BACKWARD_COMPATIBILITY.md` §5 requires a new required variable to fail loudly at
startup naming itself. The failure mode this prevents is the quiet one: an app
that starts with a default, serves wrongly, and is diagnosed hours later.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
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


class TestProductionDeploymentShape:
    """What the deployed stack must be, asserted on the parsed compose document.

    These are not style checks. Each one is a way the deployment has silently
    gone wrong before: a database that ended up on a public port, an app started
    against an unmigrated schema, a proxy that served plain HTTP because the
    redirect was never configured.
    """

    @pytest.fixture
    def deploy_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "deploy"

    @pytest.fixture
    def compose(self, deploy_dir: Path) -> dict:
        return yaml.safe_load((deploy_dir / "compose.prod.yml").read_text())

    def test_only_the_proxy_is_published(self, compose: dict) -> None:
        """The database and the app must be unreachable except through Caddy."""
        published = {
            name: service["ports"]
            for name, service in compose["services"].items()
            if service.get("ports")
        }

        also_published = sorted(set(published) - {"caddy"})
        assert set(published) == {"caddy"}, (
            f"only the proxy may publish a port; these also do: {also_published}"
        )
        assert sorted(published["caddy"]) == ["443:443", "80:80"]

    def test_the_database_is_on_an_internal_network_only(self, compose: dict) -> None:
        assert compose["services"]["db"]["networks"] == ["internal"]
        assert compose["networks"]["internal"]["internal"] is True, (
            "the database's network must have no route off the host"
        )

    def test_the_app_waits_for_the_migration_to_complete(self, compose: dict) -> None:
        """Not 'waits for it to start' — an app on an unmigrated schema 500s."""
        assert compose["services"]["app"]["depends_on"]["migrate"] == {
            "condition": "service_completed_successfully"
        }

    def test_the_release_step_migrates_rather_than_serving(self, compose: dict) -> None:
        """`migrate-and-serve` is the single-instance fallback, not the hook."""
        assert compose["services"]["migrate"]["command"] == ["migrate"]
        assert compose["services"]["app"]["command"] == ["serve"]

    def test_every_required_variable_is_set_for_both_the_app_and_the_migration(
        self, compose: dict
    ) -> None:
        """A migration step missing DATABASE_URL fails the release, loudly but late."""
        for service in ("app", "migrate"):
            environment = compose["services"][service]["environment"]
            for name in REQUIRED_ENVIRONMENT_VARIABLES:
                assert name in environment, f"compose.prod.yml never sets {name} for {service}"

    def test_no_required_variable_has_a_default_that_would_half_configure_the_stack(
        self, compose: dict
    ) -> None:
        """`${VAR:-fallback}` would start production on a development value."""
        environment = compose["services"]["app"]["environment"]
        for name in REQUIRED_ENVIRONMENT_VARIABLES:
            assert ":-" not in environment[name], (
                f"{name} has a compose default; an unset variable must refuse to start"
            )

    def test_the_stack_comes_back_after_a_reboot(self, compose: dict) -> None:
        """A URL that dies on the first reboot has not been deployed."""
        for service in ("db", "app", "caddy"):
            assert compose["services"][service]["restart"] == "unless-stopped"

    def test_the_proxy_sends_hsts(self, deploy_dir: Path) -> None:
        """The session cookie is Secure; a downgrade to http logs the user out."""
        caddyfile = (deploy_dir / "Caddyfile").read_text()

        assert "Strict-Transport-Security" in caddyfile
        assert "reverse_proxy app:8000" in caddyfile

    def test_the_release_script_refuses_without_the_env_file(self, deploy_dir: Path) -> None:
        """Secrets are written on the host by a human, never by this repository."""
        script = deploy_dir / "deploy.sh"

        assert script.stat().st_mode & 0o111, "deploy.sh must be executable"
        assert "does not exist on" in script.read_text()


def test_the_gate_and_the_ci_workflow_run_the_same_commands() -> None:
    """AGENTS.md requires the workflow to mirror validation.commands, in order."""
    root = Path(__file__).resolve().parents[2]
    commands = json.loads((root / ".ai" / "agentic.config.json").read_text())["validation"][
        "commands"
    ]
    workflow = (root / ".github" / "workflows" / "validation-gate.yml").read_text()

    for command in commands:
        assert command in workflow, f"the CI workflow does not run: {command}"
