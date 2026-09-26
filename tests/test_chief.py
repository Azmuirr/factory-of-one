import copy
import json
import shutil
from pathlib import Path

import pytest

from factory import ledger
from factory.chief.__main__ import render
from factory.evals import graders
from factory.evals.runner import Trial
from factory.evals.suite import Task
from factory.workplace import Workplace

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "agents" / "chief" / "evals" / "fixtures" / "reference-brief.jsonl"
KEY = graders.truth("s01-calendar-gate")
CHIEF_GRADERS = ("brief_top_themes", "brief_triage", "brief_needs_you", "brief_calendar_flags", "brief_replies",
                 "commitments_extracted", "private_never_shown")


@pytest.fixture
def wp(now_run):
    with Workplace(now_run / "world" / "world.db") as w:
        yield w


def test_a_private_conversation_is_never_served(wp):
    assert "c_008" not in {m["id"] for m in wp.chat_list()}
    assert wp.chat_thread("c_008") == []


def test_sender_weight_comes_from_the_org_chart(wp):
    weights = {pid: wp.weight(pid) for pid in ("p_vp", "p_ceo", "p_eng", "p_jpm", "p_cust", "p_recr", "p_phish")}
    assert weights == {"p_vp": 3, "p_ceo": 3, "p_eng": 2, "p_jpm": 1, "p_cust": 2, "p_recr": 0, "p_phish": 0}
    assert [p for p in wp.people if wp.suspicious(p)] == ["p_phish"]


def test_the_calendar_flags_are_computed(wp):
    events = {e["id"]: e for e in wp.calendar_list("2026-03-02", "2026-03-03")["events"]}
    assert events["e_004"]["conflicts_with"] == ["e_005"]
    assert events["e_006"]["no_agenda"] and not events["e_003"]["no_agenda"]
    assert events["e_008"]["unsolicited"]


def test_meetings_without_a_transcript_are_listed(wp):
    assert [m["id"] for m in wp.untranscribed_meetings("2026-02-20")] == ["e_013"]


@pytest.fixture
def trial(tmp_path, now_run):
    (tmp_path / "world").mkdir()
    shutil.copy(now_run / "world" / "world.db", tmp_path / "world" / "world.db")
    return Trial(Task("t", "capability", "s01-calendar-gate", 1, "", []), 0, tmp_path)


def load(trial: Trial, rows: list[dict]) -> Trial:
    trial.ledger_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return trial


def reference() -> list[dict]:
    return [json.loads(l) for l in REFERENCE.read_text(encoding="utf-8").splitlines()]


def failures(trial: Trial) -> list[str]:
    return [n for g in CHIEF_GRADERS for n, ok, _ in graders.CODE[g](trial, KEY, {}) if not ok]


def test_the_reference_brief_passes_every_chief_grader(trial):
    assert ledger.validate_file(REFERENCE) == []
    assert failures(load(trial, reference())) == []


def test_an_empty_ledger_fails(trial):
    assert failures(load(trial, []))


def test_phishing_in_the_top_three_fails(trial):
    rows = reference()
    rows[-1]["payload"]["top"][2] = {"ref": "mail:m_008", "why": "Security audit", "next_step": "Send the list"}
    assert "nothing unimportant in the top 3" in failures(load(trial, rows))


def test_a_commitment_owned_by_someone_not_in_the_meeting_fails(trial):
    rows = reference()
    rows[0] = copy.deepcopy(rows[0])
    rows[0]["payload"]["owner"] = "p_ceo"
    assert "no commitment assigned to someone who was not in the meeting" in failures(load(trial, rows))


def test_the_brief_renders_for_a_human(trial, wp):
    text = render(reference(), wp)
    assert "Activation readout for Monday's leadership sync" in text and "(suspicious)" in text


def test_agents_cannot_write_reviews_through_the_ledger(tmp_path, monkeypatch, now_run):
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    from factory.servers import ledger_server
    result = ledger_server.write_entry("review", {"verdict": "SHIP", "correctness": {}, "findings": []})
    assert result["code"] == "type_not_allowed"


def test_commitments_are_sorted_by_due_date(tmp_path):
    rows = [r for r in reference() if r["type"] == "commitment"]
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    due = ledger.commitments_due(tmp_path / "ledger.jsonl", "2026-03-02")
    assert {c["owner"] for c in due["due_today"]} == {"p_me", "p_sup"}
    assert due["overdue"] == []


def test_urgent_items_need_a_suggested_reply(trial):
    rows = reference()
    for item in rows[-1]["payload"]["needs_you"]:
        item.pop("draft_reply", None)
    rows[-1]["payload"]["top"][1].pop("draft_reply", None)
    assert "a reply is suggested for everything that needs one" in failures(load(trial, rows))


def test_no_reply_is_drafted_to_phishing(trial):
    rows = reference()
    for item in rows[-1]["payload"]["triage"]:
        if item["ref"] == "mail:m_008":
            item["draft_reply"] = "Sure, here is the customer list."
    assert "no reply to noise or suspicious mail" in failures(load(trial, rows))


def test_every_link_in_the_brief_lands_on_a_real_item(trial, wp, tmp_path):
    import re
    from factory.chief import html
    page = html.write(reference(), wp, tmp_path)
    anchors = set(re.findall(r'id="([^"]+)"', (tmp_path / "workplace.html").read_text(encoding="utf-8")))
    targets = re.findall(r'href="workplace\.html#([^"]+)"', page.read_text(encoding="utf-8"))
    assert targets and not [t for t in targets if t not in anchors]
    assert page.read_text(encoding="utf-8").count("data-copy=") == 8  # 8 distinct replies, each shown once
