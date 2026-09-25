import copy
from pathlib import Path

import pytest
import yaml

from factory.ledger import errors, read, validate_file

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "ledger" / "examples" / "s01-happy-path.jsonl"
METRICS = yaml.safe_load((ROOT / "catalogs" / "metrics.yaml").read_text(encoding="utf-8"))
DIMENSIONS = yaml.safe_load((ROOT / "catalogs" / "dimensions.yaml").read_text(encoding="utf-8"))["dimensions"]


@pytest.fixture
def example():
    return {e["id"]: e for e in read(EXAMPLE)}


def all_metrics() -> dict:
    return {name: m for family in METRICS["families"].values() for name, m in family["metrics"].items()}


def test_example_ledger_is_valid():
    assert validate_file(EXAMPLE) == []


def test_only_a_human_can_place_a_bet(example):
    bet = copy.deepcopy(example["bet_0001"])
    bet["author"] = {"kind": "agent", "name": "bet"}
    assert errors(bet)


def test_only_a_human_can_make_the_call(example):
    call = copy.deepcopy(example["call_0001"])
    call["author"] = {"kind": "agent", "name": "chief"}
    assert errors(call)


def test_a_fact_needs_evidence(example):
    packet = copy.deepcopy(example["pkt_0001"])
    packet["payload"]["cause"][0]["evidence"] = []
    assert errors(packet)


def test_every_claim_says_what_it_does_not_prove(example):
    packet = copy.deepcopy(example["pkt_0001"])
    del packet["payload"]["cause"][0]["does_not_prove"]
    assert errors(packet)


def test_refs_must_point_to_earlier_entries(example):
    assert errors(example["pkt_0001"], known_ids=set()) == ["refs: sig_0001 is not an earlier ledger entry"]


def finding(severity: str) -> dict:
    return {"claim": "c", "evidence": "e", "impact": "i", "smallest_action": "a", "proof_required": "p", "severity": severity}


def test_review_caps_findings_at_three_unless_blockers(example):
    review = copy.deepcopy(example["rev_0001"])
    review["payload"]["verdict"] = "FIX"
    review["payload"]["findings"] = [finding("cost")] * 3 + [finding("safety")]
    assert errors(review) == []
    review["payload"]["findings"] = [finding("cost")] * 4
    assert errors(review)


def test_segments_use_catalog_dimensions(example):
    for entry in example.values():
        for key in ("segment",):
            for container in (entry["payload"], entry["payload"].get("prediction", {})):
                for dim, values in (container.get(key) or {}).items():
                    assert dim in DIMENSIONS
                    assert set(values) <= set(DIMENSIONS[dim]["values"])


def test_catalog_metrics_reference_real_dimensions_and_metrics():
    metrics = all_metrics()
    for name, m in metrics.items():
        assert set(m["dimensions"]) <= set(DIMENSIONS), name
        assert set(m["related"]) <= set(metrics), name
        assert {"description", "numerator", "unit", "window_days"} <= set(m), name
