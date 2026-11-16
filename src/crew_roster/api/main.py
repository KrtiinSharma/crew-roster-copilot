"""FastAPI backend: stateless; the browser sends its whole scenario with every request.

uv run crew-serve            # http://localhost:8000/docs
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache

import groq
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from crew_roster.agent.explain import explain_changes
from crew_roster.agent.graph import AgentAnswer, ChatTurn, run_agent
from crew_roster.agent.llm import LlmFactory, active_provider, default_llm_factory
from crew_roster.agent.tools import RulesetName
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

log = logging.getLogger(__name__)
REPLAN_LIMIT_FACTOR = 3  # /replan is free (no LLM call) but runs the solver


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


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request,
                                   exc: RequestValidationError) -> JSONResponse:
    """One 422 shape for the frontend: {"detail": "<loc>: <msg>; ..."}."""
    detail = "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', ()) if p != 'body')}: {e.get('msg', '')}"
        for e in exc.errors())
    return JSONResponse(status_code=422, content={"detail": detail})


def get_llm_factory() -> LlmFactory | None:
    return default_llm_factory if active_provider() else None


_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def client_ip(request: Request) -> str:
    """Cloud Run appends the real client IP to X-Forwarded-For, so trust only the last entry;
    earlier entries are whatever the client chose to send."""
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
    return forwarded or (request.client.host if request.client else "?")


def _check_rate(bucket: str, request: Request, limit: int, message: str) -> None:
    """Sliding one-minute window per client IP and bucket."""
    key, now = f"{bucket}:{client_ip(request)}", time.time()
    with _hits_lock:
        for k in list(_hits):  # prune every window, dropping the ones left empty
            window = _hits[k]
            while window and now - window[0] > 60:
                window.popleft()
            if not window:
                del _hits[k]
        if len(_hits.get(key, ())) >= limit:
            raise HTTPException(429, message)
        _hits[key].append(now)


def rate_limit(request: Request) -> None:
    """Protects the free Groq quota."""
    _check_rate("chat", request, get_settings().rate_limit_per_minute,
                "Too many questions, please wait a minute.")


def replan_rate_limit(request: Request) -> None:
    """Looser limit: no LLM quota at stake, but each re-plan runs the solver."""
    _check_rate("replan", request, REPLAN_LIMIT_FACTOR * get_settings().rate_limit_per_minute,
                "Too many re-plans, please wait a minute.")


class ScenarioRequest(BaseModel):
    ruleset: RulesetName = "dgca_current"
    disruptions: list[Disruption] = Field(default_factory=list, max_length=30)


class ChatRequest(ScenarioRequest):
    messages: list[ChatTurn] = Field(min_length=1, max_length=20)

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


async def _scenario_or_500(ruleset: str, disruptions: list[Disruption],
                           factory: LlmFactory | None) -> ScenarioView:
    # HTTPException is answered inside the CORS middleware; an unhandled error is not, and
    # the browser would then see a CORS failure instead of the error
    try:
        return await run_in_threadpool(_scenario, ruleset, disruptions, factory)
    except ValueError:
        raise  # bad ids/days: 422 via the handler above
    except Exception as exc:
        log.exception("scenario failed")
        raise HTTPException(500, "Internal error") from exc


@app.get("/roster", response_model=ScenarioView)
async def roster(ruleset: RulesetName = "dgca_current",
                 factory: LlmFactory | None = Depends(get_llm_factory)) -> ScenarioView:
    return await _scenario_or_500(ruleset, [], factory)


@app.post("/replan", response_model=ScenarioView, dependencies=[Depends(replan_rate_limit)])
async def replan_endpoint(req: ScenarioRequest,
                          factory: LlmFactory | None = Depends(get_llm_factory)) -> ScenarioView:
    return await _scenario_or_500(req.ruleset, req.disruptions, factory)


@app.post("/chat", response_model=AgentAnswer, dependencies=[Depends(rate_limit)])
async def chat(req: ChatRequest,
               factory: LlmFactory | None = Depends(get_llm_factory)) -> AgentAnswer:
    if factory is None:
        raise HTTPException(
            503, "The assistant is not configured (no ANTHROPIC_API_KEY or GROQ_API_KEY).")
    *history, question = req.messages
    try:
        return await run_in_threadpool(run_agent, question.content, history, req.ruleset,
                                       req.disruptions, factory,
                                       get_settings().solve_time_limit)
    except ValueError:
        raise  # 422 via the handler above
    except groq.RateLimitError as exc:
        raise HTTPException(
            429, "The free AI quota is used up for now; please try again later.") from exc
    except (groq.APIError, groq.APIConnectionError) as exc:
        log.warning("Groq call failed: %s", exc)
        raise HTTPException(502, "The AI service failed; please try again.") from exc
    except Exception as exc:
        log.exception("chat failed")
        raise HTTPException(500, "Internal error") from exc


def main() -> None:
    import uvicorn

    uvicorn.run("crew_roster.api.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
