"""Apply disruptions and re-plan from the current roster."""

from __future__ import annotations

from collections.abc import Sequence

from crew_roster.disrupt import Disruption, apply, lock_time
from crew_roster.models import Frozen, Roster
from crew_roster.problem import Problem
from crew_roster.roster.diff import Change, diff
from crew_roster.roster.greedy import greedy_repair
from crew_roster.roster.solver import SolveResult, solve


class Replan(Frozen):
    problem: Problem
    result: SolveResult
    changes: list[Change]
    locked_before: int | None


def replan(
    problem: Problem,
    base: Roster,
    disruptions: Sequence[Disruption],
    method: str = "cpsat",
    time_limit: float = 10.0,
) -> Replan:
    new = apply(problem, disruptions)
    lock = lock_time(problem, disruptions)
    if method == "cpsat":
        result = solve(new, base=base, locked_before=lock, time_limit=time_limit)
    elif method == "scratch":
        result = solve(new, base=base, locked_before=lock, time_limit=time_limit, change_weight=0)
    elif method == "greedy":
        result = greedy_repair(new, base, locked_before=lock)
    else:
        raise ValueError(f"unknown method {method!r}")
    return Replan(
        problem=new, result=result, changes=diff(new, base, result.roster), locked_before=lock
    )
