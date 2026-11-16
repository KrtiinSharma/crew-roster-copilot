import json

import pytest

from crew_roster.eval import cli
from crew_roster.eval.optimiser import summarise
from crew_roster.eval.report import build_report


def row(scenario, size, method, changes, uncrewed, seconds):
    return {"scenario": scenario, "size": size, "method": method, "changes": changes,
            "uncrewed": uncrewed, "seconds": seconds, "breaches": 0, "status": "OPTIMAL"}


ROWS = [row("S00", "small", "cpsat", 1, 0, 2.0), row("S00", "small", "greedy", 1, 0, 0.02),
        row("S00", "small", "scratch", 40, 0, 6.0), row("S01", "large", "cpsat", 7, 0, 8.0),
        row("S01", "large", "greedy", 5, 2, 0.03), row("S01", "large", "scratch", 190, 0, 10.0)]
SIZING = [{"base": b, "ruleset": rs,
           "duties": 50 if (b, rs) == ("BOM", "dgca_dec2025_exemption") else 63,
           "pilots_available": {"CPT": 20, "FO": 20},
           "pilots_needed": {"CPT": n, "FO": n + 1}, "uncovered": 0, "feasible": True,
           "proven_optimal": rs == "dgca_current", "seconds": 15.0}
          for b, n0 in (("DEL", 17), ("BOM", 16))
          for rs, n in (("dgca_current", n0), ("dgca_dec2025_exemption", n0 - 1))]


def write_optimiser(d):
    data = {"config": {"n": 2, "seed": 11, "ruleset": "dgca_current", "time_limit": 10.0,
                       "methods": ["cpsat", "greedy", "scratch"]},
            "rows": ROWS, "summary": summarise(ROWS), "sizing": SIZING}
    (d / "optimiser.json").write_text(json.dumps(data), encoding="utf-8")


def test_report_without_any_data_says_how_to_produce_it(tmp_path):
    md = build_report(tmp_path)
    assert "uv run crew-eval optimiser" in md and "uv run crew-eval agent" in md


def test_report_with_only_optimiser_data(tmp_path):
    write_optimiser(tmp_path)
    md = build_report(tmp_path)
    assert "| cpsat | small | 1 |" in md and "| scratch | large |" in md
    assert "2 of 2" in md  # cpsat fewer changes than scratch
    assert "1 of 2" in md  # cpsat fewer uncrewed than greedy
    assert "Total rule breaches" in md
    assert "greedy 2 (0)" in md  # uncrewed seats (of which on illegal duties)
    assert "| DEL | 17 / 18 | 16 / 17 |" in md
    assert "proven" in md and "upper bound" in md
    assert "| 63 / 63 |" in md and "| 63 / 50 |" in md  # duties per ruleset
    assert "fewer, longer BOM duties" in md
    assert "hit its time limit" in md and "0/2 runs" in md  # no scratch row is FEASIBLE
    assert ("In the 1 scenarios where CP-SAT crewed more seats than greedy, greedy made fewer "
            "changes than CP-SAT in 1") in md
    assert "deterministic time limit" in md and "15 s" not in md
    assert "timings vary by machine" in md
    assert "uv run crew-eval agent" in md  # agent section explains how to fill it
    assert "Claude judge" in md


def test_report_with_agent_and_judge_data(tmp_path):
    write_optimiser(tmp_path)
    agent = {"config": {"model": "openai/gpt-oss-120b", "n_cases": 2},
             "rows": [], "stopped": None,
             "summary": {"all": {"n": 2, "tool_ok": 1.0, "args_ok": 0.5, "numbers_recall": 0.75,
                                 "names_ok": 1.0, "grounded": 1.0, "n_tool_calls": 1.5,
                                 "seconds": 3.25},
                         "by_category": {"hours": {"n": 1, "tool_ok": 1.0, "args_ok": 1.0,
                                                   "numbers_recall": 0.5, "names_ok": None,
                                                   "grounded": 1.0, "n_tool_calls": 1.0,
                                                   "seconds": 2.0}}},
             "judge": {"model": "claude-haiku-5-5", "estimated_cost_usd": 0.002, "items": [],
                       "summary": {"replan": {"n": 10, "faithful": 4.6, "clear": 4.2}}}}
    (tmp_path / "agent-openai-gpt-oss-120b.json").write_text(json.dumps(agent), encoding="utf-8")
    md = build_report(tmp_path)
    assert "| openai/gpt-oss-120b | 2 | 100% | 50% | 75% | 100% | 1.5 | 3.2 |" in md
    assert "2 questions in 1 categories" in md and "About 36" not in md
    assert "| openai/gpt-oss-120b | hours | 1 |" in md
    assert "| openai/gpt-oss-120b | replan | 10 | 4.6 | 4.2 |" in md


def test_cli_report_writes_results_md(tmp_path, capsys):
    write_optimiser(tmp_path)
    assert cli.main(["report", "--results-dir", str(tmp_path)]) == 0
    assert (tmp_path / "RESULTS.md").read_text(encoding="utf-8").startswith("# ")
    assert "RESULTS.md" in capsys.readouterr().out


def test_cli_agent_arguments_reach_the_runner(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "run_agent_eval", lambda model, **kw: seen.update(model=model, **kw))
    cli.main(["agent", "--model", "openai/gpt-oss-20b", "--limit", "3", "--judge",
              "--results-dir", str(tmp_path)])
    assert seen["model"] == "openai/gpt-oss-20b" and seen["limit"] == 3 and seen["judge"]
    assert not seen["langsmith"]


def test_cli_rejects_unknown_command():
    with pytest.raises(SystemExit):
        cli.main(["bogus"])
