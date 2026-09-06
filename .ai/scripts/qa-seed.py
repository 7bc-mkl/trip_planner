#!/usr/bin/env python3
"""Seed the QA environment with one realistic trip, so screenshots show a plan.

`.ai/scripts/test-env-up.sh` drops and recreates its database on every non-reused
run, which is the right default — QA must not inherit the previous run's data —
but it leaves the app with an empty trip list. Every screen worth photographing
(the timeline rail, the readiness counter, the filter bar, the day detail) needs
content, and clicking it in by hand is neither repeatable nor reviewable.

So: one dependency-free script, in the house style of `scripts/check_locales.py`,
that talks to the running app's own API exactly as the SPA does — same origin,
same session cookie, same CSRF double-submit. It fabricates nothing the product
would not accept through its own forms.

    python3 .ai/scripts/qa-seed.py [--base-url URL] [--allow-remote]

The base URL must be loopback unless `--allow-remote` is passed: this script
writes, and an ambient `QA_BASE_URL` pointed at a real origin would write there.

Idempotent: a trip with the same title is left alone rather than duplicated, so
re-running it after a warm `test-env-up.sh` is a no-op. The data is the brief's
own success test — the Malaysia trip of October 2026 (D10) — with items in all
three statuses and all five kinds, and one deliberately empty day, because an
empty day on the rail is a state the design has to render.
"""

from __future__ import annotations

import argparse

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESCRIPTOR = REPO_ROOT / ".ai" / "qa" / "test-env.json"
CREDENTIALS = REPO_ROOT / ".ai" / "qa" / "test-env.env"

TRIP_TITLE = "Malezja — Kuala Lumpur i Borneo"
START = date(2026, 10, 10)
END = date(2026, 10, 24)

STAGES = [
    {"place": "Kuala Lumpur", "start_date": "2026-10-10", "end_date": "2026-10-15"},
    {"place": "Kota Kinabalu", "start_date": "2026-10-16", "end_date": "2026-10-20"},
    {"place": "Sandakan", "start_date": "2026-10-21", "end_date": "2026-10-24"},
]

# (day offset, kind, status, start, end, title, notes)
ITEMS = [
    (0, "transport", "done", "06:10", "23:55", "WAW → KUL, LOT 7822 / MH 3", "Przesiadka w Dosze, 2 h 15 min."),
    (0, "accommodation", "done", "15:00", None, "Hotel Bukit Bintang", "Check-in od 15:00, śniadanie w cenie."),
    (1, "activity", "to_book", "09:30", "11:30", "Petronas Towers — skybridge", "Bilety tylko online, limit dzienny."),
    (1, "meal", "to_plan", "19:00", None, "Kolacja na Jalan Alor", None),
    (2, "activity", "to_book", "08:00", "17:00", "Batu Caves i Gombak", "Autobus 11 z Titiwangsa."),
    (4, "transport", "to_plan", "13:40", "16:25", "KUL → BKI", "Do sprawdzenia: bagaż rejestrowany."),
    (5, "accommodation", "to_book", "14:00", None, "Kota Kinabalu — nocleg przy nabrzeżu", None),
    (6, "activity", "to_plan", None, None, "Wyspy Tunku Abdul Rahman", "Zależne od pogody."),
    (8, "meal", "done", "20:00", None, "Targ rybny Filipino", "Zarezerwowane na dwie osoby."),
    (11, "transport", "to_book", "07:15", "08:05", "BKI → Sandakan", None),
    (11, "activity", "to_plan", "10:00", "12:00", "Sepilok — ośrodek orangutanów", "Karmienie o 10:00 i 15:00."),
    (13, "other", "to_plan", None, None, "Pamiątki i pakowanie", None),
    (14, "transport", "to_book", "18:30", None, "Sandakan → KUL → WAW", "Wylot powrotny."),
]


def fail(message: str) -> None:
    print(f"qa-seed: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_loopback(base_url: str) -> None:
    """Refuse to seed anything that is not the local QA environment.

    The base URL can come from `--base-url` or from an ambient `QA_BASE_URL`,
    both of which override the descriptor silently. This script logs in with the
    credentials sitting next to it and then CREATES a trip and thirteen items; if
    the URL ever pointed at a real deployment, it would write fabricated QA data
    into somebody's actual plan. The guard is a hostname check, and the opt-out
    is explicit rather than an environment variable, so it cannot be inherited.
    """
    host = (urllib.parse.urlsplit(base_url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return
    fail(
        f"refusing to seed '{base_url}': host '{host or base_url}' is not loopback. "
        f"Pass --allow-remote if you genuinely mean to write test data there."
    )


def read_base_url() -> str:
    if not DESCRIPTOR.exists():
        fail(f"{DESCRIPTOR} is missing — run `sh .ai/scripts/test-env-up.sh` first.")
    return json.loads(DESCRIPTOR.read_text(encoding="utf-8"))["baseUrl"]


def read_credentials() -> tuple[str, str]:
    if not CREDENTIALS.exists():
        fail(f"{CREDENTIALS} is missing — run `sh .ai/scripts/test-env-up.sh` first.")
    values: dict[str, str] = {}
    for line in CREDENTIALS.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    try:
        return values["TEST_OWNER_EMAIL"], values["TEST_OWNER_PASSWORD"]
    except KeyError as missing:
        fail(f"{CREDENTIALS} does not define {missing}.")
        raise  # unreachable; keeps the type checker honest


class Client:
    """The SPA's fetch client, in twenty lines: cookies plus the CSRF double-submit.

    The jar is a plain dict rather than `http.cookiejar` because there are exactly
    two cookies with one path between them; the standard jar's domain and policy
    machinery buys nothing against an IP-literal host and hides which header was
    actually sent when something goes wrong.
    """

    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/") + "/api/v1"
        self.cookies: dict[str, str] = {}
        self.opener = urllib.request.build_opener()

    def _store(self, response: object) -> None:
        for raw in response.headers.get_all("Set-Cookie") or []:  # type: ignore[attr-defined]
            pair = raw.split(";", 1)[0]
            name, _, value = pair.partition("=")
            self.cookies[name.strip()] = value.strip()

    def call(
        self, method: str, path: str, body: object | None = None, *, _quiet: bool = False
    ) -> object:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if method not in {"GET", "HEAD", "OPTIONS"} and "csrf_token" in self.cookies:
            headers["X-CSRF-Token"] = self.cookies["csrf_token"]
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                self._store(response)
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:400]
            if _quiet and error.code == 401:
                raise PermissionError(detail) from error
            fail(f"{method} {path} → {error.code}: {detail}")
            raise  # unreachable
        return json.loads(raw) if raw else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None, help="defaults to .ai/qa/test-env.json")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="permit a non-loopback base URL; off by default, and never taken from the environment",
    )
    args = parser.parse_args()

    base_url = args.base_url or os.environ.get("QA_BASE_URL") or read_base_url()
    if not args.allow_remote:
        require_loopback(base_url)
    email, password = read_credentials()

    client = Client(base_url)
    client.call("GET", "/health")
    client.call("POST", "/auth/login", {"email": email, "password": password})

    # `login` answers 204 before its request transaction commits: FastAPI exits a
    # `yield` dependency — here `get_db`, which owns the commit — after the
    # response has gone out. A client fast enough to reuse the cookie inside that
    # window is answered 401 by a server that has already accepted it. A browser
    # never is; two dependency-free scripts in a row were, every time. Waiting for
    # the session to become visible is the caller's business, not a reason to
    # change the API, so this polls rather than sleeping blind.
    existing = None
    for attempt in range(20):
        try:
            existing = client.call("GET", "/trips", _quiet=True)
            break
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))
    if existing is None:
        fail("the session never became visible — GET /trips kept answering 401.")
    assert isinstance(existing, list)
    for trip in existing:
        if trip["title"] == TRIP_TITLE:
            print(f"qa-seed: trip already present ({trip['id']}); nothing to do.")
            print(f"TRIP_ID: {trip['id']}")
            print(f"BASE_URL: {base_url}")
            return 0

    trip = client.call(
        "POST",
        "/trips",
        {
            "title": TRIP_TITLE,
            "start_date": START.isoformat(),
            "end_date": END.isoformat(),
            "departure_place": "Warszawa",
            "return_place": "Warszawa",
            "stages": STAGES,
        },
    )
    assert isinstance(trip, dict)
    trip_id = trip["id"]

    for offset, kind, status, start_time, end_time, title, notes in ITEMS:
        day = (START + timedelta(days=offset)).isoformat()
        client.call(
            "POST",
            f"/trips/{trip_id}/days/{day}/items",
            {
                "kind": kind,
                "status": status,
                "start_time": None if start_time is None else f"{start_time}:00",
                "end_time": None if end_time is None else f"{end_time}:00",
                "end_date": None,
                "title": title,
                "notes": notes,
            },
        )

    print(f"qa-seed: seeded {len(ITEMS)} items across {(END - START).days + 1} days.")
    print(f"TRIP_ID: {trip_id}")
    print(f"BASE_URL: {base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
