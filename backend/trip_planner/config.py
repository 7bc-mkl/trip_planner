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
}


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


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str

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

    return Settings(database_url=env["DATABASE_URL"].strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return require_settings()
