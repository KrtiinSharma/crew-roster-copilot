import json
import sys
import types

import groq
import httpx
import pytest
from fakes import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from crew_roster.agent.graph import AgentAnswer
from crew_roster.agent.tools import ToolCallTrace
from crew_roster.config import Settings
from crew_roster.eval import agent_eval
from crew_roster.eval.agent_dataset import AgentCase
from crew_roster.eval.agent_eval import model_slug, run_agent_eval, score, summarise
from crew_roster.service import evaluate, hours, pilot_status

HOURS = AgentCase(id="hours-00", category="hours", ruleset="dgca_current",
                  question="How many flight hours has DEL-C01 flown in the 7 days up to day 3?",
                  expected_tool="pilot_status", expected_args={"pilot_id": "DEL-C01", "day": 3},
                  expected_numbers=[12.5, 22.5])
ROSTER = AgentCase(id="roster-00", category="roster", ruleset="dgca_current",
                   question="Who flies DEL-D1-01?", expected_tool="get_roster",
                   expected_names=["Capt. A. Rao", "F/O B. Sen"])


def answer(text, calls=(), verified=True):
    return AgentAnswer(answer=text, verified=verified, ungrounded=[] if verified else ["9"],
                       tool_calls=[ToolCallTrace(name=n, args=a, seconds=0.1, ok=True)
                                   for n, a in calls])


def test_score_all_good():
    s = score(HOURS, answer("Used 12.5 h, 22.5 h left.",
                            [("lookup", {"query": "x"}),
                             ("pilot_status", {"pilot_id": "DEL-C01", "day": 3})]), seconds=2.5)
    assert s == {"tool_ok": True, "args_ok": True, "numbers_recall": 1.0, "names_ok": None,
                 "grounded": True, "n_tool_calls": 2, "seconds": 2.5}


def test_score_missing_tool_wrong_args_and_missing_numbers():
    s = score(HOURS, answer("About 12.5 hours.", [("get_roster", {})], verified=False))
    assert not s["tool_ok"] and not s["args_ok"] and not s["grounded"]
    assert s["numbers_recall"] == 0.5
    s = score(HOURS, answer("12.54 and 22.46", [("pilot_status",
                                                 {"pilot_id": "DEL-C01", "day": 4})]))
    assert s["tool_ok"] and not s["args_ok"] and s["numbers_recall"] == 1.0  # within 0.051


def test_score_names_and_no_expected_numbers():
    s = score(ROSTER, answer("Captain Capt. A. Rao with F/O B. Sen.", [("get_roster", {})]))
    assert s["names_ok"] is True and s["numbers_recall"] == 1.0 and s["args_ok"]
    assert score(ROSTER, answer("Capt. A. Rao", [("get_roster", {})]))["names_ok"] is False


def test_summarise_per_metric_and_category():
    rows = [{"category": "hours", "tool_ok": True, "args_ok": False, "numbers_recall": 0.5,
             "names_ok": None, "grounded": True, "n_tool_calls": 2, "seconds": 1.0},
            {"category": "roster", "tool_ok": False, "args_ok": False, "numbers_recall": 1.0,
             "names_ok": True, "grounded": False, "n_tool_calls": 0, "seconds": 3.0}]
    s = summarise(rows)
    assert s["all"]["tool_ok"] == 0.5 and s["all"]["names_ok"] == 1.0
    assert s["all"]["n"] == 2 and s["all"]["seconds"] == 2.0
    assert s["by_category"]["hours"]["numbers_recall"] == 0.5
    assert s["by_category"]["hours"]["names_ok"] is None


def test_model_slug():
    assert model_slug("openai/gpt-oss-120b") == "openai-gpt-oss-120b"


def scripted_factory(scripts, made):
    def factory(tools):
        made.append(1)
        return ScriptedChatModel(script=scripts[len(made) - 1])
    return factory


def real_hours_case():
    st = pilot_status(evaluate("dgca_current", []), "DEL-C01", 3)
    ft = next(u for u in st.usage if u.rule == "ft_7d")
    return HOURS.model_copy(update={"expected_numbers": [hours(ft.used), hours(ft.remaining)]})


def test_run_writes_json_and_resumes(tmp_path):
    case = real_hours_case()
    used, left = case.expected_numbers
    scripts = [[tool_call("pilot_status", {"pilot_id": "DEL-C01", "day": 3}),
                AIMessage(content=f"DEL-C01 flew {used} hours; {left} hours remain.")],
               [AIMessage(content="I could not find that duty.")]]
    made = []
    out = tmp_path / "agent.json"
    data = run_agent_eval("fake/model", [case, ROSTER], llm_factory=scripted_factory(scripts, made),
                          out=out, pause=0)
    assert len(made) == 2
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved == data and saved["config"]["model"] == "fake/model"
    first, second = saved["rows"]
    assert first["id"] == "hours-00" and first["tool_ok"] and first["args_ok"]
    assert first["numbers_recall"] == 1.0 and first["grounded"]
    assert second["tool_ok"] is False and second["names_ok"] is False
    assert saved["summary"]["all"]["n"] == 2

    run_agent_eval("fake/model", [case, ROSTER], llm_factory=scripted_factory(scripts, made),
                   out=out, pause=0)
    assert len(made) == 2  # both cases already done: nothing re-run


class RateLimitError(Exception):
    status_code = 429


def test_daily_limit_stops_cleanly_and_keeps_progress(tmp_path):
    made = []

    def factory(tools):
        made.append(1)
        if len(made) == 2:
            raise RateLimitError("Rate limit reached: tokens per day (TPD): Limit 200000")
        return ScriptedChatModel(script=[AIMessage(content="No idea.")])

    out = tmp_path / "agent.json"
    data = run_agent_eval("fake/model", [ROSTER, HOURS], llm_factory=factory, out=out, pause=0)
    assert [r["id"] for r in data["rows"]] == ["roster-00"]
    assert data["stopped"].startswith("daily limit")
    assert json.loads(out.read_text(encoding="utf-8"))["rows"][0]["id"] == "roster-00"


REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def status_error(cls, status):
    return cls("boom", response=httpx.Response(status, request=REQUEST), body=None)


@pytest.mark.parametrize("exc", [
    groq.APITimeoutError(request=REQUEST),
    groq.APIConnectionError(request=REQUEST),
    status_error(groq.InternalServerError, 500),
    status_error(groq.APIStatusError, 503),
], ids=["timeout", "connection", "500", "503"])
def test_transient_errors_stop_cleanly_and_are_never_scored(tmp_path, exc):
    made = []

    def factory(tools):
        made.append(1)
        if len(made) == 2:
            raise exc
        return ScriptedChatModel(script=[AIMessage(content="No idea.")])

    out = tmp_path / "agent.json"
    data = run_agent_eval("fake/model", [ROSTER, HOURS], llm_factory=factory, out=out, pause=0)
    assert [r["id"] for r in data["rows"]] == ["roster-00"]
    assert data["stopped"].startswith("transient error")
    assert json.loads(out.read_text(encoding="utf-8"))["stopped"] == data["stopped"]

    again = run_agent_eval("fake/model", [ROSTER, HOURS], out=out, pause=0,
                           llm_factory=lambda t: ScriptedChatModel(
                               script=[AIMessage(content="Still no idea.")]))
    assert [r["id"] for r in again["rows"]] == ["roster-00", "hours-00"]  # resumed
    assert again["stopped"] is None


def test_groq_bad_request_is_a_failed_row_not_a_stop(tmp_path):
    def factory(tools):
        raise status_error(groq.BadRequestError, 400)

    data = run_agent_eval("fake/model", [ROSTER], llm_factory=factory,
                          out=tmp_path / "a.json", pause=0)
    assert data["stopped"] is None and data["rows"][0]["error"].startswith("BadRequestError")


def test_per_minute_rate_limit_waits_then_retries(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(agent_eval.time, "sleep", sleeps.append)
    made = []

    def factory(tools):
        made.append(1)
        if len(made) == 1:
            raise RateLimitError("Rate limit reached: tokens per minute (TPM)")
        return ScriptedChatModel(script=[AIMessage(content="No idea.")])

    data = run_agent_eval("fake/model", [ROSTER], llm_factory=factory,
                          out=tmp_path / "a.json", pause=0)
    assert sleeps == [agent_eval.RATE_LIMIT_WAIT] and len(made) == 2
    assert [r["id"] for r in data["rows"]] == ["roster-00"] and data["stopped"] is None


def test_second_per_minute_rate_limit_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_eval.time, "sleep", lambda s: None)

    def factory(tools):
        raise RateLimitError("Rate limit reached: tokens per minute (TPM)")

    data = run_agent_eval("fake/model", [ROSTER], llm_factory=factory,
                          out=tmp_path / "a.json", pause=0)
    assert data["rows"] == [] and data["stopped"].startswith("rate limit")


def test_args_use_subset_matching_for_nested_what_if_arguments():
    case = HOURS.model_copy(update={"expected_tool": "what_if", "expected_numbers": [],
                                    "expected_args": {"sick": [{"pilot_id": "P1", "from_day": 2,
                                                                "to_day": 3}]}})
    sick = {"pilot_id": "P1", "from_day": 2, "to_day": 3, "kind": "sick"}
    assert score(case, answer("x", [("what_if", {"sick": [sick], "delays": []})]))["args_ok"]
    wrong = {**sick, "to_day": 4}
    assert not score(case, answer("x", [("what_if", {"sick": [wrong]})]))["args_ok"]
    assert not score(case, answer("x", [("what_if", {"delays": []})]))["args_ok"]


def test_default_time_limit_is_the_api_setting(tmp_path, monkeypatch):
    seen = []
    real = agent_eval.run_agent

    def spy(*a, **kw):
        seen.append(kw["time_limit"])
        return real(*a, **kw)

    monkeypatch.setattr(agent_eval, "run_agent", spy)
    monkeypatch.setattr(agent_eval, "get_settings",
                        lambda: Settings(_env_file=None, solve_time_limit=3.5))
    data = run_agent_eval("fake/model", [ROSTER], out=tmp_path / "a.json", pause=0,
                          llm_factory=lambda t: ScriptedChatModel(
                              script=[AIMessage(content="x")]))
    assert seen == [3.5] and data["config"]["time_limit"] == 3.5


def fake_anthropic(monkeypatch, calls):
    class Chat:
        def __init__(self, **kw):
            pass

        def invoke(self, messages):
            calls.append(1)
            return AIMessage(content='{"faithful": 5, "clear": 4, "why": "ok"}')

    monkeypatch.setitem(sys.modules, "langchain_anthropic",
                        types.SimpleNamespace(ChatAnthropic=Chat))


def test_judge_skips_scored_items_unless_rejudge(monkeypatch):
    items = [{"source": "replan", "id": f"S0/{i}", "sentence": "x", "reasons": []}
             for i in range(3)]
    monkeypatch.setattr(agent_eval, "_judge_items", lambda *a: [dict(i) for i in items])
    calls = []
    fake_anthropic(monkeypatch, calls)
    settings = Settings(_env_file=None, anthropic_api_key="test")
    previous = {"items": [{**items[0], "faithful": 3, "clear": 3, "why": "old"},
                          {**items[1], "faithful": None, "clear": None, "why": "error"}]}
    out = agent_eval.run_judge([], [], settings, None, 1.0, lambda m: None, previous=previous)
    assert len(calls) == 2  # item 0 kept; the errored item 1 and new item 2 scored
    assert [i["faithful"] for i in out["items"]] == [3, 5, 5]
    assert out["summary"]["replan"]["n"] == 3

    calls.clear()
    agent_eval.run_judge([], [], settings, None, 1.0, lambda m: None, previous=previous,
                         rejudge=True)
    assert len(calls) == 3


def test_other_errors_are_recorded_as_failed_rows(tmp_path):
    def factory(tools):
        raise ValueError("tool_use_failed")

    data = run_agent_eval("fake/model", [ROSTER], llm_factory=factory,
                          out=tmp_path / "a.json", pause=0)
    row = data["rows"][0]
    assert "tool_use_failed" in row["error"] and not row["tool_ok"] and not row["grounded"]


@pytest.fixture
def no_keys(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(agent_eval, "get_settings", lambda: Settings(_env_file=None))


def test_judge_without_key_exits_with_a_clear_message(no_keys, tmp_path):
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        run_agent_eval("fake/model", [ROSTER], llm_factory=lambda t: None,
                       out=tmp_path / "a.json", judge=True)
    assert not (tmp_path / "a.json").exists()


def test_langsmith_without_key_exits(no_keys, tmp_path):
    with pytest.raises(SystemExit, match="LANGSMITH_API_KEY"):
        run_agent_eval("fake/model", [ROSTER], llm_factory=lambda t: None,
                       out=tmp_path / "a.json", langsmith=True)


def test_default_factory_needs_a_groq_key(no_keys, tmp_path):
    with pytest.raises(SystemExit, match="GROQ_API_KEY"):
        run_agent_eval("openai/gpt-oss-120b", [ROSTER], out=tmp_path / "a.json")


def test_judge_cost_estimate_is_small():
    est = agent_eval.judge_cost(calls=18, input_tokens=600, output_tokens=120)
    assert est == pytest.approx(18 * (600 * 0.10 + 120 * 0.50) / 1e6)
