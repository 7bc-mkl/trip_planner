"""The normalised inbound contract — what everything downstream actually sees.

Pure: no database, no HTTP, no AWS client and no model. The point of this module
existing beside `ses.py` is that **nothing outside `ses.py` reads an AWS field**.
Routing, storage, the screen and (later) the approval path all consume
`DeliveryNotice` and `ReceivedMessage`, so D25's choice of transport stays a
choice rather than a shape the whole feature has quietly taken on. If IMAP were
ever revisited, or a second transport added, the seam is here and the code below
it does not move.

The other half of this module's job is **refusing an event before it can cause
work**. Every validation that can be decided from the envelope's own fields
happens here, returning a `RejectedEvent` rather than raising, so the endpoint
can answer a permanent `4xx` for a forged or malformed event without ever
reaching the database or S3. Only the signature check — which needs a
certificate, and therefore the network — lives in `ses.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

__all__ = [
    "MAX_SNS_BODY_BYTES",
    "DeliveryNotice",
    "EnvelopeType",
    "RejectedEvent",
    "Rejection",
    "SubscriptionRequest",
    "normalise_notification",
    "parse_envelope",
]

#: The bound on an SNS POST body.
#:
#: SNS's own message limit is 256 KB and an S3-action notification is a few
#: kilobytes of JSON, so this is generous by an order of magnitude and still far
#: below what an unauthenticated caller could otherwise ask this process to hold.
#: The route is public, so "how much memory can a stranger make us allocate" is a
#: question with an answer here rather than in the ASGI server's defaults.
MAX_SNS_BODY_BYTES = 256 * 1024


class EnvelopeType(StrEnum):
    """The three SNS envelope types, of which this endpoint acts on two."""

    NOTIFICATION = "Notification"
    SUBSCRIPTION_CONFIRMATION = "SubscriptionConfirmation"
    UNSUBSCRIBE_CONFIRMATION = "UnsubscribeConfirmation"


class Rejection(StrEnum):
    """Why an event was refused. The value is what goes in a log line — a code, never prose.

    Every one of these is a **permanent** refusal answered `4xx`, so SNS stops
    retrying: none of them is a condition a retry could change. Transient
    failures (the database, S3) are deliberately not in this enum — they are
    `5xx` so that SNS *does* retry, and they are decided at the call site rather
    than here.
    """

    MALFORMED = "malformed"
    UNKNOWN_TYPE = "unknown_type"
    WRONG_TOPIC = "wrong_topic"
    WRONG_REGION = "wrong_region"
    UNTRUSTED_CERTIFICATE_URL = "untrusted_certificate_url"
    BAD_SIGNATURE = "bad_signature"
    NOT_AN_S3_ACTION = "not_an_s3_action"
    WRONG_BUCKET = "wrong_bucket"
    WRONG_OBJECT_KEY = "wrong_object_key"
    WRONG_RECIPIENT = "wrong_recipient"
    MISSING_SES_MESSAGE_ID = "missing_ses_message_id"


@dataclass(frozen=True, slots=True)
class RejectedEvent:
    """A refusal with the reason attached. Returned, never raised — see the module docstring."""

    reason: Rejection


@dataclass(frozen=True, slots=True)
class SubscriptionRequest:
    """An SNS `SubscriptionConfirmation` that passed verification.

    `subscribe_url` is carried but is **never followed by this module**, and the
    caller must not follow it blindly either: the URL comes from the request
    body, so confirming whatever it names would turn this endpoint into a
    request-forgery primitive pointed at anything AWS-shaped. `ses.py` confirms
    only after the signature and the topic ARN have both been checked, and only
    against the region's own SNS host.
    """

    topic_arn: str
    token: str
    subscribe_url: str


@dataclass(frozen=True, slots=True)
class DeliveryNotice:
    """One verified SES delivery: where the mail is, and what SES concluded about it.

    This is the whole of what the ingestion path knows before it fetches
    anything — deliberately, because the sender policy has to be decidable from
    it. `ses_message_id` is the idempotency key; the three verdicts are what
    `domain.inbound.decide_sender` reads; `s3_object_key` is where the bytes are.

    There is no `to_address`: it has already been checked against the configured
    recipient, and a value that has been validated and then carried around is a
    value a later reader will validate differently.
    """

    ses_message_id: str
    s3_object_key: str
    from_address: str
    subject: str
    received_at: datetime
    dmarc_verdict: str | None
    spam_verdict: str | None
    virus_verdict: str | None


@dataclass(frozen=True, slots=True)
class ReceivedMessage:
    """A message whose MIME has been fetched and reduced — the ingestion path's output.

    Deliberately not a database row and deliberately not an AWS type: it is the
    value a second transport would also produce, which is the seam this module
    exists to hold.
    """

    notice: DeliveryNotice
    raw_mime: bytes


def parse_envelope(payload: Any) -> tuple[EnvelopeType, dict[str, Any]] | RejectedEvent:
    """The envelope's type, or a permanent refusal.

    Checked before anything else because every later step's meaning depends on
    it: the fields that go into the signature's canonical string differ between
    a notification and a subscription confirmation, so "what type is this" is not
    a detail that can be deferred.
    """
    if not isinstance(payload, dict):
        return RejectedEvent(Rejection.MALFORMED)

    raw_type = payload.get("Type")
    if not isinstance(raw_type, str):
        return RejectedEvent(Rejection.MALFORMED)

    try:
        envelope_type = EnvelopeType(raw_type)
    except ValueError:
        return RejectedEvent(Rejection.UNKNOWN_TYPE)

    return envelope_type, payload


def normalise_notification(
    message: Any, *, expected_recipient: str, expected_bucket: str, expected_prefix: str
) -> DeliveryNotice | RejectedEvent:
    """An SES S3-action event turned into a `DeliveryNotice`, or a permanent refusal.

    Every check here answers a question the signature cannot. A valid signature
    proves the event came from the configured SNS topic; it says nothing about
    whether the topic was pointed at *our* recipient, *our* bucket or a key under
    *our* prefix. A misconfigured — or repointed — receipt rule is exactly the
    case where the signature is perfect and the event is still not ours, so:

    - **the action must be `S3`.** An SNS receipt action carries raw MIME and is
      capped at 150 KB, so a rule configured that way silently truncates every
      reservation PDF. Refusing it loudly is better than ingesting the first
      150 KB of a voucher.
    - **the bucket and key prefix must match configuration**, so a verified event
      can never make this application read an object it does not own.
    - **the recipient must be the configured address**, because one address is
      the product decision (D20) and a rule matching a second one is a
      configuration error rather than a feature.
    - **the SES message id must be present**, because it is the idempotency key
      and a delivery without one cannot be de-duplicated at all.

    The RFC-5322 `Message-ID` header is deliberately never read: it is written by
    the sender, so keying on it would let anyone collapse two real confirmations
    into one, or replay an old one over a new one.
    """
    if not isinstance(message, dict):
        return RejectedEvent(Rejection.MALFORMED)

    mail = message.get("mail")
    receipt = message.get("receipt")
    if not isinstance(mail, dict) or not isinstance(receipt, dict):
        return RejectedEvent(Rejection.MALFORMED)

    action = receipt.get("action")
    if not isinstance(action, dict) or action.get("type") != "S3":
        return RejectedEvent(Rejection.NOT_AN_S3_ACTION)

    if action.get("bucketName") != expected_bucket:
        return RejectedEvent(Rejection.WRONG_BUCKET)

    object_key = action.get("objectKey")
    if not isinstance(object_key, str) or not object_key:
        return RejectedEvent(Rejection.WRONG_OBJECT_KEY)
    if not object_key.startswith(expected_prefix) or ".." in object_key:
        return RejectedEvent(Rejection.WRONG_OBJECT_KEY)

    recipients = receipt.get("recipients")
    if not isinstance(recipients, list) or not any(
        isinstance(one, str) and one.strip().lower() == expected_recipient
        for one in recipients
    ):
        return RejectedEvent(Rejection.WRONG_RECIPIENT)

    ses_message_id = mail.get("messageId")
    if not isinstance(ses_message_id, str) or not ses_message_id.strip():
        return RejectedEvent(Rejection.MISSING_SES_MESSAGE_ID)

    return DeliveryNotice(
        ses_message_id=ses_message_id.strip(),
        s3_object_key=object_key,
        from_address=_first_source(mail),
        subject=_header(mail, "subject"),
        received_at=_timestamp(mail.get("timestamp")),
        dmarc_verdict=_verdict(receipt, "dmarcVerdict"),
        spam_verdict=_verdict(receipt, "spamVerdict"),
        virus_verdict=_verdict(receipt, "virusVerdict"),
    )


def _first_source(mail: dict[str, Any]) -> str:
    """SES's own `source`, falling back to the `From` header it parsed.

    `source` is the envelope sender SES saw, which is the value the DMARC verdict
    is about; the header is what the message claims. Preferring the former means
    the allow-list is checked against the thing that was actually authenticated.
    """
    source = mail.get("source")
    if isinstance(source, str) and source.strip():
        return source.strip().lower()
    return _header(mail, "from").strip().lower()


def _header(mail: dict[str, Any], name: str) -> str:
    """One header out of SES's own parsed list, or an empty string.

    Read from `commonHeaders` when SES supplied it — SES parsed the message, so
    this is not us parsing attacker-controlled bytes ahead of the sender policy.
    The value is still untrusted *content*; it is normalised before storage by
    `domain.inbound`.
    """
    common = mail.get("commonHeaders")
    if not isinstance(common, dict):
        return ""
    value = common.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[0], str):
        return value[0]
    return ""


def _verdict(receipt: dict[str, Any], name: str) -> str | None:
    """A verdict's status, or `None` when SES did not report one.

    `None` is meaningful and is not smoothed over: `domain.inbound` treats an
    absent verdict as a failure, and turning it into `""` here would hide which
    of "SES said no" and "SES said nothing" actually happened.
    """
    entry = receipt.get(name)
    if not isinstance(entry, dict):
        return None
    status = entry.get("status")
    return status if isinstance(status, str) and status.strip() else None


def _timestamp(raw: Any) -> datetime:
    """SES's receipt timestamp, never the sender-controlled `Date` header.

    An unparseable timestamp falls back to now rather than refusing the message:
    losing a real confirmation over a malformed field would be a worse trade than
    a receipt time that is a second or two late.
    """
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC)
