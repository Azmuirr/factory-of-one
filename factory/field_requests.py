"""Customer requests logged by Sales and Customer Success, owned by code. Counts and revenue are computed here, so an agent
can cite a search and Quality can replay it. An account asking twice is still one account."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from factory.metrics import query_id
from factory.support import contains_all as _contains_all

KEYS = ["request_id", "ts", "logged_by", "account", "arr_at_stake", "plan", "tag", "text"]


SUFFIXES = ("ations", "ation", "ings", "ing", "ed", "es", "al", "e", "s")


def stem(word: str) -> str:
    """Match a word's other forms, as a search tool would: approval, approve, and approved all match "approv"."""
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def contains_all(words: list[str]) -> tuple[str, list]:
    clause, values = _contains_all([stem(w) for w in words])
    clause = clause.replace("t.subject", "r.text").replace("t.body", "r.account")
    return clause, values


def search(world_path: Path, query: str = "", any_of: list[str] | None = None, tag: str | None = None,
           since: str | None = None, until: str | None = None) -> dict:
    args = {"query": query, "any_of": any_of, "tag": tag, "since": since, "until": until}
    sql = "SELECT * FROM requests r WHERE 1 = 1"
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
        params += [v for _, vs in parts for v in vs]
    if tag:
        sql += " AND r.tag = ?"
        params.append(tag)
    if since:
        sql += " AND date(r.ts) >= ?"
        params.append(since)
    if until:
        sql += " AND date(r.ts) <= ?"
        params.append(until)
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY r.ts", params).fetchall()]
    conn.close()
    per_account = {}
    for r in rows:
        per_account[r["account"]] = max(per_account.get(r["account"], 0), r["arr_at_stake"])
    return {"status": "value", "query_id": query_id({"tool": "search_requests", **args}), "matches": len(rows),
            "distinct_accounts": len(per_account), "arr_at_stake": int(sum(per_account.values())),
            "requests": [{"id": r["request_id"], "url": f"workplace.html#req-{r['request_id']}", **{k: r[k] for k in KEYS if k != "request_id"}} for r in rows]}
