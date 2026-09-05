#!/usr/bin/env python3
"""Locale parity check — part of the validation gate.

Fails when a translation key exists in the reference locale but is missing
(or left empty) in another required locale, or vice versa. This is the gate
that stops a PR from shipping an English-only string into a PL+EN product.

Supports two common layouts per locale root:

    <root>/en.json, <root>/pl.json                 (single file per locale)
    <root>/en/common.json, <root>/pl/common.json   (namespaced per locale)

The check is a no-op (exit 0) while a locale root does not exist yet, so it
is safe to run against a repository that has not been scaffolded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Locale roots to check. Add a root here when a new translated surface appears.
LOCALE_ROOTS = [
    Path("frontend/src/locales"),
    Path("backend/trip_planner/locales"),
]

# Every locale the product must ship. The reference supplies the key set.
REQUIRED_LOCALES = ["en", "pl"]
REFERENCE_LOCALE = "en"


def flatten(value: object, prefix: str = "") -> dict[str, object]:
    """Flatten nested JSON into dotted keys -> leaf values."""
    flat: dict[str, object] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            flat.update(flatten(child, f"{prefix}.{key}" if prefix else str(key)))
    else:
        flat[prefix] = value
    return flat


def load_locale(root: Path, locale: str) -> dict[str, object] | None:
    """Load one locale from a root, or None when it is absent."""
    single = root / f"{locale}.json"
    if single.is_file():
        return flatten(json.loads(single.read_text(encoding="utf-8")))

    namespaced = root / locale
    if namespaced.is_dir():
        flat: dict[str, object] = {}
        for path in sorted(namespaced.rglob("*.json")):
            namespace = path.relative_to(namespaced).with_suffix("").as_posix().replace("/", ".")
            flat.update(flatten(json.loads(path.read_text(encoding="utf-8")), namespace))
        return flat

    return None


def is_untranslated(value: object) -> bool:
    return isinstance(value, str) and not value.strip()


def check_root(root: Path) -> list[str]:
    errors: list[str] = []
    loaded: dict[str, dict[str, object]] = {}

    for locale in REQUIRED_LOCALES:
        keys = load_locale(root, locale)
        if keys is None:
            errors.append(f"{root}: required locale '{locale}' has no {locale}.json or {locale}/ directory")
            continue
        loaded[locale] = keys

    reference = loaded.get(REFERENCE_LOCALE)
    if reference is None:
        return errors

    for locale, keys in loaded.items():
        if locale == REFERENCE_LOCALE:
            continue
        missing = sorted(set(reference) - set(keys))
        extra = sorted(set(keys) - set(reference))
        empty = sorted(key for key, value in keys.items() if is_untranslated(value))
        for key in missing:
            errors.append(f"{root}: '{locale}' is missing key '{key}' (present in '{REFERENCE_LOCALE}')")
        for key in extra:
            errors.append(f"{root}: '{locale}' has key '{key}' that '{REFERENCE_LOCALE}' does not define")
        for key in empty:
            errors.append(f"{root}: '{locale}' leaves key '{key}' empty — untranslated")

    empty_reference = sorted(key for key, value in reference.items() if is_untranslated(value))
    for key in empty_reference:
        errors.append(f"{root}: '{REFERENCE_LOCALE}' leaves key '{key}' empty — untranslated")

    return errors


def main() -> int:
    existing = [root for root in LOCALE_ROOTS if root.is_dir()]
    if not existing:
        print("check_locales: no locale roots present yet — nothing to check.")
        print(f"check_locales: expected one of {', '.join(str(r) for r in LOCALE_ROOTS)}")
        return 0

    errors: list[str] = []
    for root in existing:
        errors.extend(check_root(root))

    if errors:
        print(f"check_locales: {len(errors)} problem(s) found\n", file=sys.stderr)
        for error in errors:
            print(f"  ✗ {error}", file=sys.stderr)
        print(
            f"\ncheck_locales: every key must exist, non-empty, in all of: {', '.join(REQUIRED_LOCALES)}",
            file=sys.stderr,
        )
        return 1

    checked = ", ".join(str(root) for root in existing)
    print(f"check_locales: OK — {', '.join(REQUIRED_LOCALES)} in sync across {checked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
