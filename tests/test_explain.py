import json

from factories import mk_duty, mk_pilot, mk_problem, mk_roster
from fakes import ScriptedChatModel
from langchain_core.messages import AIMessage

from crew_roster.agent.explain import explain_changes, template
from crew_roster.roster.diff import diff

PILOTS = [mk_pilot("C1"), mk_pilot("C2"), mk_pilot("F1", rank="FO"), mk_pilot("F2", rank="FO")]


def rest_case():
    d1 = mk_duty("D1", 0, "08:00", 13, ft_hours=7)
    d2 = mk_duty("D2", 1, "06:00", 8, ft_hours=6)
    problem = mk_problem([d1, d2], PILOTS)
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}, "D2": {"CPT": "C1", "FO": "F2"}})
    new = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}, "D2": {"CPT": "C2", "FO": "F2"}})
    return problem, diff(problem, old, new)


def test_templates_state_the_rule_and_numbers():
    problem, [change] = rest_case()
    text = template(change, problem)
    assert text == ("D2: C1 would get only 9h00 rest before this duty (minimum 13h00); "
                    "C2 takes the captain seat.")


def test_sick_and_uncrewed_templates():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    problem = mk_problem([d], PILOTS, sick={"C1": [2]})
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}})
    [change] = diff(problem, old, mk_roster({"D1": {"FO": "F1"}}))
    assert template(change, problem) == (
        "D1: C1 reported sick for day 2; the captain seat is left uncrewed.")


def test_llm_rewrite_is_used_only_when_numbers_match():
    problem, changes = rest_case()
    cid = changes[0].id
    good = ScriptedChatModel(script=[AIMessage(content=json.dumps(
        {cid: "C2 flies D2 because C1 would only get 9h00 of rest, below the 13h00 minimum."}))])
    out = explain_changes(changes, problem, lambda tools: good)
    assert out[cid].startswith("C2 flies D2")
    bad = ScriptedChatModel(script=[AIMessage(content=json.dumps(
        {cid: "C1 would only get 7 hours of rest."}))])
    out = explain_changes(changes, problem, lambda tools: bad)
    assert out[cid] == template(changes[0], problem)


def test_llm_failure_falls_back_to_templates():
    problem, changes = rest_case()

    def broken(tools):
        raise RuntimeError("no key")

    assert explain_changes(changes, problem, broken) == {
        c.id: template(c, problem) for c in changes}
    assert explain_changes(changes, problem, None) == {c.id: template(c, problem) for c in changes}
