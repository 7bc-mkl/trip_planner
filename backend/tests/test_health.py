from fastapi.testclient import TestClient

from trip_planner.app import create_app


def test_health_answers_ok() -> None:
    with TestClient(create_app(check_configuration=False)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_mounted_under_the_version_prefix() -> None:
    """The version prefix is a contract (spec A13), not a formatting detail."""
    with TestClient(create_app(check_configuration=False)) as client:
        assert client.get("/health").status_code == 404
