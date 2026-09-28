import copy
import hashlib
import json
from pathlib import Path

import pytest

from factory import code, design

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / "agents" / "builder" / "evals" / "fixtures" / "reference-change.json").read_text(encoding="utf-8"))
ACCEPTANCE = ROOT / "sandbox" / "scenarios" / "s01-calendar-gate" / "acceptance"


def propose(tmp_path, change=REFERENCE):
    return code.propose(code.APP, tmp_path / "changes", change["name"], change["edits"], change.get("new_files", {}))


def variant(**swaps):
    change = copy.deepcopy(REFERENCE)
    for i, edit in enumerate(change["edits"]):
        for a, b in swaps.items():
            change["edits"][i]["new"] = edit["new"].replace(a, b)
    return change


# The code tools ------------------------------------------------------------------------------------

def test_the_app_is_listed_and_read_but_never_changed(tmp_path):
    before = {p: hashlib.sha1((code.APP / p).read_bytes()).hexdigest() for p in code.files(code.APP)}
    assert "tallybird/onboarding.py" in before and "tests/test_onboarding.py" in before
    assert "skip" in code.read(code.APP, "tallybird/screens.py")
    propose(tmp_path)
    assert before == {p: hashlib.sha1((code.APP / p).read_bytes()).hexdigest() for p in code.files(code.APP)}


def test_search_finds_the_line(tmp_path):
    hits = code.search(code.APP, "skippable")
    assert {"tallybird/onboarding.py", "tallybird/screens.py"} <= {h["path"] for h in hits}


def test_the_reference_change_passes_its_tests_the_hidden_acceptance_and_scope(tmp_path):
    result = propose(tmp_path)
    assert result["status"] == "value" and result["tests"]["passed"], result
    assert result["new_flags"] == ["calendar_skip_microsoft"]
    change = tmp_path / "changes" / REFERENCE["name"]
    assert code.acceptance(change, ACCEPTANCE)["passed"]
    assert code.scope(code.APP, change) == []


def test_an_edit_must_match_exactly_once(tmp_path):
    change = copy.deepcopy(REFERENCE)
    change["edits"][1]["old"] = "no such line"
    result = propose(tmp_path, change)
    assert result["status"] == "rejection" and "tallybird/onboarding.py" in result["message"]


def test_paths_cannot_leave_the_app(tmp_path):
    change = copy.deepcopy(REFERENCE)
    change["new_files"] = {"../escape.py": "x = 1\n"}
    assert propose(tmp_path, change)["status"] == "rejection"


def test_a_flag_that_ships_on_fails(tmp_path):
    propose(tmp_path, variant(**{"  enabled: false\n  rules:\n    - {calendar_provider": "  enabled: true\n  rules:\n    - {calendar_provider"}))
    change = tmp_path / "changes" / REFERENCE["name"]
    assert not code.acceptance(change, ACCEPTANCE)["passed"]
    assert any("ships on" in p for p in code.scope(code.APP, change))


def test_changing_it_for_everyone_breaks_the_existing_tests(tmp_path):
    change = copy.deepcopy(REFERENCE)
    change["edits"] = [change["edits"][1]]
    change["edits"][0]["new"] = change["edits"][0]["new"].replace('flags.is_on("calendar_skip_microsoft", user)', "True")
    change["new_files"] = {}
    assert not propose(tmp_path, change)["tests"]["passed"]


def test_a_change_with_no_new_test_is_out_of_scope(tmp_path):
    change = copy.deepcopy(REFERENCE)
    change["new_files"] = {}
    propose(tmp_path, change)
    assert "adds no test" in " ".join(code.scope(code.APP, tmp_path / "changes" / REFERENCE["name"]))


# The design system -----------------------------------------------------------------------------------

EXAMPLE = (ROOT / "sandbox" / "design" / "components.md").read_text(encoding="utf-8").split("```html")[1].split("```")[0]


def test_the_example_in_the_docs_passes(tmp_path):
    result = design.render(EXAMPLE, tmp_path / "d")
    assert result["passed"], result["problems"]
    assert (tmp_path / "d" / "screen.png").stat().st_size > 1000


@pytest.mark.parametrize("markup, problem", [
    ('<div class="tb-card" style="color: red">x</div>', "inline style"),
    ('<style>.x{}</style><div class="tb-card">x</div>', "<style>"),
    ('<div class="card-fancy">x</div>', "card-fancy"),
    ('<link rel="stylesheet" href="https://x.test/a.css"><div class="tb-card">x</div>', "external"),
])
def test_anything_outside_the_system_fails(markup, problem):
    problems = design.static_problems(markup)
    assert problems and problem in " ".join(problems)


def test_the_stylesheet_uses_every_color_token_exactly():
    css = design.stylesheet()
    for name, value in design.tokens()["color"].items():
        assert f"--tb-{name}: {value};" in css


# Quality's checks, the graders, and the ledger on MVP and design builds -----------------------------

from factory import review  # noqa: E402
from factory.evals import graders  # noqa: E402
from factory.evals.runner import Trial  # noqa: E402
from factory.evals.suite import Task  # noqa: E402

MVP = {"kind": "mvp", "location": f"changes/{REFERENCE['name']}", "honesty_label": "live", "checks": {"tests_passed": True}}
DESIGN = {"kind": "design", "location": "designs/consent-fallback/index.html", "honesty_label": "mocked", "checks": {}}


def build_entry(n, payload):
    return {"id": f"bld_{n:04d}", "type": "build", "ts": "2026-03-02T00:00:00Z", "author": {"kind": "agent", "name": "builder"},
            "refs": [], "payload": payload}


@pytest.fixture
def built(tmp_path):
    """A trial folder holding the reference change and the example design, with their build entries."""
    propose(tmp_path)
    design.render(EXAMPLE, tmp_path / "designs" / "consent-fallback")
    trial = Trial(Task("t", "capability", "s01-calendar-gate", 1, "", []), 0, tmp_path)
    trial.ledger_path.write_text(json.dumps(build_entry(1, MVP)) + "\n" + json.dumps(build_entry(2, DESIGN)) + "\n", encoding="utf-8")
    return trial


def checks(trial, n):
    entries = [json.loads(l) for l in trial.ledger_path.read_text(encoding="utf-8").splitlines()]
    return review.correctness(entries[n], entries, trial.world_path, trial.dir)


def failures(trial, names=("mvp_change_passes", "design_passes_checks")):
    return [n for g in names for n, ok, _ in graders.CODE[g](trial, {}, {}) if not ok]


def test_the_reference_builds_pass_quality_and_the_graders(built):
    assert checks(built, 0)["fields"] == "pass" and checks(built, 1)["fields"] == "pass"
    assert failures(built) == []


def test_a_build_that_claims_passing_tests_it_does_not_have_fails(built):
    folder = built.dir / MVP["location"]
    (folder / "tests" / "test_broken.py").write_text("def test_broken():\n    assert False\n", encoding="utf-8")
    assert checks(built, 0)["fields"] == "fail"
    assert "code reran the tests and they pass" in failures(built)


def test_a_flag_that_ships_on_fails_the_hidden_acceptance(built):
    flags = built.dir / MVP["location"] / "tallybird" / "flags.yaml"
    flags.write_text(flags.read_text(encoding="utf-8").replace("  enabled: false\n  rules:\n    - {calendar_provider",
                                                               "  enabled: true\n  rules:\n    - {calendar_provider"), encoding="utf-8")
    failed = failures(built)
    assert "the hidden acceptance tests pass" in failed and "the change stays in scope" in failed


def test_a_design_with_an_inline_style_fails(built):
    markup = built.dir / "designs" / "consent-fallback" / "markup.html"
    markup.write_text(markup.read_text(encoding="utf-8").replace('class="tb-card"', 'class="tb-card" style="color: red"'), encoding="utf-8")
    assert checks(built, 1)["fields"] == "fail"
    assert "the design uses only the design system" in failures(built)


def test_the_ledger_accepts_a_change_that_exists_and_rejects_one_that_does_not(built, monkeypatch, now_run):
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(built.dir / "ledger2.jsonl"))
    monkeypatch.setenv("FACTORY_DEMOS", str(built.dir / "demos"))
    from factory.servers import ledger_server
    assert ledger_server.write_entry("build", MVP)["status"] == "value"
    assert ledger_server.write_entry("build", DESIGN)["status"] == "value"
    assert ledger_server.write_entry("build", {**MVP, "location": "changes/nope"})["status"] == "rejection"


def test_the_change_description_is_not_part_of_the_diff(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_CHANGES", str(tmp_path / "changes"))
    from factory.servers import code_server
    result = code_server.propose_change(REFERENCE["name"], REFERENCE["message"], REFERENCE["edits"], REFERENCE["new_files"])
    folder = tmp_path / "changes" / REFERENCE["name"]
    assert (folder / "CHANGE.md").is_file() and "CHANGE.md" not in result["diff"]
    assert code.scope(code.APP, folder) == []


def test_tests_run_without_the_callers_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    probe = tmp_path / "app"
    (probe / "tests").mkdir(parents=True)
    (probe / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (probe / "tests" / "test_env.py").write_text("import os\n\ndef test_no_secrets():\n    assert 'ANTHROPIC_API_KEY' not in os.environ\n", encoding="utf-8")
    assert code.run_tests(probe)["passed"]


def test_quality_sees_what_a_code_change_does(built):
    result = checks(built, 0)
    assert result["evidence"]["new_flags"] == ["calendar_skip_microsoft"]
    assert "calendar_provider: [microsoft]" in result["evidence"]["diff"] and result["evidence"]["tests"]["passed"]
