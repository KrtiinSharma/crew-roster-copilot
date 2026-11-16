"""Agent evaluation dataset. Every expected answer is computed through the service, never typed."""

from __future__ import annotations

import random

from pydantic import Field

from crew_roster.disrupt import Disruption, PilotSick
from crew_roster.models import Frozen
from crew_roster.rules import RULESETS
from crew_roster.service import TIME_RULES, evaluate, hours, pilot_status, sizing

CATEGORIES = ("hours", "roster", "what_if", "explain", "sizing")
SEAT = {"CPT": "captain", "FO": "first officer"}
LABEL = {"dgca_current": "the current DGCA rules",
         "dgca_dec2025_exemption": "the December 2025 DGCA exemption"}


class AgentCase(Frozen):
    id: str
    category: str
    question: str
    ruleset: str
    disruptions: list[Disruption] = []
    expected_tool: str
    expected_args: dict = {}
    expected_numbers: list[float] = []
    expected_names: list[str] = Field(default_factory=list)


def _who(p) -> str:
    return f"{p.name} ({p.id})"


def _days(a: int, b: int) -> str:
    return f"day {a}" if a == b else f"days {a} to {b}"


def build_dataset(seed: int = 5, per_category: int = 8,
                  time_limit: float = 10.0) -> list[AgentCase]:
    """~8 cases per category (4 sizing cases: 2 bases x 2 rulesets), reproducible for a seed.

    time_limit must match the one the agent runs with, so what_if / explain ground truth comes
    from the same (cached) re-plan the agent's tools will see.
    """
    rng = random.Random(seed)
    res0 = {rs: evaluate(rs, []) for rs in RULESETS}
    problem = res0["dgca_current"].problem
    pilots = sorted(problem.pilots, key=lambda p: p.id)
    pmap = problem.pilot_map()
    cases: list[AgentCase] = []

    def add(category: str, **kw) -> None:
        n = sum(1 for c in cases if c.category == category)
        cases.append(AgentCase(id=f"{category}-{n:02d}", category=category, **kw))

    # 1. hours: ft_7d used and remaining for a pilot who has flown in that window
    seen: set[tuple[str, int]] = set()
    while sum(c.category == "hours" for c in cases) < per_category:
        rs = RULESETS[len(seen) % 2]
        p, day = rng.choice(pilots), rng.randint(1, 6)
        ft = next(u for u in pilot_status(res0[rs], p.id, day).usage if u.rule == "ft_7d")
        if (p.id, day) in seen or ft.used == 0:
            continue
        seen.add((p.id, day))
        add("hours", ruleset=rs, expected_tool="pilot_status",
            question=f"How many flight hours has {_who(p)} flown in the 7 days up to day {day}, "
                     "and how many remain?",
            expected_args={"pilot_id": p.id, "day": day},
            expected_numbers=[hours(ft.used), hours(ft.remaining)])

    # 2. roster: both crew names on a duty
    base = res0["dgca_current"].roster
    crewed = [d for d in problem.duties if base.get(d.id, "CPT") and base.get(d.id, "FO")]
    for d in rng.sample(crewed, per_category):
        add("roster", ruleset="dgca_current", expected_tool="get_roster",
            question=f"Who is the captain and first officer on duty {d.id}?",
            expected_names=[pmap[base.get(d.id, "CPT")].name, pmap[base.get(d.id, "FO")].name])

    # sick pilots for what_if / explain: someone rostered on the first sick day
    def sick_pick(used: set[str]) -> PilotSick:
        while True:
            day = rng.randint(1, 5)
            on = sorted({p for did, _r, p in base.slots()
                         if problem.duty_map()[did].day == day} - used)
            if on:
                pid = rng.choice(on)
                used.add(pid)
                return PilotSick(pilot_id=pid, from_day=day, to_day=day + rng.randint(0, 1))

    used: set[str] = set()
    # 3. what_if: number of changes when a pilot calls in sick
    for _ in range(per_category):
        s = sick_pick(used)
        res = evaluate("dgca_current", [s], time_limit)
        add("what_if", ruleset="dgca_current", expected_tool="what_if",
            question=f"If {_who(pmap[s.pilot_id])} calls in sick on "
                     f"{_days(s.from_day, s.to_day)}, how many roster changes are needed?",
            expected_args={"sick": [{"pilot_id": s.pilot_id, "from_day": s.from_day,
                                     "to_day": s.to_day}]},
            expected_numbers=[float(res.stats.changes)])

    # 4. explain: with the sickness applied, why was someone replaced
    while sum(c.category == "explain" for c in cases) < per_category:
        s = sick_pick(used)
        res = evaluate("dgca_current", [s], time_limit)
        replaced = [c for c in res.changes if c.old_pilot]
        if not replaced:
            continue
        timed = [c for c in replaced if any(v.rule in TIME_RULES for v in c.reasons)]
        ch = rng.choice(timed or replaced)
        nums = [float(x) for v in ch.reasons if v.rule in TIME_RULES
                for x in (hours(v.value), hours(v.limit))]
        add("explain", ruleset="dgca_current", disruptions=[s], expected_tool="explain_change",
            question=f"Why was {_who(pmap[ch.old_pilot])} replaced as {SEAT[ch.role]} on duty "
                     f"{ch.duty_id}?",
            expected_args={"change_id": ch.id}, expected_numbers=nums)

    # 5. sizing: 2 bases x 2 rulesets (each ~15 s the first time)
    for rs in RULESETS:
        for b in ("DEL", "BOM"):
            need = sizing(b, rs).pilots_needed
            add("sizing", ruleset=rs, expected_tool="min_pilots_needed",
                question=f"How many captains and first officers does {b} need under {LABEL[rs]}?",
                expected_args={"base": b},
                expected_numbers=[float(need[r]) for r in ("CPT", "FO") if r in need])
    return cases
