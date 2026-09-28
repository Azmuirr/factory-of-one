from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "ledger" / "ledger.schema.json"
BLOCKER_SEVERITIES = {"safety", "correctness", "data_loss"}
MAX_FINDINGS = 3


@lru_cache(maxsize=None)
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def errors(entry: dict, known_ids: set[str] | None = None) -> list[str]:
    found = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in validator().iter_errors(entry)]
    if found:
        return found
    if known_ids is not None:
        found += [f"refs: {ref} is not an earlier ledger entry" for ref in entry["refs"] if ref not in known_ids]
    if entry["type"] == "review":
        findings = entry["payload"]["findings"]
        extra = findings[MAX_FINDINGS:]
        if any(f["severity"] not in BLOCKER_SEVERITIES for f in extra):
            found.append("payload/findings: more than 3 findings, and the extras are not safety, correctness, or data-loss blockers")
    return found


def read(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


SOURCE_KIND = {"mail": "mail", "chat": "chat", "transcripts": "tr", "calendar": "cal", "tracker": "trk"}


def with_source_refs(entries: list[dict]) -> list[dict]:
    """A brief may point at a commitment (cmt:cmt_0004). Swap in the message the promise was made in, so links and checks land on it."""
    sources = {}
    for e in entries:
        if e["type"] == "commitment":
            s = e["payload"]["source"]
            sources[f"cmt:{e['id']}"] = f"{SOURCE_KIND.get(s['source'], s['source'])}:{s['ref']}"

    def swap(v):
        if isinstance(v, str):
            return sources.get(v, v)
        if isinstance(v, list):
            return [swap(x) for x in v]
        if isinstance(v, dict):
            return {k: swap(x) for k, x in v.items()}
        return v

    return [{**e, "payload": swap(e["payload"])} if e["type"] == "brief" else e for e in entries]


def append(path: Path, entry: dict) -> None:
    existing = read(path)
    ids = {e["id"] for e in existing}
    if entry["id"] in ids:
        raise ValueError(f"{entry['id']} already exists")
    problems = errors(entry, ids)
    if problems:
        raise ValueError("; ".join(problems))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def validate_file(path: Path) -> list[str]:
    problems, ids = [], set()
    for n, entry in enumerate(read(path), start=1):
        problems += [f"line {n} ({entry.get('id')}): {p}" for p in errors(entry, ids)]
        ids.add(entry.get("id"))
    return problems


def action_key(payload: dict) -> tuple:
    """What an action does, ignoring status and ordering: name, release, and segment."""
    params = payload.get("params", {})
    segment = {k: sorted(v) for k, v in (params.get("segment") or {}).items()}
    return payload.get("name"), params.get("release_id"), json.dumps(segment, sort_keys=True)


PREFIX = {
    "signal_card": "sig", "decision_packet": "pkt", "bet": "bet", "action": "act", "build": "bld", "verdict": "ver",
    "review": "rev", "call": "call", "readout": "rdo", "commitment": "cmt", "patch": "pch", "brief": "brf", "queue": "que", "candidates": "cnd",
}


def next_id(path: Path, type: str) -> str:
    count = sum(1 for e in read(path) if e["type"] == type)
    return f"{PREFIX[type]}_{count + 1:04d}"


def sim_now(world_path: Path) -> str:
    import sqlite3

    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    value = conn.execute("SELECT value FROM meta WHERE key = 'data_through'").fetchone()[0]
    conn.close()
    return value


def commitments_due(path: Path, today: str) -> dict:
    """Open commitments sorted into overdue, due today, and upcoming."""
    out = {"overdue": [], "due_today": [], "upcoming": []}
    for e in read(path):
        if e["type"] != "commitment" or e["payload"]["status"] != "open":
            continue
        due = e["payload"]["due"]
        out["overdue" if due < today else "due_today" if due == today else "upcoming"].append({"id": e["id"], **e["payload"]})
    return out
