"""The provider-neutral contract: what is asked, what comes back, and what it costs.

**This module is where the owner's mail meets a third party**, so almost all of
it is about limiting what that means. The adapters below it do one thing each —
translate a request into their provider's HTTP shape and a response back out —
and every decision that could widen the egress lives here instead, in one place
the owner can read:

- **what leaves** — `RoutingRequest.payload()` builds the whole body, and it is
  bounded text plus three headers plus the candidate trips' id, title,
  destinations and date range. Nothing else can be added by an adapter, because
  an adapter is handed the finished payload rather than the message.
- **what may come back** — `RoutingProposal` is a Pydantic model with
  `extra="forbid"`, so an unknown field is a rejection rather than something
  that gets stored. There are no tools, no function calls and no prose: a
  message instructing the model to do something can produce, at most, a trip id
  that fails the candidate check below.
- **which trip it may name** — `parse_proposal` takes the candidate ids and
  refuses anything outside them. "Route this to the trip you are not allowed to
  see" is not expressible, which is the architectural half of this feature's
  prompt-injection answer.
- **how often, and how much** — one timeout, a bounded retry on transient
  failures only, and a budget that **fails closed**.

## The budget fails closed, and that is the interesting part

The spec requires a maximum spend per billing month *"measured from
provider-reported usage and the selected model's configured price schedule;
when usage or price is unavailable, stop model calls rather than treating cost
as zero."*

So an unpriced deployment is not an unlimited one — it makes no calls at all.
That reads severe until the alternative is written down: the other option is an
application that bills the owner an unknown amount because somebody did not
finish the configuration. Of the two ways to be wrong, a feature that visibly
does nothing is strictly recoverable and a surprise invoice is not.

## Why a transport seam

`ModelClient` talks to an adapter, and an adapter talks to a `Transport`. The
suite substitutes a transport that captures the request body and returns a
canned response, which is how the spec's requirement — *"No real network call in
the suite"* — is met while still exercising each adapter's real translation
code. A mock of the adapter itself would test nothing: the translation is the
only thing an adapter has.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from trip_planner.config import ModelSettings
from trip_planner.domain.routing import TripWindow

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_PROMPT_CHARS",
    "MAX_RESPONSE_BYTES",
    "ModelAdapter",
    "ModelBudget",
    "ModelCallFailed",
    "ModelClient",
    "ModelRefused",
    "RoutingProposal",
    "RoutingRequest",
    "Transport",
    "Usage",
    "build_adapter",
    "parse_proposal",
]

#: How much message text is ever sent.
#:
#: The stored body may be up to 200 000 characters; this is what *leaves*, and
#: the two numbers are deliberately different. A confirmation states its dates
#: in the first page — the four real ones ran 5 800 to 22 700 characters, all of
#: it useful — and anything past this is a quoted thread or a marketing footer.
#: Sending less is both cheaper and a smaller disclosure.
MAX_PROMPT_CHARS = 24_000

#: The cap on a provider's response body. The contract's answer is a few dozen
#: bytes of JSON; a megabyte of anything is a provider malfunction, and reading
#: it into memory is the application's problem rather than theirs.
MAX_RESPONSE_BYTES = 64 * 1024

#: One attempt, then two retries, on *transient* failures only.
MAX_ATTEMPTS = 3

#: How long one call may take. Generous for a small model on a short prompt, and
#: short enough that the ingestion loop's thread is never held for long.
TIMEOUT_SECONDS = 30.0

#: Pause between retries. Fixed rather than exponential: with two retries the
#: difference is academic, and a constant is one fewer thing to reason about
#: when reading a worker's timing in a log.
RETRY_PAUSE_SECONDS = 2.0


class ModelCallFailed(RuntimeError):
    """A transient failure — a timeout, a 5xx, a 429, an unreadable body.

    Retryable by its nature. The worker counts it against the message's attempt
    cap and the message stays where it is, which is how a dead provider degrades
    to a queue to clear by hand rather than to a broken page.
    """


class ModelRefused(RuntimeError):
    """The call succeeded and the answer is unusable — and that is not retryable.

    Malformed JSON, an unknown field, a trip id outside the candidate set. Trying
    again would send the owner's mail a second time to get the same answer, so it
    counts as a decided failure: the message goes to the unrouted queue, where
    placing it by hand takes two clicks.
    """


@dataclass(frozen=True, slots=True)
class Usage:
    """What the provider reported it charged for.

    `None` is a real answer and is handled as such: a provider that reports no
    usage leaves the budget uncomputable, and `ModelBudget` then stops calls
    rather than guessing.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def is_known(self) -> bool:
        return self.input_tokens is not None and self.output_tokens is not None


@dataclass(frozen=True, slots=True)
class ModelBudget:
    """The monthly spend cap, and whether another call is permitted at all.

    Pure arithmetic over values the caller supplies — the worker reads the
    month's spend out of `inbound_model_egress` and passes it in. Keeping the
    database out of here is what lets every budget rule be tested without one.
    """

    monthly_limit: Decimal | None
    spent_this_month: Decimal
    input_price_per_mtok: Decimal | None
    output_price_per_mtok: Decimal | None

    @classmethod
    def unpriced(cls) -> ModelBudget:
        """A deployment that configured no price schedule. Permits nothing."""
        return cls(None, Decimal(0), None, None)

    @property
    def is_priced(self) -> bool:
        return (
            self.monthly_limit is not None
            and self.input_price_per_mtok is not None
            and self.output_price_per_mtok is not None
        )

    def permits_a_call(self) -> bool:
        """Whether another call may be made **before** making it.

        Checked ahead rather than after, because the point of a budget is to not
        spend the money. An unpriced deployment answers `False` — see the module
        docstring for why that is the safe direction.
        """
        if not self.is_priced:
            return False
        assert self.monthly_limit is not None
        return self.spent_this_month < self.monthly_limit

    def cost_of(self, usage: Usage) -> Decimal | None:
        """What one call cost, or `None` when the provider reported no usage."""
        if not usage.is_known or not self.is_priced:
            return None
        assert usage.input_tokens is not None and usage.output_tokens is not None
        assert self.input_price_per_mtok is not None
        assert self.output_price_per_mtok is not None

        million = Decimal(1_000_000)
        return (
            Decimal(usage.input_tokens) * self.input_price_per_mtok / million
            + Decimal(usage.output_tokens) * self.output_price_per_mtok / million
        )


class RoutingProposal(BaseModel):
    """The entire Phase 2 response: one trip id, or nothing.

    `extra="forbid"` is the load-bearing line. A provider that returns extra
    keys — or a message that talks one into returning them — produces a
    validation error rather than a value anything stores. Phase 3 widens this
    with a sparse `fields` object; it does not widen what a provider may *do*,
    which stays "return data that this model accepts".
    """

    model_config = ConfigDict(extra="forbid")

    trip_id: str | None = None


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    """One routing question, and the only shape in which it may be asked.

    The adapters never see the message or the trips — they are handed
    `payload()`'s output. That is deliberate: it means no adapter *can* send a
    field this class did not put there, so reviewing what leaves the deployment
    is reviewing one method rather than three HTTP clients.
    """

    text: str
    from_address: str
    subject: str
    sent_at: str
    candidates: tuple[TripWindow, ...]

    def payload(self) -> dict[str, object]:
        """Exactly what leaves, and nothing more (D24).

        Message text bounded to `MAX_PROMPT_CHARS`, three headers, and each
        candidate's id, title, destinations and date range. No items, no notes,
        no confirmation numbers, no costs, no attachments — and never a trip
        that is not a candidate.
        """
        return {
            "message": {
                "text": self.text[:MAX_PROMPT_CHARS],
                "from": self.from_address,
                "subject": self.subject,
                "date": self.sent_at,
            },
            "candidate_trips": [
                {
                    "id": trip.id,
                    "title": trip.title,
                    "destinations": list(trip.destinations),
                    "start_date": trip.start_date.isoformat(),
                    "end_date": trip.end_date.isoformat(),
                }
                for trip in self.candidates
            ],
        }

    def candidate_ids(self) -> frozenset[str]:
        return frozenset(trip.id for trip in self.candidates)


#: The instruction every provider is given, verbatim.
#:
#: Shared rather than per-adapter so that "the three adapters answer the same
#: question" is a fact about one constant instead of a claim about three files
#: that drifted. It says what to return and nothing about how to behave,
#: because wording is not a security control — the candidate check and the
#: rejecting reader are (see the module docstring).
PROMPT = """\
You are given one forwarded travel confirmation and a list of candidate trips.

Return ONLY a JSON object of the form {"trip_id": "<id>"} naming the single \
candidate trip the confirmation belongs to, or {"trip_id": null} if none of \
them fits.

The id MUST be copied exactly from the candidate list. Do not invent an id, do \
not explain, do not return any other key.
"""


class Transport(Protocol):
    """One JSON POST. The seam the suite replaces so no test touches a network."""

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
        timeout: float,
    ) -> tuple[int, bytes]: ...


class UrllibTransport:
    """The real one. `urllib`, so this costs no dependency.

    Bounded like every other fetch in this feature: a timeout, and a read capped
    at `MAX_RESPONSE_BYTES` rather than whatever the far end decides to send.
    """

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
        timeout: float,
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return int(response.status), response.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            # An HTTP error is still an answer, and its status decides whether
            # the caller retries. Reading the body is bounded like any other.
            return int(error.code), error.read(MAX_RESPONSE_BYTES)


class ModelAdapter(Protocol):
    """What one provider knows how to do, and the whole of it.

    Three methods, none of which may make a decision: where to post, how to
    shape the request, and how to find the text in the response. Everything
    else — the prompt, the limits, the retries, the budget, the validation —
    belongs to `ModelClient`.
    """

    provider: str

    def endpoint(self, settings: ModelSettings) -> str: ...

    def headers(self, settings: ModelSettings) -> dict[str, str]: ...

    def request_body(self, settings: ModelSettings, prompt: str) -> dict[str, object]: ...

    def read_response(self, body: dict[str, object]) -> tuple[str, Usage]: ...


def build_adapter(settings: ModelSettings) -> ModelAdapter:
    """The one adapter this deployment uses. **No fallback, ever.**

    A fallback would silently widen the decision the owner made: he authorised
    one named service to see his mail, not whichever happens to be up. Import is
    local so that selecting Anthropic does not import Google's module, and an
    unknown provider cannot reach here — `config.resolve_model_settings`
    refuses it at startup — but it raises rather than defaulting if one ever did.
    """
    from trip_planner.integrations import anthropic, gemini, openai

    adapters: dict[str, ModelAdapter] = {
        anthropic.ADAPTER.provider: anthropic.ADAPTER,
        gemini.ADAPTER.provider: gemini.ADAPTER,
        openai.ADAPTER.provider: openai.ADAPTER,
    }
    try:
        return adapters[settings.provider]
    except KeyError as error:  # pragma: no cover - config refuses this first
        raise ValueError(f"no adapter for provider {settings.provider!r}") from error


def parse_proposal(raw: str, *, candidate_ids: frozenset[str]) -> RoutingProposal:
    """The model's text, validated into a proposal — or refused.

    Four ways to be refused, and all four are `ModelRefused` rather than
    retryable: the answer arrived, it is simply not usable, and asking again
    would send the owner's mail a second time for the same result.

    The candidate check is the important one. A trip id the model invented —
    or was talked into by text inside the message — is rejected here, before
    anything stores it, which is why a perfect injection's blast radius is a
    message in the unrouted queue.
    """
    text = _strip_code_fence(raw.strip())

    try:
        parsed = json.loads(text)
    except ValueError as error:
        raise ModelRefused("the model did not return JSON") from error

    if not isinstance(parsed, dict):
        raise ModelRefused("the model returned JSON that is not an object")

    try:
        proposal = RoutingProposal.model_validate(parsed)
    except ValidationError as error:
        raise ModelRefused("the model returned fields the contract does not define") from error

    if proposal.trip_id is not None and proposal.trip_id not in candidate_ids:
        raise ModelRefused("the model named a trip that was not a candidate")

    return proposal


def _strip_code_fence(text: str) -> str:
    """Unwrap ```json … ``` when a provider adds it.

    Tolerated rather than refused because it is a presentation habit, not a
    contract violation — the JSON inside is exactly right, and failing the
    message over three backticks would send the owner to the unrouted queue for
    a formatting flourish. Anything *else* around the JSON still fails.
    """
    if not text.startswith("```"):
        return text
    body = text[3:]
    if body.lower().startswith("json"):
        body = body[4:]
    return body.rsplit("```", 1)[0].strip() if "```" in body else body.strip()


@dataclass(slots=True)
class ModelClient:
    """Asks one provider one question, under every limit this feature has.

    The order is the control: budget first — so a deployment over its cap sends
    nothing rather than sending and then noticing — then the call, then the
    validation.
    """

    settings: ModelSettings
    adapter: ModelAdapter
    transport: Transport
    timeout: float = TIMEOUT_SECONDS
    max_attempts: int = MAX_ATTEMPTS
    retry_pause: float = RETRY_PAUSE_SECONDS

    @classmethod
    def for_settings(
        cls, settings: ModelSettings, *, transport: Transport | None = None
    ) -> ModelClient:
        return cls(
            settings=settings,
            adapter=build_adapter(settings),
            transport=transport if transport is not None else UrllibTransport(),
        )

    def route(
        self, request: RoutingRequest, *, budget: ModelBudget
    ) -> tuple[RoutingProposal, Usage]:
        """Ask which candidate the message belongs to.

        Raises `ModelCallFailed` for anything a retry might fix and
        `ModelRefused` for anything it would not. The caller — the ingestion
        worker — is what turns those into `attempts` and the unrouted queue.
        """
        if not budget.permits_a_call():
            raise ModelCallFailed(
                "the monthly model budget is exhausted or no price schedule is configured"
            )

        prompt = f"{PROMPT}\n{json.dumps(request.payload(), ensure_ascii=False)}"
        raw, usage = self._call(prompt)
        return parse_proposal(raw, candidate_ids=request.candidate_ids()), usage

    def _call(self, prompt: str) -> tuple[str, Usage]:
        """One call, retried only on failures a retry could fix."""
        last: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._attempt(prompt)
            except ModelCallFailed as error:
                last = error
                # Logged as the provider and the attempt, never the body: a
                # provider's error prose can echo the message's own content back
                # into our logs, which is the one place it has no business being.
                logger.warning(
                    "inbox: model call failed (%s, attempt %d/%d)",
                    self.settings.provider,
                    attempt,
                    self.max_attempts,
                )
                if attempt < self.max_attempts:
                    time.sleep(self.retry_pause)

        raise ModelCallFailed("the model could not be reached") from last

    def _attempt(self, prompt: str) -> tuple[str, Usage]:
        try:
            status, body = self.transport.post_json(
                self.adapter.endpoint(self.settings),
                headers=self.adapter.headers(self.settings),
                body=self.adapter.request_body(self.settings, prompt),
                timeout=self.timeout,
            )
        except Exception as error:
            # Timeouts, DNS, TLS, a socket closing. All transient by nature.
            raise ModelCallFailed("the model could not be reached") from error

        if status == 429 or status >= 500:
            raise ModelCallFailed(f"the provider answered {status}")
        if status >= 400:
            # 400, 401, 403 — a bad request, a bad key, a model this account
            # cannot use. Retrying sends the owner's mail again for the same
            # answer, so this is decided rather than transient.
            raise ModelRefused(f"the provider refused the request with {status}")

        try:
            decoded = json.loads(body)
        except ValueError as error:
            raise ModelCallFailed("the provider's response was not JSON") from error

        if not isinstance(decoded, dict):
            raise ModelCallFailed("the provider's response was not a JSON object")

        try:
            return self.adapter.read_response(decoded)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ModelCallFailed("the provider's response had an unexpected shape") from error


def iso_or_empty(value: date | None) -> str:
    """A date as the payload spells it. Separate so the format is stated once."""
    return value.isoformat() if value is not None else ""


def candidates_from(trips: Sequence[TripWindow]) -> tuple[TripWindow, ...]:
    """A defensive copy, so a caller's list cannot change under a request."""
    return tuple(trips)
