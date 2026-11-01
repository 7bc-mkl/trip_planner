"""The OpenAI adapter: one endpoint, one request shape, one place to read.

See `anthropic.py` — the three are deliberately the same size and shape, and
the parametrized contract tests run the same cases against all of them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, StrictInt

from trip_planner.config import ModelSettings
from trip_planner.integrations.model import Usage

__all__ = ["ADAPTER", "OpenAIAdapter"]

DEFAULT_BASE_URL = "https://api.openai.com"

MAX_OUTPUT_TOKENS = 256


class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message


class _Usage(BaseModel):
    prompt_tokens: StrictInt | None = Field(default=None, ge=0)
    completion_tokens: StrictInt | None = Field(default=None, ge=0)


class _Response(BaseModel):
    choices: list[_Choice]
    usage: _Usage | None = None


class OpenAIAdapter:
    """Chat Completions. Translation only."""

    provider = "openai"

    supported_document_types = ("application/pdf", "image/jpeg", "image/png")

    def endpoint(self, settings: ModelSettings) -> str:
        base = (settings.base_url or DEFAULT_BASE_URL).rstrip("/")
        return f"{base}/v1/chat/completions"

    def headers(self, settings: ModelSettings) -> dict[str, str]:
        return {"authorization": f"Bearer {settings.api_key}"}

    def request_body(self, settings: ModelSettings, prompt: str) -> dict[str, object]:
        return {
            "model": settings.model,
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
            # JSON mode is an *aid*: the rejecting Pydantic reader in `model.py`
            # is authoritative for all three providers, so the contract does not
            # depend on any one of them honouring a schema hint.
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }

    def read_response(self, body: dict[str, object]) -> tuple[str, Usage]:
        response = _Response.model_validate(body)
        usage = response.usage or _Usage()
        return response.choices[0].message.content or "", Usage(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )


ADAPTER = OpenAIAdapter()
