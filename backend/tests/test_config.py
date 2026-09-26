"""Settings resolution."""

from __future__ import annotations

import pytest

from trip_planner.config import (
    DEFAULT_INBOX_MAX_MESSAGE_BYTES,
    INBOX_ENVIRONMENT_VARIABLES,
    INBOX_OPTIONAL_ENVIRONMENT_VARIABLES,
    MissingConfiguration,
    Settings,
    WeakConfiguration,
    require_settings,
)

VALID_SECRET = "x" * 48

#: A complete, valid environment. Individual tests break one thing at a time.
COMPLETE_ENV = {
    "DATABASE_URL": "postgresql://u:p@h/d",
    "SESSION_SECRET": VALID_SECRET,
    "APP_BASE_URL": "https://planner.example.com",
    "ENVIRONMENT": "production",
}


def env_without(*names: str) -> dict[str, str]:
    return {k: v for k, v in COMPLETE_ENV.items() if k not in names}


def env_with(**overrides: str) -> dict[str, str]:
    return COMPLETE_ENV | overrides


def test_missing_required_variable_is_fatal_and_names_the_variable() -> None:
    with pytest.raises(MissingConfiguration) as caught:
        require_settings({})

    assert "DATABASE_URL" in caught.value.missing
    assert "DATABASE_URL" in str(caught.value)


def test_every_missing_variable_is_named_at_once() -> None:
    """An operator should not have to restart once per unset variable."""
    with pytest.raises(MissingConfiguration) as caught:
        require_settings({})

    assert caught.value.missing == [
        "APP_BASE_URL",
        "DATABASE_URL",
        "ENVIRONMENT",
        "SESSION_SECRET",
    ]


def test_blank_is_treated_as_unset() -> None:
    """An empty string in a platform's env editor is a mistake, not a value."""
    with pytest.raises(MissingConfiguration):
        require_settings(env_with(DATABASE_URL="   "))


def test_a_short_session_secret_is_refused() -> None:
    """A short secret is worse than a missing one: it looks configured."""
    with pytest.raises(WeakConfiguration) as caught:
        require_settings(env_with(SESSION_SECRET="short"))

    assert "SESSION_SECRET" in str(caught.value)


def test_a_complete_environment_resolves() -> None:
    settings = require_settings(COMPLETE_ENV)
    assert settings.session_secret == VALID_SECRET
    assert settings.is_production
    assert settings.cookies_are_secure


def test_production_refuses_a_non_https_base_url() -> None:
    """The session cookie is Secure; over http the browser silently drops it."""
    with pytest.raises(WeakConfiguration) as caught:
        require_settings(env_with(APP_BASE_URL="http://planner.example.com"))

    assert "APP_BASE_URL" in str(caught.value)


def test_development_allows_http_and_does_not_mark_cookies_secure() -> None:
    settings = require_settings(
        env_with(ENVIRONMENT="development", APP_BASE_URL="http://localhost:5173")
    )
    assert not settings.is_production
    assert not settings.cookies_are_secure


def test_an_unknown_environment_is_refused() -> None:
    with pytest.raises(WeakConfiguration):
        require_settings(env_with(ENVIRONMENT="staging"))


def test_a_trailing_slash_on_the_base_url_is_normalised_away() -> None:
    settings = require_settings(env_with(APP_BASE_URL="https://planner.example.com/"))
    assert settings.app_base_url == "https://planner.example.com"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
    ],
)
def test_platform_connection_strings_are_normalised_to_the_pinned_driver(
    given: str, expected: str
) -> None:
    """Managed platforms hand out postgres:// or postgresql://; the app pins psycopg 3."""
    settings = Settings(
        database_url=given,
        session_secret=VALID_SECRET,
        app_base_url="https://x.example.com",
        environment="production",
    )
    assert settings.sqlalchemy_url == expected


# --------------------------------------------------------------------------- #
# The reservation inbox's optional configuration
# --------------------------------------------------------------------------- #

#: A complete, coherent inbox configuration. Individual tests break one thing.
INBOX_ENV = {
    "INBOX_RECIPIENT": "Inbox@mail.Planner.example.com",
    "INBOX_AWS_REGION": "eu-central-1",
    "INBOX_SNS_TOPIC_ARN": "arn:aws:sns:eu-central-1:123456789012:trip-planner-inbound",
    "INBOX_S3_BUCKET": "trip-planner-inbound-mime",
}


def test_an_unconfigured_deployment_starts_with_the_inbox_off() -> None:
    """The state every existing deployment is in the moment this feature ships.

    §5's real requirement: adding the inbox must not turn a running installation
    into one that refuses to start. So "no INBOX_* variables" is not a missing
    configuration — it is the documented off position.
    """
    settings = require_settings(COMPLETE_ENV)

    assert settings.inbox is None
    assert not settings.inbox_enabled


def test_a_complete_inbox_configuration_resolves() -> None:
    settings = require_settings(COMPLETE_ENV | INBOX_ENV)

    assert settings.inbox_enabled
    inbox = settings.inbox
    assert inbox is not None
    # Normalised, because the policy compares the SES recipient on this form.
    assert inbox.recipient == "inbox@mail.planner.example.com"
    assert inbox.s3_bucket == "trip-planner-inbound-mime"
    assert inbox.s3_prefix == ""
    assert inbox.allowed_senders == frozenset()
    assert inbox.max_message_bytes == DEFAULT_INBOX_MAX_MESSAGE_BYTES


@pytest.mark.parametrize("omitted", sorted(INBOX_ENVIRONMENT_VARIABLES))
def test_a_partly_configured_inbox_is_refused_naming_what_is_missing(omitted: str) -> None:
    """Half a configuration looks configured and fails later, which is the worst case.

    The failure it prevents is concrete: an app that starts with a bucket but no
    topic ARN accepts notifications it cannot verify, or verifies nothing at all,
    depending on which half was set.
    """
    partial = {k: v for k, v in INBOX_ENV.items() if k != omitted}

    with pytest.raises(WeakConfiguration) as caught:
        require_settings(COMPLETE_ENV | partial)

    assert omitted in str(caught.value)


def test_a_topic_arn_that_is_not_one_is_refused() -> None:
    with pytest.raises(WeakConfiguration) as caught:
        require_settings(
            COMPLETE_ENV | INBOX_ENV | {"INBOX_SNS_TOPIC_ARN": "trip-planner-inbound"}
        )

    assert "INBOX_SNS_TOPIC_ARN" in str(caught.value)


def test_a_topic_in_another_region_is_refused_at_startup() -> None:
    """Otherwise the symptom is "no mail ever arrives" and nothing names the cause."""
    with pytest.raises(WeakConfiguration) as caught:
        require_settings(COMPLETE_ENV | INBOX_ENV | {"INBOX_AWS_REGION": "eu-west-1"})

    assert "eu-west-1" in str(caught.value)


def test_the_allow_list_is_split_normalised_and_deduplicated() -> None:
    settings = require_settings(
        COMPLETE_ENV
        | INBOX_ENV
        | {"INBOX_ALLOWED_SENDERS": " Rezerwacje@Airline.example , owner@example.com ,, "}
    )

    assert settings.inbox is not None
    assert settings.inbox.allowed_senders == {"rezerwacje@airline.example", "owner@example.com"}


@pytest.mark.parametrize("value", ["not-a-number", "-1", "0"])
def test_a_nonsense_message_cap_is_refused(value: str) -> None:
    with pytest.raises(WeakConfiguration) as caught:
        require_settings(COMPLETE_ENV | INBOX_ENV | {"INBOX_MAX_MESSAGE_BYTES": value})

    assert "INBOX_MAX_MESSAGE_BYTES" in str(caught.value)


@pytest.mark.parametrize(
    ("prefix", "key", "expected"),
    [
        ("", "any/key", True),
        ("inbound/", "inbound/ses-1", True),
        ("inbound/", "other/ses-1", False),
        ("inbound/", "inbound/../other/ses-1", False),
    ],
)
def test_only_keys_this_deployment_writes_are_accepted(
    prefix: str, key: str, expected: bool
) -> None:
    """A verified notification still names a key, and the key is not thereby ours.

    A misconfigured — or hostile — receipt rule pointing at an object outside our
    own prefix must not become a read the app performs on its own credentials.
    """
    settings = require_settings(COMPLETE_ENV | INBOX_ENV | {"INBOX_S3_PREFIX": prefix})

    assert settings.inbox is not None
    assert settings.inbox.owns_object_key(key) is expected


def test_no_inbox_credential_is_read_from_the_environment() -> None:
    """S3 is reached through the standard AWS credential chain and a scoped role.

    Stated as a test because the tempting shortcut — an access key pair in two
    more INBOX_* variables — would put a secret into `Settings`, and from there
    into any log line that formats one.
    """
    assert not any(
        "KEY" in name or "SECRET" in name or "TOKEN" in name
        for name in INBOX_ENVIRONMENT_VARIABLES | INBOX_OPTIONAL_ENVIRONMENT_VARIABLES
    )


def test_settings_repr_carries_no_secret() -> None:
    """`Settings` is formatted into crash logs; the session secret must not ride along."""
    settings = require_settings(COMPLETE_ENV | INBOX_ENV)

    assert VALID_SECRET not in repr(settings.inbox)
