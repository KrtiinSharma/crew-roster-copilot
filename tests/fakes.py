"""A chat model that replays scripted messages, so agent tests never call an LLM."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    script: list[AIMessage]
    calls: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        # fresh copy without an id: LangGraph stamps ids on messages, and a reused id would
        # replace the earlier message instead of appending a new one
        msg = self.script[min(self.calls, len(self.script) - 1)].model_copy(update={"id": None})
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted"


def tool_call(name: str, args: dict, call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
