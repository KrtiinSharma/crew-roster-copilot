from crew_roster.config import ROOT, Settings


def test_defaults_without_env_file():
    s = Settings(_env_file=None)
    assert s.answer_model == "openai/gpt-oss-120b"
    assert s.fast_model == "openai/gpt-oss-20b"
    assert s.origins == ["http://localhost:5173"]
    assert s.rate_limit_per_minute == 10 and s.solve_time_limit == 10.0


def test_origins_are_split_and_trimmed():
    s = Settings(_env_file=None, allowed_origins=" https://a.github.io , http://localhost:5173 ,")
    assert s.origins == ["https://a.github.io", "http://localhost:5173"]


def test_env_example_lists_every_setting_with_empty_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0]
        for line in text.splitlines()
        if "=" in line and not line.startswith("#")
    }
    assert keys == {name.upper() for name in Settings.model_fields}
    for secret in ("GROQ_API_KEY", "LANGSMITH_API_KEY"):
        assert f"{secret}=\n" in text + "\n"
