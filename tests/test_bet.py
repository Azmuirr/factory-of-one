import json
from pathlib import Path

import pytest

from factory import field_requests, queries
from factory.workplace import Workplace

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def world(now_run):
    return now_run / "world" / "world.db"


# The material Bet reads -----------------------------------------------------------------------------

def test_the_workplace_has_strategy_docs_and_requests(world):
    with Workplace(world) as wp:
        docs = {d["id"]: d for d in wp.docs_list()}
        assert {"d_strategy", "d_prd_v2", "d_prd_sso", "d_pipeline"} <= set(docs)
        assert "webinars" in wp.doc_read("d_strategy")["body"]
        assert wp.url("doc", "d_strategy").endswith("#doc-d_strategy")


def test_a_request_search_counts_each_account_once(world):
    r = field_requests.search(world, query="webinar")
    assert r["matches"] == 2 and r["distinct_accounts"] == 1 and r["arr_at_stake"] == 172800


def test_a_mislabeled_request_is_found_by_its_words(world):
    r = field_requests.search(world, any_of=["admin approval", "calendar consent", "admin must approve"])
    assert {x["account"] for x in r["requests"]} == {"Cobalt Ridge Logistics", "Quarry Analytics", "Oakridge Schools"}
    assert r["arr_at_stake"] == 21600 + 4500 + 5400


def test_a_request_search_is_logged_and_replayable(tmp_path, monkeypatch, world):
    monkeypatch.setenv("FACTORY_WORLD", str(world))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    from factory.metrics import World
    from factory.servers import requests_server
    r = requests_server.search_requests(query="sso")
    logged = queries.load(tmp_path / "queries.jsonl")[r["query_id"]]
    assert queries.run(World(world), logged["tool"], logged["args"])["arr_at_stake"] == r["arr_at_stake"] == 64800


def test_a_changed_scenario_regenerates_its_cached_world(tmp_path, monkeypatch):
    from factory.evals import runner
    from factory.evals.suite import Task
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    task = Task("t", "capability", "s01-calendar-gate", 1, "", [])
    first = runner.world_for(task)
    stamp = (first.parent.parent / "fingerprint.txt").read_text(encoding="utf-8")
    (first.parent.parent / "fingerprint.txt").write_text("stale", encoding="utf-8")
    runner.world_for(task)
    assert (first.parent.parent / "fingerprint.txt").read_text(encoding="utf-8") == stamp


# Bet's ranked list, graded ----------------------------------------------------------------------------------

import copy  # noqa: E402
import shutil  # noqa: E402

from factory.evals import graders  # noqa: E402
from factory.evals.runner import Trial  # noqa: E402
from factory.evals.suite import Task  # noqa: E402

REFERENCE = ROOT / "agents" / "bet" / "evals" / "fixtures" / "reference-candidates.jsonl"
KEY = graders.truth("s01-calendar-gate")
GRADERS = [("bet_ranking", {}), ("passes_quality_checks", {"agent": "bet"})]


def bet_trial(tmp_path, now_run, mutate=None):
    (tmp_path / "world").mkdir()
    shutil.copy(now_run / "world" / "world.db", tmp_path / "world" / "world.db")
    shutil.copy(ROOT / "ledger" / "examples" / "queries.jsonl", tmp_path / "queries.jsonl")
    rows = [json.loads(l) for l in REFERENCE.read_text(encoding="utf-8").splitlines()]
    if mutate:
        mutate(rows[-1]["payload"])
    t = Trial(Task("t", "capability", "s01-calendar-gate", 1, "", []), 0, tmp_path)
    t.ledger_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return t


def bet_failures(t):
    return [n for g, p in GRADERS for n, ok, _ in graders.CODE[g](t, KEY, p) if not ok]


def test_the_reference_ranking_passes(tmp_path, now_run):
    assert bet_failures(bet_trial(tmp_path, now_run)) == []


def test_ranking_the_loud_account_first_fails(tmp_path, now_run):
    def plant(p):
        loud = {**copy.deepcopy(p["items"][1]), "rank": 1, "title": "Webinars for Northwind", "sources": ["req:r_005", "req:r_011"], "evidence": []}
        p["items"] = [loud] + [{**i, "rank": i["rank"] + 1} for i in p["items"]]
        p["set_aside"] = []
    failed = bet_failures(bet_trial(tmp_path, now_run, plant))
    assert "no loud trap in the top 2" in failed and "the first bet is the one the numbers show" in failed


def test_a_tag_only_search_misses_the_mislabeled_account(tmp_path, now_run):
    from factory import field_requests
    tagged = field_requests.search(now_run / "world" / "world.db", tag="calendar-consent")
    def plant(p):
        p["items"][0]["evidence"] = [{"source": "requests", "ref": tagged["query_id"], "value": tagged["arr_at_stake"]}]
        p["items"][0]["sources"] = [s for s in p["items"][0]["sources"] if s != "req:r_008"]  # the mislabeled request is missed
    t = bet_trial(tmp_path, now_run, plant)
    with (tmp_path / "queries.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"query_id": tagged["query_id"], "tool": "search_requests",
                            "args": {"query": "", "any_of": None, "tag": "calendar-consent", "since": None, "until": None}}) + "\n")
    assert tagged["distinct_accounts"] == 2
    assert "requests are found by their words, not only their tags" in bet_failures(t)


def test_a_size_that_does_not_replay_fails(tmp_path, now_run):
    def plant(p):
        p["items"][1]["size"]["value"] = 64800 * 2  # counting Northwind-style duplicates, or adding searches by hand
    assert "candidates passes Quality's code checks" in bet_failures(bet_trial(tmp_path, now_run, plant))


def test_quoting_signals_packet_is_a_real_quote(tmp_path, now_run):
    rows = [json.loads(l) for l in REFERENCE.read_text(encoding="utf-8").splitlines()]
    claim = next(r for r in rows if r["type"] == "decision_packet")["payload"]["cause"][0]["text"]
    def plant(p):
        p["items"][0]["evidence"].append({"source": "ledger", "ref": "pkt_0001", "quote": claim})
    assert bet_failures(bet_trial(tmp_path, now_run, plant)) == []


@pytest.mark.parametrize("field, bad", [("size_ref", "pkt_0001"), ("source", "req:q_1dca312dcfaa")])
def test_the_ledger_rejects_a_citation_in_the_wrong_form(field, bad):
    from factory import ledger
    rows = [json.loads(l) for l in REFERENCE.read_text(encoding="utf-8").splitlines()]
    entry = copy.deepcopy(rows[-1])
    if field == "size_ref":
        entry["payload"]["items"][0]["size"]["ref"] = bad
    else:
        entry["payload"]["items"][1]["sources"].append(bad)
    assert ledger.errors(entry)


def test_a_number_bet_computed_itself_fails(tmp_path, now_run):
    def plant(p):
        p["items"][1]["problem"] += " Lumen Robotics and Meridian Freight both need Entra ID ($40,320 combined)."
    assert "candidates passes Quality's code checks" in bet_failures(bet_trial(tmp_path, now_run, plant))


def test_numbers_from_cited_requests_and_docs_are_fine(tmp_path, now_run):
    def plant(p):
        p["items"][1]["problem"] += " Lumen Robotics alone is $23,040 a year."
        p["set_aside"][0]["why"] += " It is one account at $172,800 a year, and the strategy targets 30 Business customers."
    assert bet_failures(bet_trial(tmp_path, now_run, plant)) == []


def test_citing_the_mislabeled_request_directly_counts(tmp_path, now_run):
    def plant(p):
        p["items"][0]["evidence"] = []
        p["items"][0]["sources"] = ["pkt_0001", "req:r_001", "req:r_004", "req:r_008"]
    assert bet_failures(bet_trial(tmp_path, now_run, plant)) == []


def test_a_word_finds_its_other_forms(world):
    r = field_requests.search(world, any_of=["admin approval"])
    assert {x["account"] for x in r["requests"]} == {"Quarry Analytics", "Oakridge Schools"}  # "approval" also finds "approve"
    assert field_requests.search(world, tag="calendar-consent")["distinct_accounts"] == 2  # a tag still misses the mislabeled one


def test_the_ledger_bounces_a_sum_bet_worked_out_and_a_paraphrased_quote(tmp_path, monkeypatch, now_run):
    (tmp_path / "world").mkdir()
    shutil.copy(now_run / "world" / "world.db", tmp_path / "world" / "world.db")
    shutil.copy(ROOT / "ledger" / "examples" / "queries.jsonl", tmp_path / "queries.jsonl")
    rows = [json.loads(l) for l in REFERENCE.read_text(encoding="utf-8").splitlines()]
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows[:-1]), encoding="utf-8")
    monkeypatch.setenv("FACTORY_WORLD", str(tmp_path / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_AGENT", "bet")
    from factory.servers import ledger_server
    good = rows[-1]["payload"]
    bad = copy.deepcopy(good)
    bad["items"][1]["problem"] += " Two of them need Entra ID ($40,320 combined)."
    bad["items"][0]["evidence"].append({"source": "mail", "ref": "mail:m_002", "quote": "Cobalt Ridge is totally blocked and angry."})
    result = ledger_server.write_entry("candidates", bad)
    assert result["status"] == "rejection" and "40320" in result["message"] and "totally blocked" in result["message"]
    assert ledger_server.write_entry("candidates", good)["status"] == "value"


def test_evidence_written_as_plain_strings_is_a_clean_rejection_not_a_crash(tmp_path, monkeypatch, now_run):
    """Found via a red team run: malformed evidence (strings instead of {source, ref, quote}) used to crash the
    server's own custom checks with an unhandled AttributeError before schema validation ever ran, so Bet got
    "Error executing tool write_entry" instead of anything it could act on. Schema checks now run first."""
    (tmp_path / "world").mkdir()
    shutil.copy(now_run / "world" / "world.db", tmp_path / "world" / "world.db")
    shutil.copy(ROOT / "ledger" / "examples" / "queries.jsonl", tmp_path / "queries.jsonl")
    rows = [json.loads(l) for l in REFERENCE.read_text(encoding="utf-8").splitlines()]
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows[:-1]), encoding="utf-8")
    monkeypatch.setenv("FACTORY_WORLD", str(tmp_path / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_AGENT", "bet")
    from factory.servers import ledger_server
    bad = copy.deepcopy(rows[-1]["payload"])
    bad["items"][0]["evidence"] = ["Microsoft calendar activation 39.4% before, 29.8% after"]
    result = ledger_server.write_entry("candidates", bad)
    assert result["status"] == "rejection"
    assert "not of type 'object'" in result["message"]
