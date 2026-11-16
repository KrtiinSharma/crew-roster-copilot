"""Step 2: CP-SAT pilot assignment — base roster, minimum-change re-plan, crew sizing.

Every hard constraint mirrors a rule in roster/check.py, so a solution is legal by construction;
check() still verifies it independently. Assignments on locked (already started) duties are
fixed; constraints that the locked part already breaks are not made worse, never infeasible.
"""

from __future__ import annotations

import time
from collections import defaultdict

from ortools.sat.python import cp_model

from crew_roster.models import DAY, ROLES, Duty, Frozen, Roster
from crew_roster.problem import Problem
from crew_roster.roster.check import WINDOWS, duty_violations
from crew_roster.roster.diff import count_changes

W_UNCOVERED = 10_000_000
W_CHANGE = 10_000
WALL_CAP_FACTOR = 6  # wall-clock safety net = this many times time_limit


class SolveResult(Frozen):
    roster: Roster
    uncovered: list[tuple[str, str]]
    illegal_duties: list[str]
    status: str
    seconds: float
    changes: int = 0
    pilots_used: dict[str, int] = {}
    hit_wall_cap: bool = False


def solve(
    problem: Problem,
    base: Roster | None = None,
    locked_before: int | None = None,
    time_limit: float = 10.0,
    minimise_pilots: bool = False,
    change_weight: int = W_CHANGE,
    workers: int = 8,
) -> SolveResult:
    t0 = time.perf_counter()
    rs, horizon = problem.ruleset, problem.horizon_days
    legal = [d for d in problem.duties if not duty_violations(d, rs)]
    # Illegal duties (locked or not) stay out of the model and are reported uncovered, not kept.
    illegal = [d.id for d in problem.duties if duty_violations(d, rs)]
    rank_of = {p.id: p.rank for p in problem.pilots}
    m = cp_model.CpModel()
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    forced: set[tuple[str, str]] = set()
    mine: dict[str, list[Duty]] = defaultdict(list)

    def is_locked(d: Duty) -> bool:
        return locked_before is not None and d.report < locked_before

    for p in problem.pilots:
        off = problem.unavailable_days(p)
        for d in legal:
            if d.base != p.base or d.day in off:
                continue
            in_base = base is not None and base.get(d.id, p.rank) == p.id
            if is_locked(d) and not in_base:
                continue
            v = m.new_bool_var(f"x[{p.id},{d.id}]")
            x[p.id, d.id] = v
            mine[p.id].append(d)
            if is_locked(d):
                m.add(v == 1)
                forced.add((p.id, d.id))

    def add_le(terms: list[tuple[int, tuple[str, str]]], limit: int) -> None:
        terms = [(c, k) for c, k in terms if k in x and c]
        if sum(c for c, _ in terms) <= limit:
            return
        if sum(c for c, k in terms if k in forced) > limit:
            for _, k in terms:  # already broken by locked duties: just don't add more
                if k not in forced:
                    m.add(x[k] == 0)
            return
        m.add(sum(c * x[k] for c, k in terms) <= limit)

    # coverage (soft)
    by_slot: dict[tuple[str, str], list] = defaultdict(list)
    for (pid, did), v in x.items():
        by_slot[did, rank_of[pid]].append(v)
    u = {}
    for d in legal:
        for role in ROLES:
            u[d.id, role] = m.new_bool_var(f"u[{d.id},{role}]")
            m.add(sum(by_slot[d.id, role]) + u[d.id, role] == 1)

    for p in problem.pilots:
        ds = sorted(mine[p.id], key=lambda d: (d.report, d.id))
        hist = problem.history.get(p.id, [])

        def key(d: Duty, pid: str = p.id) -> tuple[str, str]:
            return (pid, d.id)

        for k in range(horizon):  # one duty per calendar day (operational rule)
            add_le([(1, key(d)) for d in ds if d.day == k], 1)

        if hist:  # rest after the last history duty
            last = max(hist, key=lambda h: h.release)
            need = max(rs.min_rest, last.length)
            for d in ds:
                if d.report - last.release < need:
                    add_le([(1, key(d))], 0)

        for i, a in enumerate(ds):  # rest between roster duties
            need = max(rs.min_rest, a.length)
            for b in ds[i + 1 :]:
                if b.report - a.release >= need:
                    break
                add_le([(1, key(a)), (1, key(b))], 1)

        for t in range(horizon):  # rolling flight / duty time incl. history
            for rule, span, attr in WINDOWS:
                lo = t - span + 1
                used = sum(getattr(h, attr) for h in hist if lo <= h.day <= t)
                add_le(
                    [(getattr(d, attr), key(d)) for d in ds if lo <= d.day <= t],
                    getattr(rs, rule) - used,
                )

        busy_hist = {k for h in hist for k in h.touched_days()}  # weekly rest
        touching: dict[int, list[Duty]] = defaultdict(list)
        for d in ds:
            for k in d.touched_days():
                touching[k].append(d)
        block: dict[int, object] = {}
        for s in range(-6, horizon - 1):
            days = (s, s + 1)
            if any(k in busy_hist for k in days):
                block[s] = False
                continue
            ds_touch = list({d.id: d for k in days for d in touching.get(k, [])}.values())
            if any(key(d) in forced for d in ds_touch):
                block[s] = False
            elif not ds_touch:
                block[s] = True
            else:
                o = m.new_bool_var(f"rest[{p.id},{s}]")
                for d in ds_touch:
                    m.add_implication(o, x[key(d)].Not())
                block[s] = o
        for t in range(horizon):
            opts = [block[s] for s in range(t - 6, t)]
            if any(o is True for o in opts):
                continue
            lits = [o for o in opts if o is not False]
            if lits:
                m.add_bool_or(lits)

        k_n = rs.max_consecutive_nights  # consecutive night duties
        hist_nights = {h.day for h in hist if h.night}
        for t in range(-k_n, horizon - k_n):
            window = range(t, t + k_n + 1)
            hn = sum(1 for day in window if day in hist_nights)
            add_le([(1, key(d)) for d in ds if d.night and d.day in window], k_n - hn)

    objective = [W_UNCOVERED * sum(u.values())]
    if minimise_pilots:
        for p in problem.pilots:
            if mine[p.id]:
                used = m.new_bool_var(f"used[{p.id}]")
                for d in mine[p.id]:
                    m.add_implication(x[p.id, d.id], used)
                objective.append(used)
    else:
        groups: dict[tuple[str, str], list] = defaultdict(list)
        for p in problem.pilots:
            tot = m.new_int_var(0, horizon * DAY, f"ft[{p.id}]")
            m.add(tot == sum(d.flight_time * x[p.id, d.id] for d in mine[p.id]))
            groups[p.base, p.rank].append(tot)
        for g in groups.values():
            hi = m.new_int_var(0, horizon * DAY, "")
            lo = m.new_int_var(0, horizon * DAY, "")
            m.add_max_equality(hi, g)
            m.add_min_equality(lo, g)
            objective.append(hi - lo)
    if base is not None and change_weight:
        legal_ids = {d.id for d in legal}
        kept = [x[pid, did] for did, _, pid in base.slots() if did in legal_ids and (pid, did) in x]
        objective.append(-change_weight * sum(kept))
        for (pid, did), v in x.items():
            m.add_hint(v, int(base.get(did, rank_of[pid]) == pid))
    m.minimize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    solver.parameters.interleave_search = workers > 1  # deterministic parallel search
    solver.parameters.random_seed = 0
    solver.parameters.max_deterministic_time = time_limit
    wall_cap = WALL_CAP_FACTOR * time_limit  # safety net only; may break determinism if hit
    solver.parameters.max_time_in_seconds = wall_cap
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"roster solver: {solver.status_name(status)}")

    assignments: dict[str, dict[str, str]] = defaultdict(dict)
    for (pid, did), v in x.items():
        if solver.value(v):
            assignments[did][rank_of[pid]] = pid
    roster = Roster(assignments=dict(assignments))
    uncovered = sorted(k for k, v in u.items() if solver.value(v))
    uncovered += [(did, r) for did in illegal for r in ROLES]
    used_by_rank: dict[str, int] = defaultdict(int)
    for pid in {p for _, _, p in roster.slots()}:
        used_by_rank[rank_of[pid]] += 1
    return SolveResult(
        roster=roster,
        uncovered=uncovered,
        illegal_duties=illegal,
        status=solver.status_name(status),
        seconds=round(time.perf_counter() - t0, 3),
        changes=count_changes(problem, base, roster) if base is not None else 0,
        pilots_used=dict(used_by_rank),
        hit_wall_cap=status != cp_model.OPTIMAL and solver.wall_time >= wall_cap - 0.05,
    )
