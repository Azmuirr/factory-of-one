import asyncio
import sqlite3

import pytest

from factory import warehouse
from factory.metrics import EVALUATORS, World, catalog

BEFORE = ("2026-01-05", "2026-02-08")
AFTER = ("2026-02-10", "2026-03-01")


@pytest.fixture(scope="module")
def world(now_run):
    return World(now_run / "world" / "world.db")


@pytest.fixture(scope="module")
def db(now_run):
    return now_run / "world" / "world.db"


def test_every_registered_metric_has_an_evaluator():
    assert set(catalog()[0]) == set(EVALUATORS)


def test_activation_matches_the_answer_key_exactly(world, now_run):
    result = world.get_metric("activation_rate_7d", *BEFORE)
    truth = sqlite3.connect(now_run / "truth" / "truth.db")
    truth.execute(f"ATTACH DATABASE '{(now_run / 'world' / 'world.db').as_posix()}' AS w")
    activated = truth.execute("""
        SELECT COUNT(*) FROM w.workspaces ws JOIN latents l USING (workspace_id)
        WHERE date(ws.created_at) BETWEEN ? AND ? AND l.activated_at IS NOT NULL""", BEFORE).fetchone()[0]
    assert result["numerator"] == activated


def test_same_question_same_number(world):
    phrasings = ["activation_rate_7d", "activation", "7-day activation"]
    answers = {(world.get_metric(p, *AFTER, segment={"calendar_provider": ["microsoft"]})["value"]) for p in phrasings for _ in range(4)}
    ids = {world.get_metric(p, *AFTER, segment={"calendar_provider": ["outlook"]})["query_id"] for p in phrasings}
    assert len(answers) == 1
    assert len(ids) == 1


def test_planted_drop_is_significant_for_microsoft_only(world):
    result = world.compare_periods("activation_rate_7d", *BEFORE, *AFTER, group_by=["calendar_provider"])
    rows = {r["group"]["calendar_provider"]: r for r in result["rows"]}
    assert rows["microsoft"]["after"] == pytest.approx(0.30, abs=0.02)
    assert rows["microsoft"]["p_value"] < 0.001
    assert rows["google"]["p_value"] > 0.05


def test_overall_value_is_pooled_not_an_average_of_groups(world):
    result = world.get_metric("activation_rate_7d", *BEFORE, group_by=["calendar_provider"])
    assert result["numerator"] == sum(r["numerator"] for r in result["rows"])
    assert result["value"] == round(result["numerator"] / result["denominator"], 4)


def test_immature_cohorts_are_excluded_and_reported(world):
    through_now = world.get_metric("activation_rate_7d", "2026-02-10", "2026-03-01")
    mature_only = world.get_metric("activation_rate_7d", "2026-02-10", "2026-02-22")
    assert through_now["maturity"]["excluded_immature_workspaces"] > 0
    assert through_now["value"] == mature_only["value"]


def test_a_fully_immature_period_is_rejected(world):
    result = world.get_metric("activation_rate_7d", "2026-02-25", "2026-03-01")
    assert result["status"] == "rejection" and result["code"] == "period_immature"


def test_period_past_the_data_is_clipped_and_stated(world):
    result = world.get_metric("new_workspaces", "2026-02-23", "2026-03-10")
    assert result["period"]["end"] == "2026-03-01"
    assert any("after the data ends" in a for a in result["assumptions"])


def test_meeting_grain_dimension_is_rejected_with_the_reason(world):
    result = world.get_metric("activation_rate_7d", *BEFORE, group_by=["meeting_platform"])
    assert result["code"] == "dimension_not_allowed"
    assert "Correlated with calendar_provider" in result["message"]


def test_unknown_metric_is_rejected_never_substituted(world):
    result = world.get_metric("churn", *BEFORE)
    assert result["status"] == "rejection" and result["code"] == "metric_not_registered"
    assert "value" not in result


def test_alias_values_resolve_and_are_stated(world):
    result = world.get_metric("activation_rate_7d", *BEFORE, segment={"calendar_provider": ["Outlook"]})
    assert result["segment"] == {"calendar_provider": ["microsoft"]}
    assert "Read 'Outlook' as calendar_provider = microsoft." in result["assumptions"]


def test_warehouse_is_read_only_and_labeled_exploratory(db):
    ok = warehouse.query(db, "SELECT calendar_provider, COUNT(*) FROM workspaces GROUP BY 1")
    assert ok["status"] == "value" and ok["confidence"] == "exploratory"
    assert warehouse.query(db, "DELETE FROM workspaces")["code"] == "read_only"
    assert warehouse.query(db, "SELECT 1; DROP TABLE workspaces")["code"] == "read_only"
    assert warehouse.query(db, "SELECT * FROM events", limit=10)["truncated"] is True


def test_mcp_servers_expose_their_tools(db, monkeypatch, tmp_path):
    monkeypatch.setenv("FACTORY_WORLD", str(db))
    monkeypatch.setenv("FACTORY_QUERY_LOG", str(tmp_path / "queries.jsonl"))
    from factory.servers import metrics_server, warehouse_server

    def names(server):
        tools = server.list_tools()
        tools = asyncio.run(tools) if asyncio.iscoroutine(tools) else tools
        return {t.name for t in tools}

    assert names(metrics_server.server) == {"list_metrics", "get_metric", "compare_periods", "estimate_weekly_arr_impact"}
    assert names(warehouse_server.server) == {"describe_tables", "query"}
    assert metrics_server.get_metric("activation", *BEFORE)["status"] == "value"


def test_a_group_with_no_eligible_workspaces_is_reported_not_crashed(world):
    result = world.compare_periods("calendar_connect_rate_1d", *BEFORE, *AFTER, group_by=["calendar_provider"])
    none = next(r for r in result["rows"] if r["group"] == {"calendar_provider": "none"})
    assert none["before"] is None and none["absolute"] is None


def test_every_metrics_answer_is_logged_for_replay(db, monkeypatch, tmp_path):
    from factory import queries
    from factory.servers import metrics_server
    log = tmp_path / "queries.jsonl"
    monkeypatch.setenv("FACTORY_WORLD", str(db))
    monkeypatch.setenv("FACTORY_QUERY_LOG", str(log))
    answer = metrics_server.compare_periods("activation", *BEFORE, *AFTER, segment={"calendar_provider": ["microsoft"]})
    logged = queries.load(log)[answer["query_id"]]
    replayed = queries.run(World(db), logged["tool"], logged["args"])
    assert replayed["after"] == answer["after"]
