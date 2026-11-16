import pytest

from crew_roster.disrupt import FlightCancel, FlightDelay, PilotSick, apply, lock_time
from crew_roster.models import DAY


def test_apply_does_not_mutate(problem):
    before = problem.model_dump()
    apply(
        problem,
        [
            FlightDelay(flight_id="SK101-D2", minutes=90),
            PilotSick(pilot_id="DEL-C01", from_day=1, to_day=2),
        ],
    )
    assert problem.model_dump() == before


def test_delay_shifts_the_rest_of_the_duty(problem):
    d = next(d for d in problem.duties if "SK101-D2" in d.flight_ids)
    nd = apply(problem, [FlightDelay(flight_id="SK101-D2", minutes=90)]).duty_map()[d.id]
    assert nd.report == d.report + 90 and nd.release == d.release + 90


def test_cancel_removes_the_turn(problem):
    single = next(d for d in problem.duties if len(d.turn_ids) == 1)
    new = apply(problem, [FlightCancel(flight_id=single.flight_ids[0])])
    assert single.id not in new.duty_map()
    assert not set(single.flight_ids) & set(new.flights)

    double = next(d for d in problem.duties if len(d.turn_ids) == 2)
    new2 = apply(problem, [FlightCancel(flight_id=double.flight_ids[-1])])
    assert new2.duty_map()[double.id].landings == 2


def test_sick_marks_days_and_lock_time(problem):
    sick = PilotSick(pilot_id="BOM-F03", from_day=3, to_day=4)
    new = apply(problem, [sick])
    assert new.sick["BOM-F03"] == frozenset({3, 4})
    delay = FlightDelay(flight_id="SK101-D5", minutes=60)
    assert lock_time(problem, [sick, delay]) == 3 * DAY
    assert lock_time(problem, []) is None


def test_unknown_ids_are_rejected(problem):
    with pytest.raises(ValueError):
        apply(problem, [PilotSick(pilot_id="NOPE", from_day=1, to_day=1)])
    with pytest.raises(ValueError):
        apply(problem, [FlightCancel(flight_id="SK999-D1")])
