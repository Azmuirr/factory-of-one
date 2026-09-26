import sqlite3
from pathlib import Path

import pytest

from sandbox.generator import generate
from sandbox.generator.text import variants

SCENARIO = "s01-calendar-gate"
ROLLBACK = Path(__file__).parent / "fixtures" / "s01-rollback-microsoft.yaml"
NOW_CUTOFF = "2026-03-02T00:00:00Z"  # end of week 8
RELEASE_DAY, LAST_MATURE_DAY, ROLLBACK_DAY = 36, 48, 56

ACTIVATION = """
SELECT w.calendar_provider AS provider,
  CAST(julianday(w.created_at) - julianday('2026-01-05') AS INT) AS day,
  EXISTS (
    SELECT 1 FROM events s JOIN events m
      ON m.workspace_id = s.workspace_id AND m.name = 'meeting_recorded'
     AND json_extract(m.props, '$.meeting_id') = json_extract(s.props, '$.meeting_id')
    WHERE s.workspace_id = w.workspace_id AND s.name = 'recap_shared'
      AND json_extract(m.props, '$.participants') >= 2
      AND json_extract(m.props, '$.duration_min') >= 5
      AND julianday(s.ts) <= julianday(w.created_at) + 7
  ) AS activated
FROM workspaces w
"""


def world_db(run: Path) -> sqlite3.Connection:
    return sqlite3.connect(run / "world" / "world.db")


def activation(run: Path, first_day: int, last_day: int, provider: str | None = None) -> float:
    sql = f"SELECT AVG(activated) FROM ({ACTIVATION}) WHERE day BETWEEN ? AND ?"
    params: list = [first_day, last_day]
    if provider:
        sql += " AND provider = ?"
        params.append(provider)
    return world_db(run).execute(sql, params).fetchone()[0]


def table(run: Path, name: str, where: str = "") -> list:
    return world_db(run).execute(f"SELECT * FROM {name} {where} ORDER BY 1, 2").fetchall()


@pytest.fixture(scope="session")
def end_run(tmp_path_factory):
    return generate(SCENARIO, seed=1, through="end", out=tmp_path_factory.mktemp("end"))


@pytest.fixture(scope="session")
def rollback_run(tmp_path_factory):
    return generate(SCENARIO, seed=1, actions_path=ROLLBACK, out=tmp_path_factory.mktemp("rollback"))


def test_same_seed_builds_the_same_world(now_run, tmp_path):
    again = generate(SCENARIO, seed=1, out=tmp_path)
    for name in ("workspaces", "events", "subscriptions", "tickets"):
        assert table(now_run, name) == table(again, name)


def test_agents_see_nothing_after_now(now_run):
    db = world_db(now_run)
    for name, column in (("workspaces", "created_at"), ("events", "ts"), ("subscriptions", "ts"), ("tickets", "created_at")):
        assert db.execute(f"SELECT MAX({column}) FROM {name}").fetchone()[0] < NOW_CUTOFF


def test_truth_stays_out_of_the_world(now_run):
    assert [p.name for p in (now_run / "world").iterdir()] == ["world.db"]
    db = world_db(now_run)
    columns = {row[1] for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
               for row in db.execute(f"PRAGMA table_info({t})")}
    assert not columns & {"p_base", "requires_admin_consent", "blocked_by", "releases_applied", "activated_at"}


def test_usage_and_tickets_share_workspace_ids(now_run):
    db = world_db(now_run)
    for name in ("events", "tickets", "subscriptions"):
        orphans = db.execute(f"SELECT COUNT(*) FROM {name} WHERE workspace_id NOT IN (SELECT workspace_id FROM workspaces)")
        assert orphans.fetchone()[0] == 0


def test_baseline_matches_spec(now_run):
    assert activation(now_run, 0, 34) == pytest.approx(0.40, abs=0.015)
    assert activation(now_run, 0, 34, "google") == pytest.approx(0.41, abs=0.02)
    assert activation(now_run, 0, 34, "microsoft") == pytest.approx(0.39, abs=0.02)
    paid = world_db(now_run).execute(
        "SELECT AVG(json_extract(props, '$.outcome') = 'paid') FROM events WHERE name = 'trial_ended'"
    ).fetchone()[0]
    assert paid == pytest.approx(0.11, abs=0.01)


def test_release_drops_microsoft_activation_only(now_run):
    assert activation(now_run, RELEASE_DAY, LAST_MATURE_DAY, "microsoft") == pytest.approx(0.30, abs=0.03)
    assert activation(now_run, RELEASE_DAY, LAST_MATURE_DAY, "google") == pytest.approx(0.41, abs=0.02)


def test_customers_report_the_problem(now_run):
    planted = {subject for subject, _ in variants("templates/tickets/calendar_admin_consent.txt")}
    rows = world_db(now_run).execute(
        "SELECT CAST((julianday(created_at) - julianday('2026-01-05')) / 7 AS INT) + 1, subject, workspace_id FROM tickets"
    ).fetchall()
    for week in (6, 7, 8):
        accounts = {ws for wk, subject, ws in rows if wk == week and subject in planted}
        assert len(accounts) >= 3
    assert not any(subject in planted for wk, subject, _ in rows if wk <= 5)


def test_rollback_restores_microsoft_activation(end_run, rollback_run):
    after = (ROLLBACK_DAY, ROLLBACK_DAY + 6)
    assert activation(rollback_run, *after, "microsoft") == pytest.approx(0.39, abs=0.035)
    assert activation(end_run, *after, "microsoft") == pytest.approx(0.30, abs=0.035)


def test_history_before_the_action_is_unchanged(end_run, rollback_run):
    before = "WHERE ts < '2026-03-02'"
    assert table(end_run, "events", before) == table(rollback_run, "events", before)
    assert table(rollback_run, "actions")[0][2] == "rollback"
