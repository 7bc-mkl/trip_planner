"""The Google Gemini adapter: one endpoint, one request shape, one place to read.

See `anthropic.py`. This one differs in a way worth naming: the model name is
part of the **URL** rather than the body, and the key goes in a header rather
than a bearer token. That is exactly the sort of per-provider detail this
package exists to keep out of everything else.
"""

from __future__ import annotations

from urllib.parse import quote

from pydantic import BaseModel, Field, StrictInt

from trip_planner.config import ModelSettings
from trip_planner.integrations.model import Usage

__all__ = ["ADAPTER", "GeminiAdapter"]

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"

MAX_OUTPUT_TOKENS = 256


class _Part(BaseModel):
    text: str = ""


class _Content(BaseModel):
    parts: list[_Part]


class _Candidate(BaseModel):
    content: _Content


class _Usage(BaseModel):
    promptTokenCount: StrictInt | None = Field(default=None, ge=0)
    candidatesTokenCount: StrictInt | None = Field(default=None, ge=0)
    thoughtsTokenCount: StrictInt = Field(default=0, ge=0)


class _Response(BaseModel):
    candidates: list[_Candidate]
    usageMetadata: _Usage | None = None


class GeminiAdapter:
    """generateContent. Translation only."""

    provider = "gemini"

    supported_document_types = ("application/pdf", "image/jpeg", "image/png")

    def endpoint(self, settings: ModelSettings) -> str:
        base = (settings.base_url or DEFAULT_BASE_URL).rstrip("/")
        # Percent-encoded: the model name is configuration, and configuration
        # does not get to build a URL path unescaped.
        return f"{base}/v1beta/models/{quote(settings.model, safe='')}:generateContent"

    def headers(self, settings: ModelSettings) -> dict[str, str]:
        return {"x-goog-api-key": settings.api_key}

    def request_body(self, settings: ModelSettings, prompt: str) -> dict[str, object]:
        return {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
            },
        }

    def read_response(self, body: dict[str, object]) -> tuple[str, Usage]:
        response = _Response.model_validate(body)
        usage = response.usageMetadata or _Usage()
        return "".join(part.text for part in response.candidates[0].content.parts), Usage(
            input_tokens=usage.promptTokenCount,
            output_tokens=(
                usage.candidatesTokenCount + usage.thoughtsTokenCount
                if usage.candidatesTokenCount is not None
                else None
            ),
        )


ADAPTER = GeminiAdapter()
