"""Tiny hand-built problems for unit tests (no generator, no history unless given)."""

from crew_roster.models import DAY, Duty, Pilot, Roster, is_night
from crew_roster.problem import Problem
from crew_roster.rules import load


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def mk_duty(id, day, start, hours, ft_hours=None, landings=2, base="DEL"):
    report = day * DAY + hm(start)
    release = report + round(hours * 60)
    ft = round((ft_hours if ft_hours is not None else max(hours - 1.5, 0.5)) * 60)
    return Duty(
        id=id,
        base=base,
        report=report,
        release=release,
        flight_time=ft,
        landings=landings,
        night=is_night(report, release, 0, 360),
    )


def mk_pilot(id, rank="CPT", base="DEL", off=()):
    return Pilot(id=id, name=id, rank=rank, base=base, unavailable_days=frozenset(off))


def mk_history(pid, days, hours, ft_hours, start="06:00"):
    return {pid: [mk_duty(f"H{k}", k, start, hours, ft_hours=ft_hours) for k in days]}


def mk_problem(duties, pilots, history=None, ruleset="dgca_current", sick=None, horizon=7):
    return Problem(
        ruleset=load(ruleset),
        duties=duties,
        pilots=pilots,
        history=history or {},
        sick={k: frozenset(v) for k, v in (sick or {}).items()},
        horizon_days=horizon,
    )


def mk_roster(assignments):
    return Roster(assignments=assignments)
