"""The PM's workplace, read through code that owns the checkable parts: sender weight, conflicts, focus time,
unanswered time, and privacy. Nothing here writes."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DEADLINE = re.compile(r"\b(by|before|until)\s+(?:\w+\s+){0,2}?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|eod|noon|\d{1,2}(:\d{2})?\s?(am|pm)?|march \d+|mar \d+)\b|\b\d{1,2}:\d{2}\b", re.I)
WORKDAY = (9, 18)


def parse(ts: str) -> datetime:
    """Accepts a date, or a date and time with or without Z. Returns naive UTC."""
    value = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    return value.replace(tzinfo=None) - (value.utcoffset() or timedelta(0))


class Workplace:
    def __init__(self, db_path: Path, link_base: str | None = None):
        self.conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self.now = parse(self.conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0])
        self.people = {r["person_id"]: dict(r) for r in self.conn.execute("SELECT * FROM people")}
        self.me = next((p for p in self.people.values() if p["is_me"]), None)
        company = self.conn.execute("SELECT value FROM meta WHERE key = 'company_name'").fetchone()
        self.company = company[0].lower() if company else None
        self.link_base = link_base or os.environ.get("FACTORY_LINK_BASE", "workplace.html")

    def url(self, kind: str, item_id: str) -> str:
        """Where the item lives. In the sandbox, an anchor in the generated workplace viewer."""
        return f"{self.link_base}#{kind}-{item_id}"

    def __enter__(self) -> "Workplace":
        return self

    def __exit__(self, *_) -> None:
        self.conn.close()

    # People --------------------------------------------------------------------

    def weight(self, pid: str) -> int:
        """Sender importance from the org chart: 3 exec or my manager, 2 leads, peers, and customers, 1 my reports, 0 unsolicited."""
        p = self.people.get(pid)
        if not p or not self.me:
            return 0
        role = p["role"].lower()
        if p["external"]:
            return 2 if ("director" in role or "manager" in role) and not self.suspicious(pid) else 0
        if pid == self.me["manager_id"] or any(k in role for k in ("ceo", "coo", "cto", "vp")):
            return 3
        if p["manager_id"] == self.me["person_id"]:
            return 1
        return 2

    def suspicious(self, pid: str) -> bool:
        """An external sender whose organization imitates the company's own name."""
        p = self.people.get(pid)
        return bool(p and p["external"] and self.company and self.company in p["team"].lower())

    def person(self, pid: str) -> dict:
        p = self.people.get(pid, {"person_id": pid, "name": pid, "role": "unknown", "team": "", "external": 1})
        return {"id": pid, "name": p["name"], "role": p["role"], "team": p["team"], "external": bool(p["external"]),
                "weight": self.weight(pid), "suspicious": self.suspicious(pid)}

    def lookup(self, query: str) -> list[dict]:
        q = query.lower()
        found = [p for p in self.people.values() if q in p["name"].lower() or q in p["role"].lower() or q in p["team"].lower() or q == p["person_id"]]
        return [{**self.person(p["person_id"]), "manager": p["manager_id"],
                 "reports": [r["person_id"] for r in self.people.values() if r["manager_id"] == p["person_id"]]} for p in found]

    # Mail ----------------------------------------------------------------------

    def mail_list(self, since: str | None = None) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM mail WHERE ts >= ? ORDER BY ts", (since or "0000",)).fetchall()
        return [{"id": r["message_id"], "url": self.url("mail", r["message_id"]), "ts": r["ts"], "from": self.person(r["from_id"]), "subject": r["subject"],
                 "snippet": r["body"][:160], "deadline_hint": bool(DEADLINE.search(r["subject"] + " " + r["body"])),
                 "hours_old": round((self.now - parse(r["ts"])).total_seconds() / 3600, 1)} for r in rows]

    def mail_get(self, message_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM mail WHERE message_id = ?", (message_id,)).fetchone()
        if not r:
            return None
        return {"id": r["message_id"], "url": self.url("mail", r["message_id"]), "ts": r["ts"], "from": self.person(r["from_id"]),
                "to": [self.person(t) for t in json.loads(r["to_ids"])], "subject": r["subject"], "body": r["body"]}

    # Chat ----------------------------------------------------------------------

    def visible(self, row) -> bool:
        return row["channel"] is not None or (self.me and self.me["person_id"] in json.loads(row["dm_members"] or "[]"))

    def chat_item(self, r) -> dict:
        mentions = json.loads(r["mentions"] or "[]")
        to_me = bool(self.me) and (self.me["person_id"] in mentions or (r["channel"] is None and r["author_id"] != self.me["person_id"]))
        replied = self.conn.execute("SELECT 1 FROM chat WHERE thread_id = ? AND author_id = ?",
                                    (r["message_id"], self.me["person_id"] if self.me else "")).fetchone()
        return {"id": r["message_id"], "url": self.url("chat", r["message_id"]), "ts": r["ts"], "where": f"#{r['channel']}" if r["channel"] else "direct message",
                "author": self.person(r["author_id"]), "text": r["text"], "thread": r["thread_id"],
                "addressed_to_me": to_me,
                "unanswered_hours": round((self.now - parse(r["ts"])).total_seconds() / 3600, 1) if to_me and not replied else None}

    def chat_list(self, since: str | None = None, channel: str | None = None) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM chat WHERE ts >= ? ORDER BY ts", (since or "0000",)).fetchall()
        return [self.chat_item(r) for r in rows if self.visible(r) and (channel is None or r["channel"] == channel.lstrip("#"))]

    def chat_thread(self, message_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM chat WHERE message_id = ? OR thread_id = ? ORDER BY ts", (message_id, message_id)).fetchall()
        return [self.chat_item(r) for r in rows if self.visible(r)]

    # Calendar ------------------------------------------------------------------

    def calendar_list(self, start: str, end: str) -> dict:
        start, end = (parse(t).strftime("%Y-%m-%dT%H:%M:%SZ") for t in (start, end))
        rows = [r for r in self.conn.execute("SELECT * FROM calendar WHERE start < ? AND end > ? ORDER BY start", (end, start))
                if self.me and self.me["person_id"] in json.loads(r["attendees"])]
        events = []
        for r in rows:
            s, e = parse(r["start"]), parse(r["end"])
            conflicts = [o["event_id"] for o in rows if o["event_id"] != r["event_id"] and parse(o["start"]) < e and parse(o["end"]) > s]
            adjacent = [o["event_id"] for o in rows if o["event_id"] != r["event_id"] and (parse(o["start"]) == e or parse(o["end"]) == s)]
            attendees = [self.person(a) for a in json.loads(r["attendees"])]
            events.append({
                "id": r["event_id"], "url": self.url("cal", r["event_id"]), "start": r["start"], "end": r["end"], "title": r["title"],
                "organizer": self.person(r["organizer_id"]), "attendees": attendees, "agenda": r["agenda"],
                "no_agenda": not r["agenda"].strip() and len(attendees) > 1,
                "conflicts_with": conflicts, "back_to_back_with": adjacent,
                "unsolicited": self.person(r["organizer_id"])["weight"] == 0,
            })
        return {"events": events, "focus_minutes_by_day": self.focus_minutes(rows, start, end)}

    def event_get(self, event_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM calendar WHERE event_id = ?", (event_id,)).fetchone()
        return {"id": r["event_id"], "url": self.url("cal", r["event_id"]), "start": r["start"], "end": r["end"], "title": r["title"]} if r else None

    def focus_minutes(self, rows, start: str, end: str) -> dict:
        out = {}
        day = parse(start).replace(hour=0, minute=0, second=0)
        while day < parse(end):
            window = (day.replace(hour=WORKDAY[0]), day.replace(hour=WORKDAY[1]))
            busy = sorted((max(parse(r["start"]), window[0]), min(parse(r["end"]), window[1]))
                          for r in rows if parse(r["start"]) < window[1] and parse(r["end"]) > window[0]
                          and len(json.loads(r["attendees"])) > 1)
            free, cursor = 0, window[0]
            for s, e in busy:
                if s > cursor:
                    free += (s - cursor).total_seconds() / 60
                cursor = max(cursor, e)
            free += max(0, (window[1] - cursor).total_seconds() / 60)
            out[day.date().isoformat()] = int(free)
            day += timedelta(days=1)
        return out

    # Transcripts and tracker -----------------------------------------------------

    def transcripts_list(self, since: str | None = None) -> list[dict]:
        rows = self.conn.execute("""SELECT t.transcript_id, t.event_id, t.ts, c.title, c.attendees FROM transcripts t
                                    JOIN calendar c USING (event_id) WHERE t.ts >= ? ORDER BY t.ts""", (since or "0000",)).fetchall()
        return [{"id": r["transcript_id"], "url": self.url("tr", r["transcript_id"]), "event": r["event_id"], "ended": r["ts"], "title": r["title"],
                 "attendees": [self.person(a) for a in json.loads(r["attendees"])]} for r in rows]

    def transcript_get(self, transcript_id: str) -> dict | None:
        r = self.conn.execute("""SELECT t.*, c.title, c.attendees FROM transcripts t JOIN calendar c USING (event_id)
                                 WHERE t.transcript_id = ?""", (transcript_id,)).fetchone()
        if not r:
            return None
        return {"id": r["transcript_id"], "url": self.url("tr", r["transcript_id"]), "event": r["event_id"], "ended": r["ts"], "title": r["title"],
                "attendees": [self.person(a) for a in json.loads(r["attendees"])], "text": r["text"]}

    def untranscribed_meetings(self, since: str) -> list[dict]:
        rows = self.conn.execute("""SELECT event_id, title, start FROM calendar WHERE end < ? AND start >= ?
                                    AND event_id NOT IN (SELECT event_id FROM transcripts)""",
                                 (self.now.strftime("%Y-%m-%dT%H:%M:%SZ"), since)).fetchall()
        return [{"id": r["event_id"], "title": r["title"], "start": r["start"]} for r in rows]

    def tracker_search(self, query: str | None = None, status: str | None = None) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM tracker").fetchall()
        q = (query or "").lower()
        return [{**dict(r), "url": self.url("trk", r["issue_id"]), "owner": self.person(r["owner_id"])} for r in rows
                if (not q or q in r["title"].lower() or q in r["issue_id"].lower()) and (not status or r["status"].lower() == status.lower())]
