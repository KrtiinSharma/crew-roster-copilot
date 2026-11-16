"""Comparing rosters."""

from __future__ import annotations

from crew_roster.models import Roster
from crew_roster.problem import Problem


def count_changes(problem: Problem, base: Roster, new: Roster) -> int:
    """Base slots on duties that still exist whose pilot is different (or now empty)."""
    ids = {d.id for d in problem.duties}
    return sum(1 for did, role, pid in base.slots() if did in ids and new.get(did, role) != pid)
