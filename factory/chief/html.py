"""Renders Chief's brief as a page with a link to every item and a copy button on every suggested reply.
In the sandbox it also renders workplace.html, a read-only viewer that stands in for mail, chat, and calendar."""

from __future__ import annotations

from html import escape
from pathlib import Path

from factory.workplace import Workplace

STYLE = """
:root { --bg:#f6f5f1; --card:#fff; --ink:#1c1c1a; --muted:#6a6963; --line:#e2e0d8; --accent:#1f5eff; --warn:#b3261e; --hi:#fff4cc; }
@media (prefers-color-scheme: dark) { :root { --bg:#151514; --card:#1f1f1d; --ink:#ecebe6; --muted:#a3a29b; --line:#34332f; --accent:#7aa2ff; --warn:#ff8a80; --hi:#3a3420; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:860px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:17px; margin:28px 0 10px; }
.muted { color:var(--muted); } a { color:var(--accent); }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:10px 0; }
.card:target { background:var(--hi); }
.rank { font-weight:700; color:var(--muted); margin-right:6px; }
.draft { margin:10px 0 0; border-left:3px solid var(--accent); padding:6px 10px; background:var(--bg); border-radius:0 6px 6px 0; }
.draft p { margin:0 0 6px; white-space:pre-wrap; }
button { font:inherit; font-size:13px; border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:6px; padding:3px 10px; cursor:pointer; }
.tag { font-size:12px; border:1px solid var(--line); border-radius:999px; padding:1px 8px; margin-left:6px; color:var(--muted); }
.warn { color:var(--warn); border-color:var(--warn); }
ul, ol { padding-left:20px; } li { margin:4px 0; }
pre { white-space:pre-wrap; font:inherit; margin:6px 0 0; }
nav a { margin-right:12px; }
"""

COPY_SCRIPT = """
document.querySelectorAll("button[data-copy]").forEach(b => b.addEventListener("click", () => {
  const text = document.getElementById(b.dataset.copy).innerText;
  (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).catch(() => {});
  b.textContent = "Copied";
  setTimeout(() => { b.textContent = "Copy reply"; }, 1500);
}));
"""

LABELS = {"act_now": "Act now", "delegate": "Delegate", "answer_later": "Answer later", "ignore": "Ignore"}
LOOPS = {"my_promises": "Your promises", "waiting_on_others": "Waiting on others", "waiting_on_me": "Waiting on you"}


def page(title: str, body: str, script: str = "") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(title)}</title><style>{STYLE}</style></head><body><main>{body}</main>"
            f"{f'<script>{script}</script>' if script else ''}</body></html>")


def tag(text: str, warn: bool = False) -> str:
    return f' <span class="tag{" warn" if warn else ""}">{escape(str(text))}</span>'


class Links:
    """Turns refs into labels and links, and renders each suggested reply once."""

    def __init__(self, wp: Workplace):
        self.wp = wp
        self.drafts = 0
        self.shown: dict[str, str] = {}

    def label(self, ref: str) -> str:
        kind, rid = ref.split(":", 1)
        if kind == "mail":
            m = self.wp.mail_get(rid)
            if not m:
                return ref
            sent = m["from"]["id"] == self.wp.my_id
            return f"{'To ' + m['to'][0]['name'] if sent else m['from']['name']}: {m['subject']}"
        if kind == "chat":
            msgs = self.wp.chat_thread(rid)
            return f"{msgs[0]['author']['name']} in {msgs[0]['where']}: {msgs[0]['text'][:80]}" if msgs else ref
        if kind == "cal":
            e = self.wp.event_get(rid)
            return f"{e['start'][11:16]} {e['title']}" if e else ref
        if kind == "tr":
            t = self.wp.transcript_get(rid)
            return f"Transcript: {t['title']}" if t else ref
        if kind == "doc":
            d = self.wp.doc_read(rid)
            return f"Doc: {d['title']}" if d else ref
        if kind == "req":
            r = self.wp.conn.execute("SELECT account, text FROM requests WHERE request_id = ?", (rid,)).fetchone()
            return f"{r['account']}: {r['text'][:70]}" if r else ref
        if kind == "trk":
            found = [i for i in self.wp.tracker_search() if i["issue_id"] == rid]
            return f"{rid}: {found[0]['title']}" if found else ref
        return ref

    def link(self, item: dict | str) -> str:
        ref = item if isinstance(item, str) else item["ref"]
        url = (None if isinstance(item, str) else item.get("url")) or self.wp.url(*ref.split(":", 1))
        return f'<a href="{escape(url)}">{escape(self.label(ref))}</a>'

    def draft(self, item: dict) -> str:
        text = item.get("draft_reply")
        if not text:
            return ""
        key = item.get("ref") or item.get("person", "")
        if key in self.shown:
            return f'<div class="muted"><a href="#{self.shown[key]}">Reply suggested above</a></div>'
        self.drafts += 1
        did = f"draft-{self.drafts}"
        self.shown[key] = did
        return (f'<div class="draft"><p id="{did}">{escape(text)}</p>'
                f'<button data-copy="{did}">Copy reply</button> <span class="muted">Suggested. Nothing was sent.</span></div>')


def brief_html(entries: list[dict], wp: Workplace) -> str:
    brief = next((e["payload"] for e in reversed(entries) if e["type"] == "brief"), None)
    if not brief:
        return page("No brief", "<h1>No brief was written.</h1>")
    L = Links(wp)
    goals = {g["id"]: g["title"] for g in wp.plan.get("goals", [])}
    mode = brief.get("mode", "morning")
    focus = f"Focus time left today: {brief['focus_minutes']} minutes. " if brief.get("focus_minutes") is not None else ""
    out = [f"<h1>{escape(mode.capitalize())} brief for {escape(brief['date'])}</h1>",
           f'<p class="muted">{focus}Every link opens the item itself.</p>', "<h2>Top 3</h2>"]
    for i, t in enumerate(brief["top"], 1):
        goal = tag(goals.get(t["goal"], t["goal"])) if t.get("goal") else ""
        out.append(f'<div class="card"><span class="rank">{i}</span>{L.link(t)}{goal}<div>{escape(t["why"])}</div>'
                   f'<div class="muted">Next: {escape(t.get("next_step", ""))}</div>{L.draft(t)}</div>')

    if brief.get("changes"):
        out.append("<h2>Changes for next week</h2><ol>" + "".join(f"<li>{escape(c)}</li>" for c in brief["changes"]) + "</ol>")
    if brief.get("done"):
        out.append("<h2>Done</h2><ul>" + "".join(f"<li>{L.link(r)}</li>" for r in brief["done"]) + "</ul>")
    if brief.get("goal_check"):
        out.append("<h2>Time against goals</h2><ul>")
        for g in brief["goal_check"]:
            out.append(f'<li>{tag(g["status"].replace("_", " "), g["status"] == "starved")} {escape(goals.get(g["goal"], g["goal"]))}: '
                       f'{g["hours"]} hours. {escape(g.get("note", ""))}</li>')
        out.append("</ul>")

    if brief.get("meeting_prep"):
        out.append("<h2>Meeting prep</h2>")
        for m in brief["meeting_prep"]:
            loops = ", ".join(L.link(r) for r in m.get("open_loops", []))
            out.append(f'<div class="card">{L.link(m)}<div><strong>Purpose:</strong> {escape(m["purpose"])}</div>'
                       f'<div><strong>Your ask:</strong> {escape(m["ask"])}</div><div class="muted">{escape(m.get("context", ""))}</div>'
                       + (f"<div>Open loops: {loops}</div>" if loops else "") + "</div>")

    if brief.get("needs_you"):
        out.append("<h2>Needs you in chat</h2>")
        out += [f'<div class="card">{L.link(n)}<div class="muted">{escape(n["why"])}</div>{L.draft(n)}</div>' for n in brief["needs_you"]]

    for side, title in LOOPS.items():
        items = brief.get("open_loops", {}).get(side, [])
        if items:
            out.append(f"<h2>{title}</h2>")
            for x in items:
                days = tag(f"{x['days']} days") if x.get("days") is not None else ""
                out.append(f'<div class="card">{L.link(x)}{days}<div class="muted">{escape(wp.person(x["who"])["name"])}: '
                           f'{escape(x["what"])}</div>{L.draft(x)}</div>')

    if brief.get("at_risk"):
        out.append("<h2>At risk this week</h2><ul>")
        out += [f"<li>{L.link(a)}: {escape(a['why'])}</li>" for a in brief["at_risk"]]
        out.append("</ul>")

    if brief.get("calendar"):
        out.append("<h2>Calendar</h2><ul>")
        for c in brief["calendar"]:
            move = f" Proposed new time: {escape(c['proposed_time'][11:16])}." if c.get("proposed_time") else ""
            out.append(f'<li>{tag(c["flag"].replace("_", " "))} {L.link(c)}. {escape(c.get("suggestion", ""))}{move}</li>')
        out.append("</ul>")

    if brief.get("followups"):
        out.append("<h2>Meeting follow-ups</h2>")
        for f in brief["followups"]:
            to = ", ".join(wp.person(p)["name"] for p in f["to"])
            out.append(f'<div class="card">{L.link(f)}{tag("to " + to)}{L.draft(f)}</div>')

    if brief.get("stale"):
        out.append("<h2>Stakeholders to reach</h2>")
        for st in brief["stale"]:
            out.append(f'<div class="card"><strong>{escape(wp.person(st["person"])["name"])}</strong>{tag(str(st["days_since"]) + " days")}'
                       f'<div>{escape(st["suggestion"])}</div>{L.draft(st)}</div>')

    if brief.get("triage"):
        out.append("<h2>Inbox</h2>")
        for label, title in LABELS.items():
            items = [t for t in brief["triage"] if t["label"] == label]
            if items:
                out.append(f"<h3>{title}</h3>")
                for t in items:
                    warn = tag("suspicious", True) if t.get("suspicious") else ""
                    to = tag("to " + wp.person(t["delegate_to"])["name"]) if t.get("delegate_to") else ""
                    out.append(f'<div class="card">{L.link(t)}{warn}{to}{L.draft(t)}</div>')

    commitments = [e for e in entries if e["type"] == "commitment"]
    if commitments:
        out.append("<h2>Commitments</h2><ul>")
        for e in commitments:
            c = e["payload"]
            kind = "tr" if c["source"]["source"] == "transcripts" else "mail"
            src = f'{kind}:{c["source"]["ref"]}'
            out.append(f'<li>{tag(c["status"])} {escape(wp.person(c["owner"])["name"])}: {escape(c["task"])} (due {escape(c["due"])}), '
                       f"from {L.link(src)}</li>")
        out.append("</ul>")
    return page(f"{mode.capitalize()} brief for {brief['date']}", "".join(out), COPY_SCRIPT)


def workplace_html(wp: Workplace) -> str:
    me = wp.me["name"] if wp.me else "you"
    out = [f"<h1>Workplace: {escape(me)}</h1>",
           '<p class="muted">A read-only stand-in for mail, chat, calendar, transcripts, and the tracker. In a live install, links go to the real tools.</p>',
           '<nav><a href="#inbox">Inbox</a><a href="#sent">Sent</a><a href="#chat">Chat</a><a href="#calendar">Calendar</a>'
           '<a href="#transcripts">Transcripts</a><a href="#tracker">Tracker</a><a href="#docs">Docs</a><a href="#requests">Requests</a></nav>']
    for anchor, title, items in (("inbox", "Inbox", wp.mail_list()), ("sent", "Sent", wp.sent_list())):
        out.append(f'<h2 id="{anchor}">{title}</h2>')
        for m in sorted(items, key=lambda m: m["ts"], reverse=True):
            full = wp.mail_get(m["id"])
            who = f"To {m['to'][0]['name']}" if anchor == "sent" else f"{m['from']['name']}, {m['from']['role']}"
            out.append(f'<article class="card" id="mail-{escape(m["id"])}"><strong>{escape(m["subject"])}</strong>'
                       f'<div class="muted">{escape(who)} &middot; {escape(m["ts"])}</div><pre>{escape(full["body"])}</pre></article>')
    out.append('<h2 id="chat">Chat</h2>')
    for c in wp.chat_list():
        out.append(f'<article class="card" id="chat-{escape(c["id"])}"><div class="muted">{escape(c["where"])} &middot; '
                   f'{escape(c["author"]["name"])} &middot; {escape(c["ts"])}</div><pre>{escape(c["text"])}</pre></article>')
    out.append('<h2 id="calendar">Calendar</h2>')
    for e in wp.calendar_list("2000-01-01", "2100-01-01")["events"]:
        who = ", ".join(a["name"] for a in e["attendees"])
        out.append(f'<article class="card" id="cal-{escape(e["id"])}"><strong>{escape(e["title"])}</strong>'
                   f'<div class="muted">{escape(e["start"])} to {escape(e["end"][11:16])} &middot; {escape(who)}</div>'
                   f'<div>Agenda: {escape(e["agenda"] or "none")}</div></article>')
    out.append('<h2 id="transcripts">Transcripts</h2>')
    for t in wp.transcripts_list():
        full = wp.transcript_get(t["id"])
        out.append(f'<article class="card" id="tr-{escape(t["id"])}"><strong>{escape(t["title"])}</strong>'
                   f'<div class="muted">{escape(t["ended"])}</div><pre>{escape(full["text"])}</pre></article>')
    out.append('<h2 id="tracker">Tracker</h2>')
    for i in wp.tracker_search():
        out.append(f'<article class="card" id="trk-{escape(i["issue_id"])}"><strong>{escape(i["issue_id"])}: {escape(i["title"])}</strong>'
                   f'<div class="muted">{escape(i["status"])} &middot; {escape(i["owner"]["name"])} &middot; due {escape(i["due"] or "none")}</div></article>')
    out.append('<h2 id="docs">Docs</h2>')
    for d in wp.docs_list():
        full = wp.doc_read(d["id"])
        out.append(f'<article class="card" id="doc-{escape(d["id"])}"><strong>{escape(d["title"])}</strong>'
                   f'<div class="muted">{escape(d["owner"]["name"])} &middot; {escape(d["updated"])}</div><pre>{escape(full["body"])}</pre></article>')
    out.append('<h2 id="requests">Customer requests</h2>')
    for r in wp.conn.execute("SELECT * FROM requests WHERE ts <= ? ORDER BY ts", (wp.cutoff,)).fetchall():
        out.append(f'<article class="card" id="req-{escape(r["request_id"])}"><strong>{escape(r["account"])}</strong>'
                   f'<div class="muted">{escape(r["tag"])} &middot; ${int(r["arr_at_stake"]):,} a year &middot; {escape(r["ts"])}</div><pre>{escape(r["text"])}</pre></article>')
    return page(f"Workplace: {me}", "".join(out))


def write(entries: list[dict], wp: Workplace, out_dir: Path) -> Path:
    (out_dir / "workplace.html").write_text(workplace_html(wp), encoding="utf-8")
    path = out_dir / "brief.html"
    path.write_text(brief_html(entries, wp), encoding="utf-8")
    return path
