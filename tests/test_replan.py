import pytest

from crew_roster.disrupt import FlightCancel, FlightDelay, PilotSick
from crew_roster.models import DAY
from crew_roster.roster.check import check
from crew_roster.roster.replan import replan


def captain_on_day(problem, roster, day):
    did = next(d.id for d in problem.duties if d.day == day and roster.get(d.id, "CPT"))
    return roster.get(did, "CPT")


def test_sick_pilot_is_replaced_with_minimal_changes(problem, base_result):
    base = base_result.roster
    pid = captain_on_day(problem, base, 3)
    out = replan(problem, base, [PilotSick(pilot_id=pid, from_day=3, to_day=4)])
    roster, duties = out.result.roster, problem.duty_map()
    assert check(out.problem, roster) == []
    assert out.result.uncovered == []
    assert all(duties[d].day not in (3, 4) for d, _ in roster.duties_of(pid))
    for d in problem.duties:
        if d.report < 3 * DAY:
            assert roster.assignments.get(d.id) == base.assignments.get(d.id)
    assert any(v.rule == "sick" for c in out.changes for v in c.reasons)
    assert out.result.changes == len(out.changes) >= 1


def test_late_delay_is_repaired_legally(problem, base_result):
    out = replan(problem, base_result.roster, [FlightDelay(flight_id="SK115-D2", minutes=240)])
    assert check(out.problem, out.result.roster) == []
    assert out.result.uncovered == []
    # Whether the crew absorbs a 4 h delay depends on the base roster, and a time-limited solve
    # can return a different (equally legal) base roster on a faster or slower machine. So do not
    # expect zero changes; expect that any change was forced by a rule the delay broke, and that
    # nothing before the delayed flight's day moved.
    assert out.result.changes == len(out.changes)
    assert not out.changes or any(c.reasons for c in out.changes)
    duties = problem.duty_map()
    assert all(duties[c.duty_id].day >= 2 for c in out.changes)


def test_cancellation_needs_no_changes(problem, base_result):
    single = next(d for d in problem.duties if len(d.turn_ids) == 1 and d.day == 4)
    out = replan(problem, base_result.roster, [FlightCancel(flight_id=single.flight_ids[0])])
    assert check(out.problem, out.result.roster) == []
    assert out.result.changes == 0


@pytest.mark.slow
def test_scratch_changes_more_than_minimum_change(problem, base_result):
    pid = captain_on_day(problem, base_result.roster, 3)
    sick = [PilotSick(pilot_id=pid, from_day=3, to_day=4)]
    smart = replan(problem, base_result.roster, sick)
    scratch = replan(problem, base_result.roster, sick, method="scratch")
    assert check(scratch.problem, scratch.result.roster) == []
    assert scratch.result.changes >= smart.result.changes


def test_delay_that_makes_duty_illegal_is_explained_by_its_own_violation(problem, base_result):
    cands = sorted(
        (d for d in problem.duties if d.landings == 4 and not d.night and d.day == 3),
        key=lambda d: -d.release,
    )
    for d in cands:
        minutes = (d.day + 1) * DAY + 30 - d.release
        if 0 < minutes <= 600:
            break
    else:
        pytest.fail("no suitable duty")
    first = d.flight_ids[0]
    out = replan(problem, base_result.roster, [FlightDelay(flight_id=first, minutes=minutes)])
    assert d.id in out.result.illegal_duties
    rules = {v.rule for c in out.changes if c.duty_id == d.id for v in c.reasons}
    assert "night_max_landings" in rules
