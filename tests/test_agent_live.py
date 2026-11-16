import pytest

from crew_roster.agent.graph import run_agent
from crew_roster.config import get_settings


@pytest.mark.live
def test_live_groq_answers_with_a_tool_and_grounded_numbers():
    if not get_settings().groq_api_key:
        pytest.skip("no GROQ_API_KEY in .env")
    ans = run_agent("How many flight hours has DEL-C01 used in the 7 days up to day 3, "
                    "and how many remain?", [], "dgca_current", [])
    assert ans.tool_calls, ans
    assert ans.verified, ans
