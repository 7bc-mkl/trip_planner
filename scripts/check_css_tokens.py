#!/usr/bin/env python3
"""CSS token completeness check — part of the validation gate.

Fails when a `var(--name)` reference under `frontend/src` (plus the SPA's
`frontend/index.html`) names a custom property that nothing in reach defines.
An undefined `var()` does not raise, does not warn and does not show up in a
type check: the declaration is simply dropped and the screen quietly loses a
colour, a radius or a whole layout. This is the gate that catches it, and it is
the guard at both ends of the compatibility bridge's life — the bridge is one
block in the token file, and deleting it must not leave a dangling reference
behind.

A name counts as defined when either is true:

    it is declared in frontend/src/styles/tokens.css   the canonical token file
    it is declared in the same file as the reference   a locally scoped value

THE SECOND CONDITION IS PER-FILE ON PURPOSE. "Declared anywhere under
`frontend/src`" was the original rule and it made the gate a false negative: a
`--foo` set on one selector in `base.css` satisfied a `var(--foo)` written on an
unrelated, non-inheriting selector in `screens.css`, which is exactly the
silently-dropped declaration this script exists to catch. Per-file is still an
approximation — custom properties inherit down the DOM, not down a file — but it
is a conservative one in the direction that matters: it can ask for a
declaration that a stricter reading would not need, and it cannot miss a name
that nothing near the reference defines. Where a rule legitimately reads a
property another file sets on the same element, declare the default beside it;
that is a defined initial value, not a duplicate.

`var()` fallbacks are read correctly: in `var(--a, var(--b, 1rem))` both `--a`
and `--b` are references, and `1rem` is not. References are matched over the
whole file rather than line by line, so a `var(` broken across lines by the
formatter is still seen.

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

# The SPA's shell. It is outside `src/` but it is shipped, and a `style="--x: …"`
# or a `var()` in its inline critical CSS fails exactly as quietly as one in a
# component would.
EXTRA_SOURCES = (Path("frontend/index.html"),)

# The design contract. Every token a rule may reference is declared here.
TOKEN_FILE = SOURCE_ROOT / "styles" / "tokens.css"

# `var(--name` — the reference. Matches inside fallbacks too, since a nested
# `var()` is itself a match.
VAR_REFERENCE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")

# `--name:` — the declaration, in CSS or in an inline style object.
VAR_DECLARATION = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")


def source_files(root: Path) -> list[Path]:
    """Every source file that may carry tokens, sorted."""
    under_root = (
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    )
    extra = (path for path in EXTRA_SOURCES if path.is_file())
    return sorted({*under_root, *extra})


def declared_names(path: Path) -> set[str]:
    """Every custom property declared in one file."""
    return set(VAR_DECLARATION.findall(path.read_text(encoding="utf-8")))


def references(path: Path) -> list[tuple[str, int]]:
    """Every `var(--name)` reference in one file, as (name, line).

    Matched against the whole text rather than line by line: a formatter is free
    to break `var(\n  --name)` across lines, and a per-line scan would not only
    miss the reference but miss it silently, which is the failure mode this
    script exists to remove.
    """
    text = path.read_text(encoding="utf-8")
    return [
        (match.group(1), text.count("\n", 0, match.start()) + 1)
        for match in VAR_REFERENCE.finditer(text)
    ]


def main() -> int:
    if not TOKEN_FILE.is_file():
        print(f"check_css_tokens: {TOKEN_FILE} does not exist yet — nothing to check.")
        return 0

    paths = source_files(SOURCE_ROOT)
    tokens = declared_names(TOKEN_FILE)

    total = 0
    errors: list[str] = []
    for path in paths:
        local = declared_names(path)
        for name, number in references(path):
            total += 1
            if name not in tokens and name not in local:
                errors.append(
                    f"{path}:{number}: '{name}' is referenced but is neither a token "
                    f"nor declared in this file"
                )

    if errors:
        print(f"check_css_tokens: {len(errors)} problem(s) found\n", file=sys.stderr)
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        print(
            f"\ncheck_css_tokens: every var(--name) must resolve — declare it in "
            f"{TOKEN_FILE}, or in the same file as the reference",
            file=sys.stderr,
        )
        return 1

    print(
        f"check_css_tokens: OK — {total} var() reference(s) across {len(paths)} file(s) "
        f"all resolve against {TOKEN_FILE} or their own file"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
