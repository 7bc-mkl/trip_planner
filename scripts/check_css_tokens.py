#!/usr/bin/env python3
"""CSS token completeness check — part of the validation gate.

Fails when a `var(--name)` reference under `frontend/src` names a custom
property that nothing defines. An undefined `var()` does not raise, does not
warn and does not show up in a type check: the declaration is simply dropped
and the screen quietly loses a colour, a radius or a whole layout. This is the
gate that catches it, and it is the guard at both ends of the compatibility
bridge's life — the bridge is one block in the token file, and deleting it must
not leave a dangling reference behind.

A name counts as defined when the design contract declares it:

    frontend/src/styles/tokens.css      the canonical token file

…or when it is declared locally anywhere under `frontend/src` — a component
that scopes its own `--x: …` on an element is legitimate and is not a token.

`var()` fallbacks are read correctly: in `var(--a, var(--b, 1rem))` both `--a`
and `--b` are references, and `1rem` is not.

The check is a no-op (exit 0) while the token file does not exist yet, so it is
safe to run against a repository that has not been scaffolded.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Where references are collected from, and which file extensions carry them.
SOURCE_ROOT = Path("frontend/src")
SOURCE_SUFFIXES = {".css", ".ts", ".tsx"}

# The design contract. Every token a rule may reference is declared here.
TOKEN_FILE = SOURCE_ROOT / "styles" / "tokens.css"

# `var(--name` — the reference. Matches inside fallbacks too, since a nested
# `var()` is itself a match.
VAR_REFERENCE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")

# `--name:` — the declaration, in CSS or in an inline style object.
VAR_DECLARATION = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")


def source_files(root: Path) -> list[Path]:
    """Every source file under a root that may carry tokens, sorted."""
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    )


def declared_names(paths: list[Path]) -> set[str]:
    """Every custom property declared anywhere in the given files."""
    names: set[str] = set()
    for path in paths:
        names.update(VAR_DECLARATION.findall(path.read_text(encoding="utf-8")))
    return names


def references(paths: list[Path]) -> list[tuple[str, Path, int]]:
    """Every `var(--name)` reference, as (name, file, line)."""
    found: list[tuple[str, Path, int]] = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in VAR_REFERENCE.findall(line):
                found.append((name, path, number))
    return found


def main() -> int:
    if not TOKEN_FILE.is_file():
        print(f"check_css_tokens: {TOKEN_FILE} does not exist yet — nothing to check.")
        return 0

    paths = source_files(SOURCE_ROOT)
    defined = declared_names(paths)

    found = references(paths)

    errors: list[str] = []
    for name, path, number in found:
        if name not in defined:
            errors.append(f"{path}:{number}: '{name}' is referenced but never defined")

    if errors:
        print(f"check_css_tokens: {len(errors)} problem(s) found\n", file=sys.stderr)
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        print(
            f"\ncheck_css_tokens: every var(--name) must resolve — declare it in "
            f"{TOKEN_FILE}, or locally on the element that owns it",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_css_tokens: OK — {len(found)} var() reference(s) across {len(paths)} file(s) "
        f"all resolve against {TOKEN_FILE}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
