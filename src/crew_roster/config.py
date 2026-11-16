"""Runtime settings from environment variables or a local .env file (never commit .env)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    groq_api_key: str = ""
    answer_model: str = "openai/gpt-oss-120b"
    fast_model: str = "openai/gpt-oss-20b"
    llm_explanations: bool = True

    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "crew-roster-copilot"

    anthropic_api_key: str = ""  # only for the optional eval judge (crew-eval agent --judge)
    judge_model: str = "claude-haiku-5-5"

    allowed_origins: str = "http://localhost:5173"
    rate_limit_per_minute: int = 10
    solve_time_limit: float = 10.0

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.langsmith_tracing and s.langsmith_api_key:  # langchain reads these from the environment
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", s.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", s.langsmith_project)
    return s
