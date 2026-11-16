"""Comparing rosters and explaining each change with checker reasons."""

from __future__ import annotations

from crew_roster.models import ROLES, Frozen, Roster, Violation
from crew_roster.problem import Problem
from crew_roster.roster.check import pilot_violations


class Change(Frozen):
    id: str
    duty_id: str
    role: str
    old_pilot: str | None
    new_pilot: str | None
    reasons: list[Violation]


def count_changes(problem: Problem, base: Roster, new: Roster) -> int:
    """Base slots on duties that still exist whose pilot is different (or now empty)."""
    ids = {d.id for d in problem.duties}
    return sum(1 for did, role, pid in base.slots() if did in ids and new.get(did, role) != pid)


def _key(v: Violation) -> tuple:
    return (v.rule, v.duty_id, v.day)


def _reasons(
    problem: Problem, old: Roster, new: Roster, duty_id: str, role: str, old_pid: str
) -> list[Violation]:
    """Why old_pid could not keep this slot: what breaks if they did."""
    duty = problem.duty_map()[duty_id]
    if duty.day in problem.sick.get(old_pid, frozenset()):
        return [
            Violation(
                rule="sick",
                pilot_id=old_pid,
                duty_id=duty_id,
                day=duty.day,
                message=f"reported sick for day {duty.day}",
            )
        ]
    trial = new
    old_slots = set(old.duties_of(old_pid))
    for slot in new.duties_of(old_pid):  # undo their new assignments, then give the slot back
        if slot not in old_slots:
            trial = trial.with_slot(*slot, None)
    trial = trial.with_slot(duty_id, role, old_pid)
    before = {_key(v) for v in pilot_violations(problem, new, old_pid)}
    found = [v for v in pilot_violations(problem, trial, old_pid) if _key(v) not in before]
    return found or [
        Violation(
            rule="knock_on",
            pilot_id=old_pid,
            duty_id=duty_id,
            day=duty.day,
            message="moved to free up cover or rebalance after the disruption",
        )
    ]


def diff(problem: Problem, old: Roster, new: Roster) -> list[Change]:
    duties = problem.duty_map()
    changes: list[Change] = []
    for did in sorted(duties, key=lambda i: (duties[i].report, i)):
        for role in ROLES:
            o, n = old.get(did, role), new.get(did, role)
            if o == n:
                continue
            reasons = _reasons(problem, old, new, did, role, o) if o else []
            changes.append(
                Change(
                    id=f"C{len(changes) + 1}",
                    duty_id=did,
                    role=role,
                    old_pilot=o,
                    new_pilot=n,
                    reasons=reasons,
                )
            )
    return changes
