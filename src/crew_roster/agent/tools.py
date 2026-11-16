"""Agent tools: thin wrappers over the scenario service. They never change the live roster."""

from __future__ import annotations

import json
import logging
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

log = logging.getLogger(__name__)
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
    pilot_id: str = Field(description="Pilot id such as DEL-C04")
    from_day: int = Field(ge=0, le=6, description="First sick roster day 0-6")
    to_day: int = Field(ge=0, le=6, description="Last sick roster day 0-6")


class DelayArg(BaseModel):
    flight_id: str = Field(description="Flight id with day, e.g. SK115-D2")
    minutes: int = Field(gt=0, le=600, description="Delay in minutes (1-600)")


class WhatIfArgs(BaseModel):
    sick: list[SickArg] = Field(default_factory=list)
    delays: list[DelayArg] = Field(default_factory=list)
    cancel_flight_ids: list[str] = Field(
        default_factory=list, description="Flight ids with day to cancel, e.g. SK115-D2")
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


def _invalid_args(exc: Exception) -> dict:
    """The raw arguments as far as the validation error shows them: the handler only gets
    the exception, so this is the whole input when a field is missing, else the bad values."""
    errors = getattr(exc, "errors", None)
    args: dict = {}
    for e in errors() if callable(errors) else ():
        loc, value = tuple(e.get("loc", ())), e.get("input")
        if e.get("type") == "missing" and isinstance(value, dict):
            args.update(value)
        elif loc:
            args[".".join(str(p) for p in loc)] = value
    return _jsonable(args)


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
                                         description=desc, args_schema=schema,
                                         handle_validation_error=self._invalid(name))
            for name, desc, schema, fn in specs
        ]

    def _wrap(self, name: str, fn: Callable[..., dict]) -> Callable[..., str]:
        def run(**kwargs) -> str:
            t0 = time.perf_counter()
            try:
                out, ok = fn(**kwargs), True
            except (ValueError, KeyError) as exc:  # bad ids/days: tell the model, don't crash
                msg = f"not found: {exc.args[0]}" if isinstance(exc, KeyError) else str(exc)
                out, ok = {"error": msg}, False
            except Exception:  # a bug in a tool must not crash the chat request
                log.exception("tool %s failed", name)
                out, ok = {"error": f"internal error in {name}"}, False
            self.trace.append(ToolCallTrace(name=name, args=_jsonable(kwargs),
                                            seconds=round(time.perf_counter() - t0, 3), ok=ok))
            return json.dumps(out, separators=(",", ":"), default=str)

        return run

    def _invalid(self, name: str) -> Callable[[Exception], str]:
        def handle(exc: Exception) -> str:
            errors = getattr(exc, "errors", None)
            detail = "; ".join(
                f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', '')}"
                for e in errors()
            ) if callable(errors) else str(exc)
            self.trace.append(ToolCallTrace(name=name, args=_invalid_args(exc), seconds=0.0,
                                            ok=False))
            return json.dumps({"error": f"invalid arguments: {detail}"}, separators=(",", ":"))

        return handle

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
