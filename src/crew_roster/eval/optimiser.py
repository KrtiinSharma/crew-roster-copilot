"""Optimiser benchmark (CP-SAT re-plan vs greedy repair vs re-solve from scratch) and sizing."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Sequence
from pathlib import Path

from crew_roster.config import ROOT
from crew_roster.eval.scenarios import SIZES, Scenario, make_scenarios
from crew_roster.roster import check, min_pilots_needed, replan
from crew_roster.rules import RULESETS
from crew_roster.service import base_problem

RESULTS_DIR = ROOT / "docs" / "results"
METHODS = ("cpsat", "greedy", "scratch")
ROW_KEYS = ("scenario", "size", "method", "uncrewed", "changes", "breaches", "seconds", "status")
METRICS = ("changes", "uncrewed", "seconds")
BASES = ("DEL", "BOM")


def run_one(scenario: Scenario, method: str, time_limit: float = 10.0,
            ruleset: str = "dgca_current") -> dict:
    problem, base = base_problem(ruleset)
    t0 = time.perf_counter()
    rp = replan(problem, base, scenario.disruptions, method=method, time_limit=time_limit)
    wall = time.perf_counter() - t0
    res = rp.result
    return {"scenario": scenario.id, "size": scenario.size, "method": method,
            "uncrewed": len(res.uncovered), "changes": len(rp.changes),
            "breaches": len(check(rp.problem, res.roster)), "seconds": round(res.seconds, 3),
            "wall_seconds": round(wall, 3), "status": res.status}


def run_benchmark(scenarios: Sequence[Scenario], methods: Sequence[str] = METHODS,
                  time_limit: float = 10.0, ruleset: str = "dgca_current") -> list[dict]:
    return [run_one(s, m, time_limit, ruleset) for s in scenarios for m in methods]


def _stats(rows: list[dict]) -> dict:
    out: dict = {"n": len(rows)}
    for k in METRICS:
        vals = [r[k] for r in rows]
        out[k] = ({"mean": round(statistics.fmean(vals), 3),
                   "median": round(statistics.median(vals), 3)} if vals else None)
    return out


def _wins(rows: list[dict], a: str, b: str, metric: str) -> dict:
    by = {(r["scenario"], r["method"]): r for r in rows}
    pairs = [(by[s, a], by[s, b]) for s, m in by if m == a and (s, b) in by]
    return {"wins": sum(1 for x, y in pairs if x[metric] < y[metric]), "of": len(pairs)}


def summarise(rows: Sequence[dict]) -> dict:
    rows = list(rows)
    methods = {}
    for m in dict.fromkeys(r["method"] for r in rows):
        mine = [r for r in rows if r["method"] == m]
        entry = {"all": _stats(mine), "breaches": sum(r["breaches"] for r in mine)}
        for size in SIZES:
            sized = [r for r in mine if r["size"] == size]
            if sized:
                entry[size] = _stats(sized)
        methods[m] = entry
    return {"methods": methods, "wins": {
        "cpsat_fewer_changes_than_scratch": _wins(rows, "cpsat", "scratch", "changes"),
        "cpsat_fewer_uncrewed_than_greedy": _wins(rows, "cpsat", "greedy", "uncrewed"),
    }}


def sizing_table(time_limit: float = 15.0) -> list[dict]:
    table = []
    for ruleset in RULESETS:
        problem, _ = base_problem(ruleset)
        for base in BASES:
            table.append(min_pilots_needed(problem, base, time_limit=time_limit).model_dump())
    return table


def write_json(out: Path, data: dict) -> None:
    """Write via a temp file; OneDrive/antivirus can briefly lock the target, so retry."""
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(5):
        try:
            tmp.replace(out)
            return
        except PermissionError:
            time.sleep(0.5 * (attempt + 1))
    out.write_text(text, encoding="utf-8")
    tmp.unlink(missing_ok=True)


def run_optimiser_eval(n: int = 50, time_limit: float = 10.0,
                       out: Path = RESULTS_DIR / "optimiser.json",
                       methods: Sequence[str] = METHODS, seed: int = 11,
                       ruleset: str = "dgca_current", sizing_time_limit: float = 15.0,
                       log=print) -> dict:
    """Run the benchmark and write {config, rows, summary, sizing}; resumable row by row."""
    out = Path(out)
    config = {"n": n, "seed": seed, "ruleset": ruleset, "time_limit": time_limit,
              "methods": list(methods)}
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    same = {k: old.get("config", {}).get(k) for k in ("seed", "ruleset", "time_limit")}
    if old and same != {k: config[k] for k in same}:
        log(f"{out.name}: config changed ({old.get('config')}), starting afresh")
        old = {}
    rows: list[dict] = list(old.get("rows", []))
    done = {(r["scenario"], r["method"]) for r in rows}
    data = {"config": config, "rows": rows, "summary": summarise(rows),
            "sizing": old.get("sizing", [])}
    for s in make_scenarios(n=n, seed=seed, ruleset=ruleset):
        for m in methods:
            if (s.id, m) in done:
                continue
            r = run_one(s, m, time_limit, ruleset)
            rows.append(r)
            log(f"{s.id} {s.size:<6} {m:<7} changes={r['changes']:<4} "
                f"uncrewed={r['uncrewed']:<3} breaches={r['breaches']} {r['seconds']}s")
            data["summary"] = summarise(rows)
            write_json(out, data)
    if not data["sizing"]:
        log("crew sizing (min_pilots_needed) for DEL/BOM x both rulesets ...")
        data["sizing"] = sizing_table(sizing_time_limit)
    data["summary"] = summarise(rows)
    write_json(out, data)
    return data
