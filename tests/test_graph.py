from fakes import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from crew_roster.agent.graph import ChatTurn, run_agent
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
        AIMessage(content=f"DEL-C01 has flown {used} hours in the 7 days to day 3."),
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
