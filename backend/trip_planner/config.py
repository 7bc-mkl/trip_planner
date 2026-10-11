"""Application settings.

Every setting comes from the environment. `BACKWARD_COMPATIBILITY.md` §5 requires
a new required variable to fail loudly at startup naming itself, rather than
defaulting to something that half-works; `require_settings()` in this module is
that check, and `deploy/` calls it before the app takes traffic.

The reservation inbox's settings are **optional**, and §5 is why: an existing
deployment must start unchanged after this feature ships. So "unset" is a
supported, tested state that means *the inbox is off* — no AWS client is
constructed, no background loop starts, and the owner inbox routes answer
`409 inbox_not_configured` while the rest of the application is exactly what it
was.

**Partly set is not a third state.** Half a configuration is the thing §5 is
actually about: it looks configured, it starts, and it fails somewhere later
with an error that names none of this. So a deployment that sets one inbox
variable must set all of the required ones, and `require_settings` refuses with
`WeakConfiguration` naming the ones it is missing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache

#: Variables the application refuses to start without, with what each is for.
#: The message is part of the contract: an operator reading a crash log must be
#: able to fix it without reading the source.
REQUIRED_ENVIRONMENT_VARIABLES: dict[str, str] = {
    "DATABASE_URL": "PostgreSQL connection string, e.g. postgresql+psycopg://user:pass@host/db",
    "SESSION_SECRET": (
        "random secret (32+ bytes) keying the session-token hash and the CSRF token; "
        "rotating it signs every session out"
    ),
    "APP_BASE_URL": "absolute public URL of this installation, e.g. https://planner.example.com",
    "ENVIRONMENT": "'production' or 'development'; production refuses to start without HTTPS",
}

#: Below this, the secret is not doing the job its name claims.
MINIMUM_SESSION_SECRET_LENGTH = 32

VALID_ENVIRONMENTS = frozenset({"production", "development"})


class MissingConfiguration(RuntimeError):
    """Raised at startup when a required environment variable is unset.

    Carries the variable names so a caller (and the test that locks this
    behaviour down) can assert on them rather than on prose.
    """

    def __init__(self, missing: list[str]) -> None:
        self.missing = sorted(missing)
        details = "\n".join(
            f"  - {name}: {REQUIRED_ENVIRONMENT_VARIABLES[name]}" for name in self.missing
        )
        super().__init__(
            "Refusing to start: required environment variable(s) not set:\n"
            f"{details}\n"
            "Set them in the deployment environment and restart."
        )


class WeakConfiguration(RuntimeError):
    """Raised when a required variable is set but not to a usable value."""


#: The inbox variables a deployment must set **together** or not at all.
#:
#: There is deliberately no credential variable here. The app reaches S3 through
#: the standard AWS credential chain with a least-privilege read/delete role for
#: one bucket and prefix, so no secret is ever read by this module, ends up in a
#: `Settings` repr, or can be logged by something that formats one.
INBOX_ENVIRONMENT_VARIABLES: dict[str, str] = {
    "INBOX_RECIPIENT": (
        "the one address the SES receipt rule matches, e.g. inbox@mail.planner.example.com"
    ),
    "INBOX_AWS_REGION": "AWS region of the SES receipt rule, the SNS topic and the S3 bucket",
    "INBOX_SNS_TOPIC_ARN": (
        "exact ARN of the SNS topic the receipt rule publishes to; a notification signed "
        "for any other topic is refused"
    ),
    "INBOX_S3_BUCKET": "private, encrypted bucket the SES receipt rule writes raw MIME to",
}

#: Optional beside the four above, with a documented default each.
INBOX_OPTIONAL_ENVIRONMENT_VARIABLES: dict[str, str] = {
    "INBOX_S3_PREFIX": "key prefix the receipt rule writes under; default: no prefix",
    "INBOX_ALLOWED_SENDERS": (
        "comma-separated additional sender addresses to accept. The owner's own account "
        "address is always accepted and does not need listing; default: none"
    ),
    "INBOX_MAX_MESSAGE_BYTES": (
        "hard cap on the raw MIME object this app will fetch from S3; default: 41943040 (40 MB)"
    ),
}

#: The providers D24 permits, and the credential each one reads.
#:
#: **Exactly one is selected per deployment and there is no fallback.** A
#: fallback would silently widen the egress decision the owner made: he
#: authorised one named service to see his mail, not whichever is up.
MODEL_PROVIDERS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}

#: Set together or not at all, like the inbox block above.
MODEL_ENVIRONMENT_VARIABLES: dict[str, str] = {
    "INBOX_MODEL_PROVIDER": f"one of {sorted(MODEL_PROVIDERS)}; no default, and no fallback",
    "INBOX_MODEL_NAME": (
        "the exact model identifier to call, e.g. the provider's small/cheap tier — "
        "routing picks one of at most five candidates, which is not a frontier task"
    ),
}

#: Optional, with a documented default each.
MODEL_OPTIONAL_ENVIRONMENT_VARIABLES: dict[str, str] = {
    "INBOX_MODEL_BASE_URL": (
        "override the provider's API host — the knob for EU data residency or a "
        "gateway; default: the provider's own global endpoint"
    ),
    "INBOX_MODEL_MONTHLY_BUDGET": (
        "maximum spend per billing month, in the price schedule's currency. "
        "**Calls stop when it is reached**; default: unset, which also stops calls"
    ),
    "INBOX_MODEL_INPUT_PRICE": "price per million input tokens; default: unset",
    "INBOX_MODEL_OUTPUT_PRICE": "price per million output tokens; default: unset",
}

#: 40 MB — the message size the spec's Edge Cases table names. Past it the object
#: is not fetched at all: the cap is on the *read*, so a hostile 2 GB object
#: costs one `HEAD`-sized decision rather than 2 GB of memory.
DEFAULT_INBOX_MAX_MESSAGE_BYTES = 40 * 1024 * 1024

#: `arn:aws:sns:<region>:<account>:<name>`, loosely — enough to read the region
#: back out and to refuse something that is plainly not a topic ARN. It is not a
#: substitute for the signature check; it is what makes the *configuration*
#: wrong loudly at startup instead of quietly at the first notification.
_SNS_TOPIC_ARN = re.compile(r"^arn:aws[a-z\-]*:sns:([a-z0-9\-]+):\d{12}:[A-Za-z0-9_\-]+$")


@dataclass(frozen=True, slots=True)
class InboxSettings:
    """Everything the inbound path needs, resolved once and validated together."""

    recipient: str
    aws_region: str
    sns_topic_arn: str
    s3_bucket: str
    s3_prefix: str
    #: Normalised lower-case, and **never** the sole allow-list: the policy takes
    #: the union of this, the owner's own account address and the addresses he
    #: has trusted through the quarantine recovery action.
    allowed_senders: frozenset[str]
    max_message_bytes: int

    def owns_object_key(self, key: str) -> bool:
        """Whether a key from a verified event is one this deployment writes.

        Checked before any S3 GET. A verified notification still names a bucket
        and a key, and accepting an arbitrary key inside our own bucket would let
        a misconfigured (or hostile) rule point the app at an object it has no
        business reading.
        """
        return key.startswith(self.s3_prefix) and ".." not in key


@dataclass(frozen=True, slots=True)
class ModelSettings:
    """Which model may read a forwarded confirmation, and what it may cost.

    Separate from `InboxSettings` because the two boundaries are separate and
    the spec insists they be reviewed separately: AWS stores the owner's raw
    mail, and the model provider is shown its text. An inbox with no model is a
    supported, useful deployment — Phase 1 is exactly that — so a missing model
    configuration disables routing without disabling the inbox.

    **The API key is here and nowhere else**, and it is the one secret this
    dataclass holds. `__repr__` is overridden so it cannot reach a log line
    through something that formats settings.
    """

    provider: str
    model: str
    api_key: str
    #: `None` means the provider's own global endpoint. Set it for EU residency
    #: or to route through a gateway — the whole reason it exists is that
    #: residency should be a configuration change rather than a code change.
    base_url: str | None
    monthly_budget: Decimal | None
    input_price_per_mtok: Decimal | None
    output_price_per_mtok: Decimal | None

    @property
    def priced(self) -> bool:
        """Whether a call's cost can be computed at all.

        The spec is explicit: *when usage or price is unavailable, stop model
        calls rather than treating cost as zero*. An unpriced deployment is
        therefore not an unlimited one — it makes no calls, which is the only
        reading of "unknown cost" that cannot surprise the owner with a bill.
        """
        return (
            self.monthly_budget is not None
            and self.input_price_per_mtok is not None
            and self.output_price_per_mtok is not None
        )

    def __repr__(self) -> str:
        """Excludes `api_key`. It is the only secret here and it stays here."""
        return f"<ModelSettings provider={self.provider!r} model={self.model!r}>"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    session_secret: str
    app_base_url: str
    environment: str
    #: `None` when the deployment has no inbox configuration — a normal state.
    inbox: InboxSettings | None = None
    #: `None` when no model is configured. Also a normal state: the inbox then
    #: behaves exactly as Phase 1 shipped — stored and queued, no egress.
    model: ModelSettings | None = None

    @property
    def inbox_enabled(self) -> bool:
        return self.inbox is not None

    @property
    def routing_enabled(self) -> bool:
        """Routing needs both halves: somewhere for mail to arrive, and a reader."""
        return self.inbox is not None and self.model is not None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookies_are_secure(self) -> bool:
        """`Secure` in production, so the session cookie cannot travel in clear.

        It is off in development because a `Secure` cookie is simply not stored
        over plain http, which would make local sign-in fail in a way that looks
        like a bug in the login handler.
        """
        return self.is_production

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise the driver so `postgresql://` from a platform works unchanged.

        Managed platforms hand out `postgresql://…`; SQLAlchemy 2.0 would pick the
        default DBAPI for that, which is not the psycopg 3 driver this project
        pins. Rewriting here means the deployment does not have to know.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url


def require_settings(environ: dict[str, str] | None = None) -> Settings:
    """Read and validate settings, or raise `MissingConfiguration` naming what is unset."""
    env = os.environ if environ is None else environ

    missing = [name for name in REQUIRED_ENVIRONMENT_VARIABLES if not env.get(name, "").strip()]
    if missing:
        raise MissingConfiguration(missing)

    session_secret = env["SESSION_SECRET"].strip()
    if len(session_secret) < MINIMUM_SESSION_SECRET_LENGTH:
        # A short secret is worse than a missing one: it looks configured.
        raise WeakConfiguration(
            f"SESSION_SECRET must be at least {MINIMUM_SESSION_SECRET_LENGTH} characters; "
            f"got {len(session_secret)}. Generate one with: python3 -c "
            "'import secrets; print(secrets.token_urlsafe(48))'"
        )

    environment = env["ENVIRONMENT"].strip().lower()
    if environment not in VALID_ENVIRONMENTS:
        raise WeakConfiguration(
            f"ENVIRONMENT must be one of {sorted(VALID_ENVIRONMENTS)}; got {environment!r}"
        )

    app_base_url = env["APP_BASE_URL"].strip().rstrip("/")
    if environment == "production" and not app_base_url.startswith("https://"):
        # D14 puts this on the public internet and the session cookie is Secure.
        # Starting without TLS would hand out a cookie the browser then refuses to
        # send back, so sign-in would fail on every request instead of loudly here.
        raise WeakConfiguration(
            "ENVIRONMENT=production requires APP_BASE_URL to be an https:// URL; "
            f"got {app_base_url!r}"
        )

    return Settings(
        database_url=env["DATABASE_URL"].strip(),
        session_secret=session_secret,
        app_base_url=app_base_url,
        environment=environment,
        inbox=resolve_inbox_settings(env),
        model=resolve_model_settings(env),
    )


def resolve_model_settings(env: dict[str, str]) -> ModelSettings | None:
    """The model configuration, or `None` when this deployment has none.

    Same three outcomes as the inbox block, and the same reasoning: nothing set
    is off, everything set is on, and a partial configuration raises rather than
    starting something half-wired. Off is a supported state — the deployment
    keeps the whole Phase 1 inbox and simply never sends anything anywhere.
    """
    present = {name for name in MODEL_ENVIRONMENT_VARIABLES if env.get(name, "").strip()}
    if not present:
        return None

    missing = sorted(set(MODEL_ENVIRONMENT_VARIABLES) - present)
    if missing:
        details = "\n".join(f"  - {name}: {MODEL_ENVIRONMENT_VARIABLES[name]}" for name in missing)
        raise WeakConfiguration(
            "The inbox model is partly configured, which is worse than not "
            f"configured: {sorted(present)} are set but these are not:\n{details}\n"
            "Set them, or unset every INBOX_MODEL_* variable to run the inbox without routing."
        )

    provider = env["INBOX_MODEL_PROVIDER"].strip().lower()
    if provider not in MODEL_PROVIDERS:
        raise WeakConfiguration(
            f"INBOX_MODEL_PROVIDER must be one of {sorted(MODEL_PROVIDERS)}; got {provider!r}. "
            "D24 authorised one explicitly selected provider; there is no default."
        )

    # **Only the selected provider's key is read.** A deployment that happens to
    # have all three in its environment still sends to exactly one, and a key
    # for a provider that is not selected is never even looked at — so a stray
    # credential cannot quietly become the thing that saw the owner's mail.
    key_variable = MODEL_PROVIDERS[provider]
    api_key = env.get(key_variable, "").strip()
    if not api_key:
        raise WeakConfiguration(
            f"INBOX_MODEL_PROVIDER is {provider!r}, so {key_variable} must be set. "
            "No other provider's key is consulted."
        )

    base_url = env.get("INBOX_MODEL_BASE_URL", "").strip() or None
    if base_url is not None and not base_url.startswith("https://"):
        # The payload is the owner's mail. Plaintext is not a configuration
        # choice this application is willing to accept.
        raise WeakConfiguration(
            f"INBOX_MODEL_BASE_URL must be an https:// URL; got {base_url!r}"
        )

    return ModelSettings(
        provider=provider,
        model=env["INBOX_MODEL_NAME"].strip(),
        api_key=api_key,
        base_url=base_url,
        monthly_budget=_decimal(env, "INBOX_MODEL_MONTHLY_BUDGET"),
        input_price_per_mtok=_decimal(env, "INBOX_MODEL_INPUT_PRICE"),
        output_price_per_mtok=_decimal(env, "INBOX_MODEL_OUTPUT_PRICE"),
    )


def _decimal(env: dict[str, str], name: str) -> Decimal | None:
    """A money-shaped setting, or `None`. `Decimal`, never `float`.

    Same rule as the shipped `item.cost_amount`: money that is almost right is
    wrong, and a budget compared with floating point drifts.
    """
    raw = env.get(name, "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as error:
        raise WeakConfiguration(f"{name} must be a decimal number; got {raw!r}") from error
    if value < 0:
        raise WeakConfiguration(f"{name} cannot be negative; got {raw!r}")
    return value


def resolve_inbox_settings(env: dict[str, str]) -> InboxSettings | None:
    """The inbox configuration, or `None` when this deployment has none.

    Three outcomes and no fourth: nothing set (the feature is off), all four
    required variables set and coherent (the feature is on), or a partial
    configuration — which raises rather than starting something half-wired.
    """
    present = {name for name in INBOX_ENVIRONMENT_VARIABLES if env.get(name, "").strip()}
    if not present:
        return None

    missing = sorted(set(INBOX_ENVIRONMENT_VARIABLES) - present)
    if missing:
        details = "\n".join(f"  - {name}: {INBOX_ENVIRONMENT_VARIABLES[name]}" for name in missing)
        raise WeakConfiguration(
            "The reservation inbox is partly configured, which is worse than not "
            f"configured: {sorted(present)} are set but these are not:\n{details}\n"
            "Set them, or unset every INBOX_* variable to run with the inbox off."
        )

    region = env["INBOX_AWS_REGION"].strip()
    topic_arn = env["INBOX_SNS_TOPIC_ARN"].strip()

    match = _SNS_TOPIC_ARN.match(topic_arn)
    if match is None:
        raise WeakConfiguration(
            f"INBOX_SNS_TOPIC_ARN is not an SNS topic ARN: {topic_arn!r}. Expected "
            "arn:aws:sns:<region>:<account-id>:<topic-name>."
        )
    if match.group(1) != region:
        # Caught here rather than at the first notification, where "no
        # notification ever arrives" is the symptom and nothing names the cause.
        raise WeakConfiguration(
            f"INBOX_SNS_TOPIC_ARN names region {match.group(1)!r} but INBOX_AWS_REGION is "
            f"{region!r}. The topic, the receipt rule and the bucket must be in one region."
        )

    raw_cap = env.get("INBOX_MAX_MESSAGE_BYTES", "").strip()
    if raw_cap and not raw_cap.isdigit():
        raise WeakConfiguration(
            f"INBOX_MAX_MESSAGE_BYTES must be a positive whole number of bytes; got {raw_cap!r}"
        )
    max_message_bytes = int(raw_cap) if raw_cap else DEFAULT_INBOX_MAX_MESSAGE_BYTES
    if max_message_bytes <= 0:
        raise WeakConfiguration("INBOX_MAX_MESSAGE_BYTES must be greater than zero")

    senders = frozenset(
        address.strip().lower()
        for address in env.get("INBOX_ALLOWED_SENDERS", "").split(",")
        if address.strip()
    )

    return InboxSettings(
        recipient=env["INBOX_RECIPIENT"].strip().lower(),
        aws_region=region,
        sns_topic_arn=topic_arn,
        s3_bucket=env["INBOX_S3_BUCKET"].strip(),
        s3_prefix=env.get("INBOX_S3_PREFIX", "").strip(),
        allowed_senders=senders,
        max_message_bytes=max_message_bytes,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return require_settings()
