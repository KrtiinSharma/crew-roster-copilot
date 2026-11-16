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


def test_overlapping_duties_need_two_crews():
    duties = [mk_duty("A", 0, "06:00", 8, ft_hours=6), mk_duty("B", 0, "07:00", 8, ft_hours=6)]
    s = min_pilots_needed(mk_problem(duties, PILOTS), "DEL", time_limit=5)
    assert s.pilots_needed == {"CPT": 2, "FO": 2}


@pytest.mark.slow
def test_exemption_needs_no_more_pilots_than_current_rules():
    airline = generate()
    cur = min_pilots_needed(build_problem(airline, load("dgca_current")), "BOM")
    exm = min_pilots_needed(build_problem(airline, load("dgca_dec2025_exemption")), "BOM")
    assert cur.uncovered == exm.uncovered == 0
    assert sum(exm.pilots_needed.values()) <= sum(cur.pilots_needed.values())
