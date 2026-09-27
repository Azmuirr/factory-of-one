"""MCP server for the shared ledger. Set FACTORY_LEDGER, FACTORY_WORLD, and FACTORY_AGENT."""

import os
import sqlite3
from datetime import date
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from factory import ledger
from factory.metrics import catalog

# Humans write bets and calls. Reviews go through the review server, which runs the code checks.
PREFIX = {k: v for k, v in ledger.PREFIX.items() if k not in ("bet", "call", "review")}

server = MCPServer(
    "ledger",
    instructions="Write every artifact here. The server assigns the id, timestamp, and author. Invalid entries are rejected with reasons.",
)


def sim_now() -> str:
    conn = sqlite3.connect(f"file:{Path(os.environ['FACTORY_WORLD']).as_posix()}?mode=ro", uri=True)
    value = conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0]
    conn.close()
    return value


def world_problems(type: str, payload: dict) -> list[str]:
    """Checks a schema cannot express: the entry must agree with the world and the files it names."""
    problems = []
    if type == "action":
        params = payload.get("params", {})
        release = params.get("release_id")
        if release and os.environ.get("FACTORY_WORLD"):
            conn = sqlite3.connect(f"file:{Path(os.environ['FACTORY_WORLD']).as_posix()}?mode=ro", uri=True)
            found = conn.execute("SELECT 1 FROM releases WHERE release_id = ?", (release,)).fetchone()
            conn.close()
            if not found:
                problems.append(f"release {release} does not exist")
        dims = catalog()[1]
        for dim, values in (params.get("segment") or {}).items():
            if dim not in dims:
                problems.append(f"segment dimension {dim} does not exist")
            elif set(values) - set(dims[dim]["values"]):
                problems.append(f"segment values {sorted(set(values) - set(dims[dim]['values']))} are not values of {dim}")
    if type == "build" and os.environ.get("FACTORY_DEMOS"):
        location = Path(os.environ["FACTORY_DEMOS"]).parent / payload.get("location", "")
        if payload.get("kind") == "mvp":
            if not location.is_dir():
                problems.append(f"build location {payload.get('location')} is not a proposed change")
        elif payload.get("kind") == "design":
            if not location.is_file():
                problems.append(f"build location {payload.get('location')} does not exist")
        elif not location.is_file():
            problems.append(f"build location {payload.get('location')} does not exist")
        elif f'data-honesty="{payload.get("honesty_label")}"' not in location.read_text(encoding="utf-8"):
            problems.append(f"honesty_label {payload.get('honesty_label')} does not match the page's data-honesty")
    return problems


@server.tool()
def write_entry(type: str, payload: dict, refs: list[str] | None = None) -> dict:
    """Append one artifact. type is one of: signal_card, decision_packet, action, build, verdict, review, readout, commitment, patch."""
    if type not in PREFIX:
        return {"status": "rejection", "code": "type_not_allowed", "message": f"Agents cannot write {type} entries."}
    problems = world_problems(type, payload)
    if problems:
        return {"status": "rejection", "code": "invalid_entry", "message": "; ".join(problems)}
    path = Path(os.environ["FACTORY_LEDGER"])
    count = sum(1 for e in ledger.read(path) if e["type"] == type)
    entry = {
        "id": f"{PREFIX[type]}_{count + 1:04d}",
        "type": type,
        "ts": sim_now(),
        "author": {"kind": "agent", "name": os.environ.get("FACTORY_AGENT", "agent")},
        "refs": refs or [],
        "payload": payload,
    }
    try:
        ledger.append(path, entry)
    except ValueError as exc:
        return {"status": "rejection", "code": "invalid_entry", "message": str(exc)}
    return {"status": "value", "id": entry["id"]}


@server.tool()
def read_entries(type: str | None = None) -> dict:
    """Read ledger entries, optionally of one type."""
    entries = ledger.read(Path(os.environ["FACTORY_LEDGER"]))
    return {"status": "value", "entries": [e for e in entries if type is None or e["type"] == type]}


@server.tool()
def commitments_due() -> dict:
    """Open commitments from the ledger: overdue, due today, and upcoming."""
    today = sim_now()[:10] if os.environ.get("FACTORY_WORLD") else date.today().isoformat()
    return {"status": "value", "today": today, **ledger.commitments_due(Path(os.environ["FACTORY_LEDGER"]), today)}


if __name__ == "__main__":
    server.run()
