# Crew Roster Copilot — Plan 2: Agent + API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A LangGraph agent (Groq gpt-oss-120b) that answers what-if questions only by calling the optimiser as a tool, with a number-check guard, plus plain-language change explanations and a stateless FastAPI backend the React frontend (Plan 3) will call.

**Architecture:** A cached **scenario service** (`service.py`) turns `(ruleset, disruptions)` into a re-planned roster plus JSON-ready views. Agent tools and API endpoints are thin wrappers over it. The agent graph is `agent ⇄ tools → number_check` (one retry with feedback, then a visible "unverified" flag). Change explanations come from deterministic templates built from checker reasons; an optional LLM rewrite is accepted only if its numbers match the template. The API is stateless: the browser sends its whole disruption list on every request and identical requests hit the cache.

**Tech Stack:** Python 3.11, uv, pydantic v2 + pydantic-settings, LangGraph 1.x, langchain-core 1.x, langchain-groq 1.x, LangSmith, FastAPI + uvicorn, pytest (+ httpx for TestClient).

**Spec:** `docs/superpowers/specs/2026-11-16-crew-roster-copilot-design.md` §6–§7. **Builds on:** Plan 1 (optimiser core, HEAD `7da817d`).

## Global Constraints

- Python `>=3.11, <3.13`; dependencies only via `uv add`; run everything with `uv run`.
- API keys only in `.env` (gitignored). Never print, echo, log or commit them. `.env.example` has empty values.
- Groq free tier: answer model `openai/gpt-oss-120b`, fallback `openai/gpt-oss-20b` on `RateLimitError`; `reasoning_effort="low"`, `temperature=0`.
- **No test may call a real LLM** except those marked `@pytest.mark.live`, which are excluded by default and skip when `GROQ_API_KEY` is empty.
- Tools and the API never change the live (base) roster; every scenario is recomputed from `(ruleset, disruptions)`.
- Every number in an agent answer must appear in this turn's tool outputs, the user's question or the system prompt (number check), or the answer is returned with `verified=False` and the ungrounded numbers listed.
- Fictional airline "Skyline Air"; no IndiGo branding in UI strings or prompts.
- Days are numbered 0–6 everywhere (API, tools, prompt). Durations in tool outputs are decimal hours; API views carry both minutes (`*_min`) and display strings.
- The owner's laptop is slow: tests that re-plan use the real data (~3–5 s per re-plan); anything over ~10 s is `@pytest.mark.slow`.
- No GitHub remote yet: commit locally on `main` only; never push.
- Commit messages end with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## File map

```
.env.example                     all settings, empty secrets
src/crew_roster/
  config.py                      Settings, get_settings (LangSmith env export)
  roster/check.py                + Usage, pilot_timeline, window_totals, pilot_usage (shared with pilot_violations)
  service.py                     views + cached evaluate / base_problem / sizing / pilot_status / lookup
  agent/__init__.py              re-exports
  agent/numbers.py               extract, check_numbers, NumberCheck
  agent/tools.py                 Toolbox (6 tools + trace), reason_dict
  agent/prompts.py               SYSTEM_PROMPT, EXPLAIN_PROMPT
  agent/llm.py                   LlmFactory type, groq_llm_factory, text_of
  agent/graph.py                 ChatTurn, AgentAnswer, build_graph, run_agent
  agent/explain.py               template, explain_changes
  api/__init__.py
  api/main.py                    FastAPI app, crew-serve entry point
tests/
  fakes.py                       ScriptedChatModel
  test_config.py test_usage.py test_service.py test_numbers.py test_tools.py
  test_graph.py test_agent_live.py test_explain.py test_api.py
```

---

### Task 1: Settings, dependencies and `.env.example`

**Files:**
- Create: `src/crew_roster/config.py`, `.env.example`
- Modify: `pyproject.toml` (deps via `uv add`, `live` marker)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `crew_roster.config.Settings` (fields `groq_api_key, answer_model, fast_model, llm_explanations, langsmith_api_key, langsmith_tracing, langsmith_project, allowed_origins, rate_limit_per_minute, solve_time_limit`; property `origins -> list[str]`), `get_settings() -> Settings` (cached; exports LangSmith env vars when tracing is on), `ROOT: Path`.

- [ ] **Step 1: Add dependencies and the `live` marker**

```bash
uv add "pydantic-settings>=2.4" "langchain-core>=1.0" "langchain-groq>=1.0" "langgraph>=1.0" "langsmith>=0.3" "fastapi>=0.115" "uvicorn[standard]>=0.30"
uv add --dev "httpx>=0.27"
```

In `pyproject.toml` make the pytest table read:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
markers = [
    "slow: takes more than ~10 s on a slow laptop (run with -m slow)",
    "live: calls the real Groq API; needs GROQ_API_KEY in .env (run with -m live)",
]
addopts = "-m 'not slow and not live'"
```

- [ ] **Step 2: Write the failing test** — `tests/test_config.py`:

```python
from crew_roster.config import ROOT, Settings


def test_defaults_without_env_file():
    s = Settings(_env_file=None)
    assert s.answer_model == "openai/gpt-oss-120b"
    assert s.fast_model == "openai/gpt-oss-20b"
    assert s.origins == ["http://localhost:5173"]
    assert s.rate_limit_per_minute == 10 and s.solve_time_limit == 10.0


def test_origins_are_split_and_trimmed():
    s = Settings(_env_file=None, allowed_origins=" https://a.github.io , http://localhost:5173 ,")
    assert s.origins == ["https://a.github.io", "http://localhost:5173"]


def test_env_example_lists_every_setting_with_empty_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    keys = {line.split("=", 1)[0] for line in text.splitlines() if "=" in line and not line.startswith("#")}
    assert keys == {name.upper() for name in Settings.model_fields}
    for secret in ("GROQ_API_KEY", "LANGSMITH_API_KEY"):
        assert f"{secret}=\n" in text + "\n"
```

- [ ] **Step 3: Run it to see it fail**

Run: `uv run pytest tests/test_config.py -q`
Expected: ERROR `ModuleNotFoundError: No module named 'crew_roster.config'`.

- [ ] **Step 4: Write `src/crew_roster/config.py`**

```python
"""Runtime settings from environment variables or a local .env file (never commit .env)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    groq_api_key: str = ""
    answer_model: str = "openai/gpt-oss-120b"
    fast_model: str = "openai/gpt-oss-20b"
    llm_explanations: bool = True

    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "crew-roster-copilot"

    allowed_origins: str = "http://localhost:5173"
    rate_limit_per_minute: int = 10
    solve_time_limit: float = 10.0

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.langsmith_tracing and s.langsmith_api_key:  # langchain reads these from the environment
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", s.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", s.langsmith_project)
    return s
```

`.env.example`:

```
# Groq (free key: https://console.groq.com/keys)
GROQ_API_KEY=
ANSWER_MODEL=openai/gpt-oss-120b
FAST_MODEL=openai/gpt-oss-20b
# rewrite change explanations with the LLM (numbers are checked; templates otherwise)
LLM_EXPLANATIONS=true

# LangSmith tracing (free key: https://smith.langchain.com -> Settings -> API Keys)
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=crew-roster-copilot

# API
ALLOWED_ORIGINS=http://localhost:5173
RATE_LIMIT_PER_MINUTE=10
SOLVE_TIME_LIMIT=10
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `uv run pytest tests/test_config.py -q` → `3 passed`. Then `uv run pytest -q` (full fast suite still green).

- [ ] **Step 6: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: settings, agent/API dependencies and .env.example" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `pilot_usage` — hours used and remaining, shared with the checker

**Files:**
- Modify: `src/crew_roster/roster/check.py`, `src/crew_roster/roster/__init__.py`
- Test: `tests/test_usage.py`

**Interfaces:**
- Consumes: `WINDOWS`, `pilot_violations` (Plan 1), `Frozen`, `Duty`, `Roster`.
- Produces: in `crew_roster.roster.check` (re-exported from `crew_roster.roster`): `Usage(rule: str, used: int, limit: int, remaining: int)` (minutes); `pilot_timeline(problem, roster, pilot_id) -> list[Duty]` (history + rostered duties, sorted by `(report, id)`); `window_totals(timeline, t) -> dict[str, int]` (keys `ft_7d, ft_28d, duty_7d, duty_28d`); `pilot_usage(problem, roster, pilot_id, day) -> list[Usage]`. `pilot_violations` must use `pilot_timeline` and `window_totals`, so the agent's hours and the checker can never disagree.

- [ ] **Step 1: Write the failing tests** — `tests/test_usage.py`:

```python
from factories import mk_duty, mk_pilot, mk_problem, mk_roster

from crew_roster.roster.check import check, pilot_usage


def test_usage_matches_the_checker_on_a_breach():
    duties = [mk_duty(f"D{k}", k, "06:00", 9, ft_hours=7.5) for k in range(5)]  # 37.5 h
    p = mk_problem(duties, [mk_pilot("P1")])
    roster = mk_roster({d.id: {"CPT": "P1"} for d in duties})
    usage = {u.rule: u for u in pilot_usage(p, roster, "P1", 4)}
    assert usage["ft_7d"].used == 2250 and usage["ft_7d"].limit == 2100
    assert usage["ft_7d"].remaining == 0
    breach = next(v for v in check(p, roster) if v.rule == "ft_7d")
    assert (breach.value, breach.limit) == (usage["ft_7d"].used, usage["ft_7d"].limit)


def test_usage_counts_only_the_window_ending_that_day():
    duties = [mk_duty("D0", 0, "06:00", 9, ft_hours=7), mk_duty("D3", 3, "06:00", 9, ft_hours=6)]
    p = mk_problem(duties, [mk_pilot("P1")])
    roster = mk_roster({d.id: {"CPT": "P1"} for d in duties})
    by_day = {d: {u.rule: u.used for u in pilot_usage(p, roster, "P1", d)} for d in (0, 2, 3)}
    assert by_day[0]["ft_7d"] == 420 and by_day[2]["ft_7d"] == 420 and by_day[3]["ft_7d"] == 780
    assert by_day[3]["duty_7d"] == 2 * 540


def test_base_roster_usage_is_within_every_limit(problem, base_result):
    for pid in [p.id for p in problem.pilots][:20]:
        for day in range(problem.horizon_days):
            for u in pilot_usage(problem, base_result.roster, pid, day):
                assert u.used <= u.limit and u.remaining == u.limit - u.used
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_usage.py -q`
Expected: ERROR `ImportError: cannot import name 'pilot_usage'`.

- [ ] **Step 3: Implement in `src/crew_roster/roster/check.py`**

Change the models import to `from crew_roster.models import Duty, Frozen, Roster, Violation`, and add after `WINDOWS`:

```python
class Usage(Frozen):
    """Minutes used in the rolling window ending on a day, against the limit."""

    rule: str
    used: int
    limit: int
    remaining: int


def pilot_timeline(problem: Problem, roster: Roster, pilot_id: str) -> list[Duty]:
    """The pilot's fixed history plus their rostered duties, in report order."""
    duties = problem.duty_map()
    mine = [duties[d] for d, _ in roster.duties_of(pilot_id) if d in duties]
    return sorted(problem.history.get(pilot_id, []) + mine, key=lambda d: (d.report, d.id))


def window_totals(timeline: list[Duty], t: int) -> dict[str, int]:
    """Rolling flight / duty minutes for the windows ending on day t (history included)."""
    return {
        rule: sum(getattr(d, attr) for d in timeline if t - span + 1 <= d.day <= t)
        for rule, span, attr in WINDOWS
    }


def pilot_usage(problem: Problem, roster: Roster, pilot_id: str, day: int) -> list[Usage]:
    rs = problem.ruleset
    totals = window_totals(pilot_timeline(problem, roster, pilot_id), day)
    return [
        Usage(rule=rule, used=used, limit=getattr(rs, rule),
              remaining=max(getattr(rs, rule) - used, 0))
        for rule, used in totals.items()
    ]
```

In `pilot_violations`, replace the line building `timeline` with `timeline = pilot_timeline(problem, roster, pilot_id)`, and replace the rolling-window loop with:

```python
    spans = {rule: span for rule, span, _ in WINDOWS}
    for t in range(horizon):
        for rule, total in window_totals(timeline, t).items():
            limit = getattr(rs, rule)
            if total > limit:
                add(rule, None, t, total, limit, f"{spans[rule]}-day total ending day {t}")
```

(`mine` and its per-duty checks stay as they are; `pilot_timeline` yields the same duties.)

In `src/crew_roster/roster/__init__.py` import and add to `__all__`: `Usage`, `pilot_timeline`, `pilot_usage`, `window_totals`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_usage.py tests/test_check.py tests/test_solver.py -q` → all pass (test_check/test_solver prove the refactor kept the checker's behaviour). Then the full fast suite `uv run pytest -q`.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: pilot_usage shares window totals with the checker" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Scenario service (cached, stateless)

**Files:**
- Create: `src/crew_roster/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `generate`, `build_problem`, `load`, `RULESETS`, `load_base_roster`, `replan`, `check`, `duty_violations`, `pilot_usage`, `Usage`, `min_pilots_needed`, `Sizing`, `Change`, `Disruption`.
- Produces (`crew_roster.service`):
  - helpers `clock(minute) -> "HH:MM"`, `stamp(minute) -> "D3 06:00"`, `hours(minutes) -> float` (2 dp), `hm(minutes) -> "8h30"`; `TIME_RULES: frozenset[str]` (rules whose value/limit are minutes); `DISRUPTIONS: TypeAdapter[list[Disruption]]`; `canonical(disruptions) -> str`.
  - views: `PilotView`, `FlightView`, `DutyView`, `ChangeView`, `Stats`, `PilotStatus` (fields below).
  - `ScenarioResult(ruleset, disruptions, problem, base, roster, changes: list[Change], illegal_duties, stats)`.
  - `base_problem(ruleset) -> tuple[Problem, Roster]` (cached), `evaluate(ruleset, disruptions, time_limit=10.0) -> ScenarioResult` (cached by canonical key; identical inputs return the same object), `sizing(base, ruleset) -> Sizing` (cached).
  - `pilot_views(problem)`, `flight_views(problem)`, `duty_views(result, pilot_id=None, day=None)`, `change_views(result, explanations: dict[str, str])`, `pilot_status(result, pilot_id, day) -> PilotStatus`, `lookup(problem, query, limit=10) -> dict`, `route(problem, duty) -> "BOM-GOI-BOM"`.
  - All raise `ValueError` for unknown ruleset / pilot / base / out-of-range day.

- [ ] **Step 1: Write the failing tests** — `tests/test_service.py`:

```python
import pytest

from crew_roster.disrupt import PilotSick
from crew_roster.service import (
    canonical,
    duty_views,
    evaluate,
    flight_views,
    hm,
    lookup,
    pilot_status,
    pilot_views,
    stamp,
)


def test_formatting_helpers():
    assert stamp(3 * 1440 + 6 * 60) == "D3 06:00"
    assert stamp(1440 + 55) == "D1 00:55"
    assert hm(510) == "8h30"


def test_base_scenario_is_cached_and_clean():
    res = evaluate("dgca_current", [])
    assert evaluate("dgca_current", []) is res
    s = res.stats
    assert (s.duties, s.uncovered, s.violations, s.changes) == (126, 0, 0, 0)
    assert len(pilot_views(res.problem)) == 80
    assert len(flight_views(res.problem)) == 294


def test_route_and_duty_views():
    res = evaluate("dgca_current", [])
    views = duty_views(res)
    assert len(views) == 126
    first = next(v for v in views if "SK101-D0" in v.flight_ids)
    assert first.route == "DEL-BOM-DEL" and first.report == "D0 05:00"
    assert first.cpt and first.fo and first.legal
    pid = first.cpt
    assert all(pid in (v.cpt, v.fo) for v in duty_views(res, pilot_id=pid))
    assert {v.day for v in duty_views(res, day=2)} == {2}


def test_sick_scenario_replans_legally():
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    sick = [PilotSick(pilot_id=pid, from_day=3, to_day=4)]
    res = evaluate("dgca_current", sick)
    assert res.stats.violations == 0 and res.stats.uncovered == 0
    assert res.stats.changes >= 1 and res.changes
    assert canonical(sick) == canonical([PilotSick(pilot_id=pid, from_day=3, to_day=4)])


def test_pilot_status_and_lookup():
    res = evaluate("dgca_current", [])
    st = pilot_status(res, "DEL-C01", 3)
    assert st.pilot.id == "DEL-C01" and {u.rule for u in st.usage} == {
        "ft_7d", "ft_28d", "duty_7d", "duty_28d"}
    found = lookup(res.problem, "SK115")
    assert len(found["flights"]) == 7 and found["pilots"] == []
    assert lookup(res.problem, "del-c01")["pilots"][0]["id"] == "DEL-C01"


def test_bad_inputs_raise_value_error():
    res = evaluate("dgca_current", [])
    with pytest.raises(ValueError):
        evaluate("nope", [])
    with pytest.raises(ValueError):
        pilot_status(res, "NOPE", 1)
    with pytest.raises(ValueError):
        pilot_status(res, "DEL-C01", 9)
    with pytest.raises(ValueError):
        duty_views(res, pilot_id="NOPE")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_service.py -q` → ERROR `ModuleNotFoundError: No module named 'crew_roster.service'`.

- [ ] **Step 3: Write `src/crew_roster/service.py`**

```python
"""Stateless scenario service shared by the agent tools and the API.

A scenario is (ruleset name, ordered list of disruptions). Results are cached by a canonical key,
so the browser can resend its whole disruption list on every request and identical requests are
free. Nothing here mutates the base roster.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from functools import lru_cache

from pydantic import TypeAdapter

from crew_roster.data import generate
from crew_roster.disrupt import Disruption
from crew_roster.models import DAY, ROLES, Duty, Frozen, Pilot, Roster, Violation
from crew_roster.problem import Problem, build_problem
from crew_roster.roster import (
    Change,
    Sizing,
    Usage,
    check,
    duty_violations,
    load_base_roster,
    min_pilots_needed,
    pilot_usage,
    replan,
)
from crew_roster.rules import RULESETS, load

DISRUPTIONS = TypeAdapter(list[Disruption])
TIME_RULES = frozenset({"min_rest", "ft_7d", "ft_28d", "duty_7d", "duty_28d", "max_fdp",
                        "night_max_fdp", "max_ft_per_duty", "weekly_rest"})


def clock(minute: int) -> str:
    m = minute % DAY
    return f"{m // 60:02d}:{m % 60:02d}"


def stamp(minute: int) -> str:
    return f"D{minute // DAY} {clock(minute)}"


def hours(minutes: int) -> float:
    return round(minutes / 60, 2)


def hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def canonical(disruptions: Sequence[Disruption]) -> str:
    """Order-preserving, key-sorted JSON: the cache key for a scenario."""
    return json.dumps(DISRUPTIONS.dump_python(list(disruptions), mode="json"), sort_keys=True)


class PilotView(Frozen):
    id: str
    name: str
    rank: str
    base: str
    unavailable_days: list[int]
    sick_days: list[int]


class FlightView(Frozen):
    id: str
    day: int
    origin: str
    dest: str
    dep: str
    arr: str
    dep_min: int
    arr_min: int


class DutyView(Frozen):
    id: str
    base: str
    day: int
    route: str
    flight_ids: list[str]
    report: str
    release: str
    report_min: int
    release_min: int
    flight_time_h: float
    duty_h: float
    landings: int
    night: bool
    legal: bool
    cpt: str | None
    fo: str | None


class ChangeView(Frozen):
    id: str
    duty_id: str
    role: str
    old_pilot: str | None
    new_pilot: str | None
    reasons: list[Violation]
    explanation: str


class Stats(Frozen):
    duties: int
    slots: int
    crewed: int
    uncovered: int
    changes: int
    violations: int
    solve_seconds: float
    status: str


class PilotStatus(Frozen):
    pilot: PilotView
    day: int
    usage: list[Usage]
    duties: list[DutyView]


class ScenarioResult(Frozen):
    ruleset: str
    disruptions: list[Disruption]
    problem: Problem
    base: Roster
    roster: Roster
    changes: list[Change]
    illegal_duties: list[str]
    stats: Stats


def _ruleset(name: str) -> str:
    if name not in RULESETS:
        raise ValueError(f"unknown ruleset {name!r}; choose from {RULESETS}")
    return name


@lru_cache(maxsize=None)
def base_problem(ruleset: str) -> tuple[Problem, Roster]:
    problem = build_problem(generate(), load(_ruleset(ruleset)))
    return problem, load_base_roster(problem)


def evaluate(ruleset: str, disruptions: Sequence[Disruption],
             time_limit: float = 10.0) -> ScenarioResult:
    return _evaluate(_ruleset(ruleset), canonical(disruptions), time_limit)


@lru_cache(maxsize=64)
def _evaluate(ruleset: str, key: str, time_limit: float) -> ScenarioResult:
    disruptions = DISRUPTIONS.validate_python(json.loads(key))
    problem, base = base_problem(ruleset)
    t0 = time.perf_counter()
    if disruptions:
        rp = replan(problem, base, disruptions, time_limit=time_limit)
        new, roster, changes = rp.problem, rp.result.roster, rp.changes
        illegal, status = rp.result.illegal_duties, rp.result.status
    else:
        new, roster, changes, status = problem, base, [], "BASE"
        illegal = [d.id for d in problem.duties if duty_violations(d, problem.ruleset)]
    slots = 2 * len(new.duties)
    crewed = sum(1 for d in new.duties for r in ROLES if roster.get(d.id, r))
    stats = Stats(duties=len(new.duties), slots=slots, crewed=crewed, uncovered=slots - crewed,
                  changes=len(changes), violations=len(check(new, roster)),
                  solve_seconds=round(time.perf_counter() - t0, 3), status=status)
    return ScenarioResult(ruleset=ruleset, disruptions=disruptions, problem=new, base=base,
                          roster=roster, changes=changes, illegal_duties=illegal, stats=stats)


@lru_cache(maxsize=None)
def sizing(base: str, ruleset: str) -> Sizing:
    problem, _ = base_problem(_ruleset(ruleset))
    if base not in {d.base for d in problem.duties}:
        raise ValueError(f"unknown base {base!r}")
    return min_pilots_needed(problem, base)


def route(problem: Problem, duty: Duty) -> str:
    fl = [problem.flights[f] for f in duty.flight_ids]
    return "-".join([fl[0].origin] + [f.dest for f in fl])


def _pilot_view(problem: Problem, p: Pilot) -> PilotView:
    return PilotView(id=p.id, name=p.name, rank=p.rank, base=p.base,
                     unavailable_days=sorted(p.unavailable_days),
                     sick_days=sorted(problem.sick.get(p.id, frozenset())))


def pilot_views(problem: Problem) -> list[PilotView]:
    return [_pilot_view(problem, p) for p in problem.pilots]


def flight_views(problem: Problem) -> list[FlightView]:
    return [FlightView(id=f.id, day=f.day, origin=f.origin, dest=f.dest, dep=stamp(f.dep),
                       arr=stamp(f.arr), dep_min=f.dep, arr_min=f.arr)
            for f in sorted(problem.flights.values(), key=lambda f: (f.dep, f.id))]


def duty_views(result: ScenarioResult, pilot_id: str | None = None,
               day: int | None = None) -> list[DutyView]:
    problem, roster = result.problem, result.roster
    if pilot_id is not None and pilot_id not in problem.pilot_map():
        raise ValueError(f"unknown pilot {pilot_id}")
    out = []
    for d in problem.duties:
        cpt, fo = roster.get(d.id, "CPT"), roster.get(d.id, "FO")
        if pilot_id is not None and pilot_id not in (cpt, fo):
            continue
        if day is not None and d.day != day:
            continue
        out.append(DutyView(
            id=d.id, base=d.base, day=d.day, route=route(problem, d),
            flight_ids=list(d.flight_ids), report=stamp(d.report), release=stamp(d.release),
            report_min=d.report, release_min=d.release, flight_time_h=hours(d.flight_time),
            duty_h=hours(d.length), landings=d.landings, night=d.night,
            legal=not duty_violations(d, problem.ruleset), cpt=cpt, fo=fo))
    return out


def change_views(result: ScenarioResult, explanations: dict[str, str]) -> list[ChangeView]:
    return [ChangeView(id=c.id, duty_id=c.duty_id, role=c.role, old_pilot=c.old_pilot,
                       new_pilot=c.new_pilot, reasons=c.reasons,
                       explanation=explanations.get(c.id, ""))
            for c in result.changes]


def pilot_status(result: ScenarioResult, pilot_id: str, day: int) -> PilotStatus:
    problem = result.problem
    pilots = problem.pilot_map()
    if pilot_id not in pilots:
        raise ValueError(f"unknown pilot {pilot_id}")
    if not 0 <= day < problem.horizon_days:
        raise ValueError(f"day must be 0-{problem.horizon_days - 1}")
    return PilotStatus(pilot=_pilot_view(problem, pilots[pilot_id]), day=day,
                       usage=pilot_usage(problem, result.roster, pilot_id, day),
                       duties=duty_views(result, pilot_id=pilot_id))


def lookup(problem: Problem, query: str, limit: int = 10) -> dict:
    q = query.strip().lower()
    if not q:
        raise ValueError("empty query")
    pilots = [{"id": p.id, "name": p.name, "rank": p.rank, "base": p.base}
              for p in problem.pilots if q in p.id.lower() or q in p.name.lower()]
    flights = [{"id": f.id, "day": f.day, "from": f.origin, "to": f.dest, "dep": stamp(f.dep)}
               for f in sorted(problem.flights.values(), key=lambda f: (f.dep, f.id))
               if f.id.lower().startswith(q)]
    return {"pilots": pilots[:limit], "flights": flights[:limit]}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_service.py -q` → `6 passed` (one re-plan, ~5–10 s). Then the full fast suite.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: cached scenario service with JSON-ready views" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Number check

**Files:**
- Create: `src/crew_roster/agent/__init__.py` (empty for now: `"""LLM agent: tools, number check, LangGraph graph, explanations."""`), `src/crew_roster/agent/numbers.py`
- Test: `tests/test_numbers.py`

**Interfaces:**
- Consumes: nothing project-specific.
- Produces: `crew_roster.agent.numbers`: `extract(text) -> list[tuple[str, float]]` (ignores digits inside ids such as `DEL-C04`, `SK115-D2`, `BOM-D3-05`, `D3`; understands `8h30`, `06:00`, decimals), `NumberCheck(ok: bool, ungrounded: list[str])`, `check_numbers(answer, sources: Sequence[str]) -> NumberCheck`. A number is grounded if it equals (±0.051) a source number, or that number ÷60 or ×60 (minutes↔hours). `0` and `1` are always allowed.

- [ ] **Step 1: Write the failing tests** — `tests/test_numbers.py`:

```python
from crew_roster.agent.numbers import check_numbers, extract


def values(text):
    return [v for _, v in extract(text)]


def test_extract_ignores_ids_and_reads_durations_and_clocks():
    assert values("DEL-C04 flies SK115-D2 on duty BOM-D3-05 (D3)") == []
    assert values("8h30 then 06:15, 35 h and 7.5") == [8.5, 6.25, 35.0, 7.5]
    assert values("ruleset dgca_dec2025_exemption") == []


def test_minutes_in_tools_ground_hours_in_the_answer():
    src = ['{"used_minutes": 510, "limit_hours": 35.0}']
    assert check_numbers("8.5 hours used of 35", src).ok
    assert check_numbers("8h30 used", src).ok
    assert check_numbers("about 8.5h", src).ok


def test_rounding_to_one_decimal_is_allowed_but_new_numbers_are_not():
    src = ['{"remaining_hours": 26.67}']
    assert check_numbers("26.7 hours remain", src).ok
    res = check_numbers("27.9 hours remain after 3 duties", src)
    assert not res.ok and res.ungrounded == ["27.9", "3"]


def test_trivial_numbers_and_question_numbers():
    assert check_numbers("1 change was needed", []).ok
    assert check_numbers("Delaying by 240 minutes is fine", ["delay SK115 by 240 minutes"]).ok
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_numbers.py -q` → ERROR `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/crew_roster/agent/numbers.py`**

```python
"""Number check: every number in an answer must come from a tool result, the question or the prompt."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel

ID = re.compile(r"\b[A-Za-z]+\d*(?:-[A-Za-z]*\d+)+\b")  # DEL-C04, SK115-D2, BOM-D3-05:CPT
HM = re.compile(r"\b(\d{1,3})\s*h\s*(\d{2})\b")          # 8h30
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")              # 06:15
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")              # 35, 7.5 (not the 3 in D3)
TRIVIAL = {0.0, 1.0}
TOLERANCE = 0.051  # allows rounding to one decimal place


def extract(text: str) -> list[tuple[str, float]]:
    text = ID.sub(" ", text)
    found: list[tuple[int, str, float]] = []
    for rx in (HM, CLOCK):
        for m in rx.finditer(text):
            found.append((m.start(), m.group(0), int(m.group(1)) + int(m.group(2)) / 60))
        text = rx.sub(lambda m: " " * len(m.group(0)), text)  # keep positions for ordering
    found += [(m.start(), m.group(0), float(m.group(0))) for m in NUM.finditer(text)]
    return [(tok, val) for _, tok, val in sorted(found)]


class NumberCheck(BaseModel):
    ok: bool
    ungrounded: list[str]


def check_numbers(answer: str, sources: Sequence[str]) -> NumberCheck:
    pool: set[float] = set()
    for src in sources:
        for _, v in extract(src):
            pool |= {v, v / 60, v * 60}
    bad = [tok for tok, v in extract(answer)
           if v not in TRIVIAL and not any(abs(v - g) < TOLERANCE for g in pool)]
    return NumberCheck(ok=not bad, ungrounded=bad)
```

- [ ] **Step 4: Run the tests** → `4 passed`.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: number check for agent answers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Agent tools

**Files:**
- Create: `src/crew_roster/agent/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `evaluate`, `duty_views`, `pilot_status`, `sizing`, `lookup`, `hours`, `TIME_RULES`, `ScenarioResult` (Task 3); `PilotSick`, `FlightDelay`, `FlightCancel`, `Disruption`.
- Produces (`crew_roster.agent.tools`): `ToolCallTrace(name, args: dict, seconds, ok)`; `Toolbox(ruleset, disruptions, time_limit=10.0)` with `.tools: list[BaseTool]` (names `get_roster, pilot_status, what_if, min_pilots_needed, explain_change, lookup`), `.trace: list[ToolCallTrace]`, `.current() -> ScenarioResult`; `reason_dict(v) -> dict`. Every tool returns compact JSON text; bad input returns `{"error": "..."}` (and `ok=False` in the trace) instead of raising.

- [ ] **Step 1: Write the failing tests** — `tests/test_tools.py`:

```python
import json

import pytest

from crew_roster.agent.tools import Toolbox
from crew_roster.service import duty_views, evaluate


def call(box, name, **args):
    tool = next(t for t in box.tools if t.name == name)
    return json.loads(tool.invoke(args))


def test_tool_names_and_roster_filter():
    box = Toolbox("dgca_current", [])
    assert [t.name for t in box.tools] == [
        "get_roster", "pilot_status", "what_if", "min_pilots_needed", "explain_change", "lookup"]
    out = call(box, "get_roster", day=2)
    assert out["total"] == len(duty_views(evaluate("dgca_current", []), day=2))
    assert all(r["day"] == 2 for r in out["rows"]) and len(out["rows"]) <= 25
    assert set(out["pilot_names"]) >= {r["captain"] for r in out["rows"]}


def test_pilot_status_reports_hours():
    box = Toolbox("dgca_current", [])
    out = call(box, "pilot_status", pilot_id="DEL-C01", day=3)
    limits = {x["rule"]: x for x in out["limits"]}
    assert limits["ft_7d"]["limit_hours"] == 35.0
    ft = limits["ft_7d"]
    assert ft["used_hours"] + ft["remaining_hours"] == pytest.approx(35.0, abs=0.011)
    assert box.trace[-1].name == "pilot_status" and box.trace[-1].ok


def test_what_if_replans_without_touching_the_live_scenario():
    box = Toolbox("dgca_current", [])
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    out = call(box, "what_if", sick=[{"pilot_id": pid, "from_day": 3, "to_day": 4}])
    assert out["rule_breaches"] == 0 and out["changes"] >= 1
    assert any(r["rule"] == "sick" for c in out["change_list"] for r in c["reasons"])
    assert box.current().stats.changes == 0  # live scenario unchanged


def test_explain_change_uses_the_current_scenario():
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    from crew_roster.disrupt import PilotSick

    box = Toolbox("dgca_current", [PilotSick(pilot_id=pid, from_day=3, to_day=4)])
    cid = box.current().changes[0].id
    out = call(box, "explain_change", change_id=cid)
    assert out["id"] == cid and out["reasons"]


def test_errors_come_back_as_json():
    box = Toolbox("dgca_current", [])
    assert "error" in call(box, "pilot_status", pilot_id="NOPE", day=1)
    assert "error" in call(box, "what_if")
    assert "error" in call(box, "explain_change", change_id="X:CPT")
    assert box.trace[-1].ok is False
    assert call(box, "lookup", query="SK115")["flights"]
```

- [ ] **Step 2: Run them to see them fail** → `ModuleNotFoundError: No module named 'crew_roster.agent.tools'`.

- [ ] **Step 3: Write `src/crew_roster/agent/tools.py`**

```python
"""Agent tools: thin wrappers over the scenario service. They never change the live roster."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from crew_roster.disrupt import Disruption, FlightCancel, FlightDelay, PilotSick
from crew_roster.models import Violation
from crew_roster.problem import Problem
from crew_roster.service import (
    TIME_RULES,
    ScenarioResult,
    duty_views,
    evaluate,
    hours,
    lookup,
    pilot_status,
    sizing,
)

RulesetName = Literal["dgca_current", "dgca_dec2025_exemption"]
MAX_ROWS = 25
MAX_CHANGES = 15


class ToolCallTrace(BaseModel):
    name: str
    args: dict
    seconds: float
    ok: bool


class RosterArgs(BaseModel):
    pilot_id: str | None = Field(None, description="Pilot id such as DEL-C04; omit for everyone")
    day: int | None = Field(None, ge=0, le=6, description="Roster day 0-6; omit for the week")


class StatusArgs(BaseModel):
    pilot_id: str = Field(description="Pilot id such as DEL-C04")
    day: int = Field(ge=0, le=6, description="Roster day 0-6")


class SickArg(BaseModel):
    pilot_id: str
    from_day: int = Field(ge=0, le=6)
    to_day: int = Field(ge=0, le=6)


class DelayArg(BaseModel):
    flight_id: str = Field(description="Flight id with day, e.g. SK115-D2")
    minutes: int = Field(gt=0, le=600)


class WhatIfArgs(BaseModel):
    sick: list[SickArg] = Field(default_factory=list)
    delays: list[DelayArg] = Field(default_factory=list)
    cancel_flight_ids: list[str] = Field(default_factory=list)
    ruleset: RulesetName | None = None


class SizingArgs(BaseModel):
    base: Literal["DEL", "BOM"]
    ruleset: RulesetName | None = None


class ChangeArgs(BaseModel):
    change_id: str = Field(description="Change id such as BOM-D3-05:CPT")


class LookupArgs(BaseModel):
    query: str = Field(description="Part of a pilot name or id, or a flight number like SK115")


def reason_dict(v: Violation) -> dict:
    timed = v.rule in TIME_RULES
    return {"rule": v.rule, "day": v.day,
            "value": hours(v.value) if timed else v.value,
            "limit": hours(v.limit) if timed else v.limit,
            "unit": "hours" if timed else "count", "detail": v.message}


def _as(model: type[BaseModel], x) -> BaseModel:
    return x if isinstance(x, model) else model.model_validate(x)


def _names(problem: Problem, ids) -> dict[str, str]:
    pilots = problem.pilot_map()
    return {pid: pilots[pid].name for pid in sorted({i for i in ids if i})}


def _jsonable(kwargs: dict) -> dict:
    return json.loads(json.dumps(
        kwargs, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o)))


class Toolbox:
    """The tools for one chat turn, bound to the user's current scenario."""

    def __init__(self, ruleset: str, disruptions: Sequence[Disruption],
                 time_limit: float = 10.0) -> None:
        self.ruleset = ruleset
        self.disruptions = list(disruptions)
        self.time_limit = time_limit
        self.trace: list[ToolCallTrace] = []
        specs: list[tuple[str, str, type[BaseModel], Callable[..., dict]]] = [
            ("get_roster", "Who flies what: duties with route, report/release times and crew, "
             "filtered by pilot and/or day.", RosterArgs, self._get_roster),
            ("pilot_status", "A pilot's flight and duty hours used and remaining under each DGCA "
             "rolling limit on a day, plus their duties this week.", StatusArgs,
             self._pilot_status),
            ("what_if", "Re-plan a hypothetical on top of the current scenario: sick pilots, "
             "flight delays, cancellations and/or another ruleset. Changes are relative to the "
             "original roster. Never changes the live roster.", WhatIfArgs, self._what_if),
            ("min_pilots_needed", "Fewest captains and first officers a base needs to crew all "
             "its duties under a ruleset (first call can take ~15 s).", SizingArgs,
             self._min_pilots),
            ("explain_change", "Rule-checker reasons for one change in the current re-plan.",
             ChangeArgs, self._explain_change),
            ("lookup", "Find pilot ids by name or id fragment, or flight ids by flight number.",
             LookupArgs, self._lookup),
        ]
        self.tools: list[BaseTool] = [
            StructuredTool.from_function(func=self._wrap(name, fn), name=name,
                                         description=desc, args_schema=schema)
            for name, desc, schema, fn in specs
        ]

    def _wrap(self, name: str, fn: Callable[..., dict]) -> Callable[..., str]:
        def run(**kwargs) -> str:
            t0 = time.perf_counter()
            try:
                out, ok = fn(**kwargs), True
            except (ValueError, KeyError) as exc:  # bad ids/days: tell the model, don't crash
                out, ok = {"error": str(exc)}, False
            self.trace.append(ToolCallTrace(name=name, args=_jsonable(kwargs),
                                            seconds=round(time.perf_counter() - t0, 3), ok=ok))
            return json.dumps(out, separators=(",", ":"), default=str)

        return run

    def current(self) -> ScenarioResult:
        return evaluate(self.ruleset, self.disruptions, self.time_limit)

    def _get_roster(self, pilot_id: str | None = None, day: int | None = None) -> dict:
        res = self.current()
        rows = duty_views(res, pilot_id=pilot_id, day=day)
        shown = rows[:MAX_ROWS]
        return {
            "total": len(rows), "truncated": len(rows) > MAX_ROWS,
            "rows": [{"duty": r.id, "day": r.day, "route": r.route, "report": r.report,
                      "release": r.release, "flight_hours": r.flight_time_h, "night": r.night,
                      "captain": r.cpt, "first_officer": r.fo} for r in shown],
            "pilot_names": _names(res.problem, [p for r in shown for p in (r.cpt, r.fo)]),
        }

    def _pilot_status(self, pilot_id: str, day: int) -> dict:
        st = pilot_status(self.current(), pilot_id, day)
        return {
            "pilot": st.pilot.model_dump(), "day": day,
            "limits": [{"rule": u.rule, "used_hours": hours(u.used),
                        "limit_hours": hours(u.limit), "remaining_hours": hours(u.remaining)}
                       for u in st.usage],
            "duties": [{"duty": d.id, "day": d.day, "route": d.route, "report": d.report,
                        "flight_hours": d.flight_time_h} for d in st.duties],
        }

    def _what_if(self, sick=(), delays=(), cancel_flight_ids=(), ruleset=None) -> dict:
        extra: list[Disruption] = (
            [PilotSick(**_as(SickArg, s).model_dump()) for s in sick]
            + [FlightDelay(**_as(DelayArg, d).model_dump()) for d in delays]
            + [FlightCancel(flight_id=f) for f in cancel_flight_ids])
        target = ruleset or self.ruleset
        if not extra and target == self.ruleset:
            raise ValueError("give at least one disruption or a different ruleset")
        res = evaluate(target, self.disruptions + extra, self.time_limit)
        s = res.stats
        changes = res.changes[:MAX_CHANGES]
        return {
            "ruleset": res.ruleset, "duties": s.duties, "uncrewed_slots": s.uncovered,
            "changes": s.changes, "rule_breaches": s.violations, "solve_seconds": s.solve_seconds,
            "change_list": [{"id": c.id, "duty": c.duty_id, "role": c.role,
                             "old_pilot": c.old_pilot, "new_pilot": c.new_pilot,
                             "reasons": [reason_dict(v) for v in c.reasons]} for c in changes],
            "more_changes": max(len(res.changes) - MAX_CHANGES, 0),
            "pilot_names": _names(res.problem, [p for c in changes
                                                for p in (c.old_pilot, c.new_pilot)]),
        }

    def _min_pilots(self, base: str, ruleset: str | None = None) -> dict:
        s = sizing(base, ruleset or self.ruleset)
        note = ("proven minimum" if s.proven_optimal else
                "upper bound: a roster with this many pilots exists; fewer might also work")
        return {**s.model_dump(), "note": note}

    def _explain_change(self, change_id: str) -> dict:
        c = next((c for c in self.current().changes if c.id == change_id), None)
        if c is None:
            raise ValueError(f"no change {change_id!r} in the current scenario")
        return {"id": c.id, "duty": c.duty_id, "role": c.role, "old_pilot": c.old_pilot,
                "new_pilot": c.new_pilot, "reasons": [reason_dict(v) for v in c.reasons]}

    def _lookup(self, query: str) -> dict:
        return lookup(self.current().problem, query)
```

- [ ] **Step 4: Run the tests** → `uv run pytest tests/test_tools.py -q` → `5 passed`.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: agent tools over the scenario service" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: LangGraph agent with number check

**Files:**
- Create: `src/crew_roster/agent/prompts.py`, `src/crew_roster/agent/llm.py`, `src/crew_roster/agent/graph.py`, `tests/fakes.py`
- Modify: `src/crew_roster/agent/__init__.py`
- Test: `tests/test_graph.py`, `tests/test_agent_live.py`

**Interfaces:**
- Consumes: `Toolbox`, `ToolCallTrace` (Task 5), `check_numbers` (Task 4), `get_settings` (Task 1).
- Produces:
  - `crew_roster.agent.prompts`: `SYSTEM_PROMPT`, `EXPLAIN_PROMPT`.
  - `crew_roster.agent.llm`: `LlmFactory = Callable[[Sequence[BaseTool]], Runnable]` (given tools, returns a chat runnable with them bound; `[]` = no tools); `groq_llm_factory`; `text_of(message) -> str`.
  - `crew_roster.agent.graph`: `ChatTurn(role: "user"|"assistant", content)`, `AgentAnswer(answer, verified, ungrounded: list[str], tool_calls: list[ToolCallTrace])`, `build_graph(llm, tools)`, `run_agent(question, history, ruleset, disruptions, llm_factory=groq_llm_factory, time_limit=10.0) -> AgentAnswer`. `MAX_RETRIES = 1`.
  - `tests/fakes.py`: `ScriptedChatModel(script: list[AIMessage])` with `.calls`.

- [ ] **Step 1: Write the fake model and failing tests**

`tests/fakes.py`:

```python
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
```

`tests/test_graph.py`:

```python
from fakes import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from crew_roster.agent.graph import ChatTurn, run_agent
from crew_roster.service import evaluate, hours, pilot_status


def ft7_used_hours():
    st = pilot_status(evaluate("dgca_current", []), "DEL-C01", 3)
    return hours(next(u.used for u in st.usage if u.rule == "ft_7d"))


def factory_for(model):
    return lambda tools: model


def test_answer_grounded_in_a_tool_call_is_verified():
    used = ft7_used_hours()
    model = ScriptedChatModel(script=[
        tool_call("pilot_status", {"pilot_id": "DEL-C01", "day": 3}),
        AIMessage(content=f"DEL-C01 has flown {used} hours in the 7 days to day 3."),
    ])
    ans = run_agent("How much has DEL-C01 flown by day 3?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert ans.verified and ans.ungrounded == []
    assert [t.name for t in ans.tool_calls] == ["pilot_status"]
    assert str(used) in ans.answer


def test_invented_number_gets_one_retry_then_is_flagged():
    model = ScriptedChatModel(script=[AIMessage(content="They have 99.9 hours left.")])
    ans = run_agent("Hours left for DEL-C01?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert not ans.verified and ans.ungrounded == ["99.9"]
    assert model.calls == 2  # first draft + one retry after feedback


def test_retry_can_fix_the_answer():
    used = ft7_used_hours()
    model = ScriptedChatModel(script=[
        AIMessage(content="About 99.9 hours."),
        tool_call("pilot_status", {"pilot_id": "DEL-C01", "day": 3}),
        AIMessage(content=f"{used} hours flown."),
    ])
    ans = run_agent("Hours for DEL-C01 on day 3?", [ChatTurn(role="user", content="hi"),
                                                    ChatTurn(role="assistant", content="hello")],
                    "dgca_current", [], llm_factory=factory_for(model))
    assert ans.verified and model.calls == 3


def test_answer_without_numbers_is_verified():
    model = ScriptedChatModel(script=[AIMessage(content="Yes, the roster is fully legal.")])
    ans = run_agent("Is the roster legal?", [], "dgca_current", [],
                    llm_factory=factory_for(model))
    assert ans.verified and ans.tool_calls == []
```

`tests/test_agent_live.py`:

```python
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
```

- [ ] **Step 2: Run the fast tests to see them fail**

Run: `uv run pytest tests/test_graph.py -q` → ERROR `ModuleNotFoundError: No module named 'crew_roster.agent.graph'`.

- [ ] **Step 3: Write `src/crew_roster/agent/prompts.py`**

```python
SYSTEM_PROMPT = """You are Crew Roster Copilot, an assistant for the crew controllers of \
Skyline Air, a fictional Indian domestic airline (A320, bases DEL and BOM, a 7-day pilot roster \
with days numbered 0 to 6, times in IST).

Rosters follow India's DGCA flight duty time limitations (FDTL). Two rulesets exist: \
dgca_current (the rules in force since November 2025) and dgca_dec2025_exemption (the temporary \
December 2025 relaxation that allowed up to 6 night landings).

How to answer:
- Every number you state (hours, counts, times, pilots needed) must come from a tool result in \
this conversation. Never estimate or calculate numbers yourself; call a tool instead.
- Use what_if for any hypothetical (sick pilot, delay, cancellation, other ruleset). It never \
changes the live roster.
- Ids: pilots look like DEL-C04 (captain) or BOM-F12 (first officer); flights like SK115-D2 \
(flight SK115 on day 2); duties like BOM-D3-05; changes like BOM-D3-05:CPT. Use lookup to find \
ids from names or flight numbers.
- If a tool returns an error, fix the arguments or explain what is missing.
- min_pilots_needed may return an upper bound; say so when its note says it is not proven.
- Write for a non-technical reader: at most six short sentences or a short list."""

EXPLAIN_PROMPT = """You rewrite short roster-change notes for airline crew controllers. The \
input is a JSON object mapping change ids to factual notes. Reply with ONLY a JSON object with \
the same keys, where each value is one plain, friendly sentence that keeps every name, duty id \
and number exactly as given and adds no new facts or numbers."""
```

- [ ] **Step 4: Write `src/crew_roster/agent/llm.py`**

```python
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
                       reasoning_effort="low")
        return llm.bind_tools(list(tools)) if tools else llm

    return build(s.answer_model).with_fallbacks(
        [build(s.fast_model)], exceptions_to_handle=(RateLimitError,))


def text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part)
                   for part in content)
```

- [ ] **Step 5: Write `src/crew_roster/agent/graph.py`**

```python
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
```

`src/crew_roster/agent/__init__.py`:

```python
"""LLM agent: tools, number check, LangGraph graph, explanations."""

from crew_roster.agent.graph import AgentAnswer, ChatTurn, run_agent
from crew_roster.agent.llm import LlmFactory, groq_llm_factory
from crew_roster.agent.numbers import check_numbers
from crew_roster.agent.tools import Toolbox, ToolCallTrace

__all__ = ["AgentAnswer", "ChatTurn", "LlmFactory", "ToolCallTrace", "Toolbox",
           "check_numbers", "groq_llm_factory", "run_agent"]
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_graph.py -q` → `4 passed`. Full fast suite green (the live test is deselected).

- [ ] **Step 7: Live smoke test (needs the owner)**

Ask the owner to add `GROQ_API_KEY` (and optionally `LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true`) to `.env` themselves; never ask them to paste keys in chat and never print `.env`. If they decline or the key is empty, skip this step and say so. Otherwise run once (uses a few thousand free Groq tokens):

Run: `uv run pytest -m live -q`
Expected: `1 passed`. If it fails, report `ans` (answer, verified, ungrounded, tool names) — do not change the assertion. A common failure is gpt-oss answering without a tool call; fixing the prompt is fine, weakening the check is not.

- [ ] **Step 8: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: LangGraph agent with tool calls and number check" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Plain-language change explanations

**Files:**
- Create: `src/crew_roster/agent/explain.py`
- Test: `tests/test_explain.py`

**Interfaces:**
- Consumes: `Change` (Plan 1), `Problem`, `hm`, `TIME_RULES` (Task 3), `check_numbers` (Task 4), `EXPLAIN_PROMPT`, `LlmFactory`, `text_of` (Task 6).
- Produces: `crew_roster.agent.explain`: `template(change, problem) -> str`, `explain_changes(changes, problem, llm_factory=None) -> dict[str, str]` (change id → sentence). The LLM rewrite runs only when a factory is given and there are 1–20 changes; a rewrite is used only if all its numbers appear in that change's template; any LLM failure falls back to templates and logs a warning.

- [ ] **Step 1: Write the failing tests** — `tests/test_explain.py`:

```python
import json

from factories import mk_duty, mk_pilot, mk_problem, mk_roster
from fakes import ScriptedChatModel
from langchain_core.messages import AIMessage

from crew_roster.agent.explain import explain_changes, template
from crew_roster.roster.diff import diff

PILOTS = [mk_pilot("C1"), mk_pilot("C2"), mk_pilot("F1", rank="FO"), mk_pilot("F2", rank="FO")]


def rest_case():
    d1 = mk_duty("D1", 0, "08:00", 13, ft_hours=7)
    d2 = mk_duty("D2", 1, "06:00", 8, ft_hours=6)
    problem = mk_problem([d1, d2], PILOTS)
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}, "D2": {"CPT": "C1", "FO": "F2"}})
    new = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}, "D2": {"CPT": "C2", "FO": "F2"}})
    return problem, diff(problem, old, new)


def test_templates_state_the_rule_and_numbers():
    problem, [change] = rest_case()
    text = template(change, problem)
    assert text == ("D2: C1 would get only 9h00 rest before this duty (minimum 13h00); "
                    "C2 takes the captain seat.")


def test_sick_and_uncrewed_templates():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    problem = mk_problem([d], PILOTS, sick={"C1": [2]})
    old = mk_roster({"D1": {"CPT": "C1", "FO": "F1"}})
    [change] = diff(problem, old, mk_roster({"D1": {"FO": "F1"}}))
    assert template(change, problem) == (
        "D1: C1 reported sick for day 2; the captain seat is left uncrewed.")


def test_llm_rewrite_is_used_only_when_numbers_match():
    problem, changes = rest_case()
    cid = changes[0].id
    good = ScriptedChatModel(script=[AIMessage(content=json.dumps(
        {cid: "C2 flies D2 because C1 would only get 9h00 of rest, below the 13h00 minimum."}))])
    out = explain_changes(changes, problem, lambda tools: good)
    assert out[cid].startswith("C2 flies D2")
    bad = ScriptedChatModel(script=[AIMessage(content=json.dumps(
        {cid: "C1 would only get 7 hours of rest."}))])
    out = explain_changes(changes, problem, lambda tools: bad)
    assert out[cid] == template(changes[0], problem)


def test_llm_failure_falls_back_to_templates():
    problem, changes = rest_case()

    def broken(tools):
        raise RuntimeError("no key")

    assert explain_changes(changes, problem, broken) == {
        c.id: template(c, problem) for c in changes}
    assert explain_changes(changes, problem, None) == {c.id: template(c, problem) for c in changes}
```

- [ ] **Step 2: Run them to see them fail** → `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/crew_roster/agent/explain.py`**

```python
"""One plain-language sentence per roster change, built from checker reasons."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from langchain_core.messages import HumanMessage, SystemMessage

from crew_roster.agent.llm import LlmFactory, text_of
from crew_roster.agent.numbers import check_numbers
from crew_roster.agent.prompts import EXPLAIN_PROMPT
from crew_roster.models import Violation
from crew_roster.problem import Problem
from crew_roster.roster import Change
from crew_roster.service import TIME_RULES, hm

log = logging.getLogger(__name__)
MAX_LLM_CHANGES = 20
SEAT = {"CPT": "captain", "FO": "first officer"}
CANNOT_FLY = "so it cannot be flown as planned"
WHY = {
    "sick": "{old} reported sick for day {day}",
    "min_rest": "{old} would get only {value} rest before this duty (minimum {limit})",
    "ft_7d": "{old} would fly {value} in the 7 days to day {day} (limit {limit})",
    "ft_28d": "{old} would fly {value} in the 28 days to day {day} (limit {limit})",
    "duty_7d": "{old} would be on duty {value} in the 7 days to day {day} (limit {limit})",
    "duty_28d": "{old} would be on duty {value} in the 28 days to day {day} (limit {limit})",
    "weekly_rest": "{old} would miss the {limit} weekly rest in the 7 days to day {day}",
    "consecutive_nights": "{old} would fly {value} night duties in a row (limit {limit})",
    "night_max_landings": "the duty now has {value} landings at night (limit {limit}), "
                          + CANNOT_FLY,
    "night_max_fdp": "the duty now lasts {value} at night (limit {limit}), " + CANNOT_FLY,
    "max_fdp": "the duty now lasts {value} (limit {limit} for its landings), " + CANNOT_FLY,
    "max_ft_per_duty": "the duty now has {value} of flying (limit {limit}), " + CANNOT_FLY,
    "knock_on": "{old} was moved to free up cover elsewhere",
}


def _fmt(v: Violation, minutes: int) -> str:
    return hm(minutes) if v.rule in TIME_RULES else str(minutes)


def template(change: Change, problem: Problem) -> str:
    pilots = problem.pilot_map()
    old = pilots[change.old_pilot].name if change.old_pilot else "nobody"
    if change.reasons:
        v = change.reasons[0]
        why = WHY.get(v.rule, "{old}: " + v.message).format(
            old=old, day=v.day, value=_fmt(v, v.value), limit=_fmt(v, v.limit))
    else:
        why = f"the {SEAT[change.role]} seat was empty"
    then = (f"{pilots[change.new_pilot].name} takes the {SEAT[change.role]} seat"
            if change.new_pilot else f"the {SEAT[change.role]} seat is left uncrewed")
    return f"{change.duty_id}: {why}; {then}."


def _json_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]) if start != -1 and end > start else {}


def explain_changes(changes: Sequence[Change], problem: Problem,
                    llm_factory: LlmFactory | None = None) -> dict[str, str]:
    notes = {c.id: template(c, problem) for c in changes}
    if llm_factory is None or not 0 < len(changes) <= MAX_LLM_CHANGES:
        return notes
    try:
        reply = llm_factory([]).invoke([SystemMessage(EXPLAIN_PROMPT),
                                        HumanMessage(json.dumps(notes))])
        rewritten = _json_object(text_of(reply))
    except Exception as exc:  # optional polish: never fail the request over it
        log.warning("LLM explanations failed, using templates: %s", exc)
        return notes
    out = {}
    for cid, note in notes.items():
        cand = rewritten.get(cid)
        ok = isinstance(cand, str) and cand.strip() and check_numbers(cand, [note]).ok
        out[cid] = cand.strip() if ok else note
    return out
```

Note: the tiny test problem names pilots by id (`mk_pilot` sets `name=id`), so templates read "C1 would…".

- [ ] **Step 4: Run the tests** → `uv run pytest tests/test_explain.py -q` → `4 passed`.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: plain-language change explanations with checked LLM rewrite" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: FastAPI backend and `crew-serve`

**Files:**
- Create: `src/crew_roster/api/__init__.py` (empty), `src/crew_roster/api/main.py`
- Modify: `pyproject.toml` (`crew-serve` script)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces (`crew_roster.api.main`): `app` and endpoints:

| Method + path | Body / query | Returns |
|---|---|---|
| `GET /health` | – | `{"status": "ok"}` |
| `GET /rules` | – | `{ruleset_name: Ruleset JSON}` for both rulesets |
| `GET /roster` | `?ruleset=dgca_current` | `ScenarioView` |
| `POST /replan` | `{"ruleset", "disruptions": [Disruption…]}` | `ScenarioView` |
| `POST /chat` | `{"ruleset", "disruptions", "messages": [ChatTurn…]}` (last turn is the user's) | `AgentAnswer` |

`ScenarioView = {ruleset, label, disruptions, stats: Stats, pilots: [PilotView], flights: [FlightView], duties: [DutyView], changes: [ChangeView], illegal_duties}`. `ValueError` → HTTP 422 `{"detail": msg}`; `/chat` without a Groq key → 503; `/chat` over the per-IP limit → 429. `get_llm_factory()` is a FastAPI dependency that tests override. Script `crew-serve` runs uvicorn on `$PORT` (default 8000).

- [ ] **Step 1: Write the failing tests** — `tests/test_api.py`:

```python
import pytest
from fakes import ScriptedChatModel
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from crew_roster.api import main
from crew_roster.service import duty_views, evaluate


@pytest.fixture
def client():
    main.app.dependency_overrides[main.get_llm_factory] = lambda: None
    main._hits.clear()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def sick_body():
    pid = duty_views(evaluate("dgca_current", []), day=3)[0].cpt
    return {"ruleset": "dgca_current",
            "disruptions": [{"kind": "sick", "pilot_id": pid, "from_day": 3, "to_day": 4}]}


def test_health_and_rules(client):
    assert client.get("/health").json() == {"status": "ok"}
    rules = client.get("/rules").json()
    assert set(rules) == {"dgca_current", "dgca_dec2025_exemption"}
    assert rules["dgca_current"]["ft_7d"] == 2100
    assert rules["dgca_dec2025_exemption"]["night_max_landings"] == 6


def test_base_roster(client):
    view = client.get("/roster").json()
    assert view["stats"]["uncovered"] == 0 and view["stats"]["violations"] == 0
    assert len(view["duties"]) == 126 and len(view["pilots"]) == 80
    assert len(view["flights"]) == 294 and view["changes"] == []
    assert client.get("/roster", params={"ruleset": "dgca_dec2025_exemption"}).json()[
        "stats"]["duties"] == 113


def test_replan_returns_explained_changes(client):
    view = client.post("/replan", json=sick_body()).json()
    assert view["stats"]["violations"] == 0 and view["changes"]
    assert all(c["explanation"].startswith(c["duty_id"] + ":") for c in view["changes"])


def test_bad_disruption_is_422(client):
    body = {"ruleset": "dgca_current",
            "disruptions": [{"kind": "sick", "pilot_id": "NOPE", "from_day": 1, "to_day": 1}]}
    r = client.post("/replan", json=body)
    assert r.status_code == 422 and "NOPE" in r.json()["detail"]
    assert client.get("/roster", params={"ruleset": "nope"}).status_code == 422


def test_chat_needs_an_llm(client):
    body = {**sick_body(), "messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/chat", json=body).status_code == 503


def test_chat_with_scripted_model_and_rate_limit(client, monkeypatch):
    model = ScriptedChatModel(script=[AIMessage(content="The roster is fully crewed.")])
    main.app.dependency_overrides[main.get_llm_factory] = lambda: (lambda tools: model)
    monkeypatch.setattr(main.get_settings(), "rate_limit_per_minute", 1)
    body = {"ruleset": "dgca_current", "disruptions": [],
            "messages": [{"role": "user", "content": "Is everything crewed?"}]}
    r = client.post("/chat", json=body)
    assert r.status_code == 200 and r.json()["verified"] is True
    assert client.post("/chat", json=body).status_code == 429


def test_chat_last_turn_must_be_the_user(client):
    body = {"ruleset": "dgca_current", "disruptions": [],
            "messages": [{"role": "assistant", "content": "hello"}]}
    assert client.post("/chat", json=body).status_code == 422
```

- [ ] **Step 2: Run them to see them fail** → `ModuleNotFoundError: No module named 'crew_roster.api'`.

- [ ] **Step 3: Write `src/crew_roster/api/main.py`**

```python
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
```

Add to `[project.scripts]` in `pyproject.toml`: `crew-serve = "crew_roster.api.main:main"`, then `uv sync`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_api.py -q` → `7 passed` (one re-plan, cached across tests). Then the full fast suite `uv run pytest -q` and the slow suite once `uv run pytest -m slow -q`.

- [ ] **Step 5: Manual smoke run**

```bash
uv run crew-serve
```

In a second terminal: `curl -s http://localhost:8000/health` → `{"status":"ok"}`, and open `http://localhost:8000/docs`. Stop the server (Ctrl+C). If the owner has added a Groq key, also try one `/chat` from the docs page and report whether it came back `verified: true`.

- [ ] **Step 6: Commit**

```bash
uv run ruff check src tests
git add -A
git commit -m "feat: FastAPI backend with replan, chat and rules endpoints" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Plan 2 is done when every fast and slow test passes, ruff is clean, and (if a key is available) the live test passes. Next: Plan 3 (React frontend) against the `ScenarioView` / `AgentAnswer` shapes above.
