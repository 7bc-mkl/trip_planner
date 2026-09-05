"""Deriving which stage or stages cover a given day.

`trip_day` deliberately carries no `stage_id` (spec, Data Model): a stored foreign
key would have to be re-maintained on every stage date edit and could silently
contradict the stage's own dates. This module is the derivation instead — a pure
function over the stages already loaded with the trip, so resolving every day of a
timeline costs no extra queries.

Two properties the callers depend on:

- a day resolves to **any number** of stages, including zero (a day in transit) and
  more than one (the travel day two stages share);
- the order is always `position`, never date order, because `position` is the
  itinerary's own sequence and is what the creator's list showed the owner.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from trip_planner.db.models import TripStage
from trip_planner.errors import ApiError, ErrorCode

__all__ = [
    "LABEL_JOINER",
    "MAX_LABELLED_STAGES",
    "stage_label",
    "stages_for_day",
    "validate_stage_range",
]

#: Places are joined with an arrow because the label describes movement, not a set.
LABEL_JOINER = " → "

#: How many places the label names before it collapses into a count.
#:
#: Two, because a day card is a narrow column and three chained place names wrap
#: onto a second line at the width the timeline actually renders at. A day covered
#: by more than two stages is rare enough that "+n" is a better use of the space
#: than a name nobody can read.
MAX_LABELLED_STAGES = 2


def validate_stage_range(
    start: date | None,
    end: date | None,
    *,
    trip_start: date,
    trip_end: date,
    place: str,
) -> None:
    """Refuse a stage whose own range is invalid or escapes the trip.

    Two distinct failures, kept distinct because they need different fixes:
    a backwards range is `invalid_date_range`, a range outside the trip is
    `stage_outside_trip`. Both name the offending place in `field`, since a trip
    being created may have several stages and "one of them is wrong" is not
    actionable.

    A stage with no dates, or only one of them, passes: it is a base whose days are
    undecided, which the spec allows explicitly.
    """
    if start is not None and end is not None and end < start:
        raise ApiError(ErrorCode.INVALID_DATE_RANGE, field=place)

    for boundary in (start, end):
        if boundary is not None and not (trip_start <= boundary <= trip_end):
            raise ApiError(ErrorCode.STAGE_OUTSIDE_TRIP, field=place)


def covers(stage: TripStage, day: date) -> bool:
    """Whether a stage's own range contains `day`.

    A stage with no dates covers nothing: R03 asks the creation form for the trip's
    dates, so an undated stage is a base whose days are not yet decided, and
    guessing that it covers the whole trip would put a label on every day the owner
    never asked for. Half-open ranges are treated the same way — an end without a
    start is not a range yet.
    """
    if stage.start_date is None or stage.end_date is None:
        return False
    return stage.start_date <= day <= stage.end_date


def stages_for_day(stages: Iterable[TripStage], day: date) -> list[TripStage]:
    """The stages covering `day`, ordered by `position`.

    Sorting here rather than trusting the caller's ordering means the function is
    correct whether it is handed `trip.stages` (already ordered by the relationship)
    or an arbitrary query result.
    """
    return sorted((stage for stage in stages if covers(stage, day)), key=lambda s: s.position)


def stage_label(stages: Sequence[TripStage]) -> str:
    """The day's label: places joined with `→`, truncated after two with `+n`.

    An empty sequence gives an empty string rather than a placeholder like "—":
    a day in no stage renders *without* a label, and inventing dash copy here would
    put an untranslated string on the screen. The caller decides how absence looks.
    """
    places = [stage.place for stage in stages]
    if len(places) <= MAX_LABELLED_STAGES:
        return LABEL_JOINER.join(places)

    shown = places[:MAX_LABELLED_STAGES]
    return f"{LABEL_JOINER.join(shown)} +{len(places) - MAX_LABELLED_STAGES}"
