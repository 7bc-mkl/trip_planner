"""The Anthropic adapter: one endpoint, one request shape, one place to read.

Everything this module does not do is the point — no prompt, no retry, no
budget, no validation. Those belong to `model.py` and are identical for all
three providers, which is what keeps "switch provider" a configuration change.
"""

from __future__ import annotations

from typing import Any

from trip_planner.config import ModelSettings
from trip_planner.integrations.model import Usage

__all__ = ["ADAPTER", "AnthropicAdapter"]

#: The provider's own host, used when no base URL is configured. Overriding it
#: is how a deployment reaches a regional endpoint or a gateway without a code
#: change — see `INBOX_MODEL_BASE_URL`.
DEFAULT_BASE_URL = "https://api.anthropic.com"

#: Pinned, because the wire format is versioned and a silent upgrade is a
#: silent change to what this application sends and receives.
API_VERSION = "2023-06-01"

#: The answer is a few dozen bytes of JSON. Capping output is both a cost
#: control and a way of making a runaway response impossible rather than merely
#: unlikely.
MAX_OUTPUT_TOKENS = 256


class AnthropicAdapter:
    """Messages API. Translation only."""

    provider = "anthropic"

    #: What this provider can be sent as a document, for Phase 4's explicit
    #: `read-document` action. Declared per adapter because they differ, and the
    #: spec requires an unsupported combination to be refused *before* egress.
    supported_document_types = ("application/pdf", "image/jpeg", "image/png")

    def endpoint(self, settings: ModelSettings) -> str:
        base = (settings.base_url or DEFAULT_BASE_URL).rstrip("/")
        return f"{base}/v1/messages"

    def headers(self, settings: ModelSettings) -> dict[str, str]:
        return {
            "x-api-key": settings.api_key,
            "anthropic-version": API_VERSION,
        }

    def request_body(self, settings: ModelSettings, prompt: str) -> dict[str, object]:
        return {
            "model": settings.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            # No tools, no system prompt beyond the shared instruction, and one
            # user turn. The contract is "return data"; anything that let the
            # provider *act* would be a different product decision.
            "messages": [{"role": "user", "content": prompt}],
        }

    def read_response(self, body: dict[str, Any]) -> tuple[str, Usage]:
        blocks = body["content"]
        text = "".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        )
        usage = body.get("usage") or {}
        return text, Usage(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )


ADAPTER = AnthropicAdapter()
