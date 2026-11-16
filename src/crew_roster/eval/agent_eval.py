"""Run the agent over the evaluation dataset and score it; optional Claude judge and LangSmith.

Deterministic metrics need no extra service. The default chat model is the named Groq model
with no fallback, so every scored answer comes from that model.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from crew_roster.agent.graph import AgentAnswer, run_agent
from crew_roster.agent.llm import LlmFactory, text_of
from crew_roster.agent.numbers import TOLERANCE, extract
from crew_roster.config import Settings, get_settings
from crew_roster.eval.agent_dataset import AgentCase, build_dataset
from crew_roster.eval.optimiser import RESULTS_DIR, write_json

SCORES = ("tool_ok", "args_ok", "numbers_recall", "names_ok", "grounded", "n_tool_calls",
          "seconds")
LS_DATASET = "crew-roster-agent"
JUDGE_PRICE = {"input": 0.10, "output": 0.50}  # USD per million tokens, claude-haiku-5-5
JUDGE_OUTPUT_TOKENS = 120
REPLAN_EXPLANATIONS = 10
RATE_LIMIT_WAIT = 30.0


def model_slug(model: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")


def _contains(args: dict, expected: dict) -> bool:
    return all(args.get(k) == v for k, v in expected.items())


def score(case: AgentCase, answer: AgentAnswer, seconds: float = 0.0) -> dict:
    names = [t.name for t in answer.tool_calls]
    found = [v for _, v in extract(answer.answer)]
    hits = sum(1 for e in case.expected_numbers if any(abs(v - e) < TOLERANCE for v in found))
    text = answer.answer.lower()
    return {
        "tool_ok": case.expected_tool in names,
        "args_ok": any(t.name == case.expected_tool and _contains(t.args, case.expected_args)
                       for t in answer.tool_calls),
        "numbers_recall": (round(hits / len(case.expected_numbers), 3)
                           if case.expected_numbers else 1.0),
        "names_ok": (all(n.lower() in text for n in case.expected_names)
                     if case.expected_names else None),
        "grounded": answer.verified,
        "n_tool_calls": len(answer.tool_calls),
        "seconds": round(seconds, 3),
    }


def _means(rows: list[dict]) -> dict:
    out: dict = {"n": len(rows)}
    for k in SCORES:
        vals = [float(r[k]) for r in rows if r.get(k) is not None]
        out[k] = round(statistics.fmean(vals), 3) if vals else None
    return out


def summarise(rows: Sequence[dict]) -> dict:
    rows = list(rows)
    cats = dict.fromkeys(r["category"] for r in rows)
    return {"all": _means(rows),
            "by_category": {c: _means([r for r in rows if r["category"] == c]) for c in cats}}


def groq_factory(model: str) -> LlmFactory:
    """The named Groq model only (no fallback), tools bound."""
    key = get_settings().groq_api_key
    if not key:
        raise SystemExit("GROQ_API_KEY is not set in .env: the agent eval needs a (free) Groq "
                         "key, see https://console.groq.com/keys")

    def factory(tools):
        from langchain_groq import ChatGroq

        extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
        llm = ChatGroq(model=model, api_key=key, temperature=0, max_retries=1, timeout=30,
                       **extra)
        return llm.bind_tools(list(tools)) if tools else llm

    return factory


def _rate_limited(exc: Exception) -> bool:
    return type(exc).__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429


def _daily(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in ("per day", "(tpd)", "(rpd)", "daily"))


def _row(case: AgentCase, ans: AgentAnswer, seconds: float, error: str | None = None) -> dict:
    row = {"id": case.id, "category": case.category, "question": case.question,
           "ruleset": case.ruleset, "answer": ans.answer, "verified": ans.verified,
           "ungrounded": ans.ungrounded,
           "tool_calls": [t.model_dump() for t in ans.tool_calls], **score(case, ans, seconds)}
    if error:
        row["error"] = error
    return row


def _check_keys(s: Settings, judge: bool, langsmith: bool) -> None:
    if judge and not s.anthropic_api_key:
        raise SystemExit("--judge needs ANTHROPIC_API_KEY in .env (the judge is "
                         f"{s.judge_model}; its cost is printed before any call)")
    if langsmith and not s.langsmith_api_key:
        raise SystemExit("--langsmith needs LANGSMITH_API_KEY in .env "
                         "(free key: https://smith.langchain.com -> Settings -> API Keys)")


def run_agent_eval(model: str, cases: Sequence[AgentCase] | None = None,
                   llm_factory: LlmFactory | None = None, out: Path | None = None,
                   judge: bool = False, langsmith: bool = False, limit: int | None = None,
                   pause: float = 2.0, time_limit: float = 10.0,
                   log: Callable[[str], None] = print) -> dict:
    """Run every case once (resumable by case id) and write rows + summary as JSON."""
    settings = get_settings()
    _check_keys(settings, judge, langsmith)
    factory = llm_factory or groq_factory(model)
    out = Path(out or RESULTS_DIR / f"agent-{model_slug(model)}.json")
    if cases is None:
        log("building the evaluation dataset (sizing takes ~1 min the first time) ...")
        cases = build_dataset(time_limit=time_limit)
    cases = list(cases)[:limit] if limit else list(cases)

    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    rows: list[dict] = list(old.get("rows", []))
    done = {r["id"] for r in rows}
    data = {"config": {"model": model, "n_cases": len(cases), "time_limit": time_limit},
            "rows": rows, "summary": summarise(rows), "stopped": None}
    if "judge" in old:
        data["judge"] = old["judge"]

    todo = [c for c in cases if c.id not in done]
    for i, case in enumerate(todo):
        if i and pause:
            time.sleep(pause)
        for attempt in range(2):
            t0 = time.perf_counter()
            try:
                ans = run_agent(case.question, [], case.ruleset, case.disruptions,
                                llm_factory=factory, time_limit=time_limit)
                rows.append(_row(case, ans, time.perf_counter() - t0))
                break
            except Exception as exc:  # every failure is either scored as a miss or stops
                if _rate_limited(exc) and (_daily(exc) or attempt == 1):
                    data["stopped"] = f"{'daily limit' if _daily(exc) else 'rate limit'}: {exc}"
                    break
                if _rate_limited(exc):
                    log(f"{case.id}: rate limited, waiting {RATE_LIMIT_WAIT:.0f} s")
                    time.sleep(RATE_LIMIT_WAIT)
                    continue
                empty = AgentAnswer(answer="", verified=False, ungrounded=[], tool_calls=[])
                rows.append(_row(case, empty, time.perf_counter() - t0,
                                 error=f"{type(exc).__name__}: {exc}"))
                break
        if data["stopped"]:
            log(f"stopping: {data['stopped']} (progress saved; rerun to resume)")
            break
        r = rows[-1]
        log(f"{r['id']:<12} tool={r['tool_ok']!s:<5} args={r['args_ok']!s:<5} "
            f"numbers={r['numbers_recall']:<5} grounded={r['grounded']!s:<5} {r['seconds']}s")
        data["summary"] = summarise(rows)
        write_json(out, data)

    data["summary"] = summarise(rows)
    write_json(out, data)
    if judge and not data["stopped"]:
        data["judge"] = run_judge(cases, rows, settings, factory, time_limit, log)
        write_json(out, data)
    if langsmith:
        log_langsmith(model, cases, rows, settings)
    return data


# ----------------------------------------------------------------- optional Claude judge

JUDGE_PROMPT = """You grade one sentence that explains a change to an airline pilot roster. \
You get the rule-checker reasons (the ground truth) and the sentence. Score:
- faithful (1-5): 5 = every fact and number in the sentence matches the reasons, nothing \
invented; 1 = wrong or invented facts.
- clear (1-5): 5 = a non-technical crew controller understands it at once.
Reply with ONLY a JSON object: {"faithful": <1-5>, "clear": <1-5>, "why": "<one short sentence>"}"""


def judge_cost(calls: int, input_tokens: int, output_tokens: int = JUDGE_OUTPUT_TOKENS) -> float:
    """Estimated USD for `calls` judge calls of about this many tokens each."""
    per_call = input_tokens * JUDGE_PRICE["input"] + output_tokens * JUDGE_PRICE["output"]
    return calls * per_call / 1e6


def _judge_items(cases: Sequence[AgentCase], rows: Sequence[dict], factory: LlmFactory,
                 time_limit: float) -> list[dict]:
    """The agent's answers to the explain cases, plus 10 /replan change explanations."""
    from crew_roster.agent.explain import explain_changes
    from crew_roster.agent.tools import reason_dict
    from crew_roster.eval.scenarios import make_scenarios
    from crew_roster.service import evaluate

    items = []
    by_case = {c.id: c for c in cases}
    for r in rows:
        c = by_case.get(r["id"])
        if not c or c.category != "explain" or r.get("error"):
            continue
        res = evaluate(c.ruleset, c.disruptions, time_limit)
        ch = next(x for x in res.changes if x.id == c.expected_args["change_id"])
        items.append({"source": "agent_explain", "id": c.id, "sentence": r["answer"],
                      "reasons": [reason_dict(v) for v in ch.reasons]})
    replans: list[dict] = []
    for s in make_scenarios():
        if len(replans) >= REPLAN_EXPLANATIONS:
            break
        res = evaluate("dgca_current", s.disruptions, time_limit)
        picked = [c for c in res.changes if c.old_pilot][:2]
        if not picked:
            continue
        notes = explain_changes(picked, res.problem, factory)
        replans += [{"source": "replan", "id": f"{s.id}/{c.id}", "sentence": notes[c.id],
                     "reasons": [reason_dict(v) for v in c.reasons]} for c in picked]
    return items + replans[:REPLAN_EXPLANATIONS]


def run_judge(cases: Sequence[AgentCase], rows: Sequence[dict], settings: Settings,
              factory: LlmFactory, time_limit: float, log: Callable[[str], None]) -> dict:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    items = _judge_items(cases, rows, factory, time_limit)
    prompts = [json.dumps({"reasons": i["reasons"], "sentence": i["sentence"]}) for i in items]
    avg_in = int(statistics.fmean(len(JUDGE_PROMPT + p) for p in prompts) / 4) if prompts else 0
    cost = judge_cost(len(items), avg_in)
    log(f"judge: {len(items)} calls to {settings.judge_model}, ~{avg_in} input + "
        f"~{JUDGE_OUTPUT_TOKENS} output tokens each, estimated ${cost:.4f}")
    llm = ChatAnthropic(model=settings.judge_model, api_key=settings.anthropic_api_key,
                        max_tokens=300, max_retries=2, timeout=60)
    scored = []
    for item, prompt in zip(items, prompts, strict=True):
        try:
            reply = text_of(llm.invoke([SystemMessage(JUDGE_PROMPT), HumanMessage(prompt)]))
            start, end = reply.find("{"), reply.rfind("}")
            verdict = json.loads(reply[start:end + 1])
            scored.append({**item, "faithful": int(verdict["faithful"]),
                           "clear": int(verdict["clear"]), "why": str(verdict.get("why", ""))})
        except Exception as exc:  # one bad reply must not lose the others
            scored.append({**item, "faithful": None, "clear": None, "why": f"error: {exc}"})
    summary = {}
    for src in dict.fromkeys(i["source"] for i in scored):
        mine = [i for i in scored if i["source"] == src and i["faithful"] is not None]
        summary[src] = {
            "n": len(mine),
            "faithful": round(statistics.fmean(i["faithful"] for i in mine), 2) if mine else None,
            "clear": round(statistics.fmean(i["clear"] for i in mine), 2) if mine else None,
        }
    return {"model": settings.judge_model, "estimated_cost_usd": round(cost, 4),
            "items": scored, "summary": summary}


# ----------------------------------------------------------------- optional LangSmith

def log_langsmith(model: str, cases: Sequence[AgentCase], rows: Sequence[dict],
                  settings: Settings) -> None:
    """Upload the cases as a dataset (idempotent) and log this run as an experiment."""
    from langsmith import Client
    from langsmith import evaluate as ls_evaluate

    client = Client(api_key=settings.langsmith_api_key)
    if client.has_dataset(dataset_name=LS_DATASET):
        ds = client.read_dataset(dataset_name=LS_DATASET)
    else:
        ds = client.create_dataset(LS_DATASET, description="Crew Roster Copilot agent eval")
    have = {(ex.metadata or {}).get("case_id") for ex in client.list_examples(dataset_id=ds.id)}
    new = [c for c in cases if c.id not in have]
    if new:
        expected = {"expected_tool", "expected_args", "expected_numbers", "expected_names"}
        client.create_examples(dataset_id=ds.id, examples=[
            {"inputs": {"case_id": c.id, "question": c.question, "ruleset": c.ruleset},
             "outputs": c.model_dump(mode="json", include=expected),
             "metadata": {"case_id": c.id, "category": c.category}} for c in new])
    by_id = {r["id"]: r for r in rows}
    examples = [ex for ex in client.list_examples(dataset_id=ds.id)
                if (ex.metadata or {}).get("case_id") in by_id]

    def target(inputs: dict) -> dict:  # replays the stored run: no second LLM call
        r = by_id[inputs["case_id"]]
        return {"answer": r["answer"], **{k: r[k] for k in SCORES}}

    def scores(outputs: dict) -> dict:
        return {"results": [{"key": k, "score": float(outputs[k])}
                            for k in SCORES if outputs.get(k) is not None]}

    ls_evaluate(target, data=examples, evaluators=[scores], client=client,
                experiment_prefix=f"agent-{model_slug(model)}", metadata={"model": model})
