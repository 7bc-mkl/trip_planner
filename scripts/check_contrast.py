#!/usr/bin/env python3
"""Contrast check — part of the validation gate.

Computes the WCAG 2.1 relative-luminance contrast ratio for a declared table of
foreground/background pairs — the pairs the design system actually renders — and
fails when one falls below its class's floor: 4.5:1 for `body` text, 3:1 for
`large` text and non-text UI boundaries (focus rings, input borders).

The pairs are declared below, not inferred from CSS usage: inferring a pair from
`var()` usage would flag decorative or structural colour combinations that are
never read as text, and would miss a pair that is only ever expressed in inline
style props. `--secondary` (`#EA580C`) is deliberately absent from the table: the
spec defines it as a token that is never used behind text — white on `--secondary`
is 3.56:1, below both floors, and the design's own contract keeps it decorative
and boundary-only. `--hairline-strong` is also deliberately absent: it is the
elevation-2 hover border shift and the dashed dropzone border, neither of which
WCAG 1.4.11 requires to identify a component, so it stays at DESIGN.md's own
`#CBD5E1` uncorrected. `--field-border` is the token that actually needs the
3:1 floor — the resting input/select/textarea/date-input boundary, which *is*
required to identify the control — and it is in the table below, corrected.

`tokens.css` values are read literally, with one level of `var(--other)`
indirection resolved (`tokens.css`'s own bridge section aliases some names to
others). A value this script cannot resolve to a hex colour — not a hex literal,
not a single-level `var()` reference to one — is a loud failure, not a skip: a
silently-skipped pair is exactly the kind of failure a script like this exists to
catch.

The check is a no-op (exit 0) while the token file does not exist yet, so it is
safe to run against a repository that has not been scaffolded.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOKEN_FILE = Path("frontend/src/styles/tokens.css")

# The declared pairs: (foreground token, background token, class).
#
# class is "body" (>= 4.5:1, WCAG AA normal text) or "large" (>= 3:1, WCAG AA
# large text and non-text UI boundaries — SC 1.4.11).
#
# `--secondary` and `--hairline-strong` are intentionally not here — see the
# module docstring.
PAIRS: list[tuple[str, str, str]] = [
    # Reading text on the two neutral surfaces.
    ("--text", "--canvas", "body"),
    ("--text", "--surface", "body"),
    ("--text-muted", "--surface", "body"),
    ("--text-subtle", "--surface", "body"),
    # The primary button recipes, and the ghost button's text-on-surface case.
    ("--on-primary", "--primary", "body"),
    ("--on-primary", "--primary-deep", "body"),
    ("--primary", "--surface", "body"),  # ghost button text
    # The three status chips the spec's corrected table fixes.
    ("--status-confirmed-text", "--status-confirmed-bg", "body"),
    ("--status-progress-text", "--status-progress-bg", "body"),
    ("--status-draft-text", "--status-draft-bg", "body"),
    # The danger recipes.
    ("--on-danger", "--danger", "body"),
    ("--on-danger-surface", "--danger-surface", "body"),
    # UI boundaries: the resting field border and the two focus-ring recipes.
    ("--field-border", "--surface", "large"),
    ("--primary", "--canvas", "large"),
    ("--primary-fixed", "--primary-deep", "large"),  # dark-surface focus ring
]

THRESHOLDS = {"body": 4.5, "large": 3.0}

# `--name: value;` — the declaration. Matches inside a media-query `:root` too.
DECLARATION = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);")

HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
VAR_REFERENCE = re.compile(r"^var\(\s*(--[A-Za-z0-9_-]+)\s*\)$")


def parse_tokens(text: str) -> dict[str, str]:
    """Every `--name: value;` declaration in the token file, first-wins.

    First-wins matters for `--radius-md`, which the bridge section re-declares
    with a different meaning under the same name (a colour token is never
    re-declared like that, so this only matters for non-colour tokens this
    script never looks up).
    """
    tokens: dict[str, str] = {}
    for name, value in DECLARATION.findall(text):
        if name not in tokens:
            tokens[name] = value.strip()
    return tokens


def resolve_hex(name: str, tokens: dict[str, str]) -> str:
    """Resolve a token to a hex colour, following at most one `var()` hop."""
    if name not in tokens:
        print(f"check_contrast: '{name}' is not declared in {TOKEN_FILE}", file=sys.stderr)
        sys.exit(1)

    value = tokens[name]
    if HEX_COLOUR.match(value):
        return value

    ref = VAR_REFERENCE.match(value)
    if ref:
        ref_name = ref.group(1)
        ref_value = tokens.get(ref_name)
        if ref_value and HEX_COLOUR.match(ref_value):
            return ref_value
        print(
            f"check_contrast: '{name}' = '{value}' resolves to '{ref_name}' = "
            f"'{ref_value}', which is not a hex colour — cannot resolve",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"check_contrast: '{name}' = '{value}' is neither a hex colour nor a "
        f"single var() reference to one — cannot resolve",
        file=sys.stderr,
    )
    sys.exit(1)


def _channel(component: int) -> float:
    """sRGB channel -> linear-light channel, per the WCAG 2.1 formula."""
    fraction = component / 255.0
    if fraction <= 0.03928:
        return fraction / 12.92
    return ((fraction + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour: str) -> float:
    digits = hex_colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    lum_a, lum_b = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    if not TOKEN_FILE.is_file():
        print(f"check_contrast: {TOKEN_FILE} does not exist yet — nothing to check.")
        return 0

    tokens = parse_tokens(TOKEN_FILE.read_text(encoding="utf-8"))

    rows: list[tuple[str, str, str, float, float, bool]] = []
    for fg, bg, cls in PAIRS:
        fg_hex = resolve_hex(fg, tokens)
        bg_hex = resolve_hex(bg, tokens)
        ratio = contrast_ratio(fg_hex, bg_hex)
        threshold = THRESHOLDS[cls]
        rows.append((fg, bg, cls, ratio, threshold, ratio >= threshold))

    name_width = max(len(fg) for fg, _, _, _, _, _ in rows)
    bg_width = max(len(bg) for _, bg, _, _, _, _ in rows)
    header = (
        f"{'foreground':<{name_width}}  {'background':<{bg_width}}  "
        f"{'class':<6} {'ratio':>8}   {'min':>5}  result"
    )
    divider = "-" * len(header)
    lines = [header, divider]
    for fg, bg, cls, ratio, threshold, ok in rows:
        mark = "PASS" if ok else "FAIL"
        lines.append(
            f"{fg:<{name_width}}  {bg:<{bg_width}}  {cls:<6} "
            f"{ratio:>7.2f}:1  {threshold:>4.1f}:1  {mark}"
        )
    table = "\n".join(lines)

    errors = [
        f"{fg} on {bg}: {ratio:.2f}:1 < {threshold}:1 required ({cls})"
        for fg, bg, cls, ratio, threshold, ok in rows
        if not ok
    ]

    if errors:
        print(f"check_contrast: {len(errors)} problem(s) found\n", file=sys.stderr)
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        print(f"\n{table}", file=sys.stderr)
        print(
            f"\ncheck_contrast: every declared pair must meet its class's WCAG AA "
            f"floor (4.5:1 body, 3:1 large/UI boundary) — see PAIRS in this script",
            file=sys.stderr,
        )
        return 1

    print(table)
    print(f"\ncheck_contrast: OK — {len(rows)} pair(s) all meet WCAG AA against {TOKEN_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
