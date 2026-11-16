import pytest

from crew_roster.agent.graph import run_agent
from crew_roster.agent.llm import active_provider


@pytest.mark.live
def test_live_llm_answers_with_a_tool_and_grounded_numbers():
    if active_provider() is None:
        pytest.skip("no ANTHROPIC_API_KEY or GROQ_API_KEY in .env")
    ans = run_agent("How many flight hours has DEL-C01 used in the 7 days up to day 3, "
                    "and how many remain?", [], "dgca_current", [])
    assert ans.tool_calls, ans
    assert ans.verified, ans
