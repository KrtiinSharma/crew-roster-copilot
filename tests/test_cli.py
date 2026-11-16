from crew_roster import cli
from crew_roster.roster import cache
from crew_roster.roster.solver import SolveResult


def test_save_refused_when_uncovered(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    real = cli.solve

    def fake(problem, **kw):
        r = real(problem, **kw)
        return SolveResult(**{**r.model_dump(), "uncovered": [("X", "CPT")]})

    monkeypatch.setattr(cli, "solve", fake)
    assert cli.main(["--save"]) == 1
    assert not list(tmp_path.iterdir())
    assert "refus" in capsys.readouterr().out
