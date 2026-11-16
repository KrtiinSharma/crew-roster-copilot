"""The single legality checker. Independent of the solver; everything is verified here."""

from __future__ import annotations

from crew_roster.models import Duty, Roster, Violation
from crew_roster.problem import Problem
from crew_roster.rules import Ruleset

WINDOWS = (
    ("ft_7d", 7, "flight_time"),
    ("ft_28d", 28, "flight_time"),
    ("duty_7d", 7, "length"),
    ("duty_28d", 28, "length"),
)


def duty_violations(duty: Duty, rs: Ruleset) -> list[Violation]:
    """Rules that depend only on the duty itself (no pilot can make it legal)."""
    out: list[Violation] = []

    def add(rule: str, value: int, limit: int, message: str) -> None:
        out.append(
            Violation(
                rule=rule, duty_id=duty.id, day=duty.day, value=value, limit=limit, message=message
            )
        )

    if duty.flight_time > rs.max_ft_per_duty:
        add("max_ft_per_duty", duty.flight_time, rs.max_ft_per_duty, "flight time in one duty")
    top = max(rs.max_fdp_by_landings)
    if duty.landings > top:
        add("max_landings", duty.landings, top, "landings in one duty")
    elif duty.length > rs.max_fdp_by_landings[duty.landings]:
        add(
            "max_fdp",
            duty.length,
            rs.max_fdp_by_landings[duty.landings],
            f"duty period with {duty.landings} landings",
        )
    if duty.night:
        if duty.length > rs.night_max_fdp:
            add("night_max_fdp", duty.length, rs.night_max_fdp, "night duty period")
        if duty.landings > rs.night_max_landings:
            add(
                "night_max_landings",
                duty.landings,
                rs.night_max_landings,
                "landings in a night duty",
            )
    return out


def pilot_violations(problem: Problem, roster: Roster, pilot_id: str) -> list[Violation]:
    rs, horizon = problem.ruleset, problem.horizon_days
    pilot = problem.pilot_map()[pilot_id]
    duties = problem.duty_map()
    sick = problem.sick.get(pilot_id, frozenset())
    off = problem.unavailable_days(pilot)
    out: list[Violation] = []

    def add(rule, duty_id=None, day=None, value=0, limit=0, message=""):
        out.append(
            Violation(
                rule=rule,
                pilot_id=pilot_id,
                duty_id=duty_id,
                day=day,
                value=value,
                limit=limit,
                message=message,
            )
        )

    mine: list[Duty] = []
    for did, role in roster.duties_of(pilot_id):
        d = duties.get(did)
        if d is None:
            add("unknown_duty", did)
            continue
        mine.append(d)
        if role != pilot.rank:
            add("wrong_rank", did, d.day, message=f"{pilot.rank} rostered as {role}")
        if d.base != pilot.base:
            add("wrong_base", did, d.day, message=f"{pilot.base} pilot on a {d.base} duty")
        if d.day in off:
            add(
                "sick" if d.day in sick else "unavailable",
                did,
                d.day,
                message=f"not available on day {d.day}",
            )

    timeline = sorted(problem.history.get(pilot_id, []) + mine, key=lambda d: (d.report, d.id))
    rostered = {d.id for d in mine}
    for a, b in zip(timeline, timeline[1:], strict=False):
        need, gap = max(rs.min_rest, a.length), b.report - a.release
        if b.id in rostered and gap < need:
            add("min_rest", b.id, b.day, gap, need, f"rest before duty {b.id}")

    for t in range(horizon):
        for rule, span, attr in WINDOWS:
            lo = t - span + 1
            total = sum(getattr(d, attr) for d in timeline if lo <= d.day <= t)
            limit = getattr(rs, rule)
            if total > limit:
                add(rule, None, t, total, limit, f"{span}-day total ending day {t}")

    busy = {k for d in timeline for k in d.touched_days()}
    for t in range(horizon):
        if not any(s not in busy and s + 1 not in busy for s in range(t - 6, t)):
            add(
                "weekly_rest",
                None,
                t,
                0,
                rs.weekly_rest,
                f"no 2 consecutive free days in the 7 days ending day {t}",
            )

    nights = {d.day for d in timeline if d.night}
    k = rs.max_consecutive_nights
    for t in range(-k, horizon - k):
        if all(day in nights for day in range(t, t + k + 1)):
            add(
                "consecutive_nights",
                None,
                t + k,
                k + 1,
                k,
                f"{k + 1} night duties in a row ending day {t + k}",
            )
    return out


def check(problem: Problem, roster: Roster) -> list[Violation]:
    duties, pilots = problem.duty_map(), problem.pilot_map()
    out: list[Violation] = []
    for did in roster.assignments:
        if did in duties:
            out += duty_violations(duties[did], problem.ruleset)
    for pid in sorted({p for _, _, p in roster.slots()}):
        if pid not in pilots:
            out.append(Violation(rule="unknown_pilot", pilot_id=pid))
            continue
        out += pilot_violations(problem, roster, pid)
    return out
