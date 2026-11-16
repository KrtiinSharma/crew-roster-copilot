"""A rostering problem: duties to crew, pilots, their history, and the ruleset."""

from __future__ import annotations

from crew_roster.models import Duty, Flight, Frozen, Pilot, Turn
from crew_roster.rules import Ruleset


class Problem(Frozen):
    ruleset: Ruleset
    duties: list[Duty]
    pilots: list[Pilot]
    history: dict[str, list[Duty]] = {}
    turns: dict[str, Turn] = {}
    flights: dict[str, Flight] = {}
    sick: dict[str, frozenset[int]] = {}
    horizon_days: int = 7

    def pilot_map(self) -> dict[str, Pilot]:
        return {p.id: p for p in self.pilots}

    def duty_map(self) -> dict[str, Duty]:
        return {d.id: d for d in self.duties}

    def unavailable_days(self, pilot: Pilot) -> frozenset[int]:
        return pilot.unavailable_days | self.sick.get(pilot.id, frozenset())


def build_problem(airline, ruleset: Ruleset) -> Problem:
    from crew_roster.duties import build  # local import avoids a cycle via roster.check

    duties = build(list(airline.turns.values()), airline.flights, ruleset)
    return Problem(
        ruleset=ruleset,
        duties=duties,
        pilots=airline.pilots,
        history=airline.history,
        turns=airline.turns,
        flights=airline.flights,
        horizon_days=airline.days,
    )
