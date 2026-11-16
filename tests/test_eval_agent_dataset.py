from collections import Counter

import pytest

from crew_roster.agent.tools import Toolbox
from crew_roster.eval import agent_dataset
from crew_roster.eval.agent_dataset import CATEGORIES, build_dataset
from crew_roster.roster import Sizing
from crew_roster.service import evaluate, hours, pilot_status


def fake_sizing(base, ruleset):
    need = {"CPT": 20, "FO": 21} if ruleset == "dgca_current" else {"CPT": 18, "FO": 19}
    return Sizing(base=base, ruleset=ruleset, duties=63, pilots_available={"CPT": 20, "FO": 20},
                  pilots_needed=need, uncovered=0, feasible=True, proven_optimal=False,
                  seconds=1.0)


@pytest.fixture
def cases(monkeypatch):
    monkeypatch.setattr(agent_dataset, "sizing", fake_sizing)
    return build_dataset(seed=5, per_category=2, time_limit=2.0)


def test_small_dataset_is_deterministic_and_well_formed(cases, monkeypatch):
    assert cases == build_dataset(seed=5, per_category=2, time_limit=2.0)
    assert [c.category for c in cases].count("sizing") == 4
    assert set(Counter(c.category for c in cases)) == set(CATEGORIES)
    assert len({c.id for c in cases}) == len(cases)
    tools = {t.name for t in Toolbox("dgca_current", []).tools}
    for c in cases:
        assert c.expected_tool in tools
        assert all(isinstance(x, float) for x in c.expected_numbers)
        assert c.ruleset in ("dgca_current", "dgca_dec2025_exemption")


def test_ground_truth_comes_from_the_service(cases):
    h = next(c for c in cases if c.category == "hours")
    st = pilot_status(evaluate(h.ruleset, []), h.expected_args["pilot_id"], h.expected_args["day"])
    ft = next(u for u in st.usage if u.rule == "ft_7d")
    assert h.expected_numbers == [hours(ft.used), hours(ft.remaining)]
    assert h.expected_args["pilot_id"] in h.question

    r = next(c for c in cases if c.category == "roster")
    assert r.expected_tool == "get_roster" and len(r.expected_names) == 2
    assert r.expected_numbers == []

    w = next(c for c in cases if c.category == "what_if")
    assert w.disruptions == [] and w.expected_tool == "what_if"
    assert len(w.expected_numbers) == 1

    e = next(c for c in cases if c.category == "explain")
    assert len(e.disruptions) == 1 and e.expected_tool == "explain_change"
    change_ids = {ch.id for ch in evaluate(e.ruleset, e.disruptions, 2.0).changes}
    assert e.expected_args["change_id"] in change_ids

    s = [c for c in cases if c.category == "sizing"]
    assert {c.expected_args["base"] for c in s} == {"DEL", "BOM"}
    assert next(c for c in s if c.ruleset == "dgca_current").expected_numbers == [20.0, 21.0]


@pytest.mark.slow
def test_full_dataset_has_about_forty_cases():
    cases = build_dataset()
    counts = Counter(c.category for c in cases)
    assert counts == {"hours": 8, "roster": 8, "what_if": 8, "explain": 8, "sizing": 4}
    assert cases == build_dataset()
