from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

from .baseline import DAY, EPOCH
from .model import World
from .scenario import Action, Scenario, day_index

WORLD_SCHEMA = """
CREATE TABLE workspaces (workspace_id TEXT PRIMARY KEY, created_at TEXT, channel TEXT, company_size TEXT,
  calendar_provider TEXT, referrer_workspace_id TEXT);
CREATE TABLE users (user_id TEXT PRIMARY KEY, workspace_id TEXT, role TEXT, created_at TEXT);
CREATE TABLE events (event_id TEXT PRIMARY KEY, ts TEXT, workspace_id TEXT, user_id TEXT, product TEXT,
  name TEXT, props TEXT);
CREATE TABLE subscriptions (workspace_id TEXT, ts TEXT, plan TEXT, seats INTEGER, billing TEXT, mrr REAL);
CREATE TABLE releases (release_id TEXT PRIMARY KEY, ts TEXT, title TEXT, notes TEXT, flag TEXT);
CREATE TABLE flags (flag TEXT, segment_filter TEXT, percent REAL, ts TEXT);
CREATE TABLE assignments (workspace_id TEXT, experiment_id TEXT, arm TEXT, ts TEXT);
CREATE TABLE tickets (ticket_id TEXT PRIMARY KEY, created_at TEXT, workspace_id TEXT, user_id TEXT,
  subject TEXT, body TEXT, support_tag TEXT);
CREATE TABLE messages (message_id TEXT PRIMARY KEY, ts TEXT, from_role TEXT, subject TEXT, body TEXT);
CREATE TABLE actions (action_id TEXT PRIMARY KEY, ts TEXT, name TEXT, params TEXT, decided_by TEXT);
CREATE INDEX events_ws ON events (workspace_id);
CREATE INDEX events_name_ts ON events (name, ts);
"""

TRUTH_SCHEMA = """
CREATE TABLE latents (workspace_id TEXT PRIMARY KEY, p_base REAL, requires_admin_consent INTEGER,
  blocked_by TEXT, releases_applied TEXT, activated_at TEXT);
CREATE TABLE planted (scenario_id TEXT, version TEXT, seed INTEGER, cutoff TEXT);
"""


def iso(seconds: float) -> str:
    return (EPOCH + timedelta(seconds=float(seconds))).strftime("%Y-%m-%dT%H:%M:%SZ")


def fresh_db(path: Path, schema: str) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    return conn


def write_world(path: Path, world: World, scenario: Scenario, actions: list[Action], cutoff: float) -> dict:
    conn = fresh_db(path, WORLD_SCHEMA)
    ws_rows = [w for w in world.workspaces if w.created_at < cutoff]
    conn.executemany("INSERT INTO workspaces VALUES (?,?,?,?,?,?)", [
        (w.workspace_id, iso(w.created_at), w.channel, w.company_size, w.calendar_provider, w.referrer_workspace_id)
        for w in ws_rows
    ])
    conn.executemany("INSERT INTO users VALUES (?,?,?,?)", [
        (w.user_id, w.workspace_id, "creator", iso(w.created_at)) for w in ws_rows
    ])
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)", [
        (eid, iso(ts), ws, user, product, name, json.dumps(props, sort_keys=True))
        for ts, eid, ws, user, product, name, props in world.events if ts < cutoff
    ])
    conn.executemany("INSERT INTO subscriptions VALUES (?,?,?,?,?,?)", [
        (ws, iso(ts), plan, seats, billing, mrr) for ts, ws, plan, seats, billing, mrr in world.subscriptions if ts < cutoff
    ])
    conn.executemany("INSERT INTO releases VALUES (?,?,?,?,?)", [
        (r.id, iso(r.ts), r.title, r.notes, r.flag) for r in scenario.releases if r.ts < cutoff
    ])
    conn.executemany("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)", [
        (tid, iso(ts), ws, user, subject, body, tag)
        for ts, tid, ws, user, subject, body, tag in sorted(world.tickets) if ts < cutoff
    ])
    messages = []
    for k, m in enumerate(scenario.messages):
        ts = day_index(m["at"]) * DAY + 15 * 3600 + k * 600
        if ts < cutoff:
            messages.append((f"msg_{k + 1:03d}", iso(ts), m["from_role"], m["subject"], m["body"]))
    conn.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", messages)
    conn.executemany("INSERT INTO actions VALUES (?,?,?,?,?)", [
        (f"act_{k + 1:03d}", iso(a.ts), a.name, json.dumps(a.params, sort_keys=True), a.decided_by)
        for k, a in enumerate(actions) if a.ts < cutoff
    ])
    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("workspaces", "events", "subscriptions", "tickets", "messages", "releases", "actions")}
    conn.close()
    return counts


def write_truth(path: Path, world: World, scenario: Scenario, seed: int, cutoff: float) -> None:
    conn = fresh_db(path, TRUTH_SCHEMA)
    conn.executemany("INSERT INTO latents VALUES (?,?,?,?,?,?)", [
        (w.workspace_id, w.p_base, int(w.requires_admin_consent), w.blocked_by,
         json.dumps(w.releases_applied), iso(w.activated_at) if w.activated_at is not None else None)
        for w in world.workspaces
    ])
    conn.execute("INSERT INTO planted VALUES (?,?,?,?)", (scenario.id, scenario.version, seed, iso(cutoff)))
    conn.commit()
    conn.close()
