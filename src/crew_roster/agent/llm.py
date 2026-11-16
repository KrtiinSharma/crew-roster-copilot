"""Chat model wiring. An LlmFactory binds tools and returns a runnable (fakes in tests)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from crew_roster.config import Settings, get_settings

LlmFactory = Callable[[Sequence[BaseTool]], Runnable]

PROVIDERS = ("anthropic", "groq")


def active_provider(s: Settings | None = None) -> str | None:
    """Which LLM answers chat: LLM_PROVIDER if set, else Claude when ANTHROPIC_API_KEY is
    present, else Groq when GROQ_API_KEY is present, else None (chat is off)."""
    s = s or get_settings()
    keys = {"anthropic": s.anthropic_api_key, "groq": s.groq_api_key}
    choice = s.llm_provider.strip().lower()
    if choice in PROVIDERS:
        return choice if keys[choice] else None
    return next((p for p in PROVIDERS if keys[p]), None)


def claude_llm_factory(tools: Sequence[BaseTool]) -> Runnable:
    """Claude (CLAUDE_MODEL, default claude-haiku-5-5) at low effort, tools bound."""
    from langchain_anthropic import ChatAnthropic

    s = get_settings()
    if not s.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")
    llm = ChatAnthropic(model=s.claude_model, api_key=s.anthropic_api_key, max_tokens=8000,
                        max_retries=2, timeout=30, output_config={"effort": "low"})
    return llm.bind_tools(list(tools)) if tools else llm


def groq_llm_factory(tools: Sequence[BaseTool]) -> Runnable:
    """gpt-oss-120b on Groq, falling back to gpt-oss-20b when the free daily limit is hit."""
    from groq import RateLimitError
    from langchain_groq import ChatGroq

    s = get_settings()
    if not s.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set in .env")

    def build(model: str):
        llm = ChatGroq(model=model, api_key=s.groq_api_key, temperature=0, max_retries=1,
                       reasoning_effort="low", timeout=20)
        return llm.bind_tools(list(tools)) if tools else llm

    return build(s.answer_model).with_fallbacks(
        [build(s.fast_model)], exceptions_to_handle=(RateLimitError,))


def default_llm_factory(tools: Sequence[BaseTool]) -> Runnable:
    """The configured provider (see active_provider)."""
    provider = active_provider()
    if provider is None:
        raise RuntimeError("no LLM key: set ANTHROPIC_API_KEY or GROQ_API_KEY in .env")
    return (claude_llm_factory if provider == "anthropic" else groq_llm_factory)(tools)


def text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part)
                   for part in content)
