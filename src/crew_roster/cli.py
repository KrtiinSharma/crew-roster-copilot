"""crew-solve: solve the base roster for a ruleset and optionally cache it."""

from __future__ import annotations

import argparse

from crew_roster.data import generate
from crew_roster.problem import build_problem
from crew_roster.roster.cache import cache_path
from crew_roster.roster.check import check
from crew_roster.roster.solver import solve
from crew_roster.rules import RULESETS, load


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crew-solve")
    ap.add_argument("--ruleset", default="dgca_current", choices=RULESETS)
    ap.add_argument("--time-limit", type=float, default=10.0)
    ap.add_argument("--save", action="store_true", help="write the roster to the package cache")
    args = ap.parse_args(argv)

    problem = build_problem(generate(), load(args.ruleset))
    res = solve(problem, time_limit=args.time_limit)
    violations = check(problem, res.roster)
    print(
        f"{args.ruleset}: {len(problem.duties)} duties, {len(res.uncovered)} uncovered slots, "
        f"{len(violations)} violations, {res.status}, {res.seconds}s, used {res.pilots_used}"
    )
    if args.save:
        path = cache_path(args.ruleset)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(res.roster.model_dump_json(indent=1), encoding="utf-8")
        print(f"saved {path}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
