"""Baseline: drop broken slots, then fill each empty slot with the first legal pilot."""

from __future__ import annotations

import time

from crew_roster.models import ROLES, Roster, Violation
from crew_roster.problem import Problem
from crew_roster.roster.check import duty_violations, pilot_violations
from crew_roster.roster.diff import count_changes
from crew_roster.roster.solver import SolveResult


def _keys(vs: list[Violation]) -> set[tuple]:
    return {(v.rule, v.duty_id, v.day) for v in vs}


def greedy_repair(problem: Problem, base: Roster, locked_before: int | None = None) -> SolveResult:
    t0 = time.perf_counter()
    duties, pilots = problem.duty_map(), problem.pilot_map()
    rs = problem.ruleset
    legal_ids = {d.id for d in problem.duties if not duty_violations(d, rs)}

    def unlocked(did: str) -> bool:
        return locked_before is None or duties[did].report >= locked_before

    roster = Roster(assignments={d: dict(c) for d, c in base.assignments.items() if d in legal_ids})

    def drop_target(pid: str, vs: list[Violation]) -> tuple[str, str] | None:
        mine = sorted(roster.duties_of(pid), key=lambda s: duties[s[0]].report, reverse=True)
        for v in vs:
            if v.duty_id and (v.duty_id, pilots[pid].rank) in mine and unlocked(v.duty_id):
                return (v.duty_id, pilots[pid].rank)
            if v.day is not None:
                for did, role in mine:  # latest unlocked duty on or before the breach day
                    if duties[did].day <= v.day and unlocked(did):
                        return (did, role)
        return None

    for pid in sorted({p for _, _, p in roster.slots()}):
        while vs := pilot_violations(problem, roster, pid):
            target = drop_target(pid, vs)
            if target is None:
                break
            roster = roster.with_slot(*target, None)

    for d in sorted(problem.duties, key=lambda d: (d.report, d.id)):
        if d.id not in legal_ids or not unlocked(d.id):
            continue
        for role in ROLES:
            if roster.get(d.id, role):
                continue
            for p in sorted(pilots.values(), key=lambda p: p.id):
                if p.rank != role or p.base != d.base:
                    continue
                if any(duties[o].day == d.day for o, _ in roster.duties_of(p.id)):
                    continue
                before = _keys(pilot_violations(problem, roster, p.id))
                trial = roster.with_slot(d.id, role, p.id)
                if _keys(pilot_violations(problem, trial, p.id)) <= before:
                    roster = trial
                    break

    uncovered = [(d.id, r) for d in problem.duties for r in ROLES if roster.get(d.id, r) is None]
    return SolveResult(
        roster=roster,
        uncovered=uncovered,
        illegal_duties=sorted(set(duties) - legal_ids),
        status="GREEDY",
        seconds=round(time.perf_counter() - t0, 3),
        changes=count_changes(problem, base, roster),
    )
