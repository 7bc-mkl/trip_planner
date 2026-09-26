"""Storing a document that arrived by mail, on the table the browser uploads use.

**This is the honest part of "it reuses the shipped attachment pipeline".** The
*data* claim is true outright: one `attachment` table, one `attachment_blob`,
one `sha256`, one cascade chain and a single place in the product where "a
document" is defined. The shipped `domain/uploads.py` sniffing is called
unchanged, so an inbound part is judged by exactly the rules a browser upload is.

What is **not** reused, and would be a lie to claim: the shipped *write path*.
`api/attachments.py`'s `store_attachment` is trip-scoped — it takes a `Trip`, it
checks that trip's byte quota and it takes that trip's advisory lock — and a
message sitting in the unrouted queue has no trip at all. So this is a second,
trip-less storage function. It is deliberately small, and it reuses the pieces
that are genuinely shared rather than pretending the endpoints are.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import Attachment, AttachmentBlob, InboundMessage
from trip_planner.domain.inbound import InboundDocument

__all__ = ["store_inbound_attachment"]


def store_inbound_attachment(
    db: OrmSession, *, message: InboundMessage, document: InboundDocument
) -> Attachment:
    """Insert one inbox-parented attachment and its bytes.

    The caller has already run `domain.inbound.select_content`, which sniffed the
    bytes and normalised the filename, so the type stored here is the **derived**
    one and the name is the display form — the same two guarantees the browser
    path gives, arrived at through the same functions.

    No quota is consulted here and that is the caller's job, exactly as it is on
    the upload path: the limits run inside the ingestion transaction where they
    can take a lock, and a storage helper that checked them itself would run them
    once per document instead of once per message.
    """
    attachment = Attachment(
        inbound_message_id=message.id,
        filename=document.filename,
        # Derived from the bytes. The part's declared Content-Type was discarded
        # in `select_content` and has no way of reaching this line.
        content_type=document.inspected.content_type,
        byte_size=len(document.data),
        sha256=hashlib.sha256(document.data).hexdigest(),
    )
    db.add(attachment)
    db.flush()

    db.add(AttachmentBlob(attachment_id=attachment.id, data=document.data))
    db.flush()

    return attachment
