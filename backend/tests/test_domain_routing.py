"""Candidate selection: finding the travel dates, and the trips they point at.

**Every exclusion case below is built from a structure that a real forwarded
confirmation actually had**, not from one imagined at a desk. The four the owner
supplied are gitignored and stay on his machine; what is reproduced here is the
shape — a Gmail forward header block, a Booking.com cancellation line, a Turkish
Airlines transaction line — with invented values. Two of the three exclusions
exist *because* of what those messages contained, and one earlier attempt at a
third was removed because real mail proved it wrong.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from trip_planner.domain.routing import (
    CANDIDATE_MARGIN,
    MAX_CANDIDATE_TRIPS,
    TripWindow,
    extract_travel_dates,
    select_candidates,
    strip_forwarded_headers,
)

BORNEO = TripWindow(
    id="trip-borneo",
    title="Malezja / Borneo",
    start_date=date(2026, 10, 2),
    end_date=date(2026, 10, 25),
    destinations=("Kuala Lumpur", "Kota Kinabalu"),
)
JUNE = TripWindow(
    id="trip-june",
    title="Czerwcowy wyjazd",
    start_date=date(2026, 6, 13),
    end_date=date(2026, 6, 18),
)


def ids(candidates) -> list[str]:
    return [one.trip.id for one in candidates]


# --------------------------------------------------------------------------- #
# Finding a date at all — the precondition the whole rule rests on
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Zameldowanie sobota 17 października 2026 (14:00)", date(2026, 10, 17)),
        ("Wylot: 2 października 2026", date(2026, 10, 2)),
        ("2 October 2026 Friday", date(2026, 10, 2)),
        ("17 Oct 2026 ARRIVE 17:50", date(2026, 10, 17)),
        ("17 Sept 2026", date(2026, 9, 17)),
        ("October 17, 2026", date(2026, 10, 17)),
        ("Oct 17, 2026", date(2026, 10, 17)),
        ("2026-10-17", date(2026, 10, 17)),
    ],
)
def test_the_date_formats_real_confirmations_actually_use(written: str, expected: date) -> None:
    """Polish month names, full English, abbreviated English, and ISO.

    **No ISO date appeared in any of the four real confirmations** — every one
    used a month name. An ISO-only extractor would have scored zero out of four,
    which is worth stating as a test rather than as a comment, because ISO is
    exactly what a reasonable person implements first.
    """
    assert extract_travel_dates(written) == (expected,)


def test_a_message_with_no_date_yields_nothing() -> None:
    """Which is the case that never reaches a model: zero candidates is an answer."""
    assert extract_travel_dates("Dziękujemy za rezerwację. Szczegóły w załączniku.") == ()


def test_an_impossible_date_is_ignored_rather_than_raising() -> None:
    """A typo in a confirmation is not a reason to fail the whole message."""
    assert extract_travel_dates("31 lutego 2026 i 17 października 2026") == (
        date(2026, 10, 17),
    )


def test_dates_come_back_in_the_order_they_appear_without_duplicates() -> None:
    text = "Wylot 2 October 2026\nPowrót 25 October 2026\nPotwierdzenie 2 October 2026"

    assert extract_travel_dates(text) == (date(2026, 10, 2), date(2026, 10, 25))


# --------------------------------------------------------------------------- #
# Exclusion 1 — the forward's own envelope
# --------------------------------------------------------------------------- #

GMAIL_FORWARD = """\
---------- Forwarded message ---------
From: Turkish Airlines <ticket@mail.turkishairlines.example>
Date: Mon, Jun 15, 2026 at 9:35 PM
Subject: Ticket Details
To: Michal <michal@example.com>

Warsaw (WAW) - Kuala Lumpur (KUL)
2 October 2026 Friday
"""


def test_the_forward_header_block_contributes_no_dates() -> None:
    """Two false dates per message, in every single forward, for one split.

    The quoted `Date:` is when the original was sent; Gmail's own header above
    it is when it was forwarded. Neither says anything about the trip, and both
    were being extracted before this.
    """
    assert extract_travel_dates(GMAIL_FORWARD) == (date(2026, 10, 2),)


def test_stripping_the_envelope_keeps_the_confirmation_under_it() -> None:
    """Only the quoted header block goes. The confirmation lives below it."""
    stripped = strip_forwarded_headers(GMAIL_FORWARD)

    assert "Kuala Lumpur" in stripped
    assert "ticket@mail.turkishairlines.example" not in stripped


def test_a_message_that_is_not_a_forward_is_untouched() -> None:
    original = "Wylot: 2 October 2026"

    assert strip_forwarded_headers(original) == original


# --------------------------------------------------------------------------- #
# Exclusion 2 — the line that announces a transaction
# --------------------------------------------------------------------------- #


def test_a_transaction_date_is_not_a_travel_date() -> None:
    """The Turkish Airlines shape: bought in June, flown in October.

    Without this the message matches any trip over its *billing* date, which is
    how a confirmation that should be unambiguous arrives at the model as a
    two-candidate decision.
    """
    text = "Transaction date: 15 June 2026, 22:34 (GMT +03)\n2 October 2026 Friday"

    assert extract_travel_dates(text) == (date(2026, 10, 2),)


@pytest.mark.parametrize(
    "line",
    [
        "Transaction date: 15 June 2026",
        "Data transakcji: 15 June 2026",
        "Booked on 15 June 2026",
        "Date of issue: 15 June 2026",
        "Data wystawienia: 15 June 2026",
    ],
)
def test_every_transaction_phrasing_excludes_its_line(line: str) -> None:
    assert extract_travel_dates(line) == ()


def test_a_travel_date_is_not_lost_because_the_trip_is_already_under_way() -> None:
    """The rule this replaced, and why it had to go.

    "Ignore anything earlier than the message's own `Date`" is the filter that
    suggests itself, and real mail refuted it: the Turkish Airlines confirmation
    was forwarded on 10 October for a flight on the **2nd**, so that rule threw
    the outbound leg away. This system ingests forwards, and a forward is sent
    whenever the owner gets round to it — including mid-trip.
    """
    text = "Warsaw (WAW) - Kuala Lumpur (KUL)\n2 October 2026 Friday"

    # No clock is consulted at all, so a date in the past is still travel.
    assert extract_travel_dates(text) == (date(2026, 10, 2),)


# --------------------------------------------------------------------------- #
# Exclusion 3 — the line about cancelling
# --------------------------------------------------------------------------- #

BOOKING_CANCELLATION = """\
*Zameldowanie* sobota 17 października 2026 (14:00–00:00)
*Wymeldowanie* niedziela 18 października 2026 (07:00–12:00)
Możesz odwołać BEZPŁATNIE do 23:59, 13 października 2026 [+08].
"""


def test_a_cancellation_deadline_is_not_a_travel_date() -> None:
    """The Booking.com shape, with the check-in and check-out beside it."""
    assert extract_travel_dates(BOOKING_CANCELLATION) == (
        date(2026, 10, 17),
        date(2026, 10, 18),
    )


@pytest.mark.parametrize(
    "line",
    [
        "Free cancellation until 13 October 2026",
        "Non-refundable after 13 October 2026",
        "Valid until 13 October 2026",
        "Oferta ważna do 13 października 2026",
    ],
)
def test_every_deadline_phrasing_excludes_its_line(line: str) -> None:
    assert extract_travel_dates(line) == ()


def test_the_exclusion_is_scoped_to_its_own_line() -> None:
    """The bug the first version of this had, kept as a test.

    A character window reached past the end of the line, and a real ticket says
    `non-refundable.` immediately before `25 October 2026 Friday`. It swallowed
    both of that ticket's travel dates and sent a routable confirmation to the
    unrouted queue. Lines are the unit because confirmations are written in
    lines.
    """
    text = "Economy Class, non-refundable.\n25 October 2026 Sunday"

    assert extract_travel_dates(text) == (date(2026, 10, 25),)


# --------------------------------------------------------------------------- #
# Candidate selection
# --------------------------------------------------------------------------- #


def test_no_trip_covering_the_dates_yields_no_candidate() -> None:
    """The case that never reaches a model. Zero candidates is an answer."""
    assert select_candidates([date(2027, 3, 4)], [BORNEO]) == ()


def test_one_covering_trip_is_one_candidate() -> None:
    assert ids(select_candidates([date(2026, 10, 17)], [BORNEO, JUNE])) == [BORNEO.id]


def test_several_covering_trips_are_all_offered() -> None:
    """What the model is for — and the only situation it gets to decide anything."""
    overlapping = TripWindow(
        id="trip-overlap",
        title="Nakładający się",
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 20),
    )

    found = select_candidates([date(2026, 10, 17)], [BORNEO, overlapping])

    assert sorted(ids(found)) == sorted([BORNEO.id, overlapping.id])


def test_the_strongest_candidate_leads() -> None:
    """Ordered by how many dates matched, so a model reads the best one first."""
    narrow = TripWindow(
        id="trip-narrow",
        title="Wąski",
        start_date=date(2026, 10, 17),
        end_date=date(2026, 10, 17),
    )

    found = select_candidates([date(2026, 10, 17), date(2026, 10, 25)], [narrow, BORNEO])

    assert ids(found)[0] == BORNEO.id


@pytest.mark.parametrize(
    ("day", "covered"),
    [
        (date(2026, 10, 1), True),  # one day before the start — the overnight flight
        (date(2026, 9, 30), False),  # two days before — the trip before this one
        (date(2026, 10, 26), True),  # one day after the end
        (date(2026, 10, 27), False),
    ],
)
def test_the_margin_is_exactly_one_day_at_each_boundary(day: date, covered: bool) -> None:
    """One day, because the flight that leaves on the 9th for a trip starting on
    the 10th is the ordinary case rather than an edge one."""
    assert bool(select_candidates([day], [BORNEO])) is covered
    assert timedelta(days=1) == CANDIDATE_MARGIN


def test_a_candidate_records_which_dates_put_it_there() -> None:
    """So the routing reason can be specific and a wrong candidate is debuggable."""
    found = select_candidates([date(2026, 10, 17), date(2027, 1, 1)], [BORNEO])

    assert found[0].matched_on == (date(2026, 10, 17),)


def test_a_message_matching_too_many_trips_is_capped() -> None:
    """Far more likely a date-extraction failure than genuine ambiguity, and not
    a choice a model should be handed."""
    many = [
        TripWindow(
            id=f"trip-{n}",
            title=f"Trip {n}",
            start_date=date(2026, 10, 17),
            end_date=date(2026, 10, 18),
        )
        for n in range(MAX_CANDIDATE_TRIPS + 3)
    ]

    assert len(select_candidates([date(2026, 10, 17)], many)) == MAX_CANDIDATE_TRIPS


def test_a_trip_window_carries_only_what_a_model_may_see() -> None:
    """D24 fixes the payload at id, title, destinations and date range.

    `TripWindow` is a separate type from the ORM `Trip` precisely so that adding
    a column to the latter cannot widen what leaves the deployment.
    """
    assert set(TripWindow.__slots__) == {
        "id",
        "title",
        "start_date",
        "end_date",
        "destinations",
    }
