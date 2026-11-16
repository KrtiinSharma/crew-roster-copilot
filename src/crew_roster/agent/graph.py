"""LangGraph agent: agent <-> tools, then a number check with one retry."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from crew_roster.agent.llm import LlmFactory, groq_llm_factory, text_of
from crew_roster.agent.numbers import check_numbers
from crew_roster.agent.prompts import SYSTEM_PROMPT
from crew_roster.agent.tools import Toolbox, ToolCallTrace
from crew_roster.disrupt import Disruption

MAX_RETRIES = 1
FEEDBACK = "number_check"  # name on the feedback message, so it is not taken as a new question


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentAnswer(BaseModel):
    answer: str
    verified: bool
    ungrounded: list[str]
    tool_calls: list[ToolCallTrace]


class AgentState(MessagesState):
    retries: int
    check: dict


def build_graph(llm: Runnable, tools: Sequence[BaseTool]):
    def agent(state: AgentState) -> dict:
        return {"messages": [llm.invoke(state["messages"])]}

    def route(state: AgentState) -> str:
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else "number_check"

    def number_check(state: AgentState) -> dict:
        msgs = state["messages"]
        start = max(i for i, m in enumerate(msgs)
                    if isinstance(m, HumanMessage) and m.name != FEEDBACK)
        sources = [SYSTEM_PROMPT, text_of(msgs[start])]
        sources += [text_of(m) for m in msgs[start:] if isinstance(m, ToolMessage)]
        result = check_numbers(text_of(msgs[-1]), sources)
        retries = state.get("retries", 0) + (0 if result.ok else 1)
        return {"check": result.model_dump(), "retries": retries}

    def after_check(state: AgentState) -> str:
        return END if state["check"]["ok"] or state["retries"] > MAX_RETRIES else "feedback"

    def feedback(state: AgentState) -> dict:
        bad = ", ".join(state["check"]["ungrounded"])
        return {"messages": [HumanMessage(
            name=FEEDBACK,
            content=f"Check failed: these numbers are not in any tool result: {bad}. "
                    "Call a tool to get the real values, or remove them. Then answer again.")]}

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(list(tools)))
    g.add_node("number_check", number_check)
    g.add_node("feedback", feedback)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["tools", "number_check"])
    g.add_edge("tools", "agent")
    g.add_conditional_edges("number_check", after_check, ["feedback", END])
    g.add_edge("feedback", "agent")
    return g.compile()


def run_agent(question: str, history: Sequence[ChatTurn], ruleset: str,
              disruptions: Sequence[Disruption], llm_factory: LlmFactory = groq_llm_factory,
              time_limit: float = 10.0) -> AgentAnswer:
    box = Toolbox(ruleset, disruptions, time_limit)
    graph = build_graph(llm_factory(box.tools), box.tools)
    messages = [SystemMessage(SYSTEM_PROMPT)]
    messages += [HumanMessage(t.content) if t.role == "user" else AIMessage(t.content)
                 for t in history]
    messages.append(HumanMessage(question))
    try:
        state = graph.invoke({"messages": messages, "retries": 0, "check": {}},
                             config={"recursion_limit": 20, "run_name": "crew-copilot"})
    except GraphRecursionError:
        return AgentAnswer(answer="I could not finish within the tool-call limit. "
                                  "Please ask a narrower question.",
                           verified=False, ungrounded=[], tool_calls=box.trace)
    check = state["check"]
    return AgentAnswer(answer=text_of(state["messages"][-1]), verified=check["ok"],
                       ungrounded=check["ungrounded"], tool_calls=box.trace)
