"""Chat model wiring. An LlmFactory binds tools and returns a runnable (fakes in tests)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from crew_roster.config import get_settings

LlmFactory = Callable[[Sequence[BaseTool]], Runnable]


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


def text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part)
                   for part in content)
