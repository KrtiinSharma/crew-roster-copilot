"""FastAPI backend: stateless; the browser sends its whole scenario with every request.

uv run crew-serve            # http://localhost:8000/docs
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from crew_roster.agent.explain import explain_changes
from crew_roster.agent.graph import AgentAnswer, ChatTurn, run_agent
from crew_roster.agent.llm import LlmFactory, groq_llm_factory
from crew_roster.config import get_settings
from crew_roster.disrupt import Disruption
from crew_roster.rules import RULESETS, load
from crew_roster.service import (
    DISRUPTIONS,
    ChangeView,
    DutyView,
    FlightView,
    PilotView,
    Stats,
    base_problem,
    canonical,
    change_views,
    duty_views,
    evaluate,
    flight_views,
    pilot_views,
)


def _warm_up() -> None:
    for name in RULESETS:
        base_problem(name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="Crew Roster Copilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().origins,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


@app.exception_handler(ValueError)
async def value_error(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def get_llm_factory() -> LlmFactory | None:
    return groq_llm_factory if get_settings().groq_api_key else None


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    """Sliding one-minute window per client IP, to protect the free Groq quota."""
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")
    now, window = time.time(), _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= get_settings().rate_limit_per_minute:
        raise HTTPException(429, "Too many questions, please wait a minute.")
    window.append(now)


class ScenarioRequest(BaseModel):
    ruleset: str = "dgca_current"
    disruptions: list[Disruption] = Field(default_factory=list)


class ChatRequest(ScenarioRequest):
    messages: list[ChatTurn] = Field(min_length=1)

    @field_validator("messages")
    @classmethod
    def _ends_with_user(cls, v: list[ChatTurn]) -> list[ChatTurn]:
        if v[-1].role != "user":
            raise ValueError("the last message must be the user's question")
        return v


class ScenarioView(BaseModel):
    ruleset: str
    label: str
    disruptions: list[Disruption]
    stats: Stats
    pilots: list[PilotView]
    flights: list[FlightView]
    duties: list[DutyView]
    changes: list[ChangeView]
    illegal_duties: list[str]


@lru_cache(maxsize=64)
def _explanations(ruleset: str, key: str, factory: LlmFactory | None) -> dict[str, str]:
    res = evaluate(ruleset, DISRUPTIONS.validate_python(json.loads(key)),
                   get_settings().solve_time_limit)
    return explain_changes(res.changes, res.problem, factory)


def _scenario(ruleset: str, disruptions: list[Disruption],
              factory: LlmFactory | None) -> ScenarioView:
    s = get_settings()
    res = evaluate(ruleset, disruptions, s.solve_time_limit)
    notes = _explanations(res.ruleset, canonical(disruptions),
                          factory if s.llm_explanations else None)
    p = res.problem
    return ScenarioView(ruleset=res.ruleset, label=p.ruleset.label,
                        disruptions=res.disruptions, stats=res.stats, pilots=pilot_views(p),
                        flights=flight_views(p), duties=duty_views(res),
                        changes=change_views(res, notes), illegal_duties=res.illegal_duties)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/rules")
def rules() -> dict:
    return {name: load(name).model_dump() for name in RULESETS}


@app.get("/roster", response_model=ScenarioView)
async def roster(ruleset: str = "dgca_current",
                 factory: LlmFactory | None = Depends(get_llm_factory)) -> ScenarioView:
    return await run_in_threadpool(_scenario, ruleset, [], factory)


@app.post("/replan", response_model=ScenarioView)
async def replan_endpoint(req: ScenarioRequest,
                          factory: LlmFactory | None = Depends(get_llm_factory)) -> ScenarioView:
    return await run_in_threadpool(_scenario, req.ruleset, req.disruptions, factory)


@app.post("/chat", response_model=AgentAnswer, dependencies=[Depends(rate_limit)])
async def chat(req: ChatRequest,
               factory: LlmFactory | None = Depends(get_llm_factory)) -> AgentAnswer:
    if factory is None:
        raise HTTPException(503, "The assistant is not configured (no GROQ_API_KEY).")
    *history, question = req.messages
    return await run_in_threadpool(run_agent, question.content, history, req.ruleset,
                                   req.disruptions, factory, get_settings().solve_time_limit)


def main() -> None:
    import uvicorn

    uvicorn.run("crew_roster.api.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
