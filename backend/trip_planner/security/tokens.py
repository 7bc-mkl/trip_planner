"""Opaque session tokens and CSRF tokens.

The session token is 256 bits of `secrets` randomness handed to the browser in a
cookie. The database stores only its keyed HMAC-SHA256 digest, so a database dump
does not yield a usable session (spec, session table) — and because the digest is
keyed by `SESSION_SECRET` rather than a bare SHA-256, an attacker holding the dump
cannot even confirm a guessed token offline without also holding the secret.

Rotating `SESSION_SECRET` invalidates every session, which is the intended and
documented way to sign everyone out.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

#: 256 bits, per the spec's session table.
TOKEN_BYTES = 32


def generate_token() -> str:
    """A new opaque token. URL-safe so it survives a cookie value unencoded."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str, *, secret: str) -> str:
    """The stored form of a token: HMAC-SHA256 under the application secret."""
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), sha256).hexdigest()


def tokens_equal(left: str, right: str) -> bool:
    """Constant-time comparison.

    `==` on a string short-circuits at the first differing byte, which leaks the
    length of the matching prefix to anyone who can time the comparison.
    """
    return hmac.compare_digest(left, right)


def generate_csrf_token() -> str:
    """A CSRF token for the double-submit pair.

    Unlike the session token this one is readable by JavaScript by design: the
    SPA copies it from a non-HttpOnly cookie into a request header, and the
    server checks the two match. It is random rather than derived from the
    session so that reading it tells an attacker nothing about the session token.
    """
    return secrets.token_urlsafe(TOKEN_BYTES)
