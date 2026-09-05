"""Password hashing and token primitives."""

from __future__ import annotations

import re

import pytest

from trip_planner.security.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    verify_password,
)
from trip_planner.security.tokens import (
    TOKEN_BYTES,
    generate_csrf_token,
    generate_token,
    hash_token,
    tokens_equal,
)

SECRET = "a" * 48


class TestPasswords:
    def test_a_correct_password_verifies(self) -> None:
        assert verify_password(hash_password("correct horse"), "correct horse")

    def test_a_wrong_password_does_not(self) -> None:
        assert not verify_password(hash_password("correct horse"), "wrong horse")

    def test_the_hash_is_argon2id(self) -> None:
        assert hash_password("x").startswith("$argon2id$")

    def test_the_same_password_hashes_differently_every_time(self) -> None:
        """A per-hash salt: two owners with the same password must not look alike."""
        assert hash_password("same") != hash_password("same")

    def test_the_plaintext_never_appears_in_the_hash(self) -> None:
        assert "hunter2" not in hash_password("hunter2")

    @pytest.mark.parametrize("corrupt", ["", "not-a-hash", "$argon2id$broken"])
    def test_a_corrupt_hash_returns_false_rather_than_raising(self, corrupt: str) -> None:
        """A 500 here would tell an attacker the stored hash is malformed."""
        assert verify_password(corrupt, "anything") is False

    def test_the_dummy_hash_is_a_real_verifiable_argon2_hash(self) -> None:
        """It must cost the same as a real one, or it does not hide anything."""
        assert DUMMY_HASH.startswith("$argon2id$")
        assert verify_password(DUMMY_HASH, "not the dummy password") is False

    def test_needs_rehash_is_false_for_a_fresh_hash(self) -> None:
        assert needs_rehash(hash_password("x")) is False

    def test_needs_rehash_tolerates_a_corrupt_hash(self) -> None:
        assert needs_rehash("garbage") is False


class TestTokens:
    def test_a_token_carries_the_full_entropy(self) -> None:
        token = generate_token()
        # url-safe base64 of 32 bytes, padding stripped
        assert len(token) >= (TOKEN_BYTES * 4) // 3
        assert re.fullmatch(r"[A-Za-z0-9_-]+", token)

    def test_tokens_are_unique(self) -> None:
        assert len({generate_token() for _ in range(200)}) == 200

    def test_the_stored_form_is_not_the_token(self) -> None:
        token = generate_token()
        assert hash_token(token, secret=SECRET) != token

    def test_hashing_is_deterministic_under_one_secret(self) -> None:
        token = generate_token()
        assert hash_token(token, secret=SECRET) == hash_token(token, secret=SECRET)

    def test_a_different_secret_gives_a_different_digest(self) -> None:
        """This is what makes rotating SESSION_SECRET a global sign-out."""
        token = generate_token()
        assert hash_token(token, secret=SECRET) != hash_token(token, secret="b" * 48)

    def test_the_digest_is_not_a_bare_sha256_of_the_token(self) -> None:
        """A keyed digest means a stolen dump cannot be attacked offline alone."""
        from hashlib import sha256

        token = generate_token()
        assert hash_token(token, secret=SECRET) != sha256(token.encode()).hexdigest()

    def test_tokens_equal_matches_and_rejects(self) -> None:
        assert tokens_equal("abc", "abc")
        assert not tokens_equal("abc", "abd")
        assert not tokens_equal("abc", "abcd")

    def test_csrf_tokens_are_random_and_distinct_from_session_tokens(self) -> None:
        assert generate_csrf_token() != generate_csrf_token()
