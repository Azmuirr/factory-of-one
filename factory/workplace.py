"""The PM's workplace, read through code that owns the checkable parts: sender weight, open loops, conflicts,
free time, time by goal, staleness, and privacy. Nothing here writes."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import yaml

DEADLINE = re.compile(r"\b(by|before|until)\s+(?:\w+\s+){0,2}?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|eod|noon|\d{1,2}(:\d{2})?\s?(am|pm)?|march \d+|mar \d+)\b|\b\d{1,2}:\d{2}\b", re.I)
REQUEST = re.compile(r"\?|\b(could you|can you|please|would you)\b", re.I)
PROMISE = re.compile(r"\b(I'll|I will|I'm going to)\b", re.I)
WORKDAY = (9, 18)
FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse(ts: str) -> datetime:
    """Accepts a date, or a date and time with or without Z. Returns naive UTC."""
    value = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    return value.replace(tzinfo=None) - (value.utcoffset() or timedelta(0))


class Workplace:
    def __init__(self, db_path: Path, link_base: str | None = None, as_of: str | None = None, goals_path: Path | None = None):
        self.conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        data_through = parse(self.conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0])
        as_of = as_of or os.environ.get("FACTORY_AS_OF")
        self.now = min(parse(as_of), data_through) if as_of else data_through
        self.cutoff = self.now.strftime(FMT)
        self.people = {r["person_id"]: dict(r) for r in self.conn.execute("SELECT * FROM people")}
        self.me = next((p for p in self.people.values() if p["is_me"]), None)
        company = self.conn.execute("SELECT value FROM meta WHERE key = 'company_name'").fetchone()
        self.company = company[0].lower() if company else None
        self.link_base = link_base or os.environ.get("FACTORY_LINK_BASE", "workplace.html")
        goals_path = goals_path or os.environ.get("FACTORY_GOALS")
        self.plan = yaml.safe_load(Path(goals_path).read_text(encoding="utf-8")) if goals_path and Path(goals_path).exists() else {}

    def __enter__(self) -> "Workplace":
        return self

    def __exit__(self, *_) -> None:
        self.conn.close()

    def url(self, kind: str, item_id: str) -> str:
        """Where the item lives. In the sandbox, an anchor in the generated workplace viewer."""
        return f"{self.link_base}#{kind}-{item_id}"

    @property
    def my_id(self) -> str:
        return self.me["person_id"] if self.me else ""

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
        if p["manager_id"] == self.my_id:
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

    def days_since(self, ts: str) -> float:
        return round((self.now - parse(ts)).total_seconds() / 86400, 1)

    # Mail ----------------------------------------------------------------------

    def mail_rows(self):
        return self.conn.execute("SELECT * FROM mail WHERE ts <= ? ORDER BY ts", (self.cutoff,)).fetchall()

    def replied(self, message_id: str, by: str) -> bool:
        return bool(self.conn.execute("SELECT 1 FROM mail WHERE in_reply_to = ? AND from_id = ? AND ts <= ?",
                                      (message_id, by, self.cutoff)).fetchone())

    def mail_item(self, r) -> dict:
        return {"id": r["message_id"], "url": self.url("mail", r["message_id"]), "ts": r["ts"], "from": self.person(r["from_id"]),
                "to": [self.person(t) for t in json.loads(r["to_ids"])], "in_reply_to": r["in_reply_to"],
                "subject": r["subject"], "snippet": r["body"][:160],
                "deadline_hint": bool(DEADLINE.search(r["subject"] + " " + r["body"])),
                "hours_old": round((self.now - parse(r["ts"])).total_seconds() / 3600, 1)}

    def mail_list(self, since: str | None = None) -> list[dict]:
        """The inbox: mail to the PM from someone else, with whether the PM has replied."""
        return [{**self.mail_item(r), "replied": self.replied(r["message_id"], self.my_id)} for r in self.mail_rows()
                if r["from_id"] != self.my_id and r["ts"] >= (since or "0000")]

    def sent_list(self, since: str | None = None) -> list[dict]:
        return [{**self.mail_item(r), "answered": any(self.replied(r["message_id"], t) for t in json.loads(r["to_ids"]))}
                for r in self.mail_rows() if r["from_id"] == self.my_id and r["ts"] >= (since or "0000")]

    def mail_get(self, message_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM mail WHERE message_id = ? AND ts <= ?", (message_id, self.cutoff)).fetchone()
        return {**self.mail_item(r), "body": r["body"]} if r else None

    # Chat ----------------------------------------------------------------------

    def visible(self, row) -> bool:
        return row["channel"] is not None or self.my_id in json.loads(row["dm_members"] or "[]")

    def chat_item(self, r) -> dict:
        mentions = json.loads(r["mentions"] or "[]")
        to_me = bool(self.me) and r["author_id"] != self.my_id and (self.my_id in mentions or r["channel"] is None)
        replied = self.conn.execute("SELECT 1 FROM chat WHERE thread_id = ? AND author_id = ? AND ts <= ?",
                                    (r["message_id"], self.my_id, self.cutoff)).fetchone()
        return {"id": r["message_id"], "url": self.url("chat", r["message_id"]), "ts": r["ts"],
                "where": f"#{r['channel']}" if r["channel"] else "direct message",
                "author": self.person(r["author_id"]), "text": r["text"], "thread": r["thread_id"], "addressed_to_me": to_me,
                "unanswered_hours": round((self.now - parse(r["ts"])).total_seconds() / 3600, 1) if to_me and not replied else None}

    def chat_rows(self):
        return [r for r in self.conn.execute("SELECT * FROM chat WHERE ts <= ? ORDER BY ts", (self.cutoff,)) if self.visible(r)]

    def chat_list(self, since: str | None = None, channel: str | None = None) -> list[dict]:
        return [self.chat_item(r) for r in self.chat_rows()
                if r["ts"] >= (since or "0000") and (channel is None or r["channel"] == channel.lstrip("#"))]

    def chat_thread(self, message_id: str) -> list[dict]:
        return [self.chat_item(r) for r in self.chat_rows() if r["message_id"] == message_id or r["thread_id"] == message_id]

    # Open loops and people -----------------------------------------------------

    def open_loops(self) -> dict:
        """Waiting on the PM: unanswered mail and chat addressed to them. Waiting on others: the PM's requests with no reply."""
        mine = {m["id"] for m in self.sent_list()}
        on_me = [{"ref": f"mail:{m['id']}", "url": m["url"], "who": m["from"]["id"], "since": m["ts"], "days": self.days_since(m["ts"]),
                  "what": m["subject"]} for m in self.mail_list()
                 if not m["replied"] and m["from"]["weight"] > 0 and m["in_reply_to"] not in mine]
        on_me += [{"ref": f"chat:{c['id']}", "url": c["url"], "who": c["author"]["id"], "since": c["ts"], "days": self.days_since(c["ts"]),
                   "what": c["text"][:100]} for c in self.chat_list() if c["unanswered_hours"] is not None]
        on_others = []
        for m in self.sent_list():
            body = self.mail_get(m["id"])["body"]
            if REQUEST.search(body) and not m["answered"] and not m["in_reply_to"]:
                on_others.append({"ref": f"mail:{m['id']}", "url": m["url"], "who": m["to"][0]["id"], "since": m["ts"],
                                  "days": self.days_since(m["ts"]), "what": m["subject"]})
        promises = [{"ref": f"mail:{m['id']}", "url": m["url"], "who": m["to"][0]["id"], "since": m["ts"], "days": self.days_since(m["ts"]),
                     "what": self.mail_get(m["id"])["body"]} for m in self.sent_list() if PROMISE.search(self.mail_get(m["id"])["body"])]
        promises += [{"ref": f"chat:{r['message_id']}", "url": self.url("chat", r["message_id"]),
                      "who": next((p for p in json.loads(r["dm_members"] or "[]") if p != self.my_id), None),
                      "since": r["ts"], "days": self.days_since(r["ts"]), "what": r["text"]}
                     for r in self.chat_rows() if r["author_id"] == self.my_id and PROMISE.search(r["text"])]
        return {"waiting_on_me": sorted(on_me, key=lambda x: -x["days"]), "waiting_on_others": sorted(on_others, key=lambda x: -x["days"]),
                "my_promises": sorted(promises, key=lambda x: -x["days"])}

    def people_history(self, pid: str, limit: int = 5) -> dict:
        """The PM's direct contact with one person: mail either way, direct messages, and meetings together."""
        touches = []
        for r in self.mail_rows():
            to = json.loads(r["to_ids"])
            if (r["from_id"] == pid and self.my_id in to) or (r["from_id"] == self.my_id and pid in to):
                touches.append({"ts": r["ts"], "kind": "mail", "ref": f"mail:{r['message_id']}", "what": r["subject"]})
        for r in self.chat_rows():
            if r["channel"] is None and pid in json.loads(r["dm_members"]):
                touches.append({"ts": r["ts"], "kind": "direct message", "ref": f"chat:{r['message_id']}", "what": r["text"][:80]})
        for r in self.conn.execute("SELECT * FROM calendar WHERE end <= ?", (self.cutoff,)):
            people = json.loads(r["attendees"])
            if pid in people and self.my_id in people:
                touches.append({"ts": r["end"], "kind": "meeting", "ref": f"cal:{r['event_id']}", "what": r["title"]})
        touches.sort(key=lambda t: t["ts"], reverse=True)
        return {"person": self.person(pid), "last_touch": touches[0]["ts"] if touches else None,
                "days_since": self.days_since(touches[0]["ts"]) if touches else None, "recent": touches[:limit]}

    def stale_stakeholders(self) -> list[dict]:
        """Stakeholders the PM has not been in direct contact with for longer than the cadence they set."""
        out = []
        for s in self.plan.get("stakeholders", []):
            h = self.people_history(s["person"])
            days = h["days_since"]
            if days is None or days > s["every_days"]:
                out.append({"person": h["person"], "every_days": s["every_days"], "days_since": days, "last_touch": h["recent"][:1]})
        return out

    def writing_samples(self, limit: int = 8) -> list[str]:
        mail = [r["body"] for r in self.mail_rows() if r["from_id"] == self.my_id]
        chat = [r["text"] for r in self.chat_rows() if r["author_id"] == self.my_id]
        return (mail + chat)[-limit:]

    # Calendar ------------------------------------------------------------------

    def my_events(self, start: str, end: str):
        start, end = (parse(t).strftime(FMT) for t in (start, end))
        return [r for r in self.conn.execute("SELECT * FROM calendar WHERE start < ? AND end > ? ORDER BY start", (end, start))
                if self.my_id in json.loads(r["attendees"])]

    def calendar_list(self, start: str, end: str) -> dict:
        rows = self.my_events(start, end)
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
                "goals": self.goals_for(f"{r['title']} {r['agenda']}"),
            })
        focus = {d: sum(e - s for s, e in slots) // 60 for d, slots in self.free_intervals(start, end).items()}
        return {"events": events, "focus_minutes_by_day": focus}

    def event_get(self, event_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM calendar WHERE event_id = ?", (event_id,)).fetchone()
        return {"id": r["event_id"], "url": self.url("cal", r["event_id"]), "start": r["start"], "end": r["end"], "title": r["title"],
                "attendees": json.loads(r["attendees"]), "agenda": r["agenda"]} if r else None

    def free_intervals(self, start: str, end: str) -> dict:
        """Free time per day inside working hours, as seconds from midnight. Solo blocks such as Focus count as free."""
        rows = [r for r in self.my_events(start, end) if len(json.loads(r["attendees"])) > 1]
        out, day = {}, parse(start).replace(hour=0, minute=0, second=0)
        while day < parse(end):
            window = (day.replace(hour=WORKDAY[0]), day.replace(hour=WORKDAY[1]))
            busy = sorted((max(parse(r["start"]), window[0]), min(parse(r["end"]), window[1]))
                          for r in rows if parse(r["start"]) < window[1] and parse(r["end"]) > window[0])
            free, cursor = [], window[0]
            for s, e in busy:
                if s > cursor:
                    free.append((cursor, s))
                cursor = max(cursor, e)
            if cursor < window[1]:
                free.append((cursor, window[1]))
            out[day.date().isoformat()] = [(int((s - day).total_seconds()), int((e - day).total_seconds())) for s, e in free]
            day += timedelta(days=1)
        return out

    def free_slots(self, date: str, minutes: int = 30) -> list[dict]:
        day = parse(date).replace(hour=0, minute=0, second=0)
        slots = self.free_intervals(day.strftime(FMT), (day + timedelta(days=1)).strftime(FMT))[day.date().isoformat()]
        return [{"start": (day + timedelta(seconds=s)).strftime(FMT), "end": (day + timedelta(seconds=e)).strftime(FMT),
                 "minutes": (e - s) // 60} for s, e in slots if (e - s) >= minutes * 60]

    def is_free(self, start: str, minutes: int, ignore: str | None = None) -> bool:
        s = parse(start)
        e = s + timedelta(minutes=minutes)
        rows = [r for r in self.my_events(s.strftime("%Y-%m-%d"), (s + timedelta(days=1)).strftime("%Y-%m-%d"))
                if r["event_id"] != ignore and len(json.loads(r["attendees"])) > 1]
        inside = s.hour >= WORKDAY[0] and e <= s.replace(hour=WORKDAY[1], minute=0, second=0)
        return inside and not any(parse(r["start"]) < e and parse(r["end"]) > s for r in rows)

    def meeting_context(self, event_id: str) -> dict | None:
        """Everything to prepare for one meeting: attendees, last contact with each, open loops with them, related past meetings."""
        e = self.event_get(event_id)
        if not e:
            return None
        others = [a for a in e["attendees"] if a != self.my_id]
        loops = self.open_loops()
        related = [loop for side in loops.values() for loop in side if loop["who"] in others]
        past = []
        for r in self.conn.execute("SELECT * FROM calendar WHERE end <= ? ORDER BY end DESC", (self.cutoff,)):
            people = json.loads(r["attendees"])
            if set(people) & set(others) and self.my_id in people:
                t = self.conn.execute("SELECT transcript_id FROM transcripts WHERE event_id = ?", (r["event_id"],)).fetchone()
                past.append({"ref": f"cal:{r['event_id']}", "title": r["title"], "end": r["end"], "transcript": t[0] if t else None})
        return {"event": {**e, "attendees": [self.person(a) for a in e["attendees"]]},
                "attendees": [{"person": self.person(a), "last_touch": self.people_history(a)["last_touch"]} for a in others],
                "open_loops": related, "past_meetings": past[:3], "goals": self.goals_for(f"{e['title']} {e['agenda']}")}

    # Goals ---------------------------------------------------------------------

    def goals_for(self, text: str) -> list[str]:
        t = text.lower()
        return [g["id"] for g in self.plan.get("goals", []) if any(k in t for k in g["keywords"])]

    def time_by_goal(self, start: str, end: str) -> dict:
        """Meeting hours per goal in a period, matched by each goal's keywords. A goal with under a third of its weight is starved."""
        hours = {g["id"]: 0.0 for g in self.plan.get("goals", [])}
        other = 0.0
        for r in self.my_events(start, end):
            if len(json.loads(r["attendees"])) < 2:
                continue
            length = (parse(r["end"]) - parse(r["start"])).total_seconds() / 3600
            matched = self.goals_for(f"{r['title']} {r['agenda']}")
            for g in matched:
                hours[g] += length / len(matched)
            if not matched:
                other += length
        total = sum(hours.values()) + other
        goals = []
        for g in self.plan.get("goals", []):
            share = hours[g["id"]] / total if total else 0.0
            goals.append({"goal": g["id"], "title": g["title"], "weight": g["weight"], "hours": round(hours[g["id"]], 2),
                          "share": round(share, 3), "starved": share < g["weight"] / 3})
        return {"period": {"start": start, "end": end}, "goals": goals, "other_hours": round(other, 2), "total_hours": round(total, 2)}

    # Transcripts and tracker -----------------------------------------------------

    def transcripts_list(self, since: str | None = None) -> list[dict]:
        rows = self.conn.execute("""SELECT t.transcript_id, t.event_id, t.ts, c.title, c.attendees, c.organizer_id FROM transcripts t
                                    JOIN calendar c USING (event_id) WHERE t.ts >= ? AND t.ts <= ? ORDER BY t.ts""",
                                 (since or "0000", self.cutoff)).fetchall()
        return [{"id": r["transcript_id"], "url": self.url("tr", r["transcript_id"]), "event": r["event_id"], "ended": r["ts"],
                 "title": r["title"], "organized_by_me": r["organizer_id"] == self.my_id,
                 "attendees": [self.person(a) for a in json.loads(r["attendees"])]} for r in rows]

    def transcript_get(self, transcript_id: str) -> dict | None:
        r = self.conn.execute("""SELECT t.*, c.title, c.attendees FROM transcripts t JOIN calendar c USING (event_id)
                                 WHERE t.transcript_id = ? AND t.ts <= ?""", (transcript_id, self.cutoff)).fetchone()
        if not r:
            return None
        return {"id": r["transcript_id"], "url": self.url("tr", r["transcript_id"]), "event": r["event_id"], "ended": r["ts"],
                "title": r["title"], "attendees": [self.person(a) for a in json.loads(r["attendees"])], "text": r["text"]}

    def untranscribed_meetings(self, since: str) -> list[dict]:
        rows = self.conn.execute("""SELECT event_id, title, start FROM calendar WHERE end < ? AND start >= ?
                                    AND event_id NOT IN (SELECT event_id FROM transcripts)""", (self.cutoff, since)).fetchall()
        return [{"id": r["event_id"], "title": r["title"], "start": r["start"]} for r in rows]

    def tracker_search(self, query: str | None = None, status: str | None = None) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM tracker WHERE updated <= ?", (self.cutoff,)).fetchall()
        q = (query or "").lower()
        return [{**dict(r), "url": self.url("trk", r["issue_id"]), "owner": self.person(r["owner_id"])} for r in rows
                if (not q or q in r["title"].lower() or q in r["issue_id"].lower()) and (not status or r["status"].lower() == status.lower())]
