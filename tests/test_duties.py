from crew_roster.duties import MIN_SIT
from crew_roster.problem import build_problem
from crew_roster.roster.check import duty_violations
from crew_roster.rules import load


def test_every_turn_in_exactly_one_duty(problem, airline):
    seen = [t for d in problem.duties for t in d.turn_ids]
    assert sorted(seen) == sorted(airline.turns)


def test_duties_are_legal_and_well_formed(problem):
    assert len({d.id for d in problem.duties}) == len(problem.duties)
    for d in problem.duties:
        assert duty_violations(d, problem.ruleset) == [], d.id
        fl = [problem.flights[f] for f in d.flight_ids]
        assert fl[0].origin == d.base == fl[-1].dest
        assert d.report == fl[0].dep - 60 and d.release == fl[-1].arr + 30
        assert d.landings == len(fl) <= 4
        assert all(b.dep - a.arr >= MIN_SIT for a, b in zip(fl, fl[1:], strict=False))


def test_builder_merges_some_turns(problem, airline):
    assert len(problem.duties) < len(airline.turns)


def test_exemption_allows_merging_night_turns(airline):
    cur = build_problem(airline, load("dgca_current"))
    exm = build_problem(airline, load("dgca_dec2025_exemption"))
    assert len(exm.duties) < len(cur.duties)
    assert any(d.night and d.landings > 2 for d in exm.duties)
    assert not any(d.night and d.landings > 2 for d in cur.duties)
