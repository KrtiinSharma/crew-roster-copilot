import json

import pytest

from crew_roster.agent.tools import Toolbox
from crew_roster.service import duty_views, evaluate


def call(box, name, **args):
    tool = next(t for t in box.tools if t.name == name)
    return json.loads(tool.invoke(args))


def test_tool_names_and_roster_filter():
    box = Toolbox("dgca_current", [])
    assert [t.name for t in box.tools] == [
        "get_roster", "pilot_status", "what_if", "min_pilots_needed", "explain_change", "lookup"]
    out = call(box, "get_roster", day=2)
    assert out["total"] == len(duty_views(evaluate("dgca_current", []), day=2))
    assert all(r["day"] == 2 for r in out["rows"]) and len(out["rows"]) <= 25
    assert set(out["pilot_names"]) >= {r["captain"] for r in out["rows"]}


def test_pilot_status_reports_hours():
    box = Toolbox("dgca_current", [])
    out = call(box, "pilot_status", pilot_id="DEL-C01", day=3)
    limits = {x["rule"]: x for x in out["limits"]}
    assert limits["ft_7d"]["limit_hours"] == 35.0
    ft = limits["ft_7d"]
    assert ft["used_hours"] + ft["remaining_hours"] == pytest.approx(35.0, abs=0.011)
    assert box.trace[-1].name == "pilot_status" and box.trace[-1].ok


def test_what_if_replans_without_touching_the_live_scenario():
    box = Toolbox("dgca_current", [])
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    out = call(box, "what_if", sick=[{"pilot_id": pid, "from_day": 3, "to_day": 4}])
    assert out["rule_breaches"] == 0 and out["changes"] >= 1
    assert any(r["rule"] == "sick" for c in out["change_list"] for r in c["reasons"])
    assert box.current().stats.changes == 0  # live scenario unchanged


def test_explain_change_uses_the_current_scenario():
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    from crew_roster.disrupt import PilotSick

    box = Toolbox("dgca_current", [PilotSick(pilot_id=pid, from_day=3, to_day=4)])
    cid = box.current().changes[0].id
    out = call(box, "explain_change", change_id=cid)
    assert out["id"] == cid and out["reasons"]


def test_errors_come_back_as_json():
    box = Toolbox("dgca_current", [])
    assert "error" in call(box, "pilot_status", pilot_id="NOPE", day=1)
    assert "error" in call(box, "what_if")
    assert "error" in call(box, "explain_change", change_id="X:CPT")
    assert box.trace[-1].ok is False
    assert call(box, "lookup", query="SK115")["flights"]


def test_schema_violations_come_back_as_json_and_are_traced():
    box = Toolbox("dgca_current", [])
    out = call(box, "pilot_status", pilot_id="DEL-C01", day=9)
    assert out["error"].startswith("invalid arguments:") and "day" in out["error"]
    assert box.trace[-1].name == "pilot_status" and box.trace[-1].ok is False
    assert "error" in call(box, "min_pilots_needed", base="XXX")
    assert "error" in call(box, "pilot_status", day=2)  # missing pilot_id
