from collections import Counter

from crew_roster.disrupt import FlightCancel, FlightDelay, PilotSick, apply
from crew_roster.eval.scenarios import make_scenarios
from crew_roster.service import base_problem


def test_deterministic_for_a_seed():
    assert make_scenarios(n=12, seed=3) == make_scenarios(n=12, seed=3)
    assert make_scenarios(n=12, seed=3) != make_scenarios(n=12, seed=4)


def test_ids_and_sizes():
    sc = make_scenarios()
    assert [s.id for s in sc] == [f"S{i:02d}" for i in range(50)]
    sizes = Counter(s.size for s in sc)
    assert set(sizes) == {"small", "medium", "large"}
    assert all(16 <= v <= 17 for v in sizes.values())
    bounds = {"small": (1, 1), "medium": (2, 3), "large": (4, 6)}
    for s in sc:
        lo, hi = bounds[s.size]
        assert lo <= len(s.disruptions) <= hi


def test_disruptions_follow_the_rules_and_apply_cleanly():
    problem, base = base_problem("dgca_current")
    for s in make_scenarios():
        pilots, turns = [], []
        for d in s.disruptions:
            if isinstance(d, PilotSick):
                assert 1 <= d.from_day <= 5 and d.to_day <= 6 and d.to_day - d.from_day <= 1
                on_day = {d_.id for d_ in problem.duties if d_.day == d.from_day}
                assert any(did in on_day for did, _ in base.duties_of(d.pilot_id))
                pilots.append(d.pilot_id)
            else:
                f = problem.flights[d.flight_id]
                turns.append(f.turn_id)
                if isinstance(d, FlightDelay):
                    assert 1 <= f.day <= 5 and d.minutes in {60, 120, 180, 240, 300}
                else:
                    assert isinstance(d, FlightCancel) and 1 <= f.day <= 6
        assert len(pilots) == len(set(pilots)) and len(turns) == len(set(turns))
        apply(problem, s.disruptions)  # raises ValueError on a bad scenario
