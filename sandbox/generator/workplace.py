"""Writes a scenario's workplace (people, mail, chat, calendar, transcripts, tracker) into the world database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

SCHEMA = """
CREATE TABLE people (person_id TEXT PRIMARY KEY, name TEXT, role TEXT, team TEXT, manager_id TEXT, is_me INTEGER, external INTEGER);
CREATE TABLE mail (message_id TEXT PRIMARY KEY, ts TEXT, from_id TEXT, to_ids TEXT, in_reply_to TEXT, subject TEXT, body TEXT);
CREATE TABLE chat (message_id TEXT PRIMARY KEY, ts TEXT, channel TEXT, dm_members TEXT, author_id TEXT, mentions TEXT,
  thread_id TEXT, text TEXT);
CREATE TABLE calendar (event_id TEXT PRIMARY KEY, start TEXT, end TEXT, title TEXT, organizer_id TEXT, attendees TEXT, agenda TEXT);
CREATE TABLE transcripts (transcript_id TEXT PRIMARY KEY, event_id TEXT, ts TEXT, text TEXT);
CREATE TABLE tracker (issue_id TEXT PRIMARY KEY, title TEXT, status TEXT, owner_id TEXT, due TEXT, depends_on TEXT, updated TEXT);
CREATE TABLE docs (doc_id TEXT PRIMARY KEY, title TEXT, owner_id TEXT, updated TEXT, body TEXT);
CREATE TABLE requests (request_id TEXT PRIMARY KEY, ts TEXT, logged_by TEXT, account TEXT, arr_at_stake REAL, plan TEXT, tag TEXT, text TEXT);
"""


def write_workplace(conn: sqlite3.Connection, scenario_dir: Path, cutoff: str) -> dict:
    conn.executescript(SCHEMA)
    path = Path(scenario_dir) / "workplace.yaml"
    if not path.exists():
        return {}
    w = yaml.safe_load(path.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO meta VALUES (?, ?)", ("company_name", w["company"]))
    conn.executemany("INSERT INTO people VALUES (?,?,?,?,?,?,?)", [
        (p["id"], p["name"], p["role"], p["team"], p.get("manager"), int(p.get("me", False)), int(p.get("external", False)))
        for p in w["people"]
    ])
    conn.executemany("INSERT INTO mail VALUES (?,?,?,?,?,?,?)", [
        (m["id"], m["ts"], m["from"], json.dumps(m["to"]), m.get("in_reply_to"), m["subject"], m["body"])
        for m in w["mail"] if m["ts"] < cutoff
    ])
    conn.executemany("INSERT INTO chat VALUES (?,?,?,?,?,?,?,?)", [
        (c["id"], c["ts"], c.get("channel"), json.dumps(c["dm"]) if c.get("dm") else None, c["author"],
         json.dumps(c.get("mentions", [])), c.get("thread"), c["text"])
        for c in w["chat"] if c["ts"] < cutoff
    ])
    conn.executemany("INSERT INTO calendar VALUES (?,?,?,?,?,?,?)", [
        (e["id"], e["start"], e["end"], e["title"], e["organizer"], json.dumps(e["attendees"]), e.get("agenda", ""))
        for e in w["calendar"]
    ])
    ends = {e["id"]: e["end"] for e in w["calendar"]}
    conn.executemany("INSERT INTO transcripts VALUES (?,?,?,?)", [
        (t["id"], t["event"], ends[t["event"]], t["text"]) for t in w["transcripts"] if ends[t["event"]] < cutoff
    ])
    conn.executemany("INSERT INTO tracker VALUES (?,?,?,?,?,?,?)", [
        (i["id"], i["title"], i["status"], i["owner"], i.get("due"), i.get("depends_on"), i["updated"])
        for i in w["tracker"] if i["updated"] < cutoff
    ])
    conn.executemany("INSERT INTO docs VALUES (?,?,?,?,?)", [
        (d["id"], d["title"], d["owner"], d["updated"], d["body"]) for d in w.get("docs", []) if d["updated"] < cutoff
    ])
    conn.executemany("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?)", [
        (r["id"], r["ts"], r["logged_by"], r["account"], r["arr_at_stake"], r["plan"], r["tag"], r["text"])
        for r in w.get("requests", []) if r["ts"] < cutoff
    ])
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("people", "mail", "chat", "calendar", "transcripts", "tracker", "docs", "requests")}
