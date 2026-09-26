"""MCP server for the shared ledger. Set FACTORY_LEDGER, FACTORY_WORLD, and FACTORY_AGENT."""

import os
import sqlite3
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from factory import ledger

PREFIX = {
    "signal_card": "sig", "decision_packet": "pkt", "action": "act", "build": "bld", "verdict": "ver",
    "review": "rev", "readout": "rdo", "commitment": "cmt", "patch": "pch",
}

server = MCPServer(
    "ledger",
    instructions="Write every artifact here. The server assigns the id, timestamp, and author. Invalid entries are rejected with reasons.",
)


def sim_now() -> str:
    conn = sqlite3.connect(f"file:{Path(os.environ['FACTORY_WORLD']).as_posix()}?mode=ro", uri=True)
    value = conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0]
    conn.close()
    return value


@server.tool()
def write_entry(type: str, payload: dict, refs: list[str] | None = None) -> dict:
    """Append one artifact. type is one of: signal_card, decision_packet, action, build, verdict, review, readout, commitment, patch."""
    if type not in PREFIX:
        return {"status": "rejection", "code": "type_not_allowed", "message": f"Agents cannot write {type} entries."}
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


if __name__ == "__main__":
    server.run()
