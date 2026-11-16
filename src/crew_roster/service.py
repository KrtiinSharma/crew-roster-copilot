"""Stateless scenario service shared by the agent tools and the API.

A scenario is (ruleset name, ordered list of disruptions). Results are cached by a canonical key,
so the browser can resend its whole disruption list on every request and identical requests are
free. Nothing here mutates the base roster.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from functools import cache, lru_cache

from pydantic import TypeAdapter

from crew_roster.data import generate
from crew_roster.disrupt import Disruption
from crew_roster.models import DAY, ROLES, Duty, Frozen, Pilot, Roster, Violation
from crew_roster.problem import Problem, build_problem
from crew_roster.roster import (
    Change,
    Sizing,
    Usage,
    check,
    duty_violations,
    load_base_roster,
    min_pilots_needed,
    pilot_usage,
    replan,
)
from crew_roster.rules import RULESETS, load

DISRUPTIONS = TypeAdapter(list[Disruption])
TIME_RULES = frozenset({"min_rest", "ft_7d", "ft_28d", "duty_7d", "duty_28d", "max_fdp",
                        "night_max_fdp", "max_ft_per_duty", "weekly_rest"})


def clock(minute: int) -> str:
    m = minute % DAY
    return f"{m // 60:02d}:{m % 60:02d}"


def stamp(minute: int) -> str:
    return f"D{minute // DAY} {clock(minute)}"


def hours(minutes: int) -> float:
    return round(minutes / 60, 2)


def hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def canonical(disruptions: Sequence[Disruption]) -> str:
    """Order-preserving, key-sorted JSON: the cache key for a scenario."""
    return json.dumps(DISRUPTIONS.dump_python(list(disruptions), mode="json"), sort_keys=True)


class PilotView(Frozen):
    id: str
    name: str
    rank: str
    base: str
    unavailable_days: list[int]
    sick_days: list[int]


class FlightView(Frozen):
    id: str
    day: int
    origin: str
    dest: str
    dep: str
    arr: str
    dep_min: int
    arr_min: int


class DutyView(Frozen):
    id: str
    base: str
    day: int
    route: str
    flight_ids: list[str]
    report: str
    release: str
    report_min: int
    release_min: int
    flight_time_h: float
    duty_h: float
    landings: int
    night: bool
    legal: bool
    cpt: str | None
    fo: str | None


class ChangeView(Frozen):
    id: str
    duty_id: str
    role: str
    old_pilot: str | None
    new_pilot: str | None
    reasons: list[Violation]
    explanation: str


class Stats(Frozen):
    duties: int
    slots: int
    crewed: int
    uncovered: int
    changes: int
    violations: int
    solve_seconds: float
    status: str


class PilotStatus(Frozen):
    pilot: PilotView
    day: int
    usage: list[Usage]
    duties: list[DutyView]


class ScenarioResult(Frozen):
    ruleset: str
    disruptions: list[Disruption]
    problem: Problem
    base: Roster
    roster: Roster
    changes: list[Change]
    illegal_duties: list[str]
    stats: Stats


def _ruleset(name: str) -> str:
    if name not in RULESETS:
        raise ValueError(f"unknown ruleset {name!r}; choose from {RULESETS}")
    return name


@cache
def base_problem(ruleset: str) -> tuple[Problem, Roster]:
    problem = build_problem(generate(), load(_ruleset(ruleset)))
    return problem, load_base_roster(problem)


def evaluate(ruleset: str, disruptions: Sequence[Disruption],
             time_limit: float = 10.0) -> ScenarioResult:
    return _evaluate(_ruleset(ruleset), canonical(disruptions), time_limit)


@lru_cache(maxsize=64)
def _evaluate(ruleset: str, key: str, time_limit: float) -> ScenarioResult:
    disruptions = DISRUPTIONS.validate_python(json.loads(key))
    problem, base = base_problem(ruleset)
    t0 = time.perf_counter()
    if disruptions:
        rp = replan(problem, base, disruptions, time_limit=time_limit)
        new, roster, changes = rp.problem, rp.result.roster, rp.changes
        illegal, status = rp.result.illegal_duties, rp.result.status
    else:
        new, roster, changes, status = problem, base, [], "BASE"
        illegal = [d.id for d in problem.duties if duty_violations(d, problem.ruleset)]
    slots = 2 * len(new.duties)
    crewed = sum(1 for d in new.duties for r in ROLES if roster.get(d.id, r))
    stats = Stats(duties=len(new.duties), slots=slots, crewed=crewed, uncovered=slots - crewed,
                  changes=len(changes), violations=len(check(new, roster)),
                  solve_seconds=round(time.perf_counter() - t0, 3), status=status)
    return ScenarioResult(ruleset=ruleset, disruptions=disruptions, problem=new, base=base,
                          roster=roster, changes=changes, illegal_duties=illegal, stats=stats)


@cache
def sizing(base: str, ruleset: str) -> Sizing:
    problem, _ = base_problem(_ruleset(ruleset))
    if base not in {d.base for d in problem.duties}:
        raise ValueError(f"unknown base {base!r}")
    return min_pilots_needed(problem, base)


def route(problem: Problem, duty: Duty) -> str:
    fl = [problem.flights[f] for f in duty.flight_ids]
    return "-".join([fl[0].origin] + [f.dest for f in fl])


def _pilot_view(problem: Problem, p: Pilot) -> PilotView:
    return PilotView(id=p.id, name=p.name, rank=p.rank, base=p.base,
                     unavailable_days=sorted(p.unavailable_days),
                     sick_days=sorted(problem.sick.get(p.id, frozenset())))


def pilot_views(problem: Problem) -> list[PilotView]:
    return [_pilot_view(problem, p) for p in problem.pilots]


def flight_views(problem: Problem) -> list[FlightView]:
    return [FlightView(id=f.id, day=f.day, origin=f.origin, dest=f.dest, dep=stamp(f.dep),
                       arr=stamp(f.arr), dep_min=f.dep, arr_min=f.arr)
            for f in sorted(problem.flights.values(), key=lambda f: (f.dep, f.id))]


def duty_views(result: ScenarioResult, pilot_id: str | None = None,
               day: int | None = None) -> list[DutyView]:
    problem, roster = result.problem, result.roster
    if pilot_id is not None and pilot_id not in problem.pilot_map():
        raise ValueError(f"unknown pilot {pilot_id}")
    out = []
    for d in problem.duties:
        cpt, fo = roster.get(d.id, "CPT"), roster.get(d.id, "FO")
        if pilot_id is not None and pilot_id not in (cpt, fo):
            continue
        if day is not None and d.day != day:
            continue
        out.append(DutyView(
            id=d.id, base=d.base, day=d.day, route=route(problem, d),
            flight_ids=list(d.flight_ids), report=stamp(d.report), release=stamp(d.release),
            report_min=d.report, release_min=d.release, flight_time_h=hours(d.flight_time),
            duty_h=hours(d.length), landings=d.landings, night=d.night,
            legal=not duty_violations(d, problem.ruleset), cpt=cpt, fo=fo))
    return out


def change_views(result: ScenarioResult, explanations: dict[str, str]) -> list[ChangeView]:
    return [ChangeView(id=c.id, duty_id=c.duty_id, role=c.role, old_pilot=c.old_pilot,
                       new_pilot=c.new_pilot, reasons=c.reasons,
                       explanation=explanations.get(c.id, ""))
            for c in result.changes]


def pilot_status(result: ScenarioResult, pilot_id: str, day: int) -> PilotStatus:
    problem = result.problem
    pilots = problem.pilot_map()
    if pilot_id not in pilots:
        raise ValueError(f"unknown pilot {pilot_id}")
    if not 0 <= day < problem.horizon_days:
        raise ValueError(f"day must be 0-{problem.horizon_days - 1}")
    return PilotStatus(pilot=_pilot_view(problem, pilots[pilot_id]), day=day,
                       usage=pilot_usage(problem, result.roster, pilot_id, day),
                       duties=duty_views(result, pilot_id=pilot_id))


def lookup(problem: Problem, query: str, limit: int = 10) -> dict:
    q = query.strip().lower()
    if not q:
        raise ValueError("empty query")
    pilots = [{"id": p.id, "name": p.name, "rank": p.rank, "base": p.base}
              for p in problem.pilots if q in p.id.lower() or q in p.name.lower()]
    flights = [{"id": f.id, "day": f.day, "from": f.origin, "to": f.dest, "dep": stamp(f.dep)}
               for f in sorted(problem.flights.values(), key=lambda f: (f.dep, f.id))
               if f.id.lower().startswith(q)]
    return {"pilots": pilots[:limit], "flights": flights[:limit]}
