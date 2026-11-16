import pytest

from crew_roster.disrupt import PilotSick
from crew_roster.service import (
    canonical,
    duty_views,
    evaluate,
    flight_views,
    hm,
    lookup,
    pilot_status,
    pilot_views,
    stamp,
)


def test_formatting_helpers():
    assert stamp(3 * 1440 + 6 * 60) == "D3 06:00"
    assert stamp(1440 + 55) == "D1 00:55"
    assert hm(510) == "8h30"


def test_base_scenario_is_cached_and_clean():
    res = evaluate("dgca_current", [])
    assert evaluate("dgca_current", []) is res
    s = res.stats
    assert (s.duties, s.uncovered, s.violations, s.changes) == (126, 0, 0, 0)
    assert len(pilot_views(res.problem)) == 80
    assert len(flight_views(res.problem)) == 294


def test_route_and_duty_views():
    res = evaluate("dgca_current", [])
    views = duty_views(res)
    assert len(views) == 126
    first = next(v for v in views if "SK101-D0" in v.flight_ids)
    assert first.route == "DEL-BOM-DEL" and first.report == "D0 05:00"
    assert first.cpt and first.fo and first.legal
    pid = first.cpt
    assert all(pid in (v.cpt, v.fo) for v in duty_views(res, pilot_id=pid))
    assert {v.day for v in duty_views(res, day=2)} == {2}


def test_sick_scenario_replans_legally():
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    sick = [PilotSick(pilot_id=pid, from_day=3, to_day=4)]
    res = evaluate("dgca_current", sick)
    assert res.stats.violations == 0 and res.stats.uncovered == 0
    assert res.stats.changes >= 1 and res.changes
    assert canonical(sick) == canonical([PilotSick(pilot_id=pid, from_day=3, to_day=4)])


def test_pilot_status_and_lookup():
    res = evaluate("dgca_current", [])
    st = pilot_status(res, "DEL-C01", 3)
    assert st.pilot.id == "DEL-C01" and {u.rule for u in st.usage} == {
        "ft_7d", "ft_28d", "duty_7d", "duty_28d"}
    found = lookup(res.problem, "SK115")
    assert len(found["flights"]) == 7 and found["pilots"] == []
    assert lookup(res.problem, "del-c01")["pilots"][0]["id"] == "DEL-C01"


def test_bad_inputs_raise_value_error():
    res = evaluate("dgca_current", [])
    with pytest.raises(ValueError):
        evaluate("nope", [])
    with pytest.raises(ValueError):
        pilot_status(res, "NOPE", 1)
    with pytest.raises(ValueError):
        pilot_status(res, "DEL-C01", 9)
    with pytest.raises(ValueError):
        duty_views(res, pilot_id="NOPE")
