"""The public SNS receipt endpoint — the one route R10 permits.

**These tests sign real envelopes with a real RSA key** rather than stubbing the
verifier out. That matters: the canonical string's field list and ordering, the
`Subject`-only-when-present rule and the two signature versions are exactly the
details a stub would paper over, and a verifier that accepts everything would
make every test below pass while the endpoint trusted anyone. What *is* stubbed
is the certificate **fetch**, so no suite run reaches the network — the
certificate a fetch would have returned is handed over directly.

The other half of the file is the endpoint's real security claim, which is not
that it verifies well but that **a verified event buys almost nothing**: one row
saying mail arrived, with no body, no attachment, no S3 read and no plan write.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import TEST_ENVIRONMENT
from trip_planner.config import Settings, require_settings
from trip_planner.db.models import InboundDeliveryStatus, InboundMessage, Owner
from trip_planner.inbound.ses import SignatureVerifier

RECEIPTS = "/api/v1/inbox/receipts/sns"

TOPIC_ARN = "arn:aws:sns:eu-central-1:123456789012:trip-planner-inbound"
BUCKET = "trip-planner-inbound-mime"
PREFIX = "inbound/"
RECIPIENT = "inbox@mail.planner.example.com"
CERT_URL = "https://sns.eu-central-1.amazonaws.com/SimpleNotificationService-abc123.pem"

INBOX_ENV = {
    "INBOX_RECIPIENT": RECIPIENT,
    "INBOX_AWS_REGION": "eu-central-1",
    "INBOX_SNS_TOPIC_ARN": TOPIC_ARN,
    "INBOX_S3_BUCKET": BUCKET,
    "INBOX_S3_PREFIX": PREFIX,
}


# --------------------------------------------------------------------------- #
# A real key, a real certificate, real signatures
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def signing_certificate(signing_key: rsa.RSAPrivateKey) -> bytes:
    """A self-signed certificate carrying the test key, in the PEM a fetch would return."""
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.eu-central-1.amazonaws.com")])
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(signing_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(signing_key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM)


class _OfflineVerifier(SignatureVerifier):
    """The real verifier with the network removed — and nothing else changed.

    Every rule that matters (the host allow-list, the canonical string, the
    signature itself) is the shipped implementation. Only `_fetch_certificate`
    is replaced, and it still only ever answers for the URL a host-checked
    request would have reached.
    """

    def __init__(self, pem: bytes) -> None:
        super().__init__()
        self._pem = pem
        self.fetches: list[str] = []

    def _fetch_certificate(self, url: str) -> bytes:  # type: ignore[override]
        self.fetches.append(url)
        if url != CERT_URL:
            raise ValueError(f"no certificate at {url}")
        return self._pem


@pytest.fixture
def verifier(signing_certificate: bytes) -> _OfflineVerifier:
    return _OfflineVerifier(signing_certificate)


def sign(
    payload: dict[str, Any], key: rsa.RSAPrivateKey, *, version: str = "1"
) -> dict[str, Any]:
    """Sign an envelope exactly as SNS does, so the endpoint's check is the real one."""
    fields = (
        ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type")
        if payload["Type"] == "Notification"
        else ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type")
    )
    canonical = "".join(f"{f}\n{payload[f]}\n" for f in fields if f in payload)
    algorithm = hashes.SHA256() if version == "2" else hashes.SHA1()
    signature = key.sign(canonical.encode("utf-8"), padding.PKCS1v15(), algorithm)

    return payload | {
        "SignatureVersion": version,
        "Signature": base64.b64encode(signature).decode("ascii"),
        "SigningCertURL": CERT_URL,
    }


def ses_event(
    *,
    ses_message_id: str = "ses-message-0001",
    object_key: str = f"{PREFIX}ses-message-0001",
    bucket: str = BUCKET,
    recipient: str = RECIPIENT,
    action_type: str = "S3",
    dmarc: str | None = "PASS",
    spam: str | None = "PASS",
    virus: str | None = "PASS",
    source: str = "owner@example.com",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "recipients": [recipient],
        "action": {"type": action_type, "bucketName": bucket, "objectKey": object_key},
    }
    for name, value in (("dmarcVerdict", dmarc), ("spamVerdict", spam), ("virusVerdict", virus)):
        if value is not None:
            receipt[name] = {"status": value}

    return {
        "mail": {
            "messageId": ses_message_id,
            "source": source,
            "timestamp": "2026-10-01T09:00:00.000Z",
            "commonHeaders": {"from": [source], "subject": "Potwierdzenie rezerwacji"},
        },
        "receipt": receipt,
    }


def notification(
    key: rsa.RSAPrivateKey, event: dict[str, Any] | None = None, **overrides: Any
) -> dict[str, Any]:
    payload = {
        "Type": "Notification",
        "MessageId": str(uuid.uuid4()),
        "TopicArn": TOPIC_ARN,
        "Subject": "Amazon SES Email Receipt Notification",
        "Message": json.dumps(event if event is not None else ses_event()),
        "Timestamp": "2026-10-01T09:00:01.000Z",
    }
    payload.update(overrides)
    return sign(payload, key)


# --------------------------------------------------------------------------- #
# An application with the inbox configured
# --------------------------------------------------------------------------- #


@pytest.fixture
def inbox_settings(database_url: str) -> Settings:
    return require_settings({"DATABASE_URL": database_url, **TEST_ENVIRONMENT, **INBOX_ENV})


@pytest.fixture
def inbox_app(
    db_session: OrmSession, inbox_settings: Settings, verifier: _OfflineVerifier
) -> Iterator[FastAPI]:
    from trip_planner.api import inbox as inbox_module
    from trip_planner.api.deps import get_db
    from trip_planner.app import create_app
    from trip_planner.config import get_settings

    def request_scoped_db() -> Iterator[OrmSession]:
        db_session.expire_all()
        yield db_session

    application = create_app(check_configuration=False)
    application.dependency_overrides[get_db] = request_scoped_db
    application.dependency_overrides[get_settings] = lambda: inbox_settings

    previous = inbox_module.get_signature_verifier()
    inbox_module.set_signature_verifier(verifier)
    try:
        yield application
    finally:
        inbox_module.set_signature_verifier(previous)
        application.dependency_overrides.clear()


@pytest.fixture
def sns(inbox_app: FastAPI, owner: Owner) -> Iterator[TestClient]:
    """A client with no session and no CSRF token — which is the whole point.

    SNS holds neither, so if these tests needed them the endpoint would be
    unreachable by the only caller it exists for.
    """
    with TestClient(inbox_app, base_url="http://testserver") as client:
        yield client


def messages(db: OrmSession) -> list[InboundMessage]:
    db.expire_all()
    return list(db.execute(sa.select(InboundMessage)).scalars())


# --------------------------------------------------------------------------- #
# The happy path, and what it is allowed to have done
# --------------------------------------------------------------------------- #


def test_a_genuine_notification_records_that_mail_arrived(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    response = sns.post(RECEIPTS, json=notification(signing_key))

    assert response.status_code == 200, response.text
    stored = messages(db_session)
    assert len(stored) == 1
    assert stored[0].ses_message_id == "ses-message-0001"
    assert stored[0].s3_object_key == f"{PREFIX}ses-message-0001"
    assert stored[0].from_address == "owner@example.com"


def test_a_recorded_delivery_carries_no_body_and_no_document(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """The endpoint's actual security claim.

    A perfectly forged — or perfectly genuine — notification buys a row in a
    table nobody renders. The body, the documents and any plan write all happen
    later, in the worker, behind the sender policy.
    """
    sns.post(RECEIPTS, json=notification(signing_key))

    stored = messages(db_session)[0]
    assert stored.state == "pending_ingest"
    assert stored.text_body == ""
    assert stored.attachments == []
    assert stored.trip_id is None


def test_the_verdicts_are_recorded_from_the_signed_notification(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """From the envelope SES signed, never from a header inside the message body."""
    sns.post(RECEIPTS, json=notification(signing_key, ses_event(dmarc="FAIL", spam="PASS")))

    stored = messages(db_session)[0]
    assert stored.ses_sender_verdict == "FAIL"
    assert stored.ses_scan_verdict == "PASS"


def test_a_missing_verdict_is_stored_as_unknown_rather_than_blank(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """"SES said nothing" and "SES said no" must stay distinguishable on the row."""
    sns.post(RECEIPTS, json=notification(signing_key, ses_event(dmarc=None)))

    assert messages(db_session)[0].ses_sender_verdict == "unknown"


def test_a_delivery_stamps_the_owner_s_freshness_row(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey, owner: Owner
) -> None:
    """So an empty inbox and a broken inbox do not look the same on the screen."""
    sns.post(RECEIPTS, json=notification(signing_key))

    db_session.expire_all()
    status_row = db_session.get(InboundDeliveryStatus, owner.id)
    assert status_row is not None
    assert status_row.last_received_at is not None


def test_a_signature_version_2_envelope_is_accepted(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """SHA-256 as well as SHA-1: AWS still sends version 1 for existing subscriptions."""
    payload = notification(signing_key)
    unsigned = {k: v for k, v in payload.items() if k not in {"Signature", "SignatureVersion"}}
    response = sns.post(RECEIPTS, json=sign(unsigned, signing_key, version="2"))

    assert response.status_code == 200, response.text
    assert len(messages(db_session)) == 1


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #


def test_the_same_ses_message_delivered_twice_inserts_once(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """SNS delivers at least once, so this is the routine case rather than an exotic one."""
    first = sns.post(RECEIPTS, json=notification(signing_key))
    # A genuine redelivery is a *different* SNS MessageId carrying the same SES
    # event — which is exactly why the SES id is the key and the SNS one is not.
    second = sns.post(RECEIPTS, json=notification(signing_key))

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(messages(db_session)) == 1


def test_the_rfc_message_id_header_is_never_the_idempotency_key(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """The sender writes that header, so keying on it would let anyone collapse
    two real confirmations into one — or replay an old one over a new one."""
    shared_header = {"messageId": "<same-header@airline.example>"}
    first = ses_event(ses_message_id="ses-a", object_key=f"{PREFIX}ses-a")
    second = ses_event(ses_message_id="ses-b", object_key=f"{PREFIX}ses-b")
    first["mail"]["commonHeaders"] |= shared_header
    second["mail"]["commonHeaders"] |= shared_header

    sns.post(RECEIPTS, json=notification(signing_key, first))
    sns.post(RECEIPTS, json=notification(signing_key, second))

    assert len(messages(db_session)) == 2


# --------------------------------------------------------------------------- #
# Everything that must be refused, and refused permanently
# --------------------------------------------------------------------------- #


def test_an_unsigned_event_is_refused_and_stores_nothing(
    sns: TestClient, db_session: OrmSession
) -> None:
    """The plain forgery: a well-formed body with no signature at all."""
    response = sns.post(
        RECEIPTS,
        json={
            "Type": "Notification",
            "MessageId": str(uuid.uuid4()),
            "TopicArn": TOPIC_ARN,
            "Message": json.dumps(ses_event()),
            "Timestamp": "2026-10-01T09:00:01.000Z",
        },
    )

    assert response.status_code == 403
    assert messages(db_session) == []


def test_an_event_signed_by_someone_else_is_refused(
    sns: TestClient, db_session: OrmSession
) -> None:
    """The forgery that matters: a real signature, made with the wrong key."""
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = sns.post(RECEIPTS, json=notification(impostor))

    assert response.status_code == 403
    assert messages(db_session) == []


def test_a_tampered_message_body_is_refused(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """Signed for one event, delivered carrying another — the whole point of signing."""
    payload = notification(signing_key)
    payload["Message"] = json.dumps(ses_event(object_key=f"{PREFIX}somebody-elses-object"))

    response = sns.post(RECEIPTS, json=payload)

    assert response.status_code == 403
    assert messages(db_session) == []


@pytest.mark.parametrize(
    "certificate_url",
    [
        "https://sns.eu-central-1.amazonaws.com.evil.example/cert.pem",
        "https://evil.example/SimpleNotificationService.pem",
        "http://sns.eu-central-1.amazonaws.com/SimpleNotificationService.pem",
        "https://sns.eu-central-1.amazonaws.com@evil.example/cert.pem",
    ],
)
def test_a_certificate_url_outside_aws_is_refused_before_it_is_fetched(
    sns: TestClient,
    db_session: OrmSession,
    signing_key: rsa.RSAPrivateKey,
    verifier: _OfflineVerifier,
    certificate_url: str,
) -> None:
    """The single most load-bearing check in the whole scheme.

    Without it an attacker names their own certificate URL, signs their own
    event with their own key, and every other step passes. The suffix case is
    the one an unanchored pattern lets through; the `@` case is the one a naive
    `startswith` on the URL lets through.
    """
    payload = notification(signing_key)
    payload["SigningCertURL"] = certificate_url

    response = sns.post(RECEIPTS, json=payload)

    assert response.status_code == 403
    assert messages(db_session) == []
    # Refused *before* the fetch, so a hostile URL is never even requested.
    assert verifier.fetches == []


def test_a_validly_signed_event_for_another_topic_is_refused(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey
) -> None:
    """Somebody else's mail, correctly signed. The topic check is not decoration."""
    response = sns.post(
        RECEIPTS,
        json=notification(
            signing_key, TopicArn="arn:aws:sns:eu-central-1:123456789012:someone-else"
        ),
    )

    assert response.status_code == 403
    assert messages(db_session) == []


@pytest.mark.parametrize(
    ("label", "event"),
    [
        ("an SNS action instead of S3", ses_event(action_type="SNS")),
        ("another bucket", ses_event(bucket="somebody-elses-bucket")),
        ("a key outside our prefix", ses_event(object_key="elsewhere/ses-1")),
        ("a traversal in the key", ses_event(object_key=f"{PREFIX}../elsewhere/ses-1")),
        ("a recipient we do not serve", ses_event(recipient="someone@else.example")),
        ("no SES message id", ses_event(ses_message_id="")),
    ],
)
def test_a_signed_event_that_is_not_ours_is_refused(
    sns: TestClient,
    db_session: OrmSession,
    signing_key: rsa.RSAPrivateKey,
    label: str,
    event: dict[str, Any],
) -> None:
    """A valid signature proves the topic, and says nothing about any of these.

    A repointed or misconfigured receipt rule is exactly the case where the
    signature is perfect and the event is still not ours — including the `SNS`
    action, which caps mail at 150 KB and would silently truncate every voucher.
    """
    response = sns.post(RECEIPTS, json=notification(signing_key, event))

    assert response.status_code == 403, label
    assert messages(db_session) == []


def test_an_unknown_envelope_type_is_refused(
    sns: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    payload = notification(signing_key)
    payload["Type"] = "SomethingElse"

    assert sns.post(RECEIPTS, json=payload).status_code == 403


def test_a_body_that_is_not_json_is_refused(sns: TestClient) -> None:
    response = sns.post(
        RECEIPTS, content=b"not json at all", headers={"content-type": "application/json"}
    )

    assert response.status_code == 403


def test_an_oversized_body_is_refused_without_being_parsed(sns: TestClient) -> None:
    """Bounded here rather than in the server's defaults: this route is public."""
    from trip_planner.inbound.transport import MAX_SNS_BODY_BYTES

    response = sns.post(
        RECEIPTS,
        content=b"{" + b"x" * (MAX_SNS_BODY_BYTES + 1024),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Subscription confirmation
# --------------------------------------------------------------------------- #


def confirmation(key: rsa.RSAPrivateKey, subscribe_url: str) -> dict[str, Any]:
    return sign(
        {
            "Type": "SubscriptionConfirmation",
            "MessageId": str(uuid.uuid4()),
            "TopicArn": TOPIC_ARN,
            "Token": "a" * 64,
            "SubscribeURL": subscribe_url,
            "Message": "You have chosen to subscribe to the topic…",
            "Timestamp": "2026-10-01T09:00:01.000Z",
        },
        key,
    )


def test_a_subscribe_url_pointing_anywhere_but_aws_is_refused(
    sns: TestClient, signing_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise this endpoint is a request-forgery primitive aimed at any URL.

    The `SubscribeURL` arrives in the request body, so following whatever it
    names — even after a valid signature — would let anyone who can post here
    make the server issue a GET on their behalf.
    """
    import urllib.request

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the endpoint fetched a SubscribeURL it should have refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)

    response = sns.post(RECEIPTS, json=confirmation(signing_key, "https://evil.example/confirm"))

    assert response.status_code == 403


def test_a_genuine_confirmation_is_confirmed_and_records_no_message(
    sns: TestClient, db_session: OrmSession, signing_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    import urllib.request

    fetched: list[str] = []

    class _Response:
        def read(self, _size: int = 0) -> bytes:
            return b"<ConfirmSubscriptionResponse/>"

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def capture(url: str, *args: object, **kwargs: object) -> _Response:
        fetched.append(url)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", capture)

    url = "https://sns.eu-central-1.amazonaws.com/?Action=ConfirmSubscription&Token=aaa"
    response = sns.post(RECEIPTS, json=confirmation(signing_key, url))

    assert response.status_code == 200
    assert fetched == [url]
    # Confirming a subscription is not mail arriving.
    assert messages(db_session) == []


# --------------------------------------------------------------------------- #
# The unconfigured deployment
# --------------------------------------------------------------------------- #


def test_an_unconfigured_deployment_refuses_the_endpoint(
    client: TestClient, signing_key: rsa.RSAPrivateKey
) -> None:
    """`client` is the ordinary app fixture, with no INBOX_* settings at all.

    There is no configured topic to check a signature against, so there is
    nothing this deployment could verify — a permanent refusal rather than a
    retry that will never succeed.
    """
    assert client.post(RECEIPTS, json=notification(signing_key)).status_code == 403


def test_an_unconfigured_deployment_builds_no_aws_client(settings: Settings) -> None:
    """"The inbox is off" has to be genuinely inert, not a flag checked late.

    No client, no credential resolution, no network — which is also what keeps
    the suite itself free of AWS.
    """
    assert settings.inbox is None
