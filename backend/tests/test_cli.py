"""The create-owner management command.

The load-bearing assertion is the negative one: the password must not appear in
`sys.argv` or in anything the command prints. A password in argv is visible in
`ps`, in shell history and in any process listing.
"""

from __future__ import annotations

import io
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.cli import build_parser, create_owner, read_password
from trip_planner.db.models import Owner
from trip_planner.security.passwords import verify_password

PASSWORD = "a-sufficiently-long-password"


def test_the_password_is_not_accepted_on_the_command_line() -> None:
    """The absence of a --password flag is the feature, not an oversight.

    A password in argv is visible in `ps`, in shell history and in any process
    listing.
    """
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["create-owner", "--email", "o@example.com", "--password", PASSWORD]
        )


def test_the_email_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["create-owner"])


def test_a_valid_invocation_parses() -> None:
    args = build_parser().parse_args(["create-owner", "--email", "o@example.com"])
    assert args.email == "o@example.com"
    assert args.locale == "pl"
    assert args.replace is False


def test_the_password_is_read_from_a_pipe_when_stdin_is_not_a_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{PASSWORD}\n"))
    assert read_password() == PASSWORD


def test_an_empty_pipe_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit):
        read_password()


def test_mismatched_interactive_entries_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    answers = iter([PASSWORD, "something-else-entirely"])

    with pytest.raises(SystemExit):
        read_password(prompt=lambda _: next(answers))


def test_it_creates_an_owner_whose_password_verifies(db_session: OrmSession) -> None:
    owner = create_owner(db_session, email="Owner@Example.COM", password=PASSWORD)

    assert owner.email == "owner@example.com", "the address is normalised on write"
    assert verify_password(owner.password_hash, PASSWORD)


def test_the_plaintext_is_never_stored(db_session: OrmSession) -> None:
    create_owner(db_session, email="owner@example.com", password=PASSWORD)

    stored = db_session.execute(sa.select(Owner.password_hash)).scalar_one()
    assert PASSWORD not in stored
    assert stored.startswith("$argon2id$")


def test_a_short_password_is_refused(db_session: OrmSession) -> None:
    with pytest.raises(SystemExit):
        create_owner(db_session, email="owner@example.com", password="short")


def test_creating_a_duplicate_owner_is_refused(db_session: OrmSession) -> None:
    create_owner(db_session, email="owner@example.com", password=PASSWORD)

    with pytest.raises(SystemExit, match="already exists"):
        create_owner(db_session, email="OWNER@example.com", password=PASSWORD)


def test_replace_sets_a_new_password_on_the_existing_owner(db_session: OrmSession) -> None:
    """The documented recovery path for a forgotten password."""
    original = create_owner(db_session, email="owner@example.com", password=PASSWORD)
    original_hash = original.password_hash

    updated = create_owner(
        db_session, email="owner@example.com", password="a-brand-new-password", replace=True
    )

    assert updated.id == original.id, "it must not create a second account"
    assert updated.password_hash != original_hash
    assert verify_password(updated.password_hash, "a-brand-new-password")
    assert not verify_password(updated.password_hash, PASSWORD)


def test_the_command_output_never_contains_the_password(
    db_session: OrmSession, capsys: pytest.CaptureFixture[str]
) -> None:
    owner = create_owner(db_session, email="owner@example.com", password=PASSWORD)
    print(f"Owner ready: {owner.email}")

    captured = capsys.readouterr()
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err
    assert owner.password_hash not in captured.out
