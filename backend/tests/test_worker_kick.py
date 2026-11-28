"""`WorkerKick`: the asynchronous wake-up of the worker function on the Lambda target.

A fake `boto3.client` stands in for AWS, so these tests pin what would be sent —
the function, the invocation type, the bounded client — without any network.
"""

from __future__ import annotations

from typing import Any

import boto3
import pytest

from trip_planner.inbound.ses import (
    KICK_CONNECT_TIMEOUT_SECONDS,
    KICK_PAYLOAD,
    KICK_READ_TIMEOUT_SECONDS,
    WorkerKick,
)


class _FakeLambda:
    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        self.invocations.append(kwargs)
        return {"StatusCode": 202}


@pytest.fixture
def clients(monkeypatch: pytest.MonkeyPatch) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    built: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    fake = _FakeLambda()

    def client(*args: Any, **kwargs: Any) -> _FakeLambda:
        built.append((args, kwargs | {"_fake": fake}))
        return fake

    monkeypatch.setattr(boto3, "client", client)
    return built


def lambda_kick() -> WorkerKick:
    return WorkerKick(mode="lambda", function_name="trip-planner-worker", region="eu-central-1")


def test_constructing_a_kick_builds_no_client(clients: list[Any]) -> None:
    lambda_kick()
    assert clients == []


def test_importing_the_modules_builds_no_client() -> None:
    """In a fresh interpreter, so a reload cannot disturb the classes other tests hold."""
    import subprocess
    import sys

    script = (
        "import boto3\n"
        "def boom(*a, **k): raise SystemExit('boto3.client called on import')\n"
        "boto3.client = boom\n"
        "import trip_planner.inbound.ses, trip_planner.api.inbox\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_a_kick_is_an_asynchronous_invoke_of_the_configured_function(
    clients: list[Any],
) -> None:
    kick = lambda_kick()
    kick.kick()

    assert len(clients) == 1
    (args, kwargs) = clients[0]
    assert args == ("lambda",)
    assert kwargs["region_name"] == "eu-central-1"
    assert kwargs["_fake"].invocations == [
        {
            "FunctionName": "trip-planner-worker",
            "InvocationType": "Event",
            "Payload": KICK_PAYLOAD,
        }
    ]


def test_the_client_is_bounded_by_timeouts_and_limited_retries(clients: list[Any]) -> None:
    lambda_kick().kick()

    config = clients[0][1]["config"]
    assert config.connect_timeout == KICK_CONNECT_TIMEOUT_SECONDS
    assert config.read_timeout == KICK_READ_TIMEOUT_SECONDS
    assert config.retries["max_attempts"] <= 2


def test_the_client_is_built_once_and_reused(clients: list[Any]) -> None:
    kick = lambda_kick()
    kick.kick()
    kick.kick()

    assert len(clients) == 1
    assert len(clients[0][1]["_fake"].invocations) == 2


def test_in_thread_mode_a_kick_does_nothing(clients: list[Any]) -> None:
    kick = WorkerKick(mode="thread", function_name=None, region="eu-central-1")
    kick.kick()

    assert clients == []


def test_a_failing_invoke_raises_for_the_caller_to_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Broken:
        def invoke(self, **_: Any) -> None:
            raise RuntimeError("throttled")

    monkeypatch.setattr(boto3, "client", lambda *a, **k: _Broken())
    with pytest.raises(RuntimeError):
        lambda_kick().kick()
