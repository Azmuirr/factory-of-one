"""MCP server for Quality's reviews. Code fills the correctness checks. The model supplies only the verdict and findings."""

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from factory import ledger, review

server = MCPServer(
    "review",
    instructions="check_entry returns the code checks for a ledger entry. submit_review records your verdict; SHIP is refused when a check failed.",
)


def paths() -> tuple[Path, Path, Path]:
    ledger_path = Path(os.environ["FACTORY_LEDGER"])
    return ledger_path, Path(os.environ["FACTORY_WORLD"]), ledger_path.parent


def find(entry_id: str) -> tuple[dict | None, list[dict]]:
    entries = ledger.read(paths()[0])
    return next((e for e in entries if e["id"] == entry_id), None), entries


@server.tool()
def check_entry(entry_id: str) -> dict:
    """Run the code checks (numbers, quotes, fields, privacy) on one ledger entry."""
    entry, entries = find(entry_id)
    if not entry:
        return {"status": "rejection", "code": "not_found", "message": f"No ledger entry {entry_id}."}
    _, world, root = paths()
    return {"status": "value", "entry_id": entry_id, **review.correctness(entry, entries, world, root)}


@server.tool()
def submit_review(entry_id: str, verdict: str, findings: list[dict]) -> dict:
    """Record a review. verdict is SHIP, FIX, PROVE, DELETE, or STOP. Each finding has claim, evidence, impact,
    smallest_action, proof_required, and severity."""
    entry, entries = find(entry_id)
    if not entry:
        return {"status": "rejection", "code": "not_found", "message": f"No ledger entry {entry_id}."}
    ledger_path, world, root = paths()
    checks = review.correctness(entry, entries, world, root)
    failed = review.failed(checks)
    if verdict == "SHIP" and failed:
        return {"status": "rejection", "code": "ship_blocked",
                "message": f"SHIP is not allowed: these checks failed: {failed}. Details: {checks['details']}"}
    record = {
        "id": ledger.next_id(ledger_path, "review"),
        "type": "review",
        "ts": ledger.sim_now(world),
        "author": {"kind": "agent", "name": os.environ.get("FACTORY_AGENT", "quality")},
        "refs": [entry_id],
        "payload": {"verdict": verdict, "correctness": {c: checks[c] for c in review.CHECKS}, "findings": findings},
    }
    try:
        ledger.append(ledger_path, record)
    except ValueError as exc:
        return {"status": "rejection", "code": "invalid_review", "message": str(exc)}
    return {"status": "value", "id": record["id"], "correctness": record["payload"]["correctness"]}


if __name__ == "__main__":
    server.run()
