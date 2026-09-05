"""The brief's own success flow, walked end to end.

Phase 4 step 6. Every other test in this suite checks one rule; this one checks
that the rules *compose* — that a person can actually get from signing in to
reading the number the product exists to show, without any step contradicting
another.

The path is the brief's, not an invented one:

    log in → create a three-stage open-jaw trip → add items across several days,
    including one overnight flight → set statuses → read the counter →
    filter to what is outstanding

It runs against the real application over a real PostgreSQL database: the same
routers, dependencies, exception handlers and cookie policy the deployed image
serves. What it does not exercise is the browser — the SPA's own walk of this
path is covered by the component tests, and the screenshots from the deployed
instance are attached to the implementation PR.

`assert` messages here name the *product* consequence rather than the mechanic,
because when this test fails the useful question is which promise broke.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from trip_planner.domain.readiness import readiness

API = "/api/v1"
TRIPS = f"{API}/trips"

#: The owner's own trip from the brief: Warsaw out, Malaysia, home via Katowice.
MALAYSIA = {
    "title": "Malezja, październik 2026",
    "start_date": "2026-10-10",
    "end_date": "2026-10-24",
    "departure_place": "Warszawa",
    # Different from the departure place — an open-jaw trip (R03, D06).
    "return_place": "Katowice",
    "stages": [
        {"place": "Kuala Lumpur", "start_date": "2026-10-11", "end_date": "2026-10-15"},
        {"place": "Penang", "start_date": "2026-10-15", "end_date": "2026-10-19"},
        {"place": "Langkawi", "start_date": "2026-10-19", "end_date": "2026-10-23"},
    ],
}


class TestTheBriefsSuccessFlow:
    def test_the_whole_path(self, client: TestClient, owner, owner_password: str) -> None:
        from trip_planner.security.sessions import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

        # ── 1. Log in ────────────────────────────────────────────────────────
        signed_in = client.post(
            f"{API}/auth/login", json={"email": owner.email, "password": owner_password}
        )
        assert signed_in.status_code == 204, "the owner cannot get in at all"
        client.headers[CSRF_HEADER_NAME] = client.cookies.get(CSRF_COOKIE_NAME, "")

        assert client.get(f"{API}/auth/me").status_code == 200

        # ── 2. Create the three-stage open-jaw trip ──────────────────────────
        created = client.post(TRIPS, json=MALAYSIA)
        assert created.status_code == 201, created.text
        trip = created.json()
        trip_id = trip["id"]

        assert len(trip["stages"]) == 3, "R03: a multi-stop trip keeps all its bases"
        assert trip["return_place"] != trip["departure_place"], (
            "the open-jaw mode is what D06 requires the model to carry"
        )
        assert len(trip["days"]) == 15, "10 to 24 October inclusive — the empty timeline"
        assert trip["readiness"] == {"arranged": 0, "tracked": 0}, (
            "a brand-new trip has decided nothing yet"
        )

        # The 15th is the travel day Kuala Lumpur and Penang share.
        travel_day = next(day for day in trip["days"] if day["date"] == "2026-10-15")
        assert len(travel_day["stage_ids"]) == 2, (
            "a day two stages both contain is the travel day between them"
        )

        # ── 3. Add items across several days, including the overnight flight ─
        flight = self.add(
            client,
            trip_id,
            "2026-10-10",
            kind="transport",
            title="LOT LO79 WAW → KUL",
            start_time="23:50",
            end_time="14:00",
            # Leaves on the 10th, lands on the 11th. One item, not two halves.
            end_date="2026-10-11",
            status="done",
        )
        assert flight["end_date"] == "2026-10-11"

        hotel = self.add(
            client,
            trip_id,
            "2026-10-11",
            kind="accommodation",
            title="Nocleg: Mandarin Oriental KL",
            end_date="2026-10-15",
            status="to_book",
        )
        batu_caves = self.add(
            client,
            trip_id,
            "2026-10-12",
            kind="activity",
            title="Batu Caves",
            start_time="09:00",
            end_time="12:00",
        )
        self.add(client, trip_id, "2026-10-12", kind="meal", title="Jalan Alor")
        ferry = self.add(
            client,
            trip_id,
            "2026-10-19",
            kind="transport",
            title="Prom na Langkawi",
            start_time="08:30",
        )

        # ── 4. Set statuses ──────────────────────────────────────────────────
        assert self.patch(client, trip_id, hotel["id"], status="done")["status"] == "done"
        assert self.patch(client, trip_id, ferry["id"], status="to_book")["status"] == "to_book"

        # ── 5. Read the counter ──────────────────────────────────────────────
        timeline = client.get(f"{TRIPS}/{trip_id}").json()
        every_item = [item for day in timeline["days"] for item in day["items"]]

        assert len(every_item) == 5, (
            "the spanning flight and hotel are each one item, rendered once on "
            "their start day — not split across the days they cover"
        )
        # flight done, hotel done, ferry to_book, Batu Caves and Jalan Alor to_plan
        assert timeline["readiness"] == {"arranged": 2, "tracked": 3}, (
            "R02: to_plan items stay out of both halves of the fraction"
        )
        arranged, tracked = readiness(_Status(item["status"]) for item in every_item)
        assert timeline["readiness"] == {"arranged": arranged, "tracked": tracked}, (
            "the served counter and the domain function must not drift apart"
        )

        row = next(
            candidate for candidate in client.get(TRIPS).json() if candidate["id"] == trip_id
        )
        assert row["readiness"] == timeline["readiness"], (
            "the trip list and the timeline must agree about the same trip"
        )

        # ── 6. Filter to what is outstanding ─────────────────────────────────
        # The filter is applied in the browser over this complete payload (A11),
        # so what the API has to guarantee is that the payload supports it.
        outstanding = [item for item in every_item if item["status"] != "done"]

        assert sorted(item["title"] for item in outstanding) == [
            "Batu Caves",
            "Jalan Alor",
            "Prom na Langkawi",
        ], "outstanding is status != done — both to_plan and to_book"
        assert timeline["readiness"] == {"arranged": 2, "tracked": 3}, (
            "filtering never moves the counter"
        )

        # ── And the plan is still navigable day by day ───────────────────────
        day = client.get(f"{TRIPS}/{trip_id}/days/2026-10-12").json()
        assert [item["title"] for item in day["items"]] == ["Batu Caves", "Jalan Alor"], (
            "the untimed meal sorts after the timed activity, not before breakfast"
        )
        assert day["previous_date"] == "2026-10-11"
        assert day["next_date"] == "2026-10-13"
        assert [stage["place"] for stage in day["stages"]] == ["Kuala Lumpur"]

        assert batu_caves["status"] == "to_plan", "a new item starts undecided"

    def test_the_plan_is_private_to_its_owner(
        self, client: TestClient, owner, owner_password: str
    ) -> None:
        """R08, at the end of the flow: none of the above is reachable signed out.

        The success flow is only a success if the plan it produced is the owner's
        alone — a public deployment (D14) makes that the difference between a tool
        and a leak.
        """
        from trip_planner.security.sessions import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

        client.post(f"{API}/auth/login", json={"email": owner.email, "password": owner_password})
        client.headers[CSRF_HEADER_NAME] = client.cookies.get(CSRF_COOKIE_NAME, "")
        trip_id = client.post(TRIPS, json=MALAYSIA).json()["id"]

        client.post(f"{API}/auth/logout")

        assert client.get(TRIPS).status_code == 401
        assert client.get(f"{TRIPS}/{trip_id}").status_code == 401
        assert client.get(f"{TRIPS}/{trip_id}/days/2026-10-12").status_code == 401

    # ── helpers ─────────────────────────────────────────────────────────────

    def add(self, client: TestClient, trip_id: str, day: str, **fields: object) -> dict:
        response = client.post(f"{TRIPS}/{trip_id}/days/{day}/items", json=fields)
        assert response.status_code == 201, response.text
        return response.json()

    def patch(self, client: TestClient, trip_id: str, item_id: str, **fields: object) -> dict:
        response = client.patch(f"{TRIPS}/{trip_id}/items/{item_id}", json=fields)
        assert response.status_code == 200, response.text
        return response.json()


class _Status:
    """Minimal stand-in so the domain function can run over the JSON payload."""

    def __init__(self, status: str) -> None:
        self.status = status
