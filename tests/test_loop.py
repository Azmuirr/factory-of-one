import json
from pathlib import Path

import pytest
import yaml

from factory import ledger
from factory.loop.__main__ import Loop
from factory.loop.gates import Gates

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ledger" / "examples" / "s01-happy-path.jsonl"
GATES = yaml.safe_load((ROOT / "tests" / "fixtures" / "s01-gates.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loop_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("loop") / "run"
    summary = Loop("s01-calendar-gate", 1, out, Gates(GATES), FIXTURE).run()
    return out, summary


def test_the_loop_writes_every_artifact_in_order(loop_run):
    out, _ = loop_run
    types = [e["type"] for e in ledger.read(out / "ledger.jsonl")]
    assert types == ["signal_card", "decision_packet", "bet", "action", "build", "action", "action", "verdict", "call"]
    assert ledger.validate_file(out / "ledger.jsonl") == []


def test_the_bet_and_the_call_are_human(loop_run):
    out, _ = loop_run
    for e in ledger.read(out / "ledger.jsonl"):
        if e["type"] in ("bet", "call"):
            assert e["author"]["kind"] == "human"


def test_the_world_reacts_and_the_verdict_is_computed(loop_run):
    out, summary = loop_run
    verdict = next(e for e in ledger.read(out / "ledger.jsonl") if e["type"] == "verdict")["payload"]
    assert verdict["outcome"] == "improved"
    assert verdict["after"] == pytest.approx(0.39, abs=0.03)
    assert summary["prediction_hit"] is True
    assert summary["brier"] == pytest.approx(0.04)


def test_the_trace_records_every_station_and_the_pm_cost(loop_run):
    out, summary = loop_run
    stations = [t["station"] for t in map(json.loads, (out / "trace.jsonl").read_text(encoding="utf-8").splitlines())]
    for station in ("sense", "decide", "build", "apply", "prove", "call", "tell", "learn"):
        assert station in stations
    assert [g["gate"] for g in summary["gates"]] == ["decide", "call"]
    assert summary["pm_minutes"] > 0
