"""The model boundary: one contract, three providers, and no network anywhere.

**Every test here runs the real adapter code.** What is substituted is the
`Transport` — one method that would do an HTTP POST — so each provider's actual
translation of a request and a response is exercised, while nothing leaves the
machine. Mocking the adapter instead would test nothing: translation is the only
thing an adapter has.

The parametrized cases run identically against all three on purpose. "The three
adapters answer the same question" is the claim that makes D24's promise true —
switching provider is a configuration change — and a claim like that is worth a
test that fails when it stops holding.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from trip_planner.config import ModelSettings
from trip_planner.domain.routing import TripWindow
from trip_planner.integrations.model import (
    MAX_PROMPT_CHARS,
    ModelBudget,
    ModelCallFailed,
    ModelClient,
    ModelRefused,
    RoutingRequest,
    Usage,
    build_adapter,
    parse_proposal,
)

PROVIDERS = ["anthropic", "gemini", "openai"]

BORNEO = TripWindow(
    id="trip-borneo",
    title="Malezja / Borneo",
    start_date=date(2026, 10, 2),
    end_date=date(2026, 10, 25),
    destinations=("Kuala Lumpur", "Kota Kinabalu"),
)
JUNE = TripWindow(
    id="trip-june",
    title="Czerwcowy wyjazd",
    start_date=date(2026, 6, 13),
    end_date=date(2026, 6, 18),
)


def settings_for(provider: str, **overrides: Any) -> ModelSettings:
    fields: dict[str, Any] = {
        "provider": provider,
        "model": "small-1",
        "api_key": "test-key-not-a-real-credential",
        "base_url": None,
        "monthly_budget": Decimal("10"),
        "input_price_per_mtok": Decimal("1"),
        "output_price_per_mtok": Decimal("5"),
    }
    fields.update(overrides)
    return ModelSettings(**fields)


def request_for(*candidates: TripWindow) -> RoutingRequest:
    return RoutingRequest(
        text="PNR: SX-9912L\nKuala Lumpur 17 October 2026",
        from_address="rezerwacje@airline.example",
        subject="Potwierdzenie rezerwacji",
        sent_at="2026-10-10T10:38:58+02:00",
        candidates=candidates or (BORNEO,),
    )


def budget(**overrides: Any) -> ModelBudget:
    fields: dict[str, Any] = {
        "monthly_limit": Decimal("10"),
        "spent_this_month": Decimal("0"),
        "input_price_per_mtok": Decimal("1"),
        "output_price_per_mtok": Decimal("5"),
    }
    fields.update(overrides)
    return ModelBudget(**fields)


class CapturingTransport:
    """Records every call and replays a scripted answer. No sockets involved."""

    def __init__(self, status: int = 200, body: Any = None) -> None:
        self.status = status
        self.body = body
        self.calls: list[dict[str, Any]] = []
        self.raise_with: Exception | None = None

    def post_json(
        self, url: str, *, headers: dict[str, str], body: dict[str, object], timeout: float
    ) -> tuple[int, bytes]:
        self.calls.append(
            {"url": url, "headers": headers, "body": body, "timeout": timeout}
        )
        if self.raise_with is not None:
            raise self.raise_with
        return self.status, json.dumps(self.body).encode("utf-8")


def answer(provider: str, text: str, *, tokens: tuple[int, int] = (120, 8)) -> Any:
    """A provider's own success envelope around `text`.

    Hand-built per provider because the whole point of an adapter is that these
    three shapes differ, and a shared fake would quietly stop testing that.
    """
    prompt_tokens, output_tokens = tokens
    if provider == "anthropic":
        return {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": prompt_tokens, "output_tokens": output_tokens},
        }
    if provider == "openai":
        return {
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": output_tokens},
        }
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": output_tokens,
        },
    }


def client_for(provider: str, transport: CapturingTransport, **overrides: Any) -> ModelClient:
    settings = settings_for(provider, **overrides)
    return ModelClient(
        settings=settings,
        adapter=build_adapter(settings),
        transport=transport,
        retry_pause=0,
    )


# --------------------------------------------------------------------------- #
# The happy path, identically for all three
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_valid_answer_is_parsed_the_same_way_whichever_provider_gave_it(
    provider: str,
) -> None:
    transport = CapturingTransport(200, answer(provider, '{"trip_id": "trip-borneo"}'))

    proposal, usage = client_for(provider, transport).route(request_for(), budget=budget())

    assert proposal.trip_id == "trip-borneo"
    assert usage == Usage(input_tokens=120, output_tokens=8)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_no_matching_trip_is_a_valid_answer(provider: str) -> None:
    """`{"trip_id": null}` is the model saying none of these — not a failure."""
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    proposal, _ = client_for(provider, transport).route(request_for(), budget=budget())

    assert proposal.trip_id is None


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_fenced_answer_is_tolerated(provider: str) -> None:
    """```json … ``` is a presentation habit, not a contract violation.

    Failing the message over three backticks would send the owner to the
    unrouted queue for a formatting flourish.
    """
    fenced = '```json\n{"trip_id": "trip-borneo"}\n```'
    transport = CapturingTransport(200, answer(provider, fenced))

    proposal, _ = client_for(provider, transport).route(request_for(), budget=budget())

    assert proposal.trip_id == "trip-borneo"


# --------------------------------------------------------------------------- #
# What leaves the deployment — the payload assertions D24 asks for
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_request_carries_only_the_text_three_headers_and_the_candidates(
    provider: str,
) -> None:
    """Asserted against the **captured request body**, not against intent.

    This is the test that says what the owner's mail is exposed to. The payload
    is built in one method on `RoutingRequest`; the adapters are handed the
    finished thing, which is why reviewing egress is reviewing one function.
    """
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    client_for(provider, transport).route(request_for(BORNEO, JUNE), budget=budget())

    sent = json.dumps(transport.calls[0]["body"])

    assert "PNR: SX-9912L" in sent
    assert "rezerwacje@airline.example" in sent
    assert "Potwierdzenie rezerwacji" in sent
    assert "2026-10-10T10:38:58+02:00" in sent
    for trip in (BORNEO, JUNE):
        assert trip.id in sent
        assert trip.title in sent
        assert trip.start_date.isoformat() in sent


def test_the_payload_shape_is_exactly_what_d24_permits() -> None:
    """Checked structurally rather than by substring, on the one builder."""
    payload = request_for(BORNEO).payload()

    assert set(payload) == {"message", "candidate_trips"}
    assert set(payload["message"]) == {"text", "from", "subject", "date"}  # type: ignore[arg-type]
    assert set(payload["candidate_trips"][0]) == {  # type: ignore[index]
        "id",
        "title",
        "destinations",
        "start_date",
        "end_date",
    }


@pytest.mark.parametrize("provider", PROVIDERS)
def test_no_attachment_byte_is_ever_sent_in_this_phase(provider: str) -> None:
    """Phase 2 sends text. Documents leave only through Phase 4's explicit action.

    Asserted on the captured body because that is the only place the claim can
    actually be checked — the payload builder has no attachment parameter, and
    this proves no adapter adds one.
    """
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    client_for(provider, transport).route(request_for(), budget=budget())

    sent = json.dumps(transport.calls[0]["body"]).lower()
    for marker in ("attachment", "base64", "application/pdf", "document", "image/"):
        assert marker not in sent, marker


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_long_message_is_truncated_before_it_leaves(provider: str) -> None:
    """Sending less is both cheaper and a smaller disclosure."""
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))
    request = RoutingRequest(
        text="x" * (MAX_PROMPT_CHARS + 5_000),
        from_address="a@b.example",
        subject="s",
        sent_at="2026-10-10T00:00:00+00:00",
        candidates=(BORNEO,),
    )

    client_for(provider, transport).route(request, budget=budget())

    assert len(request.payload()["message"]["text"]) == MAX_PROMPT_CHARS  # type: ignore[index]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_credential_goes_in_a_header_and_never_in_the_body(provider: str) -> None:
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    client_for(provider, transport).route(request_for(), budget=budget())

    call = transport.calls[0]
    assert "test-key-not-a-real-credential" in json.dumps(call["headers"])
    assert "test-key-not-a-real-credential" not in json.dumps(call["body"])


# --------------------------------------------------------------------------- #
# The candidate fence — the architectural half of the injection answer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_trip_outside_the_candidate_set_is_refused(provider: str) -> None:
    """"Route this to the trip you are not allowed to see" is inexpressible.

    The id is checked against the candidates that were sent, so a model that
    invents one — or is talked into one by text inside the message — produces a
    refusal rather than a proposal.
    """
    transport = CapturingTransport(200, answer(provider, '{"trip_id": "trip-somebody-elses"}'))

    with pytest.raises(ModelRefused, match="not a candidate"):
        client_for(provider, transport).route(request_for(BORNEO), budget=budget())


def test_the_candidate_fence_is_checked_against_what_was_actually_offered() -> None:
    with pytest.raises(ModelRefused):
        parse_proposal('{"trip_id": "trip-june"}', candidate_ids=frozenset({"trip-borneo"}))

    assert parse_proposal(
        '{"trip_id": "trip-june"}', candidate_ids=frozenset({"trip-borneo", "trip-june"})
    ).trip_id == "trip-june"


# --------------------------------------------------------------------------- #
# Bad answers, and which of them are worth retrying
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider", PROVIDERS)
def test_malformed_json_is_refused_rather_than_retried(provider: str) -> None:
    """The call succeeded; the answer is unusable. Asking again sends the
    owner's mail a second time for the same result."""
    transport = CapturingTransport(200, answer(provider, "I think it is the Borneo trip!"))

    with pytest.raises(ModelRefused):
        client_for(provider, transport).route(request_for(), budget=budget())

    assert len(transport.calls) == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_unknown_field_is_refused(provider: str) -> None:
    """`extra="forbid"` is the load-bearing line: an unknown key is a rejection,
    not something that quietly gets stored."""
    transport = CapturingTransport(
        200, answer(provider, '{"trip_id": "trip-borneo", "confidence": 0.9}')
    )

    with pytest.raises(ModelRefused):
        client_for(provider, transport).route(request_for(), budget=budget())


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_timeout_is_retried_then_gives_up_as_transient(provider: str) -> None:
    transport = CapturingTransport()
    transport.raise_with = TimeoutError("the provider did not answer")

    with pytest.raises(ModelCallFailed):
        client_for(provider, transport).route(request_for(), budget=budget())

    assert len(transport.calls) == 3


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_429_is_retried(provider: str) -> None:
    """Rate limiting is the definition of worth-trying-again."""
    transport = CapturingTransport(429, {"error": "slow down"})

    with pytest.raises(ModelCallFailed):
        client_for(provider, transport).route(request_for(), budget=budget())

    assert len(transport.calls) == 3


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_server_error_is_retried(provider: str) -> None:
    transport = CapturingTransport(503, {"error": "unavailable"})

    with pytest.raises(ModelCallFailed):
        client_for(provider, transport).route(request_for(), budget=budget())

    assert len(transport.calls) == 3


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("status", [400, 401, 403])
def test_a_client_error_is_decided_rather_than_retried(provider: str, status: int) -> None:
    """A bad key or a model this account cannot use will answer the same way
    three times. Retrying only resends the owner's mail."""
    transport = CapturingTransport(status, {"error": "nope"})

    with pytest.raises(ModelRefused):
        client_for(provider, transport).route(request_for(), budget=budget())

    assert len(transport.calls) == 1


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_transient_failure_followed_by_success_succeeds(provider: str) -> None:
    """The retry has to actually work, not merely be counted."""

    class FlakyTransport(CapturingTransport):
        def post_json(self, url, *, headers, body, timeout):  # type: ignore[no-untyped-def]
            super().post_json(url, headers=headers, body=body, timeout=timeout)
            if len(self.calls) == 1:
                raise TimeoutError("first attempt")
            return 200, json.dumps(answer(provider, '{"trip_id": "trip-borneo"}')).encode()

    transport = FlakyTransport()
    proposal, _ = client_for(provider, transport).route(request_for(), budget=budget())

    assert proposal.trip_id == "trip-borneo"
    assert len(transport.calls) == 2


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_response_of_the_wrong_shape_is_transient(provider: str) -> None:
    """A provider malfunction, not a decided answer — worth one more try."""
    transport = CapturingTransport(200, {"unexpected": "envelope"})

    with pytest.raises(ModelCallFailed):
        client_for(provider, transport).route(request_for(), budget=budget())


# --------------------------------------------------------------------------- #
# The budget, which fails closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_exhausted_budget_sends_nothing_at_all(provider: str) -> None:
    """Checked **before** the call, because the point of a budget is to not
    spend the money."""
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    with pytest.raises(ModelCallFailed, match="budget"):
        client_for(provider, transport).route(
            request_for(), budget=budget(spent_this_month=Decimal("10"))
        )

    assert transport.calls == []


@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_unpriced_deployment_sends_nothing(provider: str) -> None:
    """*"When usage or price is unavailable, stop model calls rather than
    treating cost as zero."*

    An unpriced deployment is not an unlimited one. Of the two ways to be
    wrong, a feature that visibly does nothing is recoverable and a surprise
    invoice is not.
    """
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    with pytest.raises(ModelCallFailed):
        client_for(provider, transport).route(request_for(), budget=ModelBudget.unpriced())

    assert transport.calls == []


def test_the_cost_of_a_call_is_computed_from_reported_usage() -> None:
    cost = budget().cost_of(Usage(input_tokens=1_000_000, output_tokens=200_000))

    assert cost == Decimal("1") + Decimal("1")


def test_a_call_whose_usage_the_provider_did_not_report_has_no_computable_cost() -> None:
    """Which is why such a deployment stops: an unknown cost is not a zero cost."""
    assert budget().cost_of(Usage(input_tokens=None, output_tokens=None)) is None


def test_money_is_decimal_rather_than_float() -> None:
    """The shipped `item.cost_amount` rule: money that is almost right is wrong."""
    cost = budget(
        input_price_per_mtok=Decimal("0.10"), output_price_per_mtok=Decimal("0.20")
    ).cost_of(Usage(input_tokens=100_000, output_tokens=100_000))

    assert cost == Decimal("0.03")


# --------------------------------------------------------------------------- #
# Selection — exactly one provider, no fallback
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_selected_adapter_is_the_one_that_is_called(provider: str) -> None:
    """And the endpoint it posts to is that provider's, not another's."""
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    client_for(provider, transport).route(request_for(), budget=budget())

    hosts = {
        "anthropic": "api.anthropic.com",
        "openai": "api.openai.com",
        "gemini": "generativelanguage.googleapis.com",
    }
    url = transport.calls[0]["url"]

    assert hosts[provider] in url
    for other, host in hosts.items():
        if other != provider:
            assert host not in url


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_configured_base_url_replaces_the_providers_host(provider: str) -> None:
    """The EU-residency knob. Residency must be a configuration change rather
    than a code change, which is the whole reason this setting exists."""
    transport = CapturingTransport(200, answer(provider, '{"trip_id": null}'))

    client_for(provider, transport, base_url="https://eu.gateway.example").route(
        request_for(), budget=budget()
    )

    assert transport.calls[0]["url"].startswith("https://eu.gateway.example/")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_adapter_declares_the_documents_it_can_be_sent(provider: str) -> None:
    """Phase 4 refuses an unsupported type **before** egress, so each adapter has
    to say what it accepts rather than finding out from a 400."""
    adapter = build_adapter(settings_for(provider))

    assert "application/pdf" in adapter.supported_document_types  # type: ignore[attr-defined]


def test_the_three_adapters_answer_the_same_question() -> None:
    """The claim that makes "switch provider" a configuration change.

    Same request, same scripted answer, three providers, one result.
    """
    results = []
    for provider in PROVIDERS:
        transport = CapturingTransport(200, answer(provider, '{"trip_id": "trip-borneo"}'))
        proposal, usage = client_for(provider, transport).route(request_for(), budget=budget())
        results.append((proposal.trip_id, usage))

    assert len(set(results)) == 1
