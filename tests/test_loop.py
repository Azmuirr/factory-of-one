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
    assert types == ["signal_card", "decision_packet", "review", "bet", "action", "build", "review", "action", "action", "verdict", "call"]
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


def test_code_signs_what_code_wrote(loop_run):
    out, _ = loop_run
    entries = ledger.read(out / "ledger.jsonl")
    assert next(e for e in entries if e["type"] == "verdict")["author"] == {"kind": "code", "name": "verdict"}
    for e in entries:
        if e["type"] == "action" and e["payload"]["status"] in ("approved", "applied"):
            assert e["author"] == {"kind": "code", "name": "loop"}
        if e["type"] == "review":
            assert e["author"]["kind"] == "code"  # fixture mode runs Quality's code checks, not the agent
    assert not [e for e in entries if e["author"]["name"] == "chief"]  # Chief is not in the loop


def test_a_scripted_run_never_waits_at_the_keyboard(monkeypatch):
    def no_keyboard(prompt=""):
        raise AssertionError("a scripted run asked the keyboard")
    monkeypatch.setattr("builtins.input", no_keyboard)
    answers = Gates({"decide": {"approve": "yes"}}).ask("confirm", "Apply anyway?", [("apply", "Apply? (yes/no)", "no")])
    assert answers == {"apply": "no"}  # an unscripted gate takes its safe default


def test_the_world_before_the_action_is_kept_so_earlier_artifacts_stay_checkable(loop_run):
    import sqlite3
    out, _ = loop_run
    def data_through(path):
        conn = sqlite3.connect(path)
        value = conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0]
        conn.close()
        return value
    assert data_through(out / "world-before" / "world.db") < data_through(out / "world" / "world.db")
