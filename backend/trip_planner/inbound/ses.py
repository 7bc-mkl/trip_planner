"""The only module that talks to AWS, and the only one that knows AWS shapes.

Two jobs, both of which are security boundaries rather than plumbing:

**1. Proving an SNS envelope really came from the configured topic.** The
endpoint is public — the single permission R10 grants — so every field in the
body is attacker-controlled until the signature says otherwise. The check is the
one AWS documents, with the parts that are easy to get subtly wrong written down
where the next reader will see them:

- the signing certificate is fetched **only** from `sns.<region>.amazonaws.com`
  (or its China partition). This is the check whose absence turns the whole
  scheme into theatre: an attacker who can name the certificate URL signs their
  own events with their own key and every other step passes.
- **redirects are refused.** An allow-listed host that 302s to an attacker's is
  the same hole with one extra hop, and `urllib`'s default opener follows
  redirects happily.
- the fetch is bounded by a timeout and a byte cap, and the result is cached, so
  a slow or enormous "certificate" cannot be used to stall the endpoint.
- the canonical string is built from a **fixed list of fields in a fixed order**
  that differs by envelope type. Signing the JSON, or the fields in dict order,
  verifies nothing.
- the topic ARN is compared against configuration *after* the signature checks
  out, so a validly-signed event for somebody else's topic is still refused.

**2. Fetching the raw MIME out of S3, bounded.** With a connect and read
timeout, a hard byte cap applied while streaming, and a key that has already
been checked against the configured bucket and prefix. `boto3` is constructed
lazily and only when the inbox is configured, so an unconfigured deployment
never builds a client, never resolves credentials and never touches the network.
"""

from __future__ import annotations

import base64
import re
import threading
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509 import load_pem_x509_certificate

from trip_planner.config import InboxSettings
from trip_planner.inbound.transport import (
    DeliveryNotice,
    EnvelopeType,
    RejectedEvent,
    Rejection,
    SubscriptionRequest,
    normalise_notification,
    parse_envelope,
)

__all__ = [
    "CERTIFICATE_TIMEOUT_SECONDS",
    "MAX_CERTIFICATE_BYTES",
    "S3_READ_TIMEOUT_SECONDS",
    "ObjectGone",
    "S3Fetcher",
    "SignatureVerifier",
    "verify_event",
]

#: `sns.<region>.amazonaws.com`, and the China partition's own suffix. Anchored
#: at both ends: `sns.eu-central-1.amazonaws.com.evil.example` matches an
#: unanchored pattern and is not AWS.
_CERTIFICATE_HOST = re.compile(r"^sns\.[a-z0-9\-]+\.amazonaws\.com(\.cn)?$")

#: A certificate is a couple of kilobytes. The cap exists because the URL is
#: attacker-influenced up to the host check, and an allow-listed host serving a
#: gigabyte would otherwise be a memory exhaustion the endpoint pays for.
MAX_CERTIFICATE_BYTES = 32 * 1024

CERTIFICATE_TIMEOUT_SECONDS = 5.0

S3_CONNECT_TIMEOUT_SECONDS = 5.0
S3_READ_TIMEOUT_SECONDS = 20.0

#: The fields that go into the canonical string, per envelope type, **in this
#: order**. Straight from AWS's own specification; the order is part of the
#: algorithm, so this is a constant rather than something derived from the body.
_SIGNED_FIELDS: dict[EnvelopeType, tuple[str, ...]] = {
    EnvelopeType.NOTIFICATION: ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"),
    EnvelopeType.SUBSCRIPTION_CONFIRMATION: (
        "Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type",
    ),
    EnvelopeType.UNSUBSCRIBE_CONFIRMATION: (
        "Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type",
    ),
}

#: `Subject` is signed only when present. Including it as an empty string when
#: SNS omitted it produces a different canonical string and a verification that
#: fails for every real notification without a subject.
_OPTIONAL_SIGNED_FIELDS = frozenset({"Subject"})


class ObjectGone(RuntimeError):
    """The S3 object is not there — expired under the lifecycle rule, or already deleted.

    Distinct from a transient S3 error on purpose: this one must **not** be
    retried forever, and it is what the quarantine recovery actions answer
    `409 inbox_object_unavailable` for.
    """


@dataclass(frozen=True, slots=True)
class VerifiedEvent:
    """What a fully verified envelope resolved to — exactly one of the two."""

    notice: DeliveryNotice | None = None
    subscription: SubscriptionRequest | None = None


class SignatureVerifier:
    """Verifies SNS signatures, caching certificates by URL.

    A class rather than a function because of the cache: a topic rotates its
    signing certificate rarely, and fetching one per notification would put a
    synchronous outbound request on the path of every inbound mail — turning an
    AWS-side slowdown into a queue on our endpoint.

    The cache is keyed on the **already host-checked** URL, so a poisoned entry
    is not reachable: a URL that fails the host check never gets as far as being
    a key.
    """

    def __init__(self) -> None:
        self._certificates: dict[str, rsa.RSAPublicKey] = {}
        self._lock = threading.Lock()

    def verify(self, payload: dict[str, Any], envelope_type: EnvelopeType) -> Rejection | None:
        """`None` when the envelope is genuine, or the reason it is not."""
        certificate_url = payload.get("SigningCertURL") or payload.get("SigningCertUrl")
        if not isinstance(certificate_url, str) or not self._host_is_aws(certificate_url):
            return Rejection.UNTRUSTED_CERTIFICATE_URL

        raw_signature = payload.get("Signature")
        if not isinstance(raw_signature, str):
            return Rejection.BAD_SIGNATURE
        try:
            signature = base64.b64decode(raw_signature, validate=True)
        except (ValueError, TypeError):
            return Rejection.BAD_SIGNATURE

        canonical = self._canonical_string(payload, envelope_type)
        if canonical is None:
            return Rejection.MALFORMED

        # SignatureVersion 1 is SHA1-with-RSA and 2 is SHA256-with-RSA. Both are
        # accepted because AWS still sends 1 for existing subscriptions; the
        # version is read from the body, but it only selects a hash, so a caller
        # who lies about it simply fails verification.
        algorithm = hashes.SHA256() if payload.get("SignatureVersion") == "2" else hashes.SHA1()

        try:
            public_key = self._public_key(certificate_url)
        except Exception:
            # A certificate that cannot be fetched or parsed is not a verified
            # event. Refusing permanently is right: the URL is part of the body,
            # so a retry would fetch the same unusable thing.
            return Rejection.UNTRUSTED_CERTIFICATE_URL

        try:
            public_key.verify(signature, canonical.encode("utf-8"), padding.PKCS1v15(), algorithm)
        except InvalidSignature:
            return Rejection.BAD_SIGNATURE

        return None

    @staticmethod
    def _host_is_aws(url: str) -> bool:
        """HTTPS, and a host that is genuinely an SNS endpoint.

        The single most load-bearing line in this module. Without it an attacker
        names their own certificate URL, signs their own event with their own
        key, and every subsequent check passes.
        """
        parts = urlsplit(url)
        return parts.scheme == "https" and _CERTIFICATE_HOST.match(parts.hostname or "") is not None

    @staticmethod
    def _canonical_string(payload: dict[str, Any], envelope_type: EnvelopeType) -> str | None:
        """`key\\nvalue\\n` for each signed field, in AWS's fixed order."""
        chunks: list[str] = []
        for field in _SIGNED_FIELDS[envelope_type]:
            if field not in payload:
                if field in _OPTIONAL_SIGNED_FIELDS:
                    continue
                return None
            value = payload[field]
            if not isinstance(value, str):
                return None
            chunks.append(f"{field}\n{value}\n")
        return "".join(chunks)

    def _public_key(self, url: str) -> rsa.RSAPublicKey:
        with self._lock:
            cached = self._certificates.get(url)
        if cached is not None:
            return cached

        pem = self._fetch_certificate(url)
        key = load_pem_x509_certificate(pem).public_key()
        if not isinstance(key, rsa.RSAPublicKey):
            raise ValueError("SNS signing certificate does not carry an RSA public key")

        with self._lock:
            self._certificates[url] = key
        return key

    @staticmethod
    def _fetch_certificate(url: str) -> bytes:
        """Bounded, timed, and **redirect-free**.

        `urllib`'s default opener follows redirects, so an allow-listed host that
        302s to an attacker's would defeat the host check with one extra hop.
        The handler below turns any redirect into an error instead.
        """

        class _NoRedirects(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: object, **kwargs: object) -> None:
                raise ValueError("the SNS signing certificate URL redirected; refusing to follow")

        opener = urllib.request.build_opener(_NoRedirects)
        with opener.open(url, timeout=CERTIFICATE_TIMEOUT_SECONDS) as response:
            # `read(n + 1)` rather than `read(n)`: reading exactly the cap cannot
            # distinguish "fits" from "was truncated at the cap".
            body = response.read(MAX_CERTIFICATE_BYTES + 1)

        if len(body) > MAX_CERTIFICATE_BYTES:
            raise ValueError("the SNS signing certificate is implausibly large; refusing")
        return body


def verify_event(
    payload: Any,
    *,
    settings: InboxSettings,
    verifier: SignatureVerifier,
) -> VerifiedEvent | RejectedEvent:
    """The whole envelope check, in the order the spec fixes.

    **Order is the control.** Type first, because it decides which fields are
    signed. Signature next, because nothing in the body means anything until it
    is proven to come from SNS. The topic ARN *after* the signature — a validly
    signed event for another topic is somebody else's mail, and comparing first
    would mean comparing an unauthenticated string. Only then the SES-level
    checks, which the signature says nothing about.
    """
    parsed = parse_envelope(payload)
    if isinstance(parsed, RejectedEvent):
        return parsed
    envelope_type, body = parsed

    rejection = verifier.verify(body, envelope_type)
    if rejection is not None:
        return RejectedEvent(rejection)

    if body.get("TopicArn") != settings.sns_topic_arn:
        return RejectedEvent(Rejection.WRONG_TOPIC)

    if envelope_type is EnvelopeType.SUBSCRIPTION_CONFIRMATION:
        subscribe_url = body.get("SubscribeURL")
        token = body.get("Token")
        if not isinstance(subscribe_url, str) or not isinstance(token, str):
            return RejectedEvent(Rejection.MALFORMED)
        # The URL is verified to be AWS's own before anything follows it. It
        # arrived in the request body, so confirming whatever it names would make
        # this endpoint a request-forgery primitive aimed at anything AWS-shaped.
        if not SignatureVerifier._host_is_aws(subscribe_url):
            return RejectedEvent(Rejection.UNTRUSTED_CERTIFICATE_URL)
        return VerifiedEvent(
            subscription=SubscriptionRequest(
                topic_arn=settings.sns_topic_arn, token=token, subscribe_url=subscribe_url
            )
        )

    if envelope_type is EnvelopeType.UNSUBSCRIBE_CONFIRMATION:
        # Genuine, and nothing to do: this application never unsubscribes itself,
        # and acting on it would let a signed replay detach the inbox.
        return VerifiedEvent()

    message = _inner_message(body)
    if message is None:
        return RejectedEvent(Rejection.MALFORMED)

    notice = normalise_notification(
        message,
        expected_recipient=settings.recipient,
        expected_bucket=settings.s3_bucket,
        expected_prefix=settings.s3_prefix,
    )
    if isinstance(notice, RejectedEvent):
        return notice

    return VerifiedEvent(notice=notice)


def _inner_message(body: dict[str, Any]) -> Any:
    """SNS's `Message`, which carries the SES event as a JSON **string**.

    Parsed here rather than in `transport.py` because it is an AWS-shaped fact:
    the double encoding is SNS's, and nothing downstream should have to know
    about it.
    """
    import json

    raw = body.get("Message")
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


class S3Fetcher:
    """The bounded read of one raw MIME object, and the delete that follows ingestion.

    Constructed lazily: an unconfigured deployment never builds a client, never
    resolves credentials and never touches the network — which is what makes
    "the inbox is off" a genuinely inert state rather than a flag checked late.
    """

    def __init__(self, settings: InboxSettings) -> None:
        self._settings = settings
        self._client: Any | None = None
        self._lock = threading.Lock()

    def _s3(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    import boto3
                    from botocore.config import Config

                    self._client = boto3.client(
                        "s3",
                        region_name=self._settings.aws_region,
                        config=Config(
                            connect_timeout=S3_CONNECT_TIMEOUT_SECONDS,
                            read_timeout=S3_READ_TIMEOUT_SECONDS,
                            # Bounded, because an unbounded retry inside a worker
                            # thread is an outage that looks like a hang.
                            retries={"max_attempts": 3, "mode": "standard"},
                        ),
                    )
        return self._client

    def fetch(self, key: str) -> bytes:
        """The object's bytes, refused past the configured cap **while streaming**.

        Counting while reading rather than trusting `ContentLength`: the length
        is metadata, and a limiter that believes it refuses to *store* an
        oversized object without refusing to *absorb* it — the same failure the
        upload path's `read_body` is written to avoid.
        """
        if not self._settings.owns_object_key(key):
            # Defence in depth: the key was checked when the event was verified,
            # and it is checked again here, because this method is also reached
            # from the recovery actions with a key read back out of the database.
            raise ObjectGone(f"refusing to read an object outside this deployment's prefix: {key}")

        from botocore.exceptions import ClientError

        try:
            response = self._s3().get_object(Bucket=self._settings.s3_bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NoSuchBucket"}:
                raise ObjectGone(key) from error
            raise

        cap = self._settings.max_message_bytes
        body = response["Body"]
        try:
            data = body.read(cap + 1)
        finally:
            body.close()

        if len(data) > cap:
            raise ValueError(
                f"inbound message at {key} exceeds INBOX_MAX_MESSAGE_BYTES ({cap}); refusing"
            )
        return data

    def delete(self, key: str) -> None:
        """Delete an ingested object. Best-effort by design — see the ingestion path.

        The database commit happens first, so a failure here leaves a stored
        message and an orphaned S3 object that the lifecycle rule expires. The
        other order would risk a deleted object and no message, which is the one
        outcome that loses the owner's mail.
        """
        if not self._settings.owns_object_key(key):
            return
        self._s3().delete_object(Bucket=self._settings.s3_bucket, Key=key)
