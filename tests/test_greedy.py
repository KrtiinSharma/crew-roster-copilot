from crew_roster.disrupt import PilotSick
from crew_roster.roster.check import check
from crew_roster.roster.replan import replan


def test_greedy_repair_is_legal_and_cpsat_covers_at_least_as_much(problem, base_result):
    base = base_result.roster
    did = next(d.id for d in problem.duties if d.day == 2 and base.get(d.id, "FO"))
    sick = [PilotSick(pilot_id=base.get(did, "FO"), from_day=2, to_day=4)]
    greedy = replan(problem, base, sick, method="greedy")
    smart = replan(problem, base, sick)
    assert greedy.result.status == "GREEDY"
    assert check(greedy.problem, greedy.result.roster) == []
    assert len(smart.result.uncovered) <= len(greedy.result.uncovered)


def test_greedy_keeps_a_legal_roster_unchanged(problem, base_result):
    out = replan(problem, base_result.roster, [], method="greedy")
    assert out.result.changes == 0 and out.changes == []
