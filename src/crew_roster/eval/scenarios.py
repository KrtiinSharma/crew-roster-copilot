"""Seeded random disruption scenarios for the optimiser benchmark."""

from __future__ import annotations

import random
from typing import Literal

from crew_roster.disrupt import Disruption, FlightCancel, FlightDelay, PilotSick
from crew_roster.models import Frozen
from crew_roster.service import base_problem

Size = Literal["small", "medium", "large"]
SIZES: tuple[Size, ...] = ("small", "medium", "large")
COUNTS = {"small": (1, 1), "medium": (2, 3), "large": (4, 6)}
DELAYS = (60, 120, 180, 240, 300)
KINDS = ("sick", "delay", "cancel")


class Scenario(Frozen):
    id: str
    size: Size
    disruptions: list[Disruption]


def make_scenarios(n: int = 50, seed: int = 11, ruleset: str = "dgca_current") -> list[Scenario]:
    """n scenarios, about a third each small / medium / large, reproducible for a seed.

    No two disruptions in a scenario touch the same pilot, and no two flight disruptions touch
    the same duty (so never the same turn either).
    """
    problem, base = base_problem(ruleset)
    rng = random.Random(seed)
    duty_day = {d.id: d.day for d in problem.duties}
    duty_of_turn = {t: d.id for d in problem.duties for t in d.turn_ids}
    working: dict[int, list[str]] = {}  # day -> pilots with a base-roster duty that day
    for did, _role, pid in sorted(base.slots()):
        working.setdefault(duty_day[did], []).append(pid)
    flights = sorted(problem.flights.values(), key=lambda f: f.id)

    sizes = [SIZES[i % 3] for i in range(n)]
    rng.shuffle(sizes)
    out = []
    for i, size in enumerate(sizes):
        lo, hi = COUNTS[size]
        k = rng.randint(lo, hi)
        pilots: set[str] = set()
        duties: set[str] = set()
        dis: list[Disruption] = []
        while len(dis) < k:
            kind = rng.choice(KINDS)
            if kind == "sick":
                day = rng.randint(1, 5)
                cands = sorted(set(working.get(day, [])) - pilots)
                if not cands:
                    continue
                pid = rng.choice(cands)
                to_day = min(day + rng.randint(0, 1), problem.horizon_days - 1)
                pilots.add(pid)
                dis.append(PilotSick(pilot_id=pid, from_day=day, to_day=to_day))
                continue
            days = range(1, 6) if kind == "delay" else range(1, 7)
            cands = [f for f in flights
                     if f.day in days and duty_of_turn[f.turn_id] not in duties]
            if not cands:
                continue
            f = rng.choice(cands)
            duties.add(duty_of_turn[f.turn_id])
            dis.append(FlightDelay(flight_id=f.id, minutes=rng.choice(DELAYS))
                       if kind == "delay" else FlightCancel(flight_id=f.id))
        out.append(Scenario(id=f"S{i:02d}", size=size, disruptions=dis))
    return out
