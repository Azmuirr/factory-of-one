import json
from pathlib import Path

import pytest
import yaml

from factory.loop.__main__ import Loop
from factory.loop.gates import Gates
from factory.replay.__main__ import build

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ledger" / "examples" / "s01-happy-path.jsonl"
GATES = yaml.safe_load((ROOT / "tests" / "fixtures" / "s01-gates.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    run_dir = tmp_path_factory.mktemp("loop") / "run"
    Loop("s01-calendar-gate", 1, run_dir, Gates(GATES), FIXTURE).run()
    out = tmp_path_factory.mktemp("site")
    return build(run_dir, None, out), out


def test_both_worlds_match_until_the_decision_and_split_after(site):
    run, _ = site
    week = run["weeks"].index(run["today"])
    with_action, no_action = run["series"]["with_action"]["microsoft"], run["series"]["no_action"]["microsoft"]
    assert with_action[:week] == no_action[:week]
    assert with_action[week] == run["verdict"]["payload"]["after"]
    assert with_action[week] > no_action[week] + 0.05


def test_the_site_ships_its_data_and_every_build_it_links(site):
    run, out = site
    assert (out / "data" / "run.js").read_text(encoding="utf-8").startswith("window.RUN = ")
    for b in run["builds"]:
        assert (out / b["path"]).is_file(), b
    assert json.loads((out / "data" / "run.json").read_text(encoding="utf-8"))["summary"]["prediction_hit"] is True
    assert run["live_runs"] and all(set(r) == {"date", "run", "result", "found"} for r in run["live_runs"])
