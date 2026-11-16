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
