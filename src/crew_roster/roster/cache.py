"""Base rosters are solved once and shipped as JSON so the API starts instantly."""

from __future__ import annotations

import warnings
from pathlib import Path

from crew_roster.models import ROLES, Roster
from crew_roster.problem import Problem
from crew_roster.roster.check import check, duty_violations
from crew_roster.roster.solver import solve

CACHE_DIR = Path(__file__).with_name("base_rosters")


def cache_path(ruleset_name: str) -> Path:
    return CACHE_DIR / f"{ruleset_name}.json"


def load_base_roster(problem: Problem, time_limit: float = 10.0) -> Roster:
    """Cached roster if it exactly fits this problem, is fully crewed and legal, else solve now."""
    if problem.sick:
        raise ValueError("base rosters are for undisrupted problems (problem.sick is non-empty)")
    name = problem.ruleset.name
    path = cache_path(name)
    if path.exists():
        roster = Roster.model_validate_json(path.read_text(encoding="utf-8"))
        legal = {d.id for d in problem.duties if not duty_violations(d, problem.ruleset)}
        full = all(roster.get(did, role) for did in legal for role in ROLES)
        if set(roster.assignments) == legal and full and not check(problem, roster):
            return roster
    warnings.warn(f"base roster cache for {name} is missing or stale; solving now", stacklevel=2)
    return solve(problem, time_limit=time_limit).roster
