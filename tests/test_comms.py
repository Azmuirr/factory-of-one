import copy
import json
import shutil
from pathlib import Path

import pytest

from factory import comms, ledger, policy
from factory.evals import graders
from factory.evals.runner import Trial
from factory.evals.suite import Task

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "agents" / "comms" / "evals" / "fixtures"
STATUS = FIXTURES / "reference-status.jsonl"
DECIDED = FIXTURES / "reference-decided.jsonl"
RIGHTS = policy.load(ROOT / "company" / "tallybird" / "decision_rights.yaml")
KEY = graders.truth("s01-calendar-gate")


def rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def readout(entries):
    return next(e for e in reversed(entries) if e["type"] == "readout")


@pytest.fixture
def world(now_run):
    return now_run / "world" / "world.db"


# Code owns the numbers and the sending ------------------------------------------------------------

def test_the_references_are_valid_and_every_number_matches_the_ledger():
    for path in (STATUS, DECIDED):
        assert ledger.validate_file(path) == []
        entries = rows(path)
        assert comms.number_problems(readout(entries)["payload"], entries) == []


def test_a_number_that_is_not_in_the_ledger_fails():
    entries = rows(STATUS)
    r = copy.deepcopy(readout(entries))
    r["payload"]["versions"][0]["text"] = r["payload"]["versions"][0]["text"].replace("25,562", "31,000")
    assert any("31000" in p for p in comms.number_problems(r["payload"], entries))


def test_times_and_weekdays_are_not_data():
    from factory import numbers as nums
    assert nums.text_numbers("Reply by 10:00 or at 11:30 on Tuesday.") == []


def test_while_away_team_and_manager_versions_go_and_the_rest_is_held(world):
    entries = rows(STATUS)
    results = comms.deliver(readout(entries), entries, world, RIGHTS, approved_by_pm=False)
    sent = {r["audience"] for r in results if r["sent"]}
    held = {r["audience"] for r in results if not r["sent"]}
    assert sent == {"manager", "team"} and held == {"peers", "customer"}


def test_an_internal_update_addressed_to_someone_outside_is_held(world):
    entries = rows(STATUS)
    r = copy.deepcopy(readout(entries))
    next(v for v in r["payload"]["versions"] if v["audience"] == "team")["to"].append("p_cust")
    results = comms.deliver(r, entries, world, RIGHTS, approved_by_pm=False)
    team = next(x for x in results if x["audience"] == "team")
    assert not team["sent"] and "outside the company" in team["reason"]


def test_the_pm_can_approve_everything_but_numbers_must_still_match(world):
    entries = rows(DECIDED)
    results = comms.deliver(readout(entries), entries, world, RIGHTS, approved_by_pm=True)
    assert all(r["sent"] for r in results)
    r = copy.deepcopy(readout(entries))
    r["payload"]["versions"][0]["text"] += " We saved $2,000,000."
    assert not comms.deliver(r, entries, world, RIGHTS, approved_by_pm=True)[0]["sent"]


def test_the_ledger_bounces_a_readout_with_a_number_it_cannot_trace(tmp_path, monkeypatch, world):
    entries = rows(STATUS)
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries if e["type"] != "readout"), encoding="utf-8")
    monkeypatch.setenv("FACTORY_WORLD", str(world))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_AGENT", "comms")
    from factory.servers import ledger_server
    bad = copy.deepcopy(readout(entries)["payload"])
    bad["versions"][0]["text"] += " About 400 accounts are affected."
    assert ledger_server.write_entry("readout", bad)["status"] == "rejection"
    assert ledger_server.write_entry("readout", readout(entries)["payload"])["status"] == "value"


# The graders ---------------------------------------------------------------------------------------------

def comms_trial(tmp_path, now_run, path, mutate=None):
    (tmp_path / "world").mkdir()
    shutil.copy(now_run / "world" / "world.db", tmp_path / "world" / "world.db")
    entries = rows(path)
    if mutate:
        mutate(readout(entries)["payload"])
    t = Trial(Task("t", "capability", "s01-calendar-gate", 1, "", []), 0, tmp_path)
    t.ledger_path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return t


def failed(t, away):
    names = [("comms_versions", {}), ("comms_numbers_match", {}), ("comms_delivery", {"away": away}), ("comms_in_voice", {})]
    return [n for g, p in names for n, ok, _ in graders.CODE[g](t, KEY, p) if not ok]


@pytest.mark.parametrize("path, away", [(STATUS, True), (DECIDED, False)])
def test_the_reference_readouts_pass(tmp_path, now_run, path, away):
    assert failed(comms_trial(tmp_path, now_run, path), away) == []


def test_burying_the_news_fails(tmp_path, now_run):
    def plant(p):
        v = next(v for v in p["versions"] if v["audience"] == "manager")
        v["text"] = "Dana, hope your week is off to a good start. " + v["text"]
    assert "the manager hears the news first, with the number" in failed(comms_trial(tmp_path, now_run, STATUS, plant), True)


def test_a_customer_note_with_internal_numbers_fails(tmp_path, now_run):
    def plant(p):
        v = next(v for v in p["versions"] if v["audience"] == "customer")
        v["text"] = v["text"].replace("Thanks, S.", "We're losing $25,562 a week on this. Thanks, S.")
    assert "no internal numbers go to a customer" in failed(comms_trial(tmp_path, now_run, STATUS, plant), True)


def test_the_ledger_asks_for_directory_ids_not_names(tmp_path, monkeypatch, world):
    entries = rows(STATUS)
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries if e["type"] != "readout"), encoding="utf-8")
    monkeypatch.setenv("FACTORY_WORLD", str(world))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_AGENT", "comms")
    from factory.servers import ledger_server
    bad = copy.deepcopy(readout(entries)["payload"])
    bad["versions"][0]["to"] = ["Dana Okafor"]
    result = ledger_server.write_entry("readout", bad)
    assert result["status"] == "rejection" and "directory" in result["message"]
