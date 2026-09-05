"""Management commands.

The owner account is provisioned here rather than through a sign-up form: D15
says one user, and a public registration endpoint on an internet-facing app is
attack surface serving nobody. Adding registration later is an endpoint; removing
one after it has been reachable is not.

The recovery path for a forgotten password is re-running `create-owner` on the
server. That is honest at one user and must not be quietly relied on at two.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.config import get_settings
from trip_planner.db.models import Owner, normalise_email
from trip_planner.db.session import get_sessionmaker
from trip_planner.security.passwords import hash_password

MINIMUM_PASSWORD_LENGTH = 12


def read_password(prompt: Callable[[str], str] = getpass.getpass) -> str:
    """Read the password interactively, or from a pipe when stdin is not a terminal.

    It is never taken from argv: a command-line argument is visible in `ps`, in
    the shell history and in any process listing — three places a password should
    never be.
    """
    if not sys.stdin.isatty():
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise SystemExit("No password on stdin.")
        return password

    password = prompt("Password: ")
    confirmation = prompt("Repeat password: ")

    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    return password


def create_owner(
    db: OrmSession, *, email: str, password: str, locale: str = "pl", replace: bool = False
) -> Owner:
    normalised = normalise_email(email)

    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise SystemExit(
            f"Password must be at least {MINIMUM_PASSWORD_LENGTH} characters; "
            f"got {len(password)}."
        )

    existing = db.execute(
        sa.select(Owner).where(Owner.email == normalised)
    ).scalar_one_or_none()

    if existing is not None:
        if not replace:
            raise SystemExit(
                f"An owner with the address {normalised} already exists. "
                "Pass --replace to set a new password for it."
            )
        existing.password_hash = hash_password(password)
        db.flush()
        return existing

    owner = Owner(email=normalised, password_hash=hash_password(password), locale=locale)
    db.add(owner)
    db.flush()
    return owner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trip-planner")
    subcommands = parser.add_subparsers(dest="command", required=True)

    create = subcommands.add_parser(
        "create-owner",
        help="Create the owner account. The password is read from stdin, never from argv.",
    )
    create.add_argument("--email", required=True)
    create.add_argument("--locale", default="pl", choices=["pl", "en"])
    create.add_argument(
        "--replace",
        action="store_true",
        help="Set a new password for an existing owner rather than failing.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "create-owner":
        password = read_password()

        get_settings()  # fail fast and loudly when the environment is incomplete

        with get_sessionmaker()() as db:
            owner = create_owner(
                db,
                email=args.email,
                password=password,
                locale=args.locale,
                replace=args.replace,
            )
            db.commit()

            # The address is echoed; the password and its hash are not.
            print(f"Owner ready: {owner.email}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
