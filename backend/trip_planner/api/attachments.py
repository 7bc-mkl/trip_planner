"""Uploading a file to a day or to an item — the two `POST` routes.

**The order of the checks in this module is the security control**, and it is the
reason these handlers drive the raw request instead of declaring an
`UploadFile` parameter. The spec fixes the order:

    authenticate → check the per-owner rate window → reject on `Content-Length`
    → read and count the body → exactly one part named `file` → sniff →
    structural check → open the transaction → advisory lock → re-check the
    window and the byte quotas → insert the metadata and the blob → record the
    `upload_event`.

Two properties of that order are load-bearing, and FastAPI's ergonomic
`file: UploadFile` parameter breaks both:

- **Nothing may touch the filesystem.** Starlette's `UploadFile` wraps a
  `SpooledTemporaryFile` that rolls over to a real file on disk past ~1 MB —
  which is every real voucher. The spec is explicit that "no uploaded byte ever
  touches the application's filesystem … there is no temporary file, so there is
  no temporary-file race, no leftover on a crash". So the body is accumulated in
  a `bytearray` here and handed to the driver as a bind parameter; no file
  object of any kind is constructed on the way.
- **The rate window and `Content-Length` are checked before the body is read.** A
  declared parameter means FastAPI has already parsed the entire body before the
  handler's first line runs, which would make the memory control decorative —
  the exact failure the spec names: a limiter that "refuses to *store* the flood
  but not to *absorb* it". Here `check_rate` runs first, against the owner and
  nothing else, and the read is a `request.stream()` loop with a hard byte
  counter so that a chunked request lying about (or omitting) its length is
  refused mid-flight rather than believed.

The multipart bytes are then parsed **in memory** by `python-multipart`'s own
low-level parser — the same parser Starlette uses, driven directly so that no
`UploadFile` and no spooled file exists at any point.

Every rejection reason arrives as an `UploadRejection` or a `QuotaRejection`
whose *value is already the wire code*, so mapping one onto an `ErrorCode` is
`ErrorCode(rejection.value)` — an identity lookup that cannot fall out of step
with a new member, rather than an `if` ladder that silently would.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type

from fastapi import APIRouter, Request, status
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from sqlalchemy.orm import Session as OrmSession

from trip_planner.api.deps import CurrentOwner, DbSession, OwnedTrip
from trip_planner.api.items import find_item, get_day
from trip_planner.api.schemas import AttachmentRead
from trip_planner.db.models import Attachment, AttachmentBlob, Owner, Trip
from trip_planner.domain.uploads import (
    MAX_ATTACHMENT_BYTES,
    UploadRejection,
    inspect_upload,
    normalise_filename,
)
from trip_planner.errors import ApiError, ErrorCode
from trip_planner.security.quota import QuotaRejection, get_upload_quota

router = APIRouter(prefix="/trips/{trip_id}", tags=["attachments"])

#: The one part name accepted. Exactly one part carries it; anything else — none,
#: two, or a differently named file part — is `malformed_upload`.
FILE_PART_NAME = b"file"

#: The cap on a non-file field's value (spec, Limits). Nothing this API offers
#: sends such a field; the cap exists so that a caller cannot smuggle megabytes
#: past the file checks by calling them something else. It is applied *while*
#: parsing rather than to a fully-built value.
MAX_FIELD_BYTES = 200


def _refuse(rejection: UploadRejection | QuotaRejection) -> ApiError:
    """Turn a domain or quota rejection into the API error carrying its code.

    `UploadRejection` and `QuotaRejection` were given the wire codes as their
    values precisely so this stays an identity lookup: a member added to either
    enum is answered correctly here without this function changing.
    """
    return ApiError(ErrorCode(rejection.value), field="file")


# --------------------------------------------------------------------------- #
# Reading the body: bounded, counted, and never written anywhere
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _Part:
    """One multipart part, accumulated in memory."""

    name: bytes | None = None
    filename: bytes | None = None
    data: bytearray = field(default_factory=bytearray)
    #: Set when a non-file field ran past `MAX_FIELD_BYTES`. The bytes past the
    #: cap are dropped rather than buffered, so the flag is the only evidence.
    overflowed: bool = False


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """The single `file` part: its raw bytes and the filename the client claimed.

    The part's own `Content-Type` header is deliberately **not** carried here.
    It is discarded by the parser below, before any decision, so that no later
    line of this module can accidentally consult it.
    """

    data: bytes
    filename: bytes


async def read_body(request: Request) -> bytes:
    """The request body, in memory, refused the moment it passes the per-file cap.

    Both halves of the spec's per-file limit live here: `Content-Length` is
    refused *before a byte is read*, and the bytes are counted *while* they are
    read, because a chunked request can lie about or omit its length. Neither
    check alone is the limit.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_ATTACHMENT_BYTES:
        raise ApiError(ErrorCode.ATTACHMENT_TOO_LARGE, field="file")

    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_ATTACHMENT_BYTES:
            # Abandoned mid-stream rather than after the fact: the remaining
            # bytes are never accumulated, so the memory a hostile caller can
            # make this process hold is bounded by the cap and not by the body.
            raise ApiError(ErrorCode.ATTACHMENT_TOO_LARGE, field="file")

    return bytes(body)


def parse_single_file_part(content_type_header: str, body: bytes) -> UploadedFile:
    """Parse `body` as `multipart/form-data` and return its one `file` part.

    Driven straight off the in-memory bytes with `python-multipart`'s low-level
    callback parser: no `UploadFile`, no `SpooledTemporaryFile`, nothing that
    could reach a filesystem. Zero `file` parts, two of them, or a part named
    something else are all `malformed_upload` — the request is well-formed HTTP
    that this endpoint has no way to interpret.
    """
    media_type, options = parse_options_header(content_type_header)
    boundary = options.get(b"boundary")
    if media_type.lower() != b"multipart/form-data" or not boundary:
        raise ApiError(ErrorCode.MALFORMED_UPLOAD, field="file")

    parts: list[_Part] = []
    header_name = bytearray()
    header_value = bytearray()

    def on_part_begin() -> None:
        parts.append(_Part())

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_name.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        # Only `Content-Disposition` is read. The part's `Content-Type` is
        # dropped here, unread, which is what makes "the client is never asked
        # what the file is" structural rather than a rule to remember.
        if bytes(header_name).lower() == b"content-disposition":
            _, params = parse_options_header(b"content-disposition: " + bytes(header_value))
            parts[-1].name = params.get(b"name")
            parts[-1].filename = params.get(b"filename")
        header_name.clear()
        header_value.clear()

    def on_part_data(data: bytes, start: int, end: int) -> None:
        part = parts[-1]
        if part.name == FILE_PART_NAME:
            # Already bounded by `read_body`: the whole request is at most the
            # per-file cap, so one part inside it cannot exceed it either.
            part.data.extend(data[start:end])
            return
        remaining = MAX_FIELD_BYTES - len(part.data)
        chunk = data[start:end]
        if len(chunk) > remaining:
            part.overflowed = True
            chunk = chunk[:remaining]
        part.data.extend(chunk)

    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_part_data": on_part_data,
        },
    )

    try:
        parser.write(body)
        parser.finalize()
    except MultipartParseError as error:
        raise ApiError(ErrorCode.MALFORMED_UPLOAD, field="file") from error

    if any(part.overflowed for part in parts):
        raise ApiError(ErrorCode.MALFORMED_UPLOAD, field="file")

    files = [part for part in parts if part.name == FILE_PART_NAME]
    if len(files) != 1:
        raise ApiError(ErrorCode.MALFORMED_UPLOAD, field="file")

    return UploadedFile(data=bytes(files[0].data), filename=files[0].filename or b"")


# --------------------------------------------------------------------------- #
# Storing it
# --------------------------------------------------------------------------- #


def store_attachment(
    db: OrmSession,
    *,
    owner: Owner,
    trip: Trip,
    upload: UploadedFile,
    item_id: uuid.UUID | None = None,
    trip_day_id: uuid.UUID | None = None,
) -> Attachment:
    """Validate the bytes, re-check every quota under the lock, and insert.

    Everything from the structural check onwards happens in the request's own
    transaction (`get_db` commits it, or rolls it back on any exception), so an
    upload that fails a quota — or that dies half way — leaves neither a metadata
    row, nor bytes, nor an `upload_event`.
    """
    inspected = inspect_upload(upload.data)
    if isinstance(inspected, UploadRejection):
        raise _refuse(inspected)

    quota = get_upload_quota()
    rejection = quota.check_within_transaction(
        db,
        owner_id=owner.id,
        trip_id=trip.id,
        incoming_bytes=len(upload.data),
        item_id=item_id,
        trip_day_id=trip_day_id,
    )
    if rejection is not None:
        raise _refuse(rejection)

    filename = normalise_filename(upload.filename, content_type=inspected.content_type)

    attachment = Attachment(
        item_id=item_id,
        trip_day_id=trip_day_id,
        filename=filename.display,
        # The derived type, always. The client's claim was discarded at the parser.
        content_type=inspected.content_type,
        # The counted length, not anything the request declared.
        byte_size=len(upload.data),
        sha256=hashlib.sha256(upload.data).hexdigest(),
    )
    db.add(attachment)
    db.flush()

    db.add(AttachmentBlob(attachment_id=attachment.id, data=upload.data))
    quota.record_upload(db, owner_id=owner.id, byte_size=len(upload.data))
    db.flush()
    # `created_at` is a server default, so it exists only once the row is written.
    db.refresh(attachment)

    return attachment


async def _receive(request: Request, db: OrmSession, owner: Owner) -> UploadedFile:
    """The pre-transaction half of the order: rate window, then length, then read."""
    rejection = get_upload_quota().check_rate(db, owner_id=owner.id)
    if rejection is not None:
        raise _refuse(rejection)

    body = await read_body(request)
    return parse_single_file_part(request.headers.get("content-type", ""), body)


@router.post(
    "/days/{day_date}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_day_attachment(
    trip: OwnedTrip, day_date: date_type, request: Request, db: DbSession, owner: CurrentOwner
) -> Attachment:
    """Attach a file to a day. A date outside the trip is a `404` before any read."""
    day = get_day(trip, day_date)
    upload = await _receive(request, db, owner)

    return store_attachment(db, owner=owner, trip=trip, upload=upload, trip_day_id=day.id)


@router.post(
    "/items/{item_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_item_attachment(
    trip: OwnedTrip, item_id: uuid.UUID, request: Request, db: DbSession, owner: CurrentOwner
) -> Attachment:
    """Attach a file to an item of this trip. Another trip's item is a `404`."""
    item = find_item(db, trip, item_id)
    upload = await _receive(request, db, owner)

    return store_attachment(db, owner=owner, trip=trip, upload=upload, item_id=item.id)


__all__ = ["router"]
