import os

import pytest

from crew_roster.config import get_settings
from crew_roster.data import generate
from crew_roster.problem import build_problem
from crew_roster.roster.solver import solve
from crew_roster.rules import load


@pytest.fixture(scope="session", autouse=True)
def no_tracing():
    """Never send LangSmith traces from tests, even if the developer's .env enables them."""
    os.environ["LANGSMITH_TRACING"] = "false"
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def airline():
    return generate()


@pytest.fixture(scope="session")
def problem(airline):
    return build_problem(airline, load("dgca_current"))


@pytest.fixture(scope="session")
def base_result(problem):
    return solve(problem, time_limit=10)
