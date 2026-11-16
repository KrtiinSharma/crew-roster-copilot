"""Disruptions and how they change a Problem. apply() always returns a new Problem."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import Field

from crew_roster.duties import make_duty
from crew_roster.models import DAY, Frozen
from crew_roster.problem import Problem


class PilotSick(Frozen):
    kind: Literal["sick"] = "sick"
    pilot_id: str
    from_day: int
    to_day: int


class FlightDelay(Frozen):
    kind: Literal["delay"] = "delay"
    flight_id: str
    minutes: int = Field(gt=0, le=600)


class FlightCancel(Frozen):
    kind: Literal["cancel"] = "cancel"
    flight_id: str


Disruption = Annotated[PilotSick | FlightDelay | FlightCancel, Field(discriminator="kind")]

DELAY_NOTICE = 120  # a delay becomes known 2 h before departure
CANCEL_NOTICE = 180  # a cancellation 3 h before


def known_at(problem: Problem, d: Disruption) -> int:
    if isinstance(d, PilotSick):
        return d.from_day * DAY
    dep = problem.flights[d.flight_id].dep
    return dep - (DELAY_NOTICE if isinstance(d, FlightDelay) else CANCEL_NOTICE)


def lock_time(problem: Problem, disruptions: Sequence[Disruption]) -> int | None:
    """Duties reporting before this minute have already started and keep their crew."""
    return min((known_at(problem, d) for d in disruptions), default=None)


def apply(problem: Problem, disruptions: Sequence[Disruption]) -> Problem:
    flights, turns = dict(problem.flights), dict(problem.turns)
    sick = dict(problem.sick)
    duties = {d.id: d for d in problem.duties}
    duty_of_turn = {t: d.id for d in problem.duties for t in d.turn_ids}
    pilot_ids = {p.id for p in problem.pilots}
    rs = problem.ruleset

    for dis in disruptions:
        if isinstance(dis, PilotSick):
            if dis.pilot_id not in pilot_ids:
                raise ValueError(f"unknown pilot {dis.pilot_id}")
            if dis.to_day < dis.from_day:
                raise ValueError("to_day must be >= from_day")
            days = frozenset(range(dis.from_day, dis.to_day + 1))
            sick[dis.pilot_id] = sick.get(dis.pilot_id, frozenset()) | days
            continue
        if dis.flight_id not in flights:
            raise ValueError(f"unknown or cancelled flight {dis.flight_id}")
        f = flights[dis.flight_id]
        did = duty_of_turn[f.turn_id]
        duty = duties[did]
        if isinstance(dis, FlightDelay):
            for fid in duty.flight_ids:
                g = flights[fid]
                if g.dep >= f.dep:
                    flights[fid] = g.model_copy(
                        update={"dep": g.dep + dis.minutes, "arr": g.arr + dis.minutes}
                    )
            duties[did] = make_duty(did, duty.base, [turns[t] for t in duty.turn_ids], flights, rs)
        else:
            turn = turns.pop(f.turn_id)
            for fid in turn.flight_ids:
                flights.pop(fid)
            remaining = [turns[t] for t in duty.turn_ids if t != turn.id]
            if remaining:
                duties[did] = make_duty(did, duty.base, remaining, flights, rs)
            else:
                del duties[did]

    return problem.model_copy(
        update={
            "flights": flights,
            "turns": turns,
            "sick": sick,
            "duties": sorted(duties.values(), key=lambda d: (d.report, d.id)),
        }
    )


__all__ = [
    "CANCEL_NOTICE",
    "DELAY_NOTICE",
    "Disruption",
    "FlightCancel",
    "FlightDelay",
    "PilotSick",
    "apply",
    "known_at",
    "lock_time",
]
