"""Base rosters are solved once and shipped as JSON so the API starts instantly."""

from __future__ import annotations

from pathlib import Path

from crew_roster.models import Roster
from crew_roster.problem import Problem
from crew_roster.roster.check import check
from crew_roster.roster.solver import solve

CACHE_DIR = Path(__file__).with_name("base_rosters")


def cache_path(ruleset_name: str) -> Path:
    return CACHE_DIR / f"{ruleset_name}.json"


def load_base_roster(problem: Problem, time_limit: float = 10.0) -> Roster:
    """Cached roster if it still fits this problem and is legal, else solve now."""
    path = cache_path(problem.ruleset.name)
    if path.exists():
        roster = Roster.model_validate_json(path.read_text(encoding="utf-8"))
        if set(roster.assignments) <= {d.id for d in problem.duties} and not check(problem, roster):
            return roster
    return solve(problem, time_limit=time_limit).roster
