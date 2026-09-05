"""Error codes — the single source of both locales' error keys.

Errors on the wire are `{"error": {"code": "<stable_code>", "field": "<name|null>"}}`:
a stable machine-readable code, never a prose message. The SPA turns the code into
text through `error.<code>` in its locale files, which is what keeps a
backend-originated message translatable without the backend owning any copy.

`scripts/check_locales.py` checks that `en.json` and `pl.json` agree *with each
other*. It cannot check that a key the code needs actually exists — a forgotten
mapping would ship as a blank message in both languages and pass the gate green.
`tests/test_errors.py` is the missing half: every member below must resolve to a
non-empty value in both files.

Members are added alongside the endpoints that raise them. The trip-related codes
the spec names (`stages_required`, `invalid_time_span`, `days_have_items`, …)
arrive with the trip endpoints in Phases 2 to 4 — adding them now would mean
locale entries for conditions nothing can produce.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import HTTPException, status


class ErrorCode(StrEnum):
    """Stable, machine-readable error codes. The value is the wire format.

    Changing a member's value, or the condition it names, is a breaking change
    under `BACKWARD_COMPATIBILITY.md` — frontends branch on these.
    """

    INVALID_CREDENTIALS = "invalid_credentials"
    NOT_AUTHENTICATED = "not_authenticated"
    CSRF_TOKEN_INVALID = "csrf_token_invalid"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    SERVICE_UNAVAILABLE = "service_unavailable"


#: The status each code is served with. Kept beside the enum so a code cannot be
#: introduced without deciding its status, and so the pairing is assertable.
STATUS_FOR_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.NOT_AUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.CSRF_TOKEN_INVALID: status.HTTP_403_FORBIDDEN,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SERVICE_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def error_body(code: ErrorCode, field: str | None = None) -> dict[str, Any]:
    return {"error": {"code": str(code), "field": field}}


class ApiError(HTTPException):
    """An error the API answers with, carrying a code rather than prose."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        field: str | None = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.field = field
        super().__init__(
            status_code=status_code or STATUS_FOR_CODE[code],
            detail=error_body(code, field),
            headers=headers,
        )


def typescript_union() -> str:
    """The generated TypeScript the SPA imports.

    Generated rather than hand-maintained so the union cannot fall behind the
    enum; `tests/test_errors.py` fails when the checked-in file is stale.
    """
    members = "\n".join(f"  | '{code.value}'" for code in ErrorCode)
    return (
        "// Generated from backend/trip_planner/errors.py — do not edit by hand.\n"
        "// Regenerate with: (cd backend && uv run python -m trip_planner.errors)\n"
        "\n"
        "export type ErrorCode =\n"
        f"{members}\n"
        "\n"
        "export const ERROR_CODES: readonly ErrorCode[] = [\n"
        + "".join(f"  '{code.value}',\n" for code in ErrorCode)
        + "] as const\n"
    )


GENERATED_TS_PATH = "frontend/src/api/errorCodes.ts"


def main() -> None:  # pragma: no cover - a developer entry point
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    target = repo_root / GENERATED_TS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(typescript_union(), encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":  # pragma: no cover
    main()
