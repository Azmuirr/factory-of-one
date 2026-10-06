from pathlib import Path

import pytest

from sandbox.generator import generate
from tests.test_generator import ACTIVATION, table, world_db

SCENARIO = "s03-share-link-scanner"
ROLLBACK = Path(__file__).parent / "fixtures" / "s03-rollback-paid-search.yaml"
RELEASE_DAY, LAST_MATURE_DAY, ROLLBACK_DAY = 30, 48, 56


def activation(run: Path, first_day: int, last_day: int, channel: str | None = None) -> float:
    base = ACTIVATION.replace("w.calendar_provider AS provider", "w.channel AS provider")
    sql = f"SELECT AVG(activated) FROM ({base}) WHERE day BETWEEN ? AND ?"
    params: list = [first_day, last_day]
    if channel:
        sql += " AND provider = ?"
        params.append(channel)
    return world_db(run).execute(sql, params).fetchone()[0]


@pytest.fixture(scope="session")
def s03_now(tmp_path_factory):
    return generate(SCENARIO, seed=1, out=tmp_path_factory.mktemp("s03-now"))


@pytest.fixture(scope="session")
def s03_end(tmp_path_factory):
    return generate(SCENARIO, seed=1, through="end", out=tmp_path_factory.mktemp("s03-end"))


@pytest.fixture(scope="session")
def s03_rollback(tmp_path_factory):
    return generate(SCENARIO, seed=1, actions_path=ROLLBACK, out=tmp_path_factory.mktemp("s03-rollback"))


def test_share_block_drops_paid_search_activation_only(s03_now):
    assert activation(s03_now, RELEASE_DAY, LAST_MATURE_DAY, "paid_search") == pytest.approx(0.20, abs=0.03)
    assert activation(s03_now, RELEASE_DAY, LAST_MATURE_DAY, "organic") == pytest.approx(0.39, abs=0.03)
    assert activation(s03_now, RELEASE_DAY, LAST_MATURE_DAY, "direct") == pytest.approx(0.39, abs=0.03)


def test_the_second_release_has_no_effect(s03_now):
    """rel_0702 (the shorter subject line) ships after rel_0612 but changes nothing: the trap is its timing."""
    db = world_db(s03_now)
    releases = db.execute("SELECT release_id FROM releases ORDER BY ts").fetchall()
    assert [r[0] for r in releases] == ["rel_0612", "rel_0702"]


def test_customers_report_the_share_link_problem(s03_now):
    from sandbox.generator.text import variants
    planted = {subject for subject, _ in variants("templates/tickets/share_link_prefetched.txt")}
    rows = world_db(s03_now).execute(
        "SELECT CAST((julianday(created_at) - julianday('2026-01-05')) / 7 AS INT) + 1, subject, workspace_id FROM tickets"
    ).fetchall()
    for week in (6, 7, 8):
        accounts = {ws for wk, subject, ws in rows if wk == week and subject in planted}
        assert len(accounts) >= 3
    assert not any(subject in planted for wk, subject, _ in rows if wk <= 4)


def test_calendar_connect_and_first_meeting_are_unaffected(s03_now):
    """The break is isolated to the share step: calendar_connect and first_meeting don't move for the segment,
    the same registered metrics Signal would check to rule out an earlier funnel step."""
    from factory.metrics import World

    m = World(s03_now / "world" / "world.db")
    for metric in ("calendar_connect_rate_1d", "first_meeting_rate_7d", "trial_to_paid_rate"):
        cmp = m.compare_periods(metric, "2026-01-05", "2026-02-04", "2026-02-04", "2026-03-01",
                                 segment={"channel": ["paid_search"]})
        assert cmp["status"] == "value" and not cmp["material"], (metric, cmp)


def test_rollback_restores_paid_search_activation(s03_end, s03_rollback):
    after = (ROLLBACK_DAY, ROLLBACK_DAY + 6)
    assert activation(s03_rollback, *after, "paid_search") == pytest.approx(0.31, abs=0.04)
    assert activation(s03_end, *after, "paid_search") == pytest.approx(0.20, abs=0.04)


def test_history_before_the_action_is_unchanged(s03_end, s03_rollback):
    before = "WHERE ts < '2026-03-02'"
    assert table(s03_end, "events", before) == table(s03_rollback, "events", before)
    assert table(s03_rollback, "actions")[0][2] == "rollback"
