"""Query log and replay. Every metric answer is logged by query_id so a reviewer can recompute any cited number exactly."""

from __future__ import annotations

import json
import os
from pathlib import Path

from factory import sizing
from factory.metrics import World, query_id

TOOLS = ("get_metric", "compare_periods", "estimate_weekly_arr_impact")


def log_path(ledger_path: Path | None = None) -> Path:
    if os.environ.get("FACTORY_QUERY_LOG"):
        return Path(os.environ["FACTORY_QUERY_LOG"])
    ledger_path = ledger_path or Path(os.environ["FACTORY_LEDGER"])
    return Path(ledger_path).parent / "queries.jsonl"


def record(tool: str, args: dict, result: dict, ledger_path: Path | None = None) -> None:
    if result.get("status") != "value":
        return
    path = log_path(ledger_path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"query_id": result["query_id"], "tool": tool, "args": args}, sort_keys=True))
        f.write("\n")


def load(path: Path) -> dict[str, dict]:
    if not Path(path).exists():
        return {}
    return {q["query_id"]: q for q in map(json.loads, Path(path).read_text(encoding="utf-8").splitlines()) if q}


def run(world: World, tool: str, args: dict) -> dict:
    if tool == "get_metric":
        return world.get_metric(**args)
    if tool == "compare_periods":
        return world.compare_periods(**args)
    if tool == "estimate_weekly_arr_impact":
        return sizing.weekly_arr_impact(world, **args)
    raise ValueError(f"Unknown query tool {tool}")


def sizing_query_id(args: dict) -> str:
    return query_id({"tool": "estimate_weekly_arr_impact", **args})
