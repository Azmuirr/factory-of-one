import pytest

from sandbox.generator import generate

SCENARIO = "s01-calendar-gate"


@pytest.fixture(scope="session")
def now_run(tmp_path_factory):
    return generate(SCENARIO, seed=1, out=tmp_path_factory.mktemp("now"))
