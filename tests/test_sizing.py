import pytest
from factories import mk_duty, mk_pilot, mk_problem

from crew_roster.data import generate
from crew_roster.problem import build_problem
from crew_roster.roster.sizing import min_pilots_needed
from crew_roster.rules import load

PILOTS = [mk_pilot(f"C{i}") for i in range(3)] + [mk_pilot(f"F{i}", rank="FO") for i in range(3)]


def test_one_crew_can_fly_three_spread_out_duties():
    duties = [mk_duty(f"D{k}", k, "06:00", 8, ft_hours=6) for k in range(3)]
    s = min_pilots_needed(mk_problem(duties, PILOTS), "DEL", time_limit=5)
    assert s.pilots_needed == {"CPT": 1, "FO": 1} and s.uncovered == 0
    assert s.feasible and s.proven_optimal


def test_overlapping_duties_need_two_crews():
    duties = [mk_duty("A", 0, "06:00", 8, ft_hours=6), mk_duty("B", 0, "07:00", 8, ft_hours=6)]
    s = min_pilots_needed(mk_problem(duties, PILOTS), "DEL", time_limit=5)
    assert s.pilots_needed == {"CPT": 2, "FO": 2}
    assert s.feasible and s.proven_optimal


def test_infeasible_base_reports_no_pilot_count():
    bad = mk_duty("BAD", 1, "06:00", 10, ft_hours=9)  # 9 h flight time: illegal for anyone
    s = min_pilots_needed(mk_problem([bad], PILOTS), "DEL", time_limit=5)
    assert s.feasible is False and s.pilots_needed == {} and s.proven_optimal is False


@pytest.mark.slow
def test_exemption_needs_no_more_pilots_than_current_rules():
    airline = generate()
    cur = min_pilots_needed(build_problem(airline, load("dgca_current")), "BOM")
    exm = min_pilots_needed(build_problem(airline, load("dgca_dec2025_exemption")), "BOM")
    assert cur.feasible and exm.feasible
    # upper bounds unless proven_optimal; the solver is deterministic, so this is stable
    assert sum(exm.pilots_needed.values()) <= sum(cur.pilots_needed.values())
