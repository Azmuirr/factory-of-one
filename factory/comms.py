"""Sending, owned by code. Comms drafts a readout; code checks every number against the ledger and sends only what the
PM approved at the Tell gate, or, while the PM is away, what the decision rights allow (decision D10)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from factory import ledger, policy
from factory import numbers as nums

SOURCES = ("signal_card", "decision_packet", "candidates", "bet", "verdict", "call", "queue", "review")


def entry_pool(entry: dict) -> set[float]:
    """Every number an entry states: its fields, and the numbers written in its prose."""
    pool = {float(v) for v in nums.field_numbers(entry["payload"])}
    for text in nums.texts(entry["payload"]):
        pool |= {float(d.replace(",", "")) for d, _ in nums.TEXT_NUMBER.findall(text)}
    return pool


def ledger_pool(entries: list[dict]) -> set[float]:
    return {v for e in entries if e["type"] in SOURCES for v in entry_pool(e)}


def version_problems(version: dict, pool: set[float]) -> list[str]:
    return [f"{version['audience']}: {v:g} is not in the ledger" for v, tol in nums.text_numbers(version["text"])
            if not nums.text_grounded(v, tol, pool)]


def number_problems(payload: dict, entries: list[dict]) -> list[str]:
    pool = ledger_pool(entries)
    problems = [p for v in payload["versions"] for p in version_problems(v, pool)]
    by_id = {e["id"]: e for e in entries}
    for n in payload.get("numbers", []):
        source = by_id.get(n["ref"])
        if not source or not nums.field_grounded(n["value"], entry_pool(source)):
            problems.append(f"{n['label']}: {n['value']:g} does not match {n['ref']}")
    return problems


def people(world_path: Path) -> dict[str, bool]:
    """Person id to whether they are outside the company."""
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    rows = dict(conn.execute("SELECT person_id, external FROM people").fetchall())
    conn.close()
    return {k: bool(v) for k, v in rows.items()}


def deliver(entry: dict, entries: list[dict], world_path: Path, rights: dict, approved_by_pm: bool, out: Path | None = None) -> list[dict]:
    """Decide, per version, whether it goes out. Numbers must match the ledger either way. Writes outbox.jsonl and held.jsonl
    when `out` is given; otherwise it is a dry run."""
    pool, directory = ledger_pool(entries), people(world_path)
    results = []
    for v in entry["payload"]["versions"]:
        reason = None
        bad = version_problems(v, pool)
        outside = [t for t in v["to"] if not t.startswith("#") and directory.get(t, True)]
        if bad:
            reason = "numbers do not match the ledger: " + "; ".join(bad)
        elif v["audience"] != "customer" and outside:
            reason = f"an internal update is addressed to someone outside the company or not in the directory: {outside}"
        elif not approved_by_pm:
            ok, why = policy.may_send(rights, v["audience"])
            reason = None if ok else why
        results.append({"audience": v["audience"], "to": v["to"], "channel": v["channel"], "text": v["text"], "readout": entry["id"],
                        "sent": reason is None, "reason": reason or ("approved by the PM" if approved_by_pm else "allowed by the decision rights")})
    if out:
        ts = ledger.sim_now(out / "world" / "world.db") if (out / "world" / "world.db").exists() else ""
        for r in results:
            with (out / ("outbox.jsonl" if r["sent"] else "held.jsonl")).open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts, **{k: r[k] for k in ("audience", "to", "channel", "text", "readout", "reason")}}) + "\n")
    return results
