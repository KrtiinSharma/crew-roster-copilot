from fakes import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from crew_roster.agent.graph import ChatTurn, run_agent
from crew_roster.agent.numbers import extract
from crew_roster.agent.prompts import SYSTEM_PROMPT
from crew_roster.service import evaluate, hours, pilot_status


def ft7_used_hours():
    st = pilot_status(evaluate("dgca_current", []), "DEL-C01", 3)
    return hours(next(u.used for u in st.usage if u.rule == "ft_7d"))


def factory_for(model):
    return lambda tools: model


def test_answer_grounded_in_a_tool_call_is_verified():
    used = ft7_used_hours()
    model = ScriptedChatModel(script=[
        tool_call("pilot_status", {"pilot_id": "DEL-C01", "day": 3}),
        AIMessage(content=f"DEL-C01 has flown {used} hours in the seven days to day 3."),
    ])
    ans = run_agent("How much has DEL-C01 flown by day 3?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert ans.verified and ans.ungrounded == []
    assert [t.name for t in ans.tool_calls] == ["pilot_status"]
    assert str(used) in ans.answer


def test_invented_number_gets_one_retry_then_is_flagged():
    model = ScriptedChatModel(script=[AIMessage(content="They have 99.9 hours left.")])
    ans = run_agent("Hours left for DEL-C01?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert not ans.verified and ans.ungrounded == ["99.9"]
    assert model.calls == 2  # first draft + one retry after feedback


def test_retry_can_fix_the_answer():
    used = ft7_used_hours()
    model = ScriptedChatModel(script=[
        AIMessage(content="About 99.9 hours."),
        tool_call("pilot_status", {"pilot_id": "DEL-C01", "day": 3}),
        AIMessage(content=f"{used} hours flown."),
    ])
    ans = run_agent("Hours for DEL-C01 on day 3?", [ChatTurn(role="user", content="hi"),
                                                    ChatTurn(role="assistant", content="hello")],
                    "dgca_current", [], llm_factory=factory_for(model))
    assert ans.verified and model.calls == 3


def test_answer_without_numbers_is_verified():
    model = ScriptedChatModel(script=[AIMessage(content="Yes, the roster is fully legal.")])
    ans = run_agent("Is the roster legal?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert ans.verified and ans.tool_calls == []


def test_system_prompt_grounds_no_numbers_except_years():
    assert {v for _, v in extract(SYSTEM_PROMPT)} <= {2025.0}


def test_prompt_numbers_do_not_ground_an_answer():
    reply = "You need 6 more pilots, about 120 hours."
    model = ScriptedChatModel(script=[AIMessage(content=reply)])
    ans = run_agent("How many pilots?", [], "dgca_current", [], llm_factory=factory_for(model))
    assert not ans.verified and ans.ungrounded == ["6", "120"]


def test_feedback_does_not_reset_the_turn():
    used = ft7_used_hours()
    model = ScriptedChatModel(script=[
        tool_call("pilot_status", {"pilot_id": "DEL-C01", "day": 3}),
        AIMessage(content="About 99.9 hours."),
        AIMessage(content=f"{used} hours flown."),
    ])
    ans = run_agent("Hours for DEL-C01 on day 3?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert ans.verified and model.calls == 3


def test_numbers_from_earlier_turns_do_not_ground_a_new_answer():
    model = ScriptedChatModel(script=[AIMessage(content="Still 12.5 hours.")])
    history = [ChatTurn(role="user", content="hours?"),
               ChatTurn(role="assistant", content="12.5 hours")]
    ans = run_agent("and now?", history, "dgca_current", [], llm_factory=factory_for(model))
    assert not ans.verified


def test_question_minutes_ground_hours_but_tool_minutes_do_not():
    model = ScriptedChatModel(script=[AIMessage(content="A 90 minute delay is 1.5 hours.")])
    ans = run_agent("What if SK115 is delayed by 90 minutes?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert ans.verified
    model = ScriptedChatModel(script=[
        tool_call("get_roster", {"day": 1}), AIMessage(content="You have 60 hours left.")])
    ans = run_agent("How many hours are left?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert not ans.verified and ans.ungrounded == ["60"]


def test_blank_answer_is_replaced_and_not_verified():
    model = ScriptedChatModel(script=[AIMessage(content="  ")])
    ans = run_agent("Is the roster legal?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert ans.answer == "I couldn't produce an answer; please rephrase."
    assert not ans.verified
