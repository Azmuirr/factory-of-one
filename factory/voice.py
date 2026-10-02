"""The PM's writing voice, owned by code: one config (company/tallybird/voice.yaml, not a scenario answer key),
checked the same way whether the write happens live or in an eval. Chief's draft replies and Comms' readout
versions both go through here."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import yaml


def load(path: Path | str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def config_path() -> Path | None:
    raw = os.environ.get("FACTORY_VOICE")
    return Path(raw) if raw else None


def all_drafts(brief: dict) -> list[tuple[str, str]]:
    out = []
    for section in ("top", "needs_you", "triage", "followups", "stale"):
        for item in brief.get(section, []):
            if item.get("draft_reply"):
                out.append((item.get("ref", ""), item["draft_reply"]))
    for side in ("waiting_on_me", "waiting_on_others", "my_promises"):
        for item in brief.get("open_loops", {}).get(side, []):
            if item.get("draft_reply"):
                out.append((item["ref"], item["draft_reply"]))
    return out


def _recipient_first_name(world_path: Path, ref: str) -> str | None:
    if not ref.startswith("mail:"):
        return None
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    row = conn.execute("SELECT from_id, to_ids FROM mail WHERE message_id = ?", (ref.split(":", 1)[1],)).fetchone()
    if not row:
        conn.close()
        return None
    from_id, to_ids = row
    import json

    me = conn.execute("SELECT person_id FROM people WHERE is_me = 1").fetchone()
    my_id = me[0] if me else None
    to_id = from_id if from_id != my_id else json.loads(to_ids)[0]
    name_row = conn.execute("SELECT name FROM people WHERE person_id = ?", (to_id,)).fetchone()
    conn.close()
    return name_row[0].split()[0] if name_row else None


def draft_problems(drafts: list[tuple[str, str]], world_path: Path, config: dict) -> list[dict]:
    """Every draft reply: short, signed off, opens with the recipient's first name, no stock opening. Each
    problem names its ref and category, so a caller can report them grouped or flat."""
    problems = []
    max_words = config["max_words"]["draft_reply"]
    for ref, text in drafts:
        if len(text.split()) > max_words:
            problems.append({"ref": ref, "category": "length", "message": f"{ref}: draft reply is over {max_words} words"})
        if ref.startswith("mail:") and not text.rstrip().endswith(config["signoff"]):
            problems.append({"ref": ref, "category": "signoff", "message": f"{ref}: draft reply does not end with the sign-off {config['signoff']!r}"})
        opener = text.strip().split()[0].strip(",").lower() if text.strip() else ""
        if opener in config["banned_openings"]:
            problems.append({"ref": ref, "category": "opening", "message": f"{ref}: draft reply opens with a stock greeting ({opener!r})"})
        name = _recipient_first_name(world_path, ref)
        if name and not text.startswith(name + ","):
            problems.append({"ref": ref, "category": "name", "message": f"{ref}: draft reply does not open with the recipient's first name ({name!r})"})
    return problems


def version_problems(versions: list[dict], config: dict) -> list[dict]:
    """Every readout version: short, and mail carries the sign-off with no stock opening."""
    problems = []
    max_words = config["max_words"]["readout"]
    for v in versions:
        ref = v["audience"]
        if len(v["text"].split()) > max_words:
            problems.append({"ref": ref, "category": "length", "message": f"{ref}: readout version is over {max_words} words"})
        if v.get("channel") == "mail" and not v["text"].rstrip().endswith(config["signoff"]):
            problems.append({"ref": ref, "category": "signoff", "message": f"{ref}: mail version does not end with the sign-off {config['signoff']!r}"})
        opener = v["text"].strip().split()[0].strip(",").lower() if v["text"].strip() else ""
        if opener in config["banned_openings"]:
            problems.append({"ref": ref, "category": "opening", "message": f"{ref}: readout version opens with a stock greeting ({opener!r})"})
    return problems
