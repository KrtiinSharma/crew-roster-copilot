import os

from crew_roster.agent.llm import groq_llm_factory
from crew_roster.config import get_settings


def test_groq_models_time_out(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "gsk_fake_for_tests")
    llm = groq_llm_factory([])  # builds clients only; nothing is sent
    assert [m.request_timeout for m in (llm.runnable, *llm.fallbacks)] == [20, 20]


def test_tests_never_send_traces():
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert get_settings().langsmith_tracing is False
