"""Step 1: group out-and-back turns into duties with the fewest duties (CP-SAT set partitioning)."""

from __future__ import annotations

from collections import defaultdict

from ortools.sat.python import cp_model

from crew_roster.models import Duty, Flight, Turn, is_night
from crew_roster.rules import Ruleset

MIN_SIT = 40  # minutes between arriving at base and the next departure in the same duty
MAX_SIT = 180  # longer sits are not worth pairing
REPORT_BEFORE = 60
RELEASE_AFTER = 30


def make_duty(
    duty_id: str, base: str, turns: list[Turn], flights: dict[str, Flight], rs: Ruleset
) -> Duty:
    turns = sorted(turns, key=lambda t: flights[t.out_id].dep)
    fl = [flights[f] for t in turns for f in t.flight_ids]
    report, release = fl[0].dep - REPORT_BEFORE, fl[-1].arr + RELEASE_AFTER
    return Duty(
        id=duty_id,
        base=base,
        report=report,
        release=release,
        flight_time=sum(f.block for f in fl),
        landings=len(fl),
        night=is_night(report, release, rs.night_start, rs.night_end),
        turn_ids=tuple(t.id for t in turns),
        flight_ids=tuple(f.id for f in fl),
    )


def candidate_chains(
    turns: list[Turn], flights: dict[str, Flight], rs: Ruleset
) -> list[tuple[Turn, ...]]:
    """Every single turn, plus every legal pair of turns from the same base."""
    # Imported here, not at module top: crew_roster.roster imports replan -> disrupt -> duties,
    # so a top-level import would be circular.
    from crew_roster.roster.check import duty_violations

    chains: list[tuple[Turn, ...]] = [(t,) for t in turns]
    by_base: dict[str, list[Turn]] = defaultdict(list)
    for t in turns:
        by_base[t.base].append(t)
    for base, ts in by_base.items():
        ts.sort(key=lambda t: (flights[t.out_id].dep, t.id))
        for a in ts:
            a_end = flights[a.back_id].arr
            for b in ts:
                if MIN_SIT <= flights[b.out_id].dep - a_end <= MAX_SIT:
                    if not duty_violations(make_duty("tmp", base, [a, b], flights, rs), rs):
                        chains.append((a, b))
    return chains


def build(
    turns: list[Turn], flights: dict[str, Flight], rs: Ruleset, time_limit: float = 10.0
) -> list[Duty]:
    chains = candidate_chains(turns, flights, rs)
    m = cp_model.CpModel()
    y = [m.new_bool_var(f"chain{i}") for i in range(len(chains))]
    cover = defaultdict(list)
    for i, chain in enumerate(chains):
        for t in chain:
            cover[t.id].append(y[i])
    for t in turns:
        m.add_exactly_one(cover[t.id])
    m.minimize(sum(y))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"duty builder: {solver.status_name(status)}")

    picked = [chains[i] for i in range(len(chains)) if solver.value(y[i])]
    drafts = sorted(
        (make_duty("tmp", c[0].base, list(c), flights, rs) for c in picked),
        key=lambda d: (d.base, d.report, d.turn_ids),
    )
    seq: dict[tuple[str, int], int] = defaultdict(int)
    duties = []
    for d in drafts:
        seq[d.base, d.day] += 1
        duties.append(d.model_copy(update={"id": f"{d.base}-D{d.day}-{seq[d.base, d.day]:02d}"}))
    return sorted(duties, key=lambda d: (d.report, d.id))
