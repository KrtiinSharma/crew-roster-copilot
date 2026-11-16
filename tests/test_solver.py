import pytest
from factories import mk_duty, mk_pilot, mk_problem, mk_roster

from crew_roster.data import generate
from crew_roster.models import DAY
from crew_roster.problem import build_problem
from crew_roster.roster import cache
from crew_roster.roster.check import check
from crew_roster.roster.solver import solve
from crew_roster.rules import load

PILOTS = [
    mk_pilot("C1"),
    mk_pilot("C2"),
    mk_pilot("C3"),
    mk_pilot("F1", rank="FO"),
    mk_pilot("F2", rank="FO"),
    mk_pilot("F3", rank="FO"),
]


def test_solver_respects_rest_and_reports_shortage():
    d1 = mk_duty("D1", 0, "06:00", 10, ft_hours=6)  # release 16:00
    d2 = mk_duty("D2", 1, "02:00", 6, ft_hours=4)  # only 10 h later
    p = mk_problem([d1, d2], PILOTS)
    res = solve(p, time_limit=5)
    assert res.uncovered == [] and check(p, res.roster) == []
    assert res.roster.get("D1", "CPT") != res.roster.get("D2", "CPT")

    short = mk_problem([d1, d2], [PILOTS[0], PILOTS[3], PILOTS[4]])  # one captain
    res = solve(short, time_limit=5)
    assert [r for _, r in res.uncovered] == ["CPT"]
    assert check(short, res.roster) == []


def test_unavailable_pilot_is_not_used():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    p = mk_problem([d], [mk_pilot("C1", off=[2]), mk_pilot("C2"), mk_pilot("F1", rank="FO")])
    assert solve(p, time_limit=5).roster.get("D1", "CPT") == "C2"


def test_illegal_duty_is_left_uncovered():
    bad = mk_duty("BAD", 1, "06:00", 10, ft_hours=9)  # 9 h flight time
    res = solve(mk_problem([bad], PILOTS), time_limit=5)
    assert res.illegal_duties == ["BAD"] and len(res.uncovered) == 2


def test_resolve_from_base_changes_nothing():
    duties = [mk_duty(f"D{k}", k, "06:00", 8, ft_hours=6) for k in range(3)]
    p = mk_problem(duties, PILOTS)
    first = solve(p, time_limit=5)
    again = solve(p, base=first.roster, time_limit=5)
    assert again.changes == 0 and again.roster == first.roster


def test_locked_duties_keep_their_crew():
    duties = [mk_duty(f"D{k}", k, "06:00", 8, ft_hours=6) for k in range(3)]
    p = mk_problem(duties, PILOTS)
    manual = mk_roster({f"D{k}": {"CPT": "C3", "FO": "F3"} for k in range(3)})
    assert check(p, manual) == []
    res = solve(p, base=manual, locked_before=DAY, change_weight=0, time_limit=5)
    assert res.roster.assignments["D0"] == {"CPT": "C3", "FO": "F3"}


def test_base_roster_is_legal_and_fully_crewed(problem, base_result):
    assert check(problem, base_result.roster) == []
    assert base_result.uncovered == []


def test_cache_round_trip(problem, base_result, tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    cache.cache_path(problem.ruleset.name).write_text(base_result.roster.model_dump_json())
    assert cache.load_base_roster(problem) == base_result.roster


@pytest.mark.slow
def test_solve_is_deterministic(problem, base_result):
    assert solve(problem, time_limit=10).roster == base_result.roster


@pytest.mark.slow
def test_exemption_roster_is_legal():
    p = build_problem(generate(), load("dgca_dec2025_exemption"))
    res = solve(p, time_limit=10)
    assert check(p, res.roster) == [] and res.uncovered == []


def test_tiny_solve_does_not_hit_wall_cap():
    d = mk_duty("D1", 0, "06:00", 8, ft_hours=6)
    assert solve(mk_problem([d], PILOTS), time_limit=5).hit_wall_cap is False
