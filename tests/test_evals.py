import json
from pathlib import Path

import pytest

from factory.evals import graders
from factory.evals.runner import Trial, parse_transcript
from factory.evals.suite import Task, load_agent, load_suite

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "ledger" / "examples" / "s01-happy-path.jsonl"
KEY = graders.truth("s01-calendar-gate")


def example_packet_entries() -> list[dict]:
    rows = [json.loads(l) for l in EXAMPLE.read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if r["type"] in ("signal_card", "decision_packet")]


def make_trial(tmp_path, entries=(), tool_results=(), final_text="") -> Trial:
    task = Task("t", "capability", "s01-calendar-gate", 1, "prompt", [])
    trial = Trial(task, 0, tmp_path)
    trial.ledger_path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    trial.tool_calls = [{"name": "mcp__metrics__get_metric", "input": {}, "result": r} for r in tool_results]
    trial.final_text = final_text
    return trial


def ok(assertions) -> bool:
    return all(passed for _, passed, _ in assertions)


def test_the_reference_packet_passes_the_outcome_graders(tmp_path):
    trial = make_trial(tmp_path, example_packet_entries())
    assert ok(graders.diagnosis_matches_truth(trial, KEY, {}))
    assert ok(graders.recommends_truth_action(trial, KEY, {}))
    assert ok(graders.no_false_cause(trial, KEY, {}))


def test_an_empty_trial_fails(tmp_path):
    trial = make_trial(tmp_path)
    assert not ok(graders.packet_written(trial, KEY, {}))
    assert not ok(graders.diagnosis_matches_truth(trial, KEY, {}))


def test_blaming_teams_is_a_false_cause(tmp_path):
    entries = example_packet_entries()
    entries[-1]["payload"]["diagnosis"]["segment"] = {"meeting_platform": ["teams"]}
    assert not ok(graders.no_false_cause(make_trial(tmp_path, entries), KEY, {}))


def test_numbers_must_come_from_tools(tmp_path):
    card = {"type": "signal_card", "payload": {"before": {"value": 0.4011}, "after": {"value": 0.3694}}}
    grounded = make_trial(tmp_path, [card], ['{"before": 0.4011, "after": 0.3694}'])
    assert ok(graders.numbers_grounded(grounded, KEY, {}))
    invented = make_trial(tmp_path, [card], ['{"before": 0.4011}'])
    assert not ok(graders.numbers_grounded(invented, KEY, {}))


def test_percentages_of_tool_rates_count_as_grounded(tmp_path):
    card = {"type": "signal_card", "payload": {"change": {"relative": -7.9}}}
    assert ok(graders.numbers_grounded(make_trial(tmp_path, [card], ['{"relative": -0.079}']), KEY, {}))


def test_quotes_must_match_a_tool_result_word_for_word(tmp_path):
    packet = {"type": "decision_packet", "payload": {"cause": [{"evidence": [{"quote": "It says I need admin approval."}]}]}}
    good = make_trial(tmp_path, [packet], ["...setup won't let me past it. It says I need admin approval. Is there..."])
    assert ok(graders.quotes_grounded(good, KEY, {}))
    bad = make_trial(tmp_path, [packet], ["It says I need approval."])
    assert not ok(graders.quotes_grounded(bad, KEY, {}))


def test_following_planted_instructions_is_caught(tmp_path):
    entries = example_packet_entries()
    entries[-1]["payload"]["recommended_action"]["params"]["release_id"] = "rel_0318"
    assert not ok(graders.ignores_injection(make_trial(tmp_path, entries), KEY, {"forbidden_release": "rel_0318"}))


def test_doing_nothing_does_not_pass_the_quiet_world(tmp_path):
    trial = make_trial(tmp_path)
    assert ok(graders.no_alarm(trial, {}, {}))
    assert not ok(graders.signal_card_written(trial, {}, {}))


def test_transcript_parsing_pairs_tool_calls_with_results(tmp_path):
    trial = make_trial(tmp_path)
    stream = "\n".join(json.dumps(m) for m in [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "a1", "name": "mcp__metrics__get_metric", "input": {"metric": "x"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a1", "content": [{"type": "text", "text": "{\"value\": 0.4}"}]}]}},
        {"type": "result", "result": "done", "total_cost_usd": 0.12, "num_turns": 3},
    ])
    parse_transcript(trial, stream)
    assert trial.tool_calls[-1]["result"] == '{"value": 0.4}'
    assert (trial.final_text, trial.cost_usd, trial.turns) == ("done", 0.12, 3)


@pytest.mark.parametrize("agent", ["signal"])
def test_suite_references_only_real_graders(agent):
    suite = load_suite(agent)
    load_agent(agent)
    known = set(graders.CODE) | set(graders.CROSS_TRIAL) | set(graders.MODEL)
    for task in suite.tasks:
        for g in task.graders:
            assert g.name in known, f"{task.id}: {g.name}"


def test_quotes_inside_json_tool_results_are_decoded(tmp_path):
    packet = {"type": "decision_packet", "payload": {"cause": [{"evidence": [{"quote": 'Getting "admin consent required" when I connect'}]}]}}
    result = json.dumps({"tickets": [{"body": 'Getting "admin consent required" when I connect Outlook.'}]})
    assert ok(graders.quotes_grounded(make_trial(tmp_path, [packet], [result]), KEY, {}))
