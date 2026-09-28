"""Ticket search, owned by code. The support server and Quality's replay both call this, so a cited count can be checked."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from factory.metrics import query_id

MAX_RESULTS = 50
KEYS = ["ticket_id", "created_at", "workspace_id", "calendar_provider", "subject", "body", "support_tag"]


def contains_all(words: list[str]) -> tuple[str, list]:
    clause = " AND ".join("(lower(t.subject) LIKE ? OR lower(t.body) LIKE ?)" for _ in words)
    return f"({clause})", [p for w in words for p in (f"%{w}%", f"%{w}%")]


def search(world_path: Path, query: str = "", start: str | None = None, end: str | None = None,
           calendar_provider: str | None = None, any_of: list[str] | None = None) -> dict:
    args = {"query": query, "start": start, "end": end, "calendar_provider": calendar_provider, "any_of": any_of}
    sql = """SELECT t.ticket_id, t.created_at, t.workspace_id, w.calendar_provider, t.subject, t.body, t.support_tag
             FROM tickets t JOIN workspaces w USING (workspace_id) WHERE 1 = 1"""
    params: list = []
    terms = [t.lower() for t in query.split() if t.strip()]
    if terms:
        clause, values = contains_all(terms)
        sql += f" AND {clause}"
        params += values
    phrases = [[w.lower() for w in p.split()] for p in (any_of or []) if p.strip()]
    if phrases:
        parts = [contains_all(words) for words in phrases]
        sql += " AND (" + " OR ".join(c for c, _ in parts) + ")"
        params += [v for _, values in parts for v in values]
    if start:
        sql += " AND date(t.created_at) >= ?"
        params.append(start)
    if end:
        sql += " AND date(t.created_at) <= ?"
        params.append(end)
    if calendar_provider:
        sql += " AND w.calendar_provider = ?"
        params.append(calendar_provider)
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    rows = conn.execute(sql + " ORDER BY t.created_at", params).fetchall()
    conn.close()
    return {
        "status": "value",
        "query_id": query_id({"tool": "search_tickets", **args}),
        "matches": len(rows),
        "distinct_workspaces": len({r[2] for r in rows}),
        "tickets": [dict(zip(KEYS, r)) for r in rows[:MAX_RESULTS]],
        "truncated": len(rows) > MAX_RESULTS,
    }
