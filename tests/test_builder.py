import json
import shutil
from pathlib import Path

import pytest
import yaml

from factory import demos, ledger
from factory.loop.__main__ import Loop
from factory.loop.gates import Gates

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "ledger" / "examples" / "demos" / "s01-consent-fallback" / "index.html"
EXAMPLE = ROOT / "ledger" / "examples" / "s01-happy-path.jsonl"
GATES = yaml.safe_load((ROOT / "tests" / "fixtures" / "s01-gates.yaml").read_text(encoding="utf-8"))

PAGE = """<!doctype html><html><body><main data-decision="pkt_0001" data-honesty="{honesty}">
<h1>Headline</h1>{extra}</main></body></html>"""


def page(tmp_path, honesty="hardcoded", extra="") -> Path:
    path = tmp_path / "index.html"
    path.write_text(PAGE.format(honesty=honesty, extra=extra), encoding="utf-8")
    return path


def test_the_reference_demo_passes():
    result = demos.check(REFERENCE)
    assert result["passed"], result["problems"]


def test_a_button_that_does_nothing_is_a_dead_click(tmp_path):
    result = demos.check(page(tmp_path, extra="<button>Approve</button>"))
    assert not result["passed"] and result["dead_clicks"] == 1


def test_a_missing_honesty_label_fails(tmp_path):
    assert "honesty label" in demos.check(page(tmp_path, honesty="probably"))["problems"][0]


def test_a_network_request_fails(tmp_path):
    result = demos.check(page(tmp_path, extra='<img src="https://example.com/x.png">'))
    assert any("network" in p for p in result["problems"])


def test_a_page_taller_than_one_screen_fails(tmp_path):
    result = demos.check(page(tmp_path, extra='<div style="height:2000px"></div>'))
    assert any("one screen" in p for p in result["problems"])


@pytest.fixture
def ledger_env(tmp_path, monkeypatch, now_run):
    (tmp_path / "demos").mkdir()
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_DEMOS", str(tmp_path / "demos"))
    monkeypatch.setenv("FACTORY_AGENT", "builder")
    from factory.servers import ledger_server
    return ledger_server, tmp_path


def test_the_ledger_rejects_an_action_on_a_release_that_does_not_exist(ledger_env):
    server, _ = ledger_env
    result = server.write_entry("action", {"name": "rollback", "params": {"release_id": "rel_9999"}, "status": "proposed"})
    assert result["status"] == "rejection" and "rel_9999" in result["message"]


def test_the_ledger_rejects_a_segment_value_that_does_not_exist(ledger_env):
    server, _ = ledger_env
    payload = {"name": "rollback", "params": {"release_id": "rel_0412", "segment": {"calendar_provider": ["yahoo"]}}, "status": "proposed"}
    assert server.write_entry("action", payload)["status"] == "rejection"


def test_the_ledger_rejects_a_build_whose_honesty_label_does_not_match(ledger_env):
    server, root = ledger_env
    shutil.copytree(REFERENCE.parent, root / "demos" / "s01-consent-fallback")
    payload = {"kind": "prototype", "location": "demos/s01-consent-fallback/index.html", "honesty_label": "live", "checks": {}}
    assert server.write_entry("build", payload)["status"] == "rejection"
    payload["honesty_label"] = "hardcoded"
    assert server.write_entry("build", payload)["status"] == "value"


def test_a_proposal_that_differs_from_the_decision_goes_to_the_pm(tmp_path):
    rows = [json.loads(l) for l in EXAMPLE.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["id"] == "act_0001":
            row["payload"]["params"]["segment"] = {}  # Builder widened the rollback to everyone
    fixture = tmp_path / "fixture" / "ledger.jsonl"
    fixture.parent.mkdir()
    fixture.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    shutil.copytree(REFERENCE.parent.parent, fixture.parent / "demos")
    gates = Gates({**GATES, "confirm": {"apply": "no"}})
    summary = Loop("s01-calendar-gate", 1, tmp_path / "run", gates, fixture).run()
    statuses = [e["payload"]["status"] for e in ledger.read(tmp_path / "run" / "ledger.jsonl") if e["type"] == "action"]
    assert statuses == ["proposed"]
    assert [g["gate"] for g in summary["gates"]] == ["decide", "confirm"]
