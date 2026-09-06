"""Password hashing.

Argon2id via `argon2-cffi` (spec, owner table). The parameters are the library's
current defaults rather than hand-tuned constants: they track the maintainers'
reading of the RFC 9106 guidance, and a number frozen here would silently rot.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

#: A valid Argon2id hash of a value nothing will ever submit. Verifying against it
#: costs the same as a real verification, which is what lets the login handler do
#: identical work for an unknown e-mail as for a wrong password.
DUMMY_HASH = _hasher.hash("a password no account has")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password, returning False rather than raising on any mismatch.

    Every failure mode collapses to False on purpose: the caller must not be able
    to tell "wrong password" from "corrupt hash" from "unknown user", because
    that distinction is exactly what user enumeration is built out of.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with weaker parameters than today's defaults."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False
