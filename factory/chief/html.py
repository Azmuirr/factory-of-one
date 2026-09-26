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
ul { padding-left:20px; } li { margin:4px 0; }
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


def page(title: str, body: str, script: str = "") -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(title)}</title><style>{STYLE}</style></head><body><main>{body}</main>"
            f"{f'<script>{script}</script>' if script else ''}</body></html>")


class Links:
    def __init__(self, wp: Workplace):
        self.wp = wp
        self.drafts = 0
        self.shown: dict[str, str] = {}

    def label(self, ref: str) -> str:
        kind, rid = ref.split(":", 1)
        if kind == "mail":
            m = self.wp.mail_get(rid)
            return f"{m['from']['name']}: {m['subject']}" if m else ref
        if kind == "chat":
            msgs = self.wp.chat_thread(rid)
            return f"{msgs[0]['author']['name']} in {msgs[0]['where']}: {msgs[0]['text'][:80]}" if msgs else ref
        if kind == "cal":
            e = self.wp.event_get(rid)
            return f"{e['start'][11:16]} {e['title']}" if e else ref
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
        if item["ref"] in self.shown:
            return f'<div class="muted"><a href="#{self.shown[item["ref"]]}">Reply suggested above</a></div>'
        self.drafts += 1
        did = f"draft-{self.drafts}"
        self.shown[item["ref"]] = did
        return (f'<div class="draft"><p id="{did}">{escape(text)}</p>'
                f'<button data-copy="{did}">Copy reply</button> <span class="muted">Suggested. Nothing was sent.</span></div>')


def brief_html(entries: list[dict], wp: Workplace) -> str:
    brief = next((e["payload"] for e in reversed(entries) if e["type"] == "brief"), None)
    if not brief:
        return page("No brief", "<h1>No brief was written.</h1>")
    L = Links(wp)
    out = [f"<h1>Brief for {escape(brief['date'])}</h1>",
           f'<p class="muted">Focus time left today: {brief.get("focus_minutes", "unknown")} minutes. Every link opens the item itself.</p>',
           "<h2>Top 3</h2>"]
    for i, t in enumerate(brief["top"], 1):
        out.append(f'<div class="card"><span class="rank">{i}</span>{L.link(t)}<div>{escape(t["why"])}</div>'
                   f'<div class="muted">Next: {escape(t.get("next_step", ""))}</div>{L.draft(t)}</div>')
    if brief.get("needs_you"):
        out.append("<h2>Needs you in chat</h2>")
        out += [f'<div class="card">{L.link(n)}<div class="muted">{escape(n["why"])}</div>{L.draft(n)}</div>' for n in brief["needs_you"]]
    if brief.get("at_risk"):
        out.append("<h2>At risk this week</h2><ul>")
        out += [f"<li>{L.link(a)}: {escape(a['why'])}</li>" for a in brief["at_risk"]]
        out.append("</ul>")
    out.append("<h2>Calendar</h2><ul>")
    out += [f'<li><span class="tag">{escape(c["flag"].replace("_", " "))}</span> {L.link(c)}. {escape(c.get("suggestion", ""))}</li>'
            for c in brief["calendar"]]
    out.append("</ul><h2>Inbox</h2>")
    for label, title in LABELS.items():
        items = [t for t in brief["triage"] if t["label"] == label]
        if items:
            out.append(f"<h3>{title}</h3>")
            for t in items:
                warn = ' <span class="tag warn">suspicious</span>' if t.get("suspicious") else ""
                to = f' <span class="tag">to {escape(wp.person(t["delegate_to"])["name"])}</span>' if t.get("delegate_to") else ""
                out.append(f'<div class="card">{L.link(t)}{warn}{to}{L.draft(t)}</div>')
    commitments = [e for e in entries if e["type"] == "commitment"]
    if commitments:
        out.append("<h2>Commitments from meetings</h2><ul>")
        for e in commitments:
            c = e["payload"]
            out.append(f'<li><span class="tag">{escape(c["status"])}</span> {escape(wp.person(c["owner"])["name"])}: {escape(c["task"])} '
                       f'(due {escape(c["due"])}), from <a href="{escape(wp.url("tr", c["source"]["ref"]))}">the meeting transcript</a></li>')
        out.append("</ul>")
    return page(f"Brief for {brief['date']}", "".join(out), COPY_SCRIPT)


def workplace_html(wp: Workplace) -> str:
    me = wp.me["name"] if wp.me else "you"
    out = [f"<h1>Workplace: {escape(me)}</h1>",
           '<p class="muted">A read-only stand-in for mail, chat, calendar, transcripts, and the tracker. In a live install, links go to the real tools.</p>',
           '<nav><a href="#inbox">Inbox</a><a href="#chat">Chat</a><a href="#calendar">Calendar</a><a href="#transcripts">Transcripts</a><a href="#tracker">Tracker</a></nav>',
           '<h2 id="inbox">Inbox</h2>']
    for m in sorted(wp.mail_list(), key=lambda m: m["ts"], reverse=True):
        full = wp.mail_get(m["id"])
        out.append(f'<article class="card" id="mail-{escape(m["id"])}"><strong>{escape(m["subject"])}</strong>'
                   f'<div class="muted">{escape(m["from"]["name"])}, {escape(m["from"]["role"])} &middot; {escape(m["ts"])}</div>'
                   f'<pre>{escape(full["body"])}</pre></article>')
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
    return page(f"Workplace: {me}", "".join(out))


def write(entries: list[dict], wp: Workplace, out_dir: Path) -> Path:
    (out_dir / "workplace.html").write_text(workplace_html(wp), encoding="utf-8")
    path = out_dir / "brief.html"
    path.write_text(brief_html(entries, wp), encoding="utf-8")
    return path
