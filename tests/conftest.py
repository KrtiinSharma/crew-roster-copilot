import pytest

from crew_roster.data import generate
from crew_roster.problem import build_problem
from crew_roster.roster.solver import solve
from crew_roster.rules import load


@pytest.fixture(scope="session")
def airline():
    return generate()


@pytest.fixture(scope="session")
def problem(airline):
    return build_problem(airline, load("dgca_current"))


@pytest.fixture(scope="session")
def base_result(problem):
    return solve(problem, time_limit=10)
