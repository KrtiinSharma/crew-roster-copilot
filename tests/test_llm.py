import os

import pytest

from crew_roster.agent.llm import active_provider, claude_llm_factory, groq_llm_factory
from crew_roster.config import Settings, get_settings


def test_groq_models_time_out(monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", "gsk_fake_for_tests")
    llm = groq_llm_factory([])  # builds clients only; nothing is sent
    assert [m.request_timeout for m in (llm.runnable, *llm.fallbacks)] == [20, 20]


def test_claude_model_uses_haiku_at_low_effort(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-ant-fake-for-tests")
    llm = claude_llm_factory([])  # builds the client only; nothing is sent
    assert llm.model == "claude-haiku-5-5"
    assert llm.output_config == {"effort": "low"}
    assert llm.temperature is None  # Haiku 5.5 rejects non-default sampling settings
    assert llm.default_request_timeout == 30


@pytest.mark.parametrize(("provider", "anthropic", "groq", "expected"), [
    ("auto", "", "", None),
    ("auto", "k", "", "anthropic"),
    ("auto", "", "k", "groq"),
    ("auto", "k", "k", "anthropic"),
    ("groq", "k", "k", "groq"),
    ("anthropic", "", "k", None),
    ("Anthropic", "k", "", "anthropic"),
])
def test_provider_choice(provider, anthropic, groq, expected):
    s = Settings(_env_file=None, llm_provider=provider, anthropic_api_key=anthropic,
                 groq_api_key=groq)
    assert active_provider(s) == expected


def test_tests_never_send_traces():
    assert os.environ["LANGSMITH_TRACING"] == "false"
    assert get_settings().langsmith_tracing is False
