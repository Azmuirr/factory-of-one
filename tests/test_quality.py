import copy
import json
import shutil
from pathlib import Path

import pytest

from factory import ledger, review

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "agents" / "quality" / "evals" / "fixtures"
QUERIES = ROOT / "ledger" / "examples" / "queries.jsonl"


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("quality")
    shutil.copy(QUERIES, d / "queries.jsonl")
    shutil.copytree(FIXTURES / "demos", d / "demos")
    return d


def checks(name: str, target: str, world: Path, run_dir: Path) -> dict:
    rows = [json.loads(l) for l in (FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
    return review.correctness(next(r for r in rows if r["id"] == target), rows, world, run_dir)


@pytest.fixture(scope="module")
def world(now_run):
    return now_run / "world" / "world.db"


def test_the_clean_packet_passes_every_check(world, run_dir):
    result = checks("clean", "pkt_0001", world, run_dir)
    assert review.failed(result) == [], result.get("details")


def test_a_wrong_number_fails_by_replaying_its_query(world, run_dir):
    result = checks("wrong-number", "pkt_0001", world, run_dir)
    assert review.failed(result) == ["numbers"]
    assert "does not match query" in result["details"]["numbers"][0]


def test_a_made_up_quote_fails(world, run_dir):
    assert review.failed(checks("fake-quote", "pkt_0001", world, run_dir)) == ["quotes"]


def test_a_dead_click_demo_fails(world, run_dir):
    assert "fields" in review.failed(checks("dead-click", "bld_0001", world, run_dir))


def test_a_wrong_cause_with_true_numbers_passes_code_and_needs_judgment(world, run_dir):
    assert review.failed(checks("wrong-cause", "pkt_0001", world, run_dir)) == []


def test_a_signal_card_is_recomputed_exactly(world, run_dir):
    rows = [json.loads(l) for l in (FIXTURES / "clean.jsonl").read_text(encoding="utf-8").splitlines()]
    card = copy.deepcopy(rows[0])
    card["payload"]["after"]["value"] = 0.3601
    result = review.correctness(card, rows, world, run_dir)
    assert review.failed(result) == ["numbers"]


def test_metric_evidence_must_cite_a_query(world, run_dir):
    rows = [json.loads(l) for l in (FIXTURES / "clean.jsonl").read_text(encoding="utf-8").splitlines()]
    packet = copy.deepcopy(rows[1])
    packet["payload"]["cause"][0]["evidence"][0]["ref"] = "activation by calendar provider"
    result = review.correctness(packet, [rows[0], packet], world, run_dir)
    assert any("does not cite a query_id" in d for d in result["details"]["numbers"])


@pytest.fixture
def review_env(tmp_path, monkeypatch, world):
    shutil.copy(QUERIES, tmp_path / "queries.jsonl")
    for name in ("clean", "wrong-number"):
        (tmp_path / name).mkdir()
        shutil.copy(QUERIES, tmp_path / name / "queries.jsonl")
        shutil.copy(FIXTURES / f"{name}.jsonl", tmp_path / name / "ledger.jsonl")
    monkeypatch.setenv("FACTORY_WORLD", str(world))
    monkeypatch.setenv("FACTORY_AGENT", "quality")
    from factory.servers import review_server
    return review_server, tmp_path, monkeypatch


def test_ship_is_refused_when_a_check_failed(review_env):
    server, root, monkeypatch = review_env
    monkeypatch.setenv("FACTORY_LEDGER", str(root / "wrong-number" / "ledger.jsonl"))
    assert server.submit_review("pkt_0001", "SHIP", [])["code"] == "ship_blocked"


def test_a_submitted_review_carries_the_code_checks(review_env):
    server, root, monkeypatch = review_env
    monkeypatch.setenv("FACTORY_LEDGER", str(root / "clean" / "ledger.jsonl"))
    result = server.submit_review("pkt_0001", "SHIP", [])
    assert result["status"] == "value"
    written = ledger.read(root / "clean" / "ledger.jsonl")[-1]
    assert written["type"] == "review" and written["payload"]["correctness"]["numbers"] == "pass"


def test_a_product_name_is_not_a_data_number():
    from factory import numbers as nums
    text = "Microsoft 365 admin consent blocks the calendar step; Office 365 tenants too."
    assert nums.text_numbers(text) == []
    assert [v for v, _ in nums.text_numbers("Microsoft 30 workspaces filed tickets")] == [30.0]


def test_the_sibling_builds_fixture_passes_every_code_check(tmp_path):
    import shutil
    from factory import review
    from factory.evals.suite import load_suite
    fixture = ROOT / "agents" / "quality" / "evals" / "fixtures" / "sibling-builds"
    for folder in ("changes", "designs", "demos"):
        shutil.copytree(fixture / folder, tmp_path / folder)
    entries = [json.loads(l) for l in (fixture / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    for entry in (e for e in entries if e["type"] == "build"):
        checks = review.correctness(entry, entries, tmp_path / "world.db", tmp_path)
        assert checks["fields"] == "pass" and checks["numbers"] != "fail", (entry["payload"]["kind"], checks)
    assert "sibling-builds" in {t.id for t in load_suite("quality").tasks}


# The voice count, like every number, cites what produced it ------------------------------------------

def clean_rows():
    return [json.loads(l) for l in (FIXTURES / "clean.jsonl").read_text(encoding="utf-8").splitlines()]


def test_a_voice_count_must_cite_the_search_it_came_from(world, run_dir):
    rows = clean_rows()
    del rows[1]["payload"]["diagnosis"]["voice_ref"]
    result = review.correctness(rows[1], rows, world, run_dir)
    assert any("voice_ref" in d for d in result["details"]["numbers"])


def test_a_voice_count_that_merges_searches_fails(world, run_dir):
    rows = clean_rows()
    rows[1]["payload"]["diagnosis"]["voice_workspaces"] = 21  # what an agent gets by adding two searches itself
    result = review.correctness(rows[1], rows, world, run_dir)
    assert any("gives 12" in d for d in result["details"]["numbers"])


# Small numbers in prose are data unless they are dates or time spans ----------------------------------

@pytest.mark.parametrize("text, checked", [
    ("12 distinct workspaces filed tickets", [12.0]),
    ("cohorts need 7 days to mature", []),
    ("released Feb 10, reviewed in week 6", []),
    ("Step 1 of 3", []),
])
def test_only_dates_and_time_spans_skip_the_numbers_check(text, checked):
    from factory import numbers as nums
    assert [v for v, _ in nums.text_numbers(text)] == checked


@pytest.mark.parametrize("text", ["until a Microsoft-365-admin-consent check", "microsoft 365 tenants", "Office365 admins"])
def test_product_names_with_numbers_in_any_spelling_are_not_data(text):
    from factory import numbers as nums
    assert nums.text_numbers(text) == []


def test_a_tracker_id_is_not_a_data_number():
    from factory import numbers as nums
    assert nums.text_numbers("greenlight ONB-140 and PLAT-88 this week") == []
