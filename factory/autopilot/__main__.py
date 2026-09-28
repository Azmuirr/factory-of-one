"""A day with the PM away. Chief writes the away brief and sends urgent items to the PM's own channel, Signal checks
the numbers, Quality reviews, and any decision is queued for the PM. Nothing is applied. The digest says what happened.

python -m factory.autopilot [--out runs/autopilot/<id>] [--fixture ledger.jsonl --chief-fixture away.jsonl]
python -m factory.loop --resume runs/autopilot/<id>      # back at the keyboard: decide, and the loop continues
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from factory import ledger
from factory.evals.suite import ROOT
from factory.loop.__main__ import Loop, segment_text
from factory.loop.gates import Gates


def digest(run: Path) -> str:
    entries = ledger.read(run / "ledger.jsonl")
    outbox = run / "outbox.jsonl"
    posts = [json.loads(l) for l in outbox.read_text(encoding="utf-8").splitlines() if l.strip()] if outbox.exists() else []
    trace = [json.loads(l) for l in (run / "trace.jsonl").read_text(encoding="utf-8").splitlines()] if (run / "trace.jsonl").exists() else []
    held = [t["text"] for t in trace if t.get("event", "").startswith("held for the digest")]
    brief = next((e["payload"] for e in reversed(entries) if e["type"] == "brief"), None)
    waiting = [e for e in entries if e["type"] == "queue" and e["payload"]["status"] == "waiting_for_pm"]
    by_id = {e["id"]: e for e in entries}
    lines = [f"# While you were away: {ledger.sim_now(run / 'world' / 'world.db')[:10]}", "",
             f"## Sent to you ({len(posts)})", *[f"- {p['text']}" for p in posts], *[f"- Held, over the daily limit: {t}" for t in held], "",
             f"## Waiting for you ({len(waiting)})"]
    for q in waiting:
        p = by_id[q["payload"]["packet"]]["payload"]
        d = p["diagnosis"]
        r = by_id.get(q["payload"].get("review") or "", {}).get("payload", {})
        lines += [f"- **Decision: {p['recommended_action']['name']} {p['recommended_action']['params'].get('release_id', '')} for {segment_text(d.get('segment'))}.**",
                  f"  {d['metric']} moved for {segment_text(d.get('segment'))}; the step that broke is {d.get('mechanism_metric')}.",
                  f"  Quality: {r.get('verdict', 'no review')}. {' '.join(f['claim'] for f in r.get('findings', [])[:1])}",
                  f"  To decide: `python -m factory.loop --resume {run}`"]
    if brief:
        tri = Counter(t["label"] for t in brief.get("triage", []))
        lines += ["", "## Chief handled", f"- Triaged {sum(tri.values())} emails: {', '.join(f"{n} {k.replace('_', ' ')}" for k, n in tri.items())}. Drafted replies; none were sent.",
                  f"- {len(brief.get('needs_you', []))} chats need you, {len(brief.get('open_loops', {}).get('waiting_on_me', []))} requests are waiting on you.",
                  f"- {sum(1 for e in entries if e['type'] == 'commitment')} commitments tracked."]
    lines += ["", "## Not done while you were away", "- Nothing was applied, merged, or sent to anyone but you. Your decision rights are prepare_only."]
    return "\n".join(lines) + "\n"


def run_day(scenario: str, seed: int, out: Path, fixture: Path | None = None, chief_fixture: Path | None = None) -> str:
    Loop(scenario, seed, out, Gates({}), fixture).away(chief_fixture)
    text = digest(out)
    (out / "digest.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.autopilot")
    parser.add_argument("--scenario", default="s01-calendar-gate")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--fixture", type=Path, help="Signal and Builder output from a ledger file, instead of the agents")
    parser.add_argument("--chief-fixture", type=Path, help="Chief's away brief from a ledger file, instead of the agent")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (args.out or ROOT / "runs" / "autopilot" / f"{args.scenario}-seed{args.seed}-{run_id}").resolve()
    print(run_day(args.scenario, args.seed, out, args.fixture, args.chief_fixture))
    print(f"Run folder: {out}")


if __name__ == "__main__":
    main()
