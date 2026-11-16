from factories import mk_duty, mk_pilot, mk_problem, mk_roster

from crew_roster.roster.check import check
from crew_roster.roster.diff import diff

PILOTS = [mk_pilot("C1"), mk_pilot("C2"), mk_pilot("F1", rank="FO"), mk_pilot("F2", rank="FO")]


def rules(change):
    return {v.rule for v in change.reasons}


def test_reason_names_the_rule_the_old_pilot_would_break():
    # D1 releases 21:00 on day 0; D2 reports 06:00 on day 1 -> only 9 h rest.
    d1 = mk_duty("D1", 0, "08:00", 13, ft_hours=7)
    d2 = mk_duty("D2", 1, "06:00", 8, ft_hours=6)
    problem = mk_problem([d1, d2], PILOTS)
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}, "D2": {"CPT": "C1", "FO": "F2"}})
    new = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}, "D2": {"CPT": "C2", "FO": "F2"}})
    assert check(problem, new) == []
    [change] = diff(problem, old, new)
    got = (change.duty_id, change.role, change.old_pilot, change.new_pilot)
    assert got == ("D2", "CPT", "C1", "C2")
    assert rules(change) == {"min_rest"}


def test_unforced_swap_is_reported_as_knock_on():
    d1 = mk_duty("D1", 0, "06:00", 8, ft_hours=6)
    problem = mk_problem([d1], PILOTS)
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}})
    new = mk_roster({"D1": {"CPT": "C2", "FO": "F1"}})
    [change] = diff(problem, old, new)
    assert rules(change) == {"knock_on"}


def test_sick_pilot_reason_is_sick():
    d1 = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    problem = mk_problem([d1], PILOTS, sick={"C1": [2]})
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}})
    new = mk_roster({"D1": {"CPT": "C2", "FO": "F1"}})
    [change] = diff(problem, old, new)
    assert rules(change) == {"sick"}


def test_change_ids_are_content_based():
    d1 = mk_duty("D1", 0, "06:00", 8, ft_hours=6)
    problem = mk_problem([d1], PILOTS)
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}})
    new = mk_roster({"D1": {"CPT": "C2", "FO": "F2"}})
    assert [c.id for c in diff(problem, old, new)] == ["D1:CPT", "D1:FO"]
