"""MCP server for the `releases` tool (release log and flag state). Read-only. Set FACTORY_WORLD."""

import os
import sqlite3
from pathlib import Path

from mcp.server.mcpserver import MCPServer

server = MCPServer("releases", instructions="Release notes and feature-flag state. Read-only.")


def connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(os.environ['FACTORY_WORLD']).as_posix()}?mode=ro", uri=True)


@server.tool()
def list_releases(start: str | None = None, end: str | None = None) -> dict:
    """Releases between optional dates (YYYY-MM-DD, inclusive), oldest first."""
    sql, params = "SELECT release_id, ts, title, notes, flag FROM releases WHERE 1 = 1", []
    if start:
        sql += " AND date(ts) >= ?"
        params.append(start)
    if end:
        sql += " AND date(ts) <= ?"
        params.append(end)
    conn = connect()
    rows = conn.execute(sql + " ORDER BY ts", params).fetchall()
    conn.close()
    return {"status": "value", "releases": [dict(zip(["release_id", "ts", "title", "notes", "flag"], r)) for r in rows]}


@server.tool()
def flag_state() -> dict:
    """Current and past feature-flag settings."""
    conn = connect()
    rows = conn.execute("SELECT flag, segment_filter, percent, ts FROM flags ORDER BY ts").fetchall()
    conn.close()
    return {"status": "value", "flags": [dict(zip(["flag", "segment_filter", "percent", "ts"], r)) for r in rows]}


if __name__ == "__main__":
    server.run()
