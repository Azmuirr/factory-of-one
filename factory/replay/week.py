"""Build site/data/week.js from a `factory.autopilot --week` run: one card per day, and how it ended."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from factory import ledger

ROOT = Path(__file__).resolve().parents[2]
UNIT = {"usd_per_week": "a week", "usd_per_year": "a year"}


def top_candidate(entry: dict | None) -> dict | None:
    if not entry or not entry["payload"]["items"]:
        return None
    item = sorted(entry["payload"]["items"], key=lambda i: i["rank"])[0]
    return {"title": item["title"], "size": item["size"]["value"], "unit": UNIT[item["size"]["unit"]], "needs_from_pm": item["needs_from_pm"]}


def status_line(entry: dict | None) -> str | None:
    if not entry:
        return None
    manager = next((v for v in entry["payload"]["versions"] if v["audience"] == "manager"), entry["payload"]["versions"][0])
    return manager["text"]


def build(run: Path, out: Path) -> dict:
    entries = ledger.read(run / "ledger.jsonl")
    by_day = lambda rows: {e["ts"][:10]: e for e in rows}  # noqa: E731 (last entry of a type on a day wins)
    briefs, candidates = by_day(e for e in entries if e["type"] == "brief"), by_day(e for e in entries if e["type"] == "candidates")
    statuses = by_day(e for e in entries if e["type"] == "readout" and e["payload"]["moment"] == "status")
    dates = sorted(set(briefs) | set(candidates) | set(statuses))
    days = []
    for d in dates:
        brief = briefs.get(d)
        days.append({
            "date": d, "weekday": datetime.fromisoformat(d).strftime("%A"),
            "urgent": brief["payload"].get("urgent", []) if brief else [],
            "top_bet": top_candidate(candidates.get(d)),
            "status": status_line(statuses.get(d)),
        })
    call = next((e for e in reversed(entries) if e["type"] == "call"), None)
    verdict = next((e for e in reversed(entries) if e["type"] == "verdict"), None)
    decided_readout = next((e for e in reversed(entries) if e["type"] == "readout" and e["payload"]["moment"] == "decision"), None)
    outbox = run / "outbox.jsonl"
    to_pm = [json.loads(l) for l in outbox.read_text(encoding="utf-8").splitlines() if l.strip() and json.loads(l).get("to") == "self"] if outbox.exists() else []
    week = {
        "days": days, "urgent_to_pm": to_pm,
        "call": call["payload"] if call else None, "verdict": verdict["payload"] if verdict else None,
        "decided_note": status_line(decided_readout),
        "digest": (run / "digest.md").read_text(encoding="utf-8") if (run / "digest.md").exists() else "",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "week.json").write_text(json.dumps(week, indent=1), encoding="utf-8")
    (out / "week.js").write_text("window.WEEK = " + json.dumps(week) + ";\n", encoding="utf-8")
    return week


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.replay.week")
    parser.add_argument("--run", type=Path, required=True, help="A finished `factory.autopilot --week` run folder")
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    week = build(args.run.resolve(), (args.out / "data").resolve())
    print(f"Wrote {args.out / 'data' / 'week.json'} with {len(week['days'])} days.")
    print(f"Open {(args.out / 'week.html').resolve().as_uri()}")


if __name__ == "__main__":
    main()
