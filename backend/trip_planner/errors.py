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

    # Trips and their stages (Phase 2).
    INVALID_DATE_RANGE = "invalid_date_range"
    TRIP_TOO_LONG = "trip_too_long"
    STAGES_REQUIRED = "stages_required"
    STAGE_OUTSIDE_TRIP = "stage_outside_trip"

    # Items (Phase 3).
    INVALID_TIME_SPAN = "invalid_time_span"
    DATE_OUTSIDE_TRIP = "date_outside_trip"

    # Editing and deleting a trip (Phase 4).
    DAYS_HAVE_ITEMS = "days_have_items"
    STAGES_OUTSIDE_NEW_RANGE = "stages_outside_new_range"
    ITEMS_OUTSIDE_NEW_RANGE = "items_outside_new_range"

    # Attachments and reservation data.
    ATTACHMENT_TOO_LARGE = "attachment_too_large"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    MALFORMED_UPLOAD = "malformed_upload"
    ATTACHMENT_LIMIT_REACHED = "attachment_limit_reached"
    TRIP_STORAGE_QUOTA_EXCEEDED = "trip_storage_quota_exceeded"
    RATE_LIMITED = "rate_limited"
    INVALID_COST = "invalid_cost"
    INVALID_RESERVATION_FIELD = "invalid_reservation_field"
    DAYS_HAVE_ATTACHMENTS = "days_have_attachments"


#: The status each code is served with. Kept beside the enum so a code cannot be
#: introduced without deciding its status, and so the pairing is assertable.
STATUS_FOR_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.NOT_AUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.CSRF_TOKEN_INVALID: status.HTTP_403_FORBIDDEN,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SERVICE_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCode.INVALID_DATE_RANGE: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.TRIP_TOO_LONG: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.STAGES_REQUIRED: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.STAGE_OUTSIDE_TRIP: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INVALID_TIME_SPAN: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.DATE_OUTSIDE_TRIP: status.HTTP_422_UNPROCESSABLE_CONTENT,
    # 409, not 422: the request is well-formed and the rule is about the state of
    # the trip, which the caller can resolve by moving or deleting the items.
    ErrorCode.DAYS_HAVE_ITEMS: status.HTTP_409_CONFLICT,
    ErrorCode.STAGES_OUTSIDE_NEW_RANGE: status.HTTP_409_CONFLICT,
    ErrorCode.ITEMS_OUTSIDE_NEW_RANGE: status.HTTP_409_CONFLICT,
    ErrorCode.ATTACHMENT_TOO_LARGE: status.HTTP_413_CONTENT_TOO_LARGE,
    ErrorCode.UNSUPPORTED_FILE_TYPE: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ErrorCode.MALFORMED_UPLOAD: status.HTTP_422_UNPROCESSABLE_CONTENT,
    # 409, not 422: the request is well-formed and the rule is about the state of
    # the parent (it already holds the maximum number of attachments), which the
    # caller can resolve by removing one first.
    ErrorCode.ATTACHMENT_LIMIT_REACHED: status.HTTP_409_CONFLICT,
    # 409, not 422: the request is well-formed and the rule is about the state of
    # the trip or the installation (its stored bytes), which the caller can
    # resolve by freeing space first.
    ErrorCode.TRIP_STORAGE_QUOTA_EXCEEDED: status.HTTP_409_CONFLICT,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.INVALID_COST: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INVALID_RESERVATION_FIELD: status.HTTP_422_UNPROCESSABLE_CONTENT,
    # 409, not 422: the request is well-formed and the rule is about the state of
    # the trip, which the caller can resolve by moving or deleting the items.
    ErrorCode.DAYS_HAVE_ATTACHMENTS: status.HTTP_409_CONFLICT,
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
