"""crew-eval {optimiser, agent, report}."""

from __future__ import annotations

import argparse
from pathlib import Path

from crew_roster.eval.agent_eval import model_slug, run_agent_eval
from crew_roster.eval.optimiser import RESULTS_DIR, run_optimiser_eval
from crew_roster.eval.report import write_report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crew-eval", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    o = sub.add_parser("optimiser", help="CP-SAT vs greedy vs scratch benchmark + crew sizing "
                                         "(no LLM; roughly 25 min)")
    o.add_argument("--n", type=int, default=50, help="number of scenarios")
    o.add_argument("--time-limit", type=float, default=10.0, help="CP-SAT seconds per solve")

    a = sub.add_parser("agent", help="run the agent over the eval dataset (needs GROQ_API_KEY)")
    a.add_argument("--model", default="openai/gpt-oss-120b", help="Groq model, no fallback")
    a.add_argument("--limit", type=int, default=None, help="only the first N cases")
    a.add_argument("--judge", action="store_true",
                   help="score explanations with Claude (needs ANTHROPIC_API_KEY; costs cents)")
    a.add_argument("--rejudge", action="store_true",
                   help="with --judge: score items again even if they already have a score")
    a.add_argument("--langsmith", action="store_true",
                   help="log the run as a LangSmith experiment (needs LANGSMITH_API_KEY)")

    sub.add_parser("report", help="write docs/results/RESULTS.md from the JSON results")
    for p in sub.choices.values():
        p.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    out_dir: Path = args.results_dir

    if args.cmd == "optimiser":
        run_optimiser_eval(n=args.n, time_limit=args.time_limit, out=out_dir / "optimiser.json")
    elif args.cmd == "agent":
        run_agent_eval(args.model, out=out_dir / f"agent-{model_slug(args.model)}.json",
                       limit=args.limit, judge=args.judge, rejudge=args.rejudge,
                       langsmith=args.langsmith)
    if args.cmd == "report" or (out_dir / "optimiser.json").exists():
        print(f"wrote {write_report(out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
