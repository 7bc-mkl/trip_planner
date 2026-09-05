"""Application settings.

Every setting comes from the environment. `BACKWARD_COMPATIBILITY.md` §5 requires
a new required variable to fail loudly at startup naming itself, rather than
defaulting to something that half-works; `require_settings()` in this module is
that check, and `deploy/` calls it before the app takes traffic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    session_secret: str
    app_base_url: str
    environment: str

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
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return require_settings()
