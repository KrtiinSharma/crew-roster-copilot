"""docs/results/RESULTS.md from whatever result JSON exists."""

from __future__ import annotations

import json
from pathlib import Path

from crew_roster.eval.optimiser import RESULTS_DIR

SIZES = ("small", "medium", "large", "all")
METHOD_LABEL = {"cpsat": "CP-SAT minimum-change re-plan", "greedy": "greedy repair",
                "scratch": "CP-SAT re-solve from scratch (no change penalty)"}
CATEGORY_LABEL = {"hours": "flight hours used / left", "roster": "who flies a duty",
                  "what_if": "what-if sick pilot", "explain": "why was a pilot replaced",
                  "sizing": "pilots needed per base"}


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _mm(stat: dict | None, digits: int = 1) -> str:
    if not stat:
        return "-"
    return f"{stat['mean']:.{digits}f} ({stat['median']:.{digits}f})"


def _pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.0%}"


def _num(v: float | None, digits: int = 1) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def _optimiser(data: dict | None) -> list[str]:
    out = ["## Optimiser benchmark", ""]
    if not data or not data.get("rows"):
        return out + ["No optimiser results yet. Produce them with `uv run crew-eval optimiser` "
                      "(seeded scenarios x 3 methods, roughly 25 minutes on a laptop), then "
                      "`uv run crew-eval report`.", ""]
    c, s = data["config"], data["summary"]
    n_sc = len({r["scenario"] for r in data["rows"]})
    out += [f"{n_sc} seeded disruption scenarios (seed {c['seed']}, ruleset `{c['ruleset']}`, "
            f"CP-SAT deterministic time limit {c['time_limit']:g} s). Small = 1 disruption, "
            "medium = 2-3, large = 4-6 (sick pilots, delays of 1-5 h, cancellations). Methods: "
            + "; ".join(f"**{m}** = {METHOD_LABEL.get(m, m)}" for m in s["methods"]) + ".",
            "",
            "Cells are mean (median). *Changes* = base-roster slots that got a different pilot; "
            "*uncrewed* = empty seats after the re-plan; *seconds* = solver time.", "",
            "| Method | Size | Scenarios | Changes | Uncrewed seats | Seconds |",
            "|---|---|---|---|---|---|"]
    for m, entry in s["methods"].items():
        for size in SIZES:
            st = entry.get(size)
            if st:
                out.append(f"| {m} | {size} | {st['n']} | {_mm(st['changes'])} | "
                           f"{_mm(st['uncrewed'])} | {_mm(st['seconds'], 2)} |")
    w = s["wins"]
    ch, un = w["cpsat_fewer_changes_than_scratch"], w["cpsat_fewer_uncrewed_than_greedy"]
    out += ["",
            f"- CP-SAT re-plan needed **fewer changes than re-solving from scratch** in "
            f"**{ch['wins']} of {ch['of']}** scenarios (more in {ch.get('losses', '?')}).",
            f"- CP-SAT re-plan left **fewer uncrewed seats than greedy repair** in "
            f"**{un['wins']} of {un['of']}** scenarios and more in "
            f"{un.get('losses', '?')} (the rest are ties).",
            "- Total rule breaches found by the independent checker: "
            + ", ".join(f"{m} {e['breaches']}" for m, e in s["methods"].items()) + "."]
    if all("illegal_seats_total" in e for e in s["methods"].values()):
        out.append("- Uncrewed seats in total, of which on duties a delay made illegal (nobody "
                   "may fly them): " + ", ".join(
                       f"{m} {e['uncrewed_total']} ({e['illegal_seats_total']})"
                       for m, e in s["methods"].items()) + ".")
    out += _caveats(data["rows"])
    out.append("")
    return out


def _caveats(rows: list[dict]) -> list[str]:
    """Counts straight from the rows: scratch hitting its time limit, greedy vs CP-SAT trade-off."""
    out = []
    scratch = [r for r in rows if r["method"] == "scratch"]
    if scratch:
        hit = sum(1 for r in scratch if r["status"] == "FEASIBLE")
        out.append(f"- Re-solving from scratch hit its time limit (status FEASIBLE, not proven "
                   f"optimal) in {hit}/{len(scratch)} runs, so its numbers are of the best "
                   "solution found in time.")
    by = {(r["scenario"], r["method"]): r for r in rows}
    more = [(by[sc, "cpsat"], by[sc, "greedy"]) for sc, m in by
            if m == "cpsat" and (sc, "greedy") in by
            and by[sc, "cpsat"]["uncrewed"] < by[sc, "greedy"]["uncrewed"]]
    if more:
        fewer = sum(1 for c, g in more if g["changes"] < c["changes"])
        out.append(f"- In the {len(more)} scenarios where CP-SAT crewed more seats than greedy, "
                   f"greedy made fewer changes than CP-SAT in {fewer}: it changes less partly "
                   "because it leaves seats empty.")
    return out


def _sizing(data: dict | None) -> list[str]:
    out = ["## Crew sizing: current rules vs the December 2025 exemption", ""]
    sizing = (data or {}).get("sizing") or []
    if not sizing:
        return out + ["No sizing results yet: `uv run crew-eval optimiser` computes them at the "
                      "end of the benchmark.", ""]
    by = {(r["base"], r["ruleset"]): r for r in sizing}

    def need(r: dict | None) -> str:
        if not r or not r["feasible"]:
            return "infeasible"
        return f"{r['pilots_needed'].get('CPT', 0)} / {r['pilots_needed'].get('FO', 0)}"

    def duties(r: dict | None) -> str:
        return "-" if not r else str(r["duties"])

    def status(r: dict | None) -> str:
        if not r or not r["feasible"]:
            return "-"
        return "proven" if r["proven_optimal"] else "upper bound"

    out += ["Fewest captains / first officers per base that still crew every duty "
            "(CP-SAT, deterministic time limit per solve). *Proven* = optimal; *upper bound* = a "
            "roster with that many pilots exists, fewer might also work. Duties are shown per "
            "ruleset: the exemption allows longer night duties, so the duty builder makes "
            "fewer, longer BOM duties, and part of the lower BOM pilot count comes from that "
            "rather than from the rules alone.", "",
            "| Base | Current rules CPT / FO | Exemption CPT / FO | On the roster CPT / FO "
            "| Duties (current / exemption) | Status (current / exemption) |",
            "|---|---|---|---|---|---|"]
    for base in dict.fromkeys(r["base"] for r in sizing):
        cur, ex = by.get((base, "dgca_current")), by.get((base, "dgca_dec2025_exemption"))
        ref = cur or ex
        avail = ref["pilots_available"]
        out.append(f"| {base} | {need(cur)} | {need(ex)} | {avail.get('CPT', 0)} / "
                   f"{avail.get('FO', 0)} | {duties(cur)} / {duties(ex)} | "
                   f"{status(cur)} / {status(ex)} |")
    return out + [""]


def _agent(files: list[tuple[str, dict]]) -> list[str]:
    out = ["## Agent evaluation", ""]
    if not files:
        return out + ["No agent results yet. With `ANTHROPIC_API_KEY` in `.env`, run "
                      "`uv run crew-eval agent` (Claude Haiku; or `--model "
                      "openai/gpt-oss-120b` with `GROQ_API_KEY`), then "
                      "`uv run crew-eval report`. It is resumable.", ""]
    n_cases = max(d.get("config", {}).get("n_cases") or d["summary"]["all"]["n"]
                  for _, d in files)
    n_cats = max(len(d["summary"]["by_category"]) for _, d in files)
    out += [f"{n_cases} questions in {n_cats} categories; every expected answer is computed by the "
            "service, not written by hand. *Tool* = called the right tool; *args* = with the "
            "right arguments; *numbers* = share of expected numbers present in the answer; "
            "*grounded* = passed the number check (every number came from a tool).", "",
            "| Model | Cases | Tool | Args | Numbers | Grounded | Tool calls | Seconds |",
            "|---|---|---|---|---|---|---|---|"]
    for model, d in files:
        a = d["summary"]["all"]
        out.append(f"| {model} | {a['n']} | {_pct(a['tool_ok'])} | {_pct(a['args_ok'])} | "
                   f"{_pct(a['numbers_recall'])} | {_pct(a['grounded'])} | "
                   f"{_num(a['n_tool_calls'])} | {_num(a['seconds'])} |")
    out += ["", "Per category (names = both pilot names present, roster questions only):", "",
            "| Model | Category | Cases | Tool | Args | Numbers | Names | Grounded |",
            "|---|---|---|---|---|---|---|---|"]
    for model, d in files:
        for cat, a in d["summary"]["by_category"].items():
            out.append(f"| {model} | {cat} | {a['n']} | {_pct(a['tool_ok'])} | "
                       f"{_pct(a['args_ok'])} | {_pct(a['numbers_recall'])} | "
                       f"{_pct(a['names_ok'])} | {_pct(a['grounded'])} |")
    for model, d in files:
        if d.get("stopped"):
            out.append(f"\n> {model}: run stopped early ({d['stopped'][:120]}); rerun to resume.")
    return out + [""]


def _judge(files: list[tuple[str, dict]]) -> list[str]:
    out = ["## Claude judge on change explanations", ""]
    judged = [(m, d["judge"]) for m, d in files if d.get("judge")]
    if not judged:
        return out + ["Not run. Optional: with `ANTHROPIC_API_KEY` in `.env`, add `--judge` to "
                      "the agent run; it prints the estimated cost (a few cents with "
                      "claude-haiku-5-5) before any call.", ""]
    out += ["Scores 1-5 for the agent's *why was X replaced* answers (agent_explain) and for "
            "10 change explanations from `/replan` scenarios (replan).", "",
            "| Model | Source | Judged | Faithful | Clear |", "|---|---|---|---|---|"]
    for model, j in judged:
        for src, s in j["summary"].items():
            out.append(f"| {model} | {src} | {s['n']} | {_num(s['faithful'])} | "
                       f"{_num(s['clear'])} |")
    return out + [""]


def build_report(results_dir: Path = RESULTS_DIR) -> str:
    results_dir = Path(results_dir)
    opt = _load(results_dir / "optimiser.json")
    agents = []
    for p in sorted(results_dir.glob("agent-*.json")):
        d = _load(p)
        if d and d.get("summary"):
            agents.append((d.get("config", {}).get("model", p.stem), d))
    lines = ["# Crew Roster Copilot: results", "",
             "Generated by `uv run crew-eval report` from the JSON files in this folder. "
             "Scenarios and solver results are seeded and reproducible; timings vary by "
             "machine.", ""]
    lines += _optimiser(opt) + _sizing(opt) + _agent(agents) + _judge(agents)
    return "\n".join(lines).rstrip() + "\n"


def write_report(results_dir: Path = RESULTS_DIR) -> Path:
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "RESULTS.md"
    path.write_text(build_report(results_dir), encoding="utf-8")
    return path
