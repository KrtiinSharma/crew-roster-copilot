import pytest

from crew_roster.data import generate


@pytest.fixture(scope="session")
def airline():
    return generate()
