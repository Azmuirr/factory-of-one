"""'Your week away': a decision queued Monday plays out Tuesday to Friday with nobody at the keyboard, then the PM
returns and decides. Content-quality is spot-checked on a live run; these tests cover the mechanism."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from factory import ledger
from factory.loop.gates import Gates
from factory.loop.__main__ import Loop
from sandbox.generator.run import generate

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ledger" / "examples" / "s01-happy-path.jsonl"
AWAY = ROOT / "agents" / "chief" / "evals" / "fixtures" / "reference-away.jsonl"
STATUS = ROOT / "agents" / "comms" / "evals" / "fixtures" / "reference-status.jsonl"
GATES = yaml.safe_load((ROOT / "tests" / "fixtures" / "s01-gates.yaml").read_text(encoding="utf-8"))
DAYS = (("tuesday", 57), ("wednesday", 58), ("thursday", 59), ("friday", 60))


# The generator: a "now" snapshot for any day, not just the scenario's own ---------------------------------

def test_now_day_overrides_the_scenarios_own_cutoff(tmp_path):
    mon = generate("s01-calendar-gate", seed=1, out=tmp_path / "mon")  # the scenario's own now (Monday)
    tue = generate("s01-calendar-gate", seed=1, through="now", now_day=57, out=tmp_path / "tue")
    assert json.loads((mon / "manifest.json").read_text())["cutoff"] < json.loads((tue / "manifest.json").read_text())["cutoff"]


def test_a_later_now_day_reveals_mail_the_earlier_one_did_not(tmp_path):
    from factory.workplace import Workplace
    tue = generate("s01-calendar-gate", seed=1, through="now", now_day=57, out=tmp_path / "tue")
    with Workplace(tue / "world" / "world.db") as wp:
        ids = {m["id"] for m in wp.mail_list()}
    assert "m_014" in ids and "m_001" in ids  # Monday's mail is still visible Tuesday


# The week, run end to end from a fixture (free; live content is spot-checked separately) -------------------

DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday")


@pytest.fixture(scope="module")
def week_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("week") / "run"
    loop = Loop("s01-calendar-gate", 1, out, Gates(GATES), FIXTURE)
    summary = loop.away_week(chief_fixtures={d: AWAY for d in DAY_NAMES}, comms_fixtures={d: STATUS for d in DAY_NAMES})
    return out, summary


def test_the_world_advances_a_day_at_a_time_all_week(week_run):
    out, _ = week_run
    import sqlite3
    # Friday's snapshot, just before the decision was applied and the world jumped to the end of the scenario.
    conn = sqlite3.connect(out / "world-before" / "world.db")
    through = conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0]
    conn.close()
    assert through.startswith("2026-03-07")  # Friday day 60 + 1 day


def test_chief_and_bet_and_comms_run_every_day_signal_only_monday(week_run):
    out, _ = week_run
    entries = ledger.read(out / "ledger.jsonl")
    assert len(entries) > 0 and ledger.validate_file(out / "ledger.jsonl") == []
    assert len([e for e in entries if e["type"] == "brief"]) == 5  # Mon-Fri
    assert len([e for e in entries if e["type"] == "candidates"]) == 5
    assert len([e for e in entries if e["type"] == "readout" and e["payload"]["moment"] == "status"]) == 5
    assert len([e for e in entries if e["type"] == "signal_card"]) == 1  # weekly cadence, not daily


def test_the_pm_resumes_friday_and_a_normal_decision_follows(week_run):
    out, summary = week_run
    types = [e["type"] for e in ledger.read(out / "ledger.jsonl")]
    assert "bet" in types and "verdict" in types and "call" in types
    # Deciding Friday instead of Monday shortens the post-action window, so a Monday-tuned scripted prediction
    # need not land; the mechanism only needs a verdict to be computed at all.
    assert summary["prediction_hit"] is not None and summary["brier"] is not None


def test_the_decided_readout_is_told_after_friday(week_run):
    out, _ = week_run
    entries = ledger.read(out / "ledger.jsonl")
    decided = [e for e in entries if e["type"] == "readout" and e["payload"]["moment"] == "decision"]
    assert decided and any(e["type"] == "action" and e["payload"]["status"] == "applied" for e in entries)


def test_retro_can_read_the_whole_weeks_run_folder(tmp_path, week_run):
    from factory import retro
    out, _ = week_run
    stats = retro.week_stats(out.parent)  # the week's single run folder, as Retro would be pointed at it
    assert stats["runs"] >= 1


# The CLI: python -m factory.autopilot --week -------------------------------------------------------------

def test_the_week_cli_produces_a_digest_with_fridays_outcome(tmp_path):
    from factory.autopilot.__main__ import run_week
    STATUS = ROOT / "agents" / "comms" / "evals" / "fixtures" / "reference-status.jsonl"
    days = ("monday", "tuesday", "wednesday", "thursday", "friday")
    out = tmp_path / "cli-week"
    text = run_week("s01-calendar-gate", 1, out, gates=GATES, fixture=FIXTURE,
                    chief_fixtures={d: AWAY for d in days}, comms_fixtures={d: STATUS for d in days})
    assert (out / "digest.md").read_text(encoding="utf-8") == text
    assert "Friday: back at the keyboard" in text and "Decided:" in text


# The week page's data builder ------------------------------------------------------------------------

def test_the_week_page_data_has_one_card_per_day_and_how_it_ended(tmp_path, week_run):
    from factory.replay.week import build
    out, _ = week_run
    week = build(out, tmp_path / "site" / "data")
    assert len(week["days"]) == 5 and [d["weekday"] for d in week["days"]] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    assert all(d["top_bet"] and d["status"] for d in week["days"])
    assert week["call"]["decision"] and week["verdict"]["outcome"]
    assert (tmp_path / "site" / "data" / "week.js").read_text(encoding="utf-8").startswith("window.WEEK = ")


def test_ledger_entries_are_dated_the_day_theyre_written_not_a_day_later(week_run):
    """A latent off-by-one: sim_now() during a multi-day run reports the cutoff, one day past the label on the
    prompt and on the workplace content just revealed. Chief's, Bet's, and Comms' entries must carry the label."""
    out, _ = week_run
    entries = ledger.read(out / "ledger.jsonl")
    dates = sorted({e["ts"][:10] for e in entries if e["type"] in ("brief", "candidates") and e["author"]["kind"] == "agent"})
    assert dates == ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"]


# The label reaches live agent writes too (not just fixtures) --------------------------------------------

def test_the_ledger_server_stamps_with_the_label_when_one_is_given(tmp_path, monkeypatch, now_run):
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_AGENT", "chief")
    from factory.servers import ledger_server
    without = ledger_server.sim_now()
    monkeypatch.setenv("FACTORY_LABEL", "2026-03-03")
    with_label = ledger_server.sim_now()
    assert with_label == "2026-03-03T12:00:00Z" and with_label != without


def test_run_agent_passes_todays_label_to_the_server_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_BIN", "claude")
    from factory.loop.__main__ import Loop
    from factory.loop.gates import Gates
    loop = Loop("s01-calendar-gate", 1, tmp_path, Gates({}), None)
    loop.label = "2026-03-03"
    calls = []

    def fake_run_claude(agent, trial):
        calls.append(trial.task.env)
        trial.dir.mkdir(parents=True, exist_ok=True)
        (trial.dir / "transcript.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr("factory.loop.__main__.run_claude", fake_run_claude)
    loop.run_agent("chief", "away-monday-s01", "brief")
    assert calls == [{"FACTORY_LABEL": "2026-03-03"}]


# Quality never re-reviews a stale candidates list against a later day's world --------------------------

def test_frame_does_not_re_review_yesterdays_list_if_bet_writes_nothing_new(tmp_path, monkeypatch, now_run):
    import shutil

    from factory.loop.gates import Gates

    out = tmp_path / "run"
    (out / "world").mkdir(parents=True)
    shutil.copy(now_run / "world" / "world.db", out / "world" / "world.db")
    loop = Loop("s01-calendar-gate", 1, out, Gates({}), FIXTURE)
    loop.ledger.touch()
    loop.load_fixture(lambda row: row["type"] in ("signal_card", "decision_packet"))  # pkt_0001, so candidates' refs resolve
    loop.frame()  # writes cnd_0001 and reviews it, from the fixture
    reviews_after_first = len(ledger.read(loop.ledger))
    monkeypatch.setattr(loop, "run_agent", lambda *a, **k: None)  # a live agent that writes nothing this time
    loop.fixture = None  # force the "live agent" path, which our stub leaves empty
    loop.frame()
    entries = ledger.read(loop.ledger)
    assert len(entries) == reviews_after_first  # no second review of the same stale entry
    assert any(t["event"] == "bet wrote nothing new today" for t in loop.trace)
