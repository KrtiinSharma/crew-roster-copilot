"""Crew sizing: the fewest pilots per rank at one base that still crew every duty."""

from __future__ import annotations

from collections import Counter

from crew_roster.models import Frozen
from crew_roster.problem import Problem
from crew_roster.roster.solver import solve


class Sizing(Frozen):
    """Result of sizing one base.

    pilots_needed is the fewest pilots per rank found that crew every duty. It is a
    proven minimum only when proven_optimal is True; otherwise it is an upper bound
    (a roster with that many pilots exists, fewer might also work). It is empty when
    feasible is False.
    """

    base: str
    ruleset: str
    duties: int
    pilots_available: dict[str, int]
    pilots_needed: dict[str, int]
    uncovered: int
    feasible: bool
    proven_optimal: bool
    seconds: float


def min_pilots_needed(problem: Problem, base: str, time_limit: float = 15.0) -> Sizing:
    sub = problem.model_copy(
        update={
            "duties": [d for d in problem.duties if d.base == base],
            "pilots": [p for p in problem.pilots if p.base == base],
        }
    )
    res = solve(sub, time_limit=time_limit, minimise_pilots=True)
    feasible = not res.uncovered
    return Sizing(
        base=base,
        ruleset=problem.ruleset.name,
        duties=len(sub.duties),
        pilots_available=dict(Counter(p.rank for p in sub.pilots)),
        pilots_needed=res.pilots_used if feasible else {},
        uncovered=len(res.uncovered),
        feasible=feasible,
        proven_optimal=res.status == "OPTIMAL" and feasible,
        seconds=res.seconds,
    )
