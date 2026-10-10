"""Which trip a forwarded confirmation is about — the deterministic half.

**This module is the reason A07 is a cheap assumption to be wrong about.** The
model never picks a trip out of the air: this code computes the candidate set in
code the owner can read, and the model's only job is to choose among candidates
it was handed. An id outside that set is rejected before a proposal exists, so
"route this to the trip you are not allowed to see" is not expressible.

Everything here is pure, like the rest of `domain/`: dates and trip summaries in,
candidates out. No database, no clock it is not handed.

## The rule, and why it is not the rule the spec first wrote

The spec's original wording was *"the owner's trips whose range contains any
extracted travel date, ±1 day"*. The A07/A08 paper check on 2026-10-10 ran that
against four real forwarded confirmations and found the flaw: **a confirmation
is full of dates that are not travel dates.** A Booking.com mail carries its
free-cancellation deadline and a price-change date; an airline carries the
transaction date it was bought on; every Gmail forward carries the forwarding
header's own date and the original send date.

With one trip in the system that is harmless — everything matches the only trip
there is. With two, the Turkish Airlines confirmation matched a second trip **on
its billing date** and arrived at the model as a two-candidate decision that
should never have been ambiguous. The rule was manufacturing work for the model
out of a receipt, in exactly the situation A07 needs it to be reliable.

So three exclusions, each from an observed structure rather than imagined:

1. **The forwarded-header block is stripped** before anything is extracted. Two
   false dates per message, every message, for one `split()`.
2. **A line that announces a transaction is not announcing travel** —
   *Transaction date*, *Booked on*, *Data wystawienia*. This replaces an earlier
   rule that discarded any date before the message's own `Date` header, which
   was **wrong for the mail this system actually receives**: we ingest
   *forwards*, and a forward can be sent mid-trip or after it. The real Turkish
   Airlines confirmation was forwarded on 10 October for a trip that began on
   the 2nd, so that rule threw the outbound leg away. The date header of a
   forward says when it was forwarded and nothing about the trip.
3. **A line about cancellation or refunds states a deadline**, not a trip —
   *odwołać*, *anulować*, *cancel*, *refund*, *valid until*.

## What the real mail decided about formats

No ISO date appeared in any of the four confirmations. What appeared was
`17 października 2026`, `2 October 2026` and `17 Oct 2026` — so Polish month
names and both English forms are required, and an ISO-only extractor would have
scored zero out of four. ISO is still parsed, because it costs one pattern and
some vendor will eventually use it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

__all__ = [
    "CANDIDATE_MARGIN",
    "MAX_CANDIDATE_TRIPS",
    "CandidateTrip",
    "TripWindow",
    "extract_travel_dates",
    "select_candidates",
    "strip_forwarded_headers",
]

#: How far outside a trip's own range a date still counts as belonging to it.
#:
#: One day, because an overnight flight that leaves on the 9th for a trip
#: starting on the 10th is the ordinary case, not an edge one — the shipped
#: `Item` span exists for exactly that flight. Two days would start pulling in
#: the trip before.
CANDIDATE_MARGIN = timedelta(days=1)

#: How many candidates are ever handed to a model.
#:
#: Beyond a handful the choice is not one a model should be making — and a
#: message matching nine trips is far more likely to be a date-extraction
#: failure than a genuinely ambiguous confirmation. Past this the message goes
#: to the unrouted queue, where the owner places it in two clicks.
MAX_CANDIDATE_TRIPS = 5

#: Where Gmail's forward begins. Everything from here to the end of the quoted
#: header block is the *envelope of the forward*, not the confirmation.
_FORWARD_MARKERS = (
    "---------- Forwarded message ---------",
    "---------- Forwarded message ----------",
    "-------- Original Message --------",
    "Begin forwarded message:",
)

#: The quoted header lines a forward block is made of, in both locales.
_QUOTED_HEADER = re.compile(
    r"^\s*(From|To|Date|Subject|Sent|Od|Do|Data|Temat|Wysłano)\s*:", re.IGNORECASE
)

_PL_MONTHS = {
    "stycznia": 1, "styczeń": 1, "stycze": 1,
    "lutego": 2, "luty": 2,
    "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecień": 4,
    "maja": 5, "maj": 5,
    "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7,
    "sierpnia": 8, "sierpień": 8,
    "września": 9, "wrzesień": 9,
    "października": 10, "październik": 10,
    "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzień": 12,
}

_EN_MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_MONTHS = {**_PL_MONTHS, **_EN_MONTHS}
_MONTH_ALTERNATION = "|".join(sorted(_MONTHS, key=len, reverse=True))

#: `2026-10-17`. Not seen in any real confirmation, kept because it costs one
#: pattern and some vendor will eventually use it.
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

#: `17 października 2026`, `2 October 2026`, `17 Oct 2026`. The forms that
#: actually turned up.
_DAY_MONTH_YEAR = re.compile(
    rf"\b(\d{{1,2}})\s+({_MONTH_ALTERNATION})\.?\s+(\d{{4}})\b", re.IGNORECASE
)

#: `October 17, 2026` — the American order, which Gmail itself writes.
_MONTH_DAY_YEAR = re.compile(
    rf"\b({_MONTH_ALTERNATION})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE
)

#: Vocabulary that marks a *line* as being about something other than travel —
#: a cancellation policy, a refund rule, or the moment the booking was paid for.
#:
#: Transaction vocabulary sits here rather than in a date comparison because the
#: comparison that suggests itself — "earlier than the message's own `Date`" —
#: is wrong for forwarded mail, which is the only kind this system receives. See
#: the module docstring.
_NOT_TRAVEL_PHRASE = re.compile(
    r"("
    r"odwoła|anuluj|bezpłatn|zwrot kosztów|cancel|cancellation|refund|"
    r"do zapłaty|payment due|pay before|valid until|expires?|ważn"
    r"|transaction date|data transakcji|booked on|date of issue|data wystawienia"
    r"|purchase date|data zakupu|order date|issued on"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TripWindow:
    """A trip reduced to what routing is allowed to know about it.

    Deliberately not the ORM `Trip`. This module is pure, and — more to the
    point — this is the **exact shape that may be shown to a model** (D24): an
    id, a title, destination names and a date range. Keeping it a separate type
    means a later refactor cannot widen the model's view of a trip by adding a
    column somewhere else.
    """

    id: str
    title: str
    start_date: date
    end_date: date
    destinations: tuple[str, ...] = ()

    def covers(self, when: date, *, margin: timedelta = CANDIDATE_MARGIN) -> bool:
        return self.start_date - margin <= when <= self.end_date + margin


@dataclass(frozen=True, slots=True)
class CandidateTrip:
    """A trip the message might be about, and the dates that put it there.

    `matched_on` exists so the routing reason can be specific — the owner reads
    *"no trip covers 4–11 March"*, not *"unrouted"* — and so a wrong candidate
    is debuggable without re-running the extraction.
    """

    trip: TripWindow
    matched_on: tuple[date, ...]


def strip_forwarded_headers(text: str) -> str:
    """Remove the forward envelope so its dates are never mistaken for travel.

    Every Gmail forward opens with a marker line and a block of quoted headers
    carrying two dates that belong to the *mail*, not the trip: when it was
    originally sent, and when it was forwarded. Both were being extracted.

    Only the quoted header block is removed, never the body under it — the
    confirmation itself lives there.
    """
    for marker in _FORWARD_MARKERS:
        index = text.find(marker)
        if index == -1:
            continue

        before, after = text[:index], text[index + len(marker) :]
        lines = after.splitlines()
        cut = 0
        for position, line in enumerate(lines):
            if _QUOTED_HEADER.match(line) or not line.strip():
                cut = position + 1
                continue
            break
        text = before + "\n".join(lines[cut:])

    return text


def extract_travel_dates(text: str) -> tuple[date, ...]:
    """Every date in `text` that plausibly describes travel, in order, deduplicated.

    **There is deliberately no "ignore anything before today" parameter.** It is
    the obvious filter and it is wrong here: this system ingests forwards, and
    the owner forwards a confirmation whenever he gets round to it — including
    while the trip is under way. One of the four real confirmations was
    forwarded on 10 October for a flight on the 2nd, and a past-date filter
    silently discarded the outbound leg. Travel dates are recognised by what the
    line around them says, not by where they sit relative to a clock.
    """
    body = strip_forwarded_headers(text)
    excluded = _non_travel_spans(body)

    found: list[date] = []
    for parsed, position in _all_dates(body):
        # Half-open: `end` is the first character of the *next* line. Inclusive
        # here meant a date starting exactly at a line boundary was attributed
        # to the line above it, which is how `non-refundable.` on one line
        # excluded `25 October 2026` on the next.
        if any(start <= position < end for start, end in excluded):
            continue
        if parsed not in found:
            found.append(parsed)

    return tuple(found)


def select_candidates(
    dates: tuple[date, ...] | list[date],
    trips: list[TripWindow] | tuple[TripWindow, ...],
    *,
    margin: timedelta = CANDIDATE_MARGIN,
) -> tuple[CandidateTrip, ...]:
    """The trips any of `dates` falls inside, ±`margin`.

    Ordered by how many dates matched, then by start date, so the strongest
    candidate leads — a model given a list reads the first one first, and a
    human reading an unrouted reason does too.

    Returns empty when nothing matches, which is the case that **never reaches a
    model**: zero candidates is an answer, not a question.
    """
    candidates: list[CandidateTrip] = []
    for trip in trips:
        matched = tuple(one for one in dates if trip.covers(one, margin=margin))
        if matched:
            candidates.append(CandidateTrip(trip=trip, matched_on=matched))

    candidates.sort(key=lambda one: (-len(one.matched_on), one.trip.start_date))
    return tuple(candidates[:MAX_CANDIDATE_TRIPS])


def _all_dates(text: str) -> list[tuple[date, int]]:
    """Every parseable date with the offset it was found at, left to right."""
    found: list[tuple[date, int]] = []

    for match in _ISO.finditer(text):
        parsed = _build(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            found.append((parsed, match.start()))

    for match in _DAY_MONTH_YEAR.finditer(text):
        parsed = _build(
            int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1))
        )
        if parsed is not None:
            found.append((parsed, match.start()))

    for match in _MONTH_DAY_YEAR.finditer(text):
        parsed = _build(
            int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2))
        )
        if parsed is not None:
            found.append((parsed, match.start()))

    found.sort(key=lambda pair: pair[1])
    return found


def _build(year: int, month: int, day: int) -> date | None:
    """A real date, or `None` for `31 February` and friends.

    Returned rather than raised: a nonsense date in a confirmation is a typo or
    a false match, and neither is a reason to fail the whole message.
    """
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _non_travel_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges in which a date means something other than travel.

    **Scoped to the line, and the real mail is why.** The first version of this
    reached a fixed number of characters past the phrase, which read across line
    boundaries — and a Turkish Airlines ticket says `non-refundable.` on the line
    immediately before `25 October 2026 Friday`. The window swallowed both of
    that ticket's travel dates and sent a perfectly routable confirmation to the
    unrouted queue. A character window cannot tell "the next sentence" from "the
    next section".

    Lines are the right unit because confirmations are laid out as lines: a
    cancellation policy states its date in its own sentence
    (`Możesz odwołać BEZPŁATNIE do 23:59, 13 października 2026`), and a check-in
    date sits on a line of its own (`*Zameldowanie* sobota 17 października
    2026`). Both observed, in the same message.

    **Known residual.** Booking.com also writes its price tiers as
    `- do 13 października … : S$ 0` / `- od 14 października … : S$ 118,90`,
    which carry no cancellation word and so survive. Left alone deliberately:
    recognising them needs either a currency heuristic or a `do`/`od` rule
    general enough to start eating travel dates, and in the observed mail those
    two dates fall inside the stay's own trip, so they add no candidate that the
    check-in date does not add already.
    """
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if _NOT_TRAVEL_PHRASE.search(line):
            spans.append((offset, offset + len(line)))
        offset += len(line)
    return spans
