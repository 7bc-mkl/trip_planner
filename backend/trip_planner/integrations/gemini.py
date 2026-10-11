"""The Google Gemini adapter: one endpoint, one request shape, one place to read.

See `anthropic.py`. This one differs in a way worth naming: the model name is
part of the **URL** rather than the body, and the key goes in a header rather
than a bearer token. That is exactly the sort of per-provider detail this
package exists to keep out of everything else.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from trip_planner.config import ModelSettings
from trip_planner.integrations.model import Usage

__all__ = ["ADAPTER", "GeminiAdapter"]

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"

MAX_OUTPUT_TOKENS = 256


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

    def read_response(self, body: dict[str, Any]) -> tuple[str, Usage]:
        parts = body["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts)
        usage = body.get("usageMetadata") or {}
        return text, Usage(
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
        )


ADAPTER = GeminiAdapter()
