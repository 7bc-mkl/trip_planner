"""The owner / session / login_attempt schema.

These assert against the *database*, not against the model classes: the point of
a CHECK constraint and a functional unique index is that they hold even when a
future write path forgets the rule, so a test that only exercises Python would
be testing the wrong layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import LoginAttempt, Owner, Session, normalise_email


def make_owner(email: str = "owner@example.com", **overrides: object) -> Owner:
    values: dict[str, object] = {
        "email": normalise_email(email),
        "password_hash": "argon2-placeholder",
    }
    values.update(overrides)
    return Owner(**values)


def test_owner_round_trips(db_session: OrmSession) -> None:
    owner = make_owner()
    db_session.add(owner)
    db_session.flush()

    assert owner.id is not None
    assert owner.locale == "pl"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("owner@example.com", "OWNER@example.com"),
        ("Owner@Example.COM", "owner@example.com"),
    ],
)
def test_two_emails_differing_only_in_case_collide(
    db_session: OrmSession, first: str, second: str
) -> None:
    """The functional unique index, asserted without the application's normalisation.

    Inserting the raw values is the point: this proves the *database* refuses the
    duplicate, so a write path that forgot `normalise_email` cannot create two
    owners for one address.
    """
    db_session.execute(
        sa.text("INSERT INTO owner (id, email, password_hash) VALUES (:id, :email, 'x')"),
        {"id": uuid.uuid4(), "email": first},
    )
    db_session.flush()

    with pytest.raises(sa.exc.IntegrityError):
        db_session.execute(
            sa.text("INSERT INTO owner (id, email, password_hash) VALUES (:id, :email, 'x')"),
            {"id": uuid.uuid4(), "email": second},
        )
        db_session.flush()


def test_locale_check_constraint_rejects_an_unsupported_language(db_session: OrmSession) -> None:
    with pytest.raises(sa.exc.IntegrityError):
        db_session.execute(
            sa.text(
                "INSERT INTO owner (id, email, password_hash, locale) "
                "VALUES (:id, 'de@example.com', 'x', 'de')"
            ),
            {"id": uuid.uuid4()},
        )
        db_session.flush()


def test_password_hash_never_reaches_a_repr(db_session: OrmSession) -> None:
    """A hash in a log line is a hash in an incident report."""
    owner = make_owner(password_hash="$argon2id$v=19$m=65536,t=3,p=4$SECRETSECRET")
    db_session.add(owner)
    db_session.flush()

    assert "SECRETSECRET" not in repr(owner)
    assert "argon2id" not in repr(owner)


def test_session_token_hash_never_reaches_a_repr(db_session: OrmSession) -> None:
    owner = make_owner()
    db_session.add(owner)
    db_session.flush()

    session = Session(
        owner_id=owner.id,
        token_hash="TOKENHASHSECRET",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(session)
    db_session.flush()

    assert "TOKENHASHSECRET" not in repr(session)


def test_deleting_the_owner_cascades_to_sessions(db_session: OrmSession) -> None:
    owner = make_owner()
    db_session.add(owner)
    db_session.flush()

    db_session.add(
        Session(
            owner_id=owner.id,
            token_hash="hash",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    db_session.flush()

    db_session.execute(sa.delete(Owner).where(Owner.id == owner.id))
    db_session.flush()

    assert db_session.execute(sa.select(sa.func.count()).select_from(Session)).scalar() == 0


def test_login_attempt_stores_a_real_ip_type(db_session: OrmSession) -> None:
    """INET, not TEXT — so a malformed address is refused by the column."""
    db_session.add(LoginAttempt(email_normalised="owner@example.com", source_ip="203.0.113.7"))
    db_session.flush()

    with pytest.raises(sa.exc.DataError):
        db_session.execute(
            sa.text(
                "INSERT INTO login_attempt (email_normalised, source_ip) "
                "VALUES ('a@b.c', 'not-an-ip')"
            )
        )
        db_session.flush()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("  Owner@Example.COM  ", "owner@example.com"),
        ("owner@example.com", "owner@example.com"),
    ],
)
def test_normalise_email(given: str, expected: str) -> None:
    assert normalise_email(given) == expected
