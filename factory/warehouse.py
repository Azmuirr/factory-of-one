"""Read-only SQL for questions the metric catalog cannot answer. Every answer is labeled exploratory."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROW_LIMIT = 500
READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def _authorize(action, *_):
    return sqlite3.SQLITE_OK if action in READ_ACTIONS else sqlite3.SQLITE_DENY


def query(db_path: Path, sql: str, limit: int = ROW_LIMIT) -> dict:
    statement = sql.strip().rstrip(";").strip()
    if not statement.lower().startswith(("select", "with")) or ";" in statement:
        return {"status": "rejection", "code": "read_only", "message": "Only a single SELECT or WITH statement is allowed."}
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    conn.set_authorizer(_authorize)
    try:
        cursor = conn.execute(statement)
        rows = cursor.fetchmany(limit + 1)
        columns = [c[0] for c in cursor.description]
    except sqlite3.Error as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        conn.close()
    return {
        "status": "value",
        "confidence": "exploratory",
        "columns": columns,
        "rows": [list(r) for r in rows[:limit]],
        "truncated": len(rows) > limit,
        "does_not_prove": "That this SQL matches a registered metric definition. Check it before anyone decides on it.",
    }


def describe(db_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    tables = [t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    schema = {t: [row[1] for row in conn.execute(f"PRAGMA table_info({t})")] for t in tables}
    conn.close()
    return {"status": "value", "tables": schema}
