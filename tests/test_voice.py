"""Deterministic criterion #1: voice compliance (length, sign-off, banned openings, opens with the recipient's
first name) is mechanical and has one right answer, so code checks it live, not only in an eval."""

import os

import pytest

from factory import config as install
from factory import voice

CONFIG = voice.load(install.load().voice)


@pytest.fixture
def world(now_run):
    return now_run / "world" / "world.db"


def test_a_clean_draft_has_no_problems(world):
    drafts = [("mail:m_002", "Grace, thanks for the heads up. I'll call Luis today. Thanks, S.")]
    assert voice.draft_problems(drafts, world, CONFIG) == []


def test_a_draft_over_the_word_limit_is_flagged(world):
    long_text = "Grace, " + "word " * 61 + "Thanks, S."
    drafts = [("mail:m_002", long_text)]
    problems = voice.draft_problems(drafts, world, CONFIG)
    assert {p["category"] for p in problems} == {"length"}


def test_a_draft_missing_the_signoff_is_flagged(world):
    drafts = [("mail:m_002", "Grace, I'll call Luis today.")]
    problems = voice.draft_problems(drafts, world, CONFIG)
    assert any(p["category"] == "signoff" for p in problems)


def test_a_stock_opening_is_flagged(world):
    drafts = [("mail:m_002", "Hi Grace, I'll call Luis today. Thanks, S.")]
    problems = voice.draft_problems(drafts, world, CONFIG)
    assert any(p["category"] == "opening" for p in problems)


def test_not_opening_with_the_recipients_first_name_is_flagged(world):
    drafts = [("mail:m_002", "Thanks for the note, I'll call Luis today. Thanks, S.")]
    problems = voice.draft_problems(drafts, world, CONFIG)
    assert any(p["category"] == "name" for p in problems)


def test_a_chat_draft_is_not_held_to_the_mail_only_signoff_or_name_rule(world):
    """m_002's sender is p_sales (Grace); this draft replies in chat, which the PM does not sign off or open
    by name in, matching how Chief actually writes chat replies."""
    drafts = [("chat:c_001", "On it, will call Luis today.")]
    problems = voice.draft_problems(drafts, world, CONFIG)
    assert problems == []


def test_a_clean_readout_version_has_no_problems():
    versions = [{"audience": "manager", "channel": "mail", "text": "Dana, the fix shipped. Thanks, S."}]
    assert voice.version_problems(versions, CONFIG) == []


def test_a_long_readout_version_is_flagged():
    versions = [{"audience": "manager", "channel": "mail", "text": "Dana, " + "word " * 121 + "Thanks, S."}]
    problems = voice.version_problems(versions, CONFIG)
    assert any(p["category"] == "length" for p in problems)


def test_a_chat_version_is_not_held_to_the_mail_signoff_rule():
    versions = [{"audience": "team", "channel": "chat", "text": "Team, the fix shipped."}]
    assert voice.version_problems(versions, CONFIG) == []


def test_the_live_server_rejects_a_brief_with_a_voice_problem(monkeypatch, tmp_path, now_run):
    monkeypatch.setenv("FACTORY_WORLD", str(now_run / "world" / "world.db"))
    monkeypatch.setenv("FACTORY_LEDGER", str(tmp_path / "ledger.jsonl"))
    monkeypatch.setenv("FACTORY_VOICE", str(install.load().voice))
    from factory.servers import ledger_server

    payload = {
        "date": "2026-03-02", "mode": "morning",
        "top": [{"ref": "mail:m_002", "goal": "g1", "why": "x", "next_step": "y",
                 "draft_reply": "Hi, I'll call Luis today."}],
    }
    result = ledger_server.write_entry("brief", payload)
    assert result["status"] == "rejection"
    assert "stock greeting" in result["message"] or "first name" in result["message"]
