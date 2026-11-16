import json

import pytest

from crew_roster.eval import optimiser
from crew_roster.eval.optimiser import ROW_KEYS, run_benchmark, run_optimiser_eval, summarise
from crew_roster.eval.scenarios import make_scenarios


def small(k=2):
    return [s for s in make_scenarios() if s.size == "small"][:k]


def test_benchmark_rows_have_the_right_keys():
    rows = run_benchmark(small(), methods=("cpsat", "greedy"), time_limit=5)
    assert len(rows) == 4
    assert [(r["scenario"], r["method"]) for r in rows][:2] == [(small()[0].id, "cpsat"),
                                                                (small()[0].id, "greedy")]
    for r in rows:
        assert set(ROW_KEYS) <= set(r)
        assert r["size"] == "small"
    assert all(r["breaches"] == 0 for r in rows if r["method"] == "cpsat")


def row(scenario, size, method, changes, uncrewed, seconds, breaches=0):
    return {"scenario": scenario, "size": size, "method": method, "changes": changes,
            "uncrewed": uncrewed, "seconds": seconds, "breaches": breaches, "status": "X"}


def test_summarise_means_medians_and_wins():
    rows = [
        row("S00", "small", "cpsat", 1, 0, 1.0), row("S00", "small", "scratch", 9, 0, 3.0),
        row("S00", "small", "greedy", 1, 2, 0.1),
        row("S01", "large", "cpsat", 4, 1, 5.0), row("S01", "large", "scratch", 4, 0, 6.0),
        row("S01", "large", "greedy", 3, 1, 0.1, breaches=2),
        row("S02", "large", "cpsat", 6, 0, 7.0), row("S02", "large", "scratch", 30, 0, 8.0),
        row("S02", "large", "greedy", 5, 3, 0.2),
    ]
    s = summarise(rows)
    cp = s["methods"]["cpsat"]
    assert cp["all"]["n"] == 3
    assert cp["all"]["changes"] == {"mean": pytest.approx(11 / 3, abs=0.01), "median": 4}
    assert cp["large"]["seconds"]["mean"] == 6.0 and cp["small"]["uncrewed"]["median"] == 0
    assert s["methods"]["greedy"]["breaches"] == 2 and s["methods"]["cpsat"]["breaches"] == 0
    assert s["wins"]["cpsat_fewer_changes_than_scratch"] == {"wins": 2, "of": 3}
    assert s["wins"]["cpsat_fewer_uncrewed_than_greedy"] == {"wins": 2, "of": 3}


def test_resume_skips_rows_already_in_the_file(tmp_path, monkeypatch):
    sc = make_scenarios(n=2)
    out = tmp_path / "optimiser.json"
    calls = []
    real = optimiser.replan

    def counting(problem, base, disruptions, method="cpsat", time_limit=10.0):
        calls.append(method)
        return real(problem, base, disruptions, method=method, time_limit=time_limit)

    monkeypatch.setattr(optimiser, "replan", counting)
    monkeypatch.setattr(optimiser, "sizing_table", lambda time_limit=15.0: [])
    first = row(sc[0].id, sc[0].size, "greedy", 123, 0, 0.0)
    config = {"n": 2, "seed": 11, "ruleset": "dgca_current", "time_limit": 5.0,
              "methods": ["greedy"]}
    out.write_text(json.dumps({"config": config, "rows": [first]}), encoding="utf-8")

    data = run_optimiser_eval(n=2, time_limit=5.0, out=out, methods=("greedy",))
    assert calls == ["greedy"]  # only the second scenario was run
    assert data["rows"][0]["changes"] == 123  # the stored row was kept, not recomputed
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert [r["scenario"] for r in saved["rows"]] == [sc[0].id, sc[1].id]
    assert set(saved) == {"config", "rows", "summary", "sizing"}

    calls.clear()
    run_optimiser_eval(n=2, time_limit=5.0, out=out, methods=("greedy",))
    assert calls == []


@pytest.mark.slow
def test_sizing_table_covers_both_bases_and_rulesets():
    table = optimiser.sizing_table(time_limit=15.0)
    assert {(r["base"], r["ruleset"]) for r in table} == {
        (b, rs) for b in ("DEL", "BOM") for rs in ("dgca_current", "dgca_dec2025_exemption")}
    for r in table:
        assert r["feasible"] and set(r["pilots_needed"]) == {"CPT", "FO"}
