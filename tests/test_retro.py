import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

from factory import ledger, retro
from factory.evals import graders
from factory.evals.runner import Trial
from factory.evals.suite import Task

ROOT = Path(__file__).resolve().parents[1]
WEEK = ROOT / "agents" / "retro" / "evals" / "fixtures" / "week-1"
REFERENCE = ROOT / "agents" / "retro" / "evals" / "fixtures" / "reference-retro.jsonl"
KEY = yaml.safe_load((ROOT / "agents" / "retro" / "evals" / "fixtures" / "key.yaml").read_text(encoding="utf-8"))


# What code observes in a week of runs -------------------------------------------------------------------

def test_the_week_shows_the_recurring_failure_and_the_overrides():
    s = retro.week_stats(WEEK)
    recurring = {(p["agent"], p["check"]): p for p in s["recurring"]}
    assert recurring[("signal", "numbers")]["runs"] == 3
    assert ("bet", "quotes") not in recurring  # once is not a pattern
    assert s["overrides"] == 2 and s["mean_brier"] == pytest.approx(0.04)
    assert s["slowest_station"] == "sense"


def test_retro_reads_instructions_but_never_evals_or_answer_keys():
    assert "decision packet" in retro.read_skill("signal", "SKILL.md")
    for agent, name in (("signal", "evals/suite.yaml"), ("..", "sandbox/scenarios/s01-calendar-gate/truth.yaml"), ("signal", "../../factory/review.py")):
        with pytest.raises(ValueError):
            retro.read_skill(agent, name)


# Applying a patch, only once the PM approves -------------------------------------------------------------

def patch(**over):
    p = next(r for r in map(json.loads, REFERENCE.read_text(encoding="utf-8").splitlines()) if r["type"] == "patch")["payload"]
    return {**copy.deepcopy(p), **over}


@pytest.fixture
def agents_copy(tmp_path):
    shutil.copytree(ROOT / "agents" / "signal", tmp_path / "signal")
    return tmp_path


def test_an_approved_patch_edits_the_skill_and_adds_its_eval_case(agents_copy):
    p = patch()
    before = (agents_copy / "signal" / p["file"]).read_text(encoding="utf-8")
    retro.apply_patch(p, agents_root=agents_copy)
    after = (agents_copy / "signal" / p["file"]).read_text(encoding="utf-8")
    assert before.count(p["old"]) == 1 and after == before.replace(p["old"], p["new"])
    suite = yaml.safe_load((agents_copy / "signal" / "evals" / "suite.yaml").read_text(encoding="utf-8"))
    assert suite["tasks"][-1]["id"] == p["eval_case"]["id"]


@pytest.mark.parametrize("over, reason", [({"old": "text that is not in the file"}, "exactly once"),
                                          ({"agent": "..", "file": "factory/review.py"}, "instructions"),
                                          ({"file": "evals/suite.yaml"}, "instructions")])
def test_a_patch_that_cannot_apply_cleanly_is_refused(agents_copy, over, reason):
    with pytest.raises(ValueError, match=reason):
        retro.apply_patch(patch(**over), agents_root=agents_copy)


def test_agents_can_only_propose_patches(tmp_path, monkeypatch, now_run):
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_AGENT", "retro")
    from factory.servers import ledger_server
    assert ledger_server.write_entry("patch", {**patch(), "status": "approved"})["status"] == "rejection"
    assert ledger_server.write_entry("patch", patch())["status"] == "value"


# The graders ------------------------------------------------------------------------------------------------

def retro_trial(tmp_path, mutate=None):
    shutil.copytree(WEEK, tmp_path / "week")
    rows = [json.loads(l) for l in REFERENCE.read_text(encoding="utf-8").splitlines()]
    if mutate:
        mutate(rows)
    t = Trial(Task("t", "capability", "s01-calendar-gate", 1, "", []), 0, tmp_path)
    t.ledger_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return t


def retro_failures(t):
    return [n for g in ("retro_note", "retro_patch") for n, ok, _ in graders.CODE[g](t, {}, {"key": KEY}) if not ok]


def test_the_reference_retro_passes(tmp_path):
    assert ledger.validate_file(REFERENCE) == []
    assert retro_failures(retro_trial(tmp_path)) == []


def test_a_patch_to_the_wrong_agent_fails(tmp_path):
    def plant(rows):
        next(r for r in rows if r["type"] == "patch")["payload"]["agent"] = "bet"
    assert "the patch targets the agent behind the recurring failure" in retro_failures(retro_trial(tmp_path, plant))


def test_a_note_with_a_made_up_number_fails(tmp_path):
    def plant(rows):
        next(r for r in rows if r["type"] == "retro")["payload"]["lines"][0] = "Calibration: Brier 0.11 on 2 bets."
    assert "every number in the note comes from the week's stats" in retro_failures(retro_trial(tmp_path, plant))


def test_numbers_retro_may_cite_include_confidences_and_the_findings():
    pool = retro.stats_numbers(retro.week_stats(WEEK))
    assert {0.8, 7.0, 11.0, 0.04, 3.0, 4.0} <= pool


@pytest.fixture
def retro_ledger(tmp_path, monkeypatch, now_run):
    shutil.copytree(WEEK, tmp_path / "week")
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_WEEK", str(tmp_path / "week"))
    monkeypatch.setenv("FACTORY_AGENT", "retro")
    from factory.servers import ledger_server
    return ledger_server


def test_the_ledger_bounces_a_ratio_retro_worked_out(retro_ledger):
    note = next(r for r in map(json.loads, REFERENCE.read_text(encoding="utf-8").splitlines()) if r["type"] == "retro")["payload"]
    bad = {**note, "patches": [], "lines": note["lines"][:-1] + ["Sense took 1.5x as long as build."]}
    result = retro_ledger.write_entry("retro", bad)
    assert result["status"] == "rejection" and "1.5" in result["message"]


def test_the_ledger_names_the_real_graders_when_a_patch_invents_one(retro_ledger):
    bad = patch()
    bad["eval_case"]["graders"] = ["numbers"]
    result = retro_ledger.write_entry("patch", bad)
    assert result["status"] == "rejection" and "passes_quality_checks" in result["message"]


def test_retro_can_see_each_agents_grader_names():
    from factory.servers import retro_server
    agents = retro_server.list_skills()["agents"]
    assert "passes_quality_checks" in agents["signal"]["graders"] and "SKILL.md" in agents["signal"]["files"]
