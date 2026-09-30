"""Scenario 2: held out (D16). A different metric, a different segment dimension, built after every agent's
instructions were already written, to test whether what generalized from scenario 1 still holds."""

import pytest

from factory.metrics import World
from sandbox.generator import generate

SCENARIO = "s02-checkout-default"


@pytest.fixture(scope="module")
def s02_run(tmp_path_factory):
    return generate(SCENARIO, seed=1, out=tmp_path_factory.mktemp("s02"))


@pytest.fixture(scope="module")
def world(s02_run):
    return World(s02_run / "world" / "world.db")


def rate(world, segment, start, end):
    r = world.get_metric("trial_to_paid_rate", start, end, segment=segment)
    assert r["status"] == "value", r
    return r["value"]


def test_the_affected_segments_drop_after_the_release(world):
    for segment in (["s11_50"], ["s51_plus"]):
        before = rate(world, {"company_size": segment}, "2026-01-26", "2026-02-02")
        after = rate(world, {"company_size": segment}, "2026-02-09", "2026-02-16")
        assert after < before * 0.75  # paid_mult 0.65 plus noise


def test_unaffected_segments_do_not_drop(world):
    for segment in (["solo"], ["s2_10"]):
        before = rate(world, {"company_size": segment}, "2026-01-26", "2026-02-02")
        after = rate(world, {"company_size": segment}, "2026-02-09", "2026-02-16")
        assert after > before * 0.85  # flat to slightly up, not a real drop


def test_activation_is_unaffected_unlike_scenario_1(world):
    for segment in (["s11_50"], ["s51_plus"]):
        before = world.get_metric("activation_rate_7d", "2026-01-26", "2026-02-02", segment={"company_size": segment})
        after = world.get_metric("activation_rate_7d", "2026-02-09", "2026-02-16", segment={"company_size": segment})
        assert after["value"] == pytest.approx(before["value"], abs=0.06)  # small segment, one week: real sampling noise


def test_the_blended_overall_rate_barely_moves(world):
    before = rate(world, None, "2026-01-26", "2026-02-02")
    after = rate(world, None, "2026-02-09", "2026-02-16")
    assert after > before * 0.85  # the trap: segmenting is what reveals the real drop


def test_customers_report_price_confusion_at_checkout(s02_run):
    import sqlite3

    conn = sqlite3.connect(s02_run / "world" / "world.db")
    from sandbox.generator.text import variants

    planted = {subject for subject, _ in variants("templates/tickets/checkout_price_shock.txt")}
    rows = conn.execute("SELECT subject, workspace_id FROM tickets").fetchall()
    accounts = {ws for subject, ws in rows if subject in planted}
    assert len(accounts) >= 3


def test_no_truth_leaks_into_the_world(s02_run):
    import sqlite3

    conn = sqlite3.connect(s02_run / "world" / "world.db")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "latents" not in tables and "planted" not in tables
