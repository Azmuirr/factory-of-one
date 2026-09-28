import json
from pathlib import Path

import pytest

from factory import config as install
from factory import ledger, policy
from factory.evals.runner import Trial, build_command
from factory.evals.suite import Task, load_agent

ROOT = Path(__file__).resolve().parents[1]
RIGHTS = ROOT / "company" / "tallybird" / "decision_rights.yaml"
FIXTURE = ROOT / "ledger" / "examples" / "s01-happy-path.jsonl"
AWAY = ROOT / "agents" / "chief" / "evals" / "fixtures" / "reference-away.jsonl"


# Decision rights ---------------------------------------------------------------------------------

def test_while_away_every_action_waits_for_the_pm():
    rights = policy.load(RIGHTS)
    ok, reason = policy.may_apply(rights, {"name": "rollback", "params": {"release_id": "rel_0412"}})
    assert not ok and "waits for" in reason


def test_internal_updates_may_go_out_and_external_ones_wait():
    rights = policy.load(RIGHTS)
    assert policy.may_send(rights, "team")[0] and policy.may_send(rights, "manager")[0]
    assert not policy.may_send(rights, "customer")[0]
    assert not policy.may_send(rights, "someone_unknown")[0]  # anything not listed waits


def test_every_agent_is_told_the_decision_rights(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_BIN", "claude")
    trial = Trial(Task("t", "capability", "s01-calendar-gate", 1, "", []), 0, tmp_path)
    prompt = build_command(load_agent("signal"), trial, install.load(ROOT / "config" / "sandbox.yaml"))
    text = prompt[prompt.index("--system-prompt") + 1]
    assert "## Decision rights while the PM is away" in text and "prepare_only" in text


def test_agents_cannot_queue_decisions_only_the_autopilot_can(tmp_path, monkeypatch, now_run):
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    from factory.servers import ledger_server
    result = ledger_server.write_entry("queue", {"status": "waiting_for_pm", "packet": "pkt_0001", "reason": "x", "prepared": []})
    assert result["code"] == "type_not_allowed"


# The autopilot: a day with nobody at the keyboard --------------------------------------------------------

@pytest.fixture(scope="module")
def away_day(tmp_path_factory):
    from factory.autopilot.__main__ import run_day
    out = tmp_path_factory.mktemp("away") / "day"
    digest = run_day("s01-calendar-gate", 1, out, fixture=FIXTURE, chief_fixture=AWAY)
    return out, digest


def test_nothing_is_applied_while_the_pm_is_away(away_day):
    out, _ = away_day
    entries = ledger.read(out / "ledger.jsonl")
    assert not [e for e in entries if e["type"] in ("bet", "action", "verdict", "call")]
    queued = [e for e in entries if e["type"] == "queue"]
    assert queued and queued[0]["author"]["kind"] == "code" and queued[0]["payload"]["status"] == "waiting_for_pm"
    assert ledger.validate_file(out / "ledger.jsonl") == []


def test_urgent_items_reach_the_pm_and_nothing_else_is_sent(away_day):
    out, _ = away_day
    posts = [json.loads(l) for l in (out / "outbox.jsonl").read_text(encoding="utf-8").splitlines()]
    assert posts and all(p["to"] == "self" for p in posts)
    assert len(posts) <= policy.load(RIGHTS)["away"]["urgent"]["max_per_day"]


def test_the_digest_says_what_happened_and_what_waits(away_day):
    _, digest = away_day
    assert "Waiting for you" in digest and "Sent to you" in digest and "--resume" in digest


def test_back_at_the_keyboard_the_loop_resumes_at_the_decision(away_day, tmp_path):
    import shutil

    import yaml

    from factory.loop.__main__ import Loop
    from factory.loop.gates import Gates
    out, _ = away_day
    resumed = tmp_path / "resumed"
    shutil.copytree(out, resumed)
    gates = yaml.safe_load((ROOT / "tests" / "fixtures" / "s01-gates.yaml").read_text(encoding="utf-8"))
    summary = Loop("s01-calendar-gate", 1, resumed, Gates(gates), FIXTURE).resume()
    types = [e["type"] for e in ledger.read(resumed / "ledger.jsonl")]
    assert "bet" in types and "verdict" in types and summary["prediction_hit"] is True
