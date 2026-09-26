"""Run Chief and show the brief to a human.

python -m factory.chief [--mode morning|midday|evening|weekly] [--as-of 2026-02-27T17:00:00Z] [--fixture ledger.jsonl] [--open]
"""

from __future__ import annotations

import argparse
import json
import shutil
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from factory import config as install
from factory import ledger
from factory.chief import html
from factory.evals.runner import Trial, run_claude, world_for
from factory.evals.suite import ROOT, Task, load_agent
from factory.workplace import Workplace

PROMPTS = {
    "morning": "Good morning. It is {when}. Write the morning brief.",
    "midday": "It is {when}. Write the midday brief: only what changed since the morning.",
    "evening": "It is {when}. Write the evening wrap.",
    "weekly": "It is {when}. Write the weekly review.",
}


def render(entries: list[dict], wp: Workplace) -> str:
    brief = next((e["payload"] for e in reversed(entries) if e["type"] == "brief"), None)
    if not brief:
        return "No brief was written."
    names = html.Links(wp)
    goals = {g["id"]: g["title"] for g in wp.plan.get("goals", [])}
    shown: set[str] = set()

    def draft(item: dict) -> list[str]:
        key = item.get("ref") or item.get("person", "")
        if not item.get("draft_reply"):
            return []
        if key in shown:
            return ["   Reply suggested above."]
        shown.add(key)
        return [f"   Suggested reply: {item['draft_reply']}"]

    lines = [f"# {brief.get('mode', 'morning').capitalize()} brief for {brief['date']}", "", "## Top 3"]
    for i, t in enumerate(brief["top"], 1):
        goal = f"  [{goals.get(t['goal'], t['goal'])}]" if t.get("goal") else ""
        lines += [f"{i}. {names.label(t['ref'])}{goal}", f"   Why: {t['why']}", f"   Next: {t.get('next_step', '')}", *draft(t)]
    if brief.get("changes"):
        lines += ["", "## Changes for next week"] + [f"{i}. {c}" for i, c in enumerate(brief["changes"], 1)]
    if brief.get("done"):
        lines += ["", "## Done"] + [f"- {names.label(r)}" for r in brief["done"]]
    if brief.get("goal_check"):
        lines += ["", "## Time against goals"]
        lines += [f"- {g['status'].replace('_', ' ')}: {goals.get(g['goal'], g['goal'])}, {g['hours']} hours. {g.get('note', '')}".rstrip()
                  for g in brief["goal_check"]]
    if brief.get("meeting_prep"):
        lines += ["", "## Meeting prep"]
        for m in brief["meeting_prep"]:
            lines += [f"- {names.label(m['ref'])}", f"   Purpose: {m['purpose']}", f"   Your ask: {m['ask']}"]
            if m.get("open_loops"):
                lines.append("   Open loops: " + "; ".join(names.label(r) for r in m["open_loops"]))
    if brief.get("needs_you"):
        lines += ["", "## Needs you in chat"]
        for n in brief["needs_you"]:
            lines += [f"- {names.label(n['ref'])}", *draft(n)]
    for side, title in html.LOOPS.items():
        items = brief.get("open_loops", {}).get(side, [])
        if items:
            lines += ["", f"## {title}"]
            for x in items:
                days = f" ({x['days']} days)" if x.get("days") is not None else ""
                lines += [f"- {wp.person(x['who'])['name']}: {x['what']}{days}", *draft(x)]
    if brief.get("at_risk"):
        lines += ["", "## At risk"] + [f"- {names.label(a['ref'])}: {a['why']}" for a in brief["at_risk"]]
    if brief.get("calendar"):
        lines += ["", "## Calendar"]
        for c in brief["calendar"]:
            move = f" Proposed new time: {c['proposed_time'][11:16]}." if c.get("proposed_time") else ""
            lines.append(f"- {c['flag'].replace('_', ' ')}: {names.label(c['ref'])}. {c.get('suggestion', '')}{move}")
    if brief.get("focus_minutes") is not None:
        lines.append(f"- Focus time left today: {brief['focus_minutes']} minutes")
    if brief.get("followups"):
        lines += ["", "## Meeting follow-ups"]
        for f in brief["followups"]:
            lines += [f"- {names.label(f['ref'])}", *draft(f)]
    if brief.get("stale"):
        lines += ["", "## Stakeholders to reach"]
        for st in brief["stale"]:
            lines += [f"- {wp.person(st['person'])['name']}, {st['days_since']} days: {st['suggestion']}", *draft(st)]
    if brief.get("triage"):
        lines += ["", "## Inbox"]
        for label, title in html.LABELS.items():
            items = [t for t in brief["triage"] if t["label"] == label]
            if items:
                lines.append(f"{title}: " + "; ".join(names.label(t["ref"]) + (" (suspicious)" if t.get("suspicious") else "") for t in items))
                for t in items:
                    lines += draft(t)
    commitments = [e["payload"] for e in entries if e["type"] == "commitment"]
    if commitments:
        lines += ["", "## Commitments"]
        lines += [f"- [{c['status']}] {wp.person(c['owner'])['name']}: {c['task']} (due {c['due']})" for c in commitments]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.chief")
    parser.add_argument("--scenario", default="s01-calendar-gate")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--mode", choices=list(PROMPTS), default="morning")
    parser.add_argument("--as-of", help="Treat this time as now, for example 2026-02-27T17:00:00Z")
    parser.add_argument("--fixture", type=Path, help="Load a brief from a ledger file instead of running the agent")
    parser.add_argument("--open", action="store_true", help="Open the brief in your browser")
    args = parser.parse_args()

    cfg = install.load()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "runs" / "chief" / f"{args.scenario}-seed{args.seed}-{args.mode}-{run_id}"
    (out / "world").mkdir(parents=True)
    env = {"FACTORY_AS_OF": args.as_of} if args.as_of else {}
    task = Task("brief", "capability", args.scenario, args.seed, "", [], env=env)
    shutil.copy(world_for(task), out / "world" / "world.db")
    trial = Trial(task, 0, out)
    with Workplace(trial.world_path, as_of=args.as_of, goals_path=cfg.goals) as wp:
        task.prompt = PROMPTS[args.mode].format(when=wp.now.strftime("%A %Y-%m-%d %H:%M UTC"))
    if args.fixture:
        shutil.copy(args.fixture, trial.ledger_path)
    else:
        trial.ledger_path.touch()
        run_claude(load_agent("chief"), trial)
        print(f"Chief finished in {trial.duration_s}s, {trial.turns} turns, about ${trial.cost_usd:.2f} at list price.\n")
    with Workplace(trial.world_path, as_of=args.as_of, goals_path=cfg.goals) as wp:
        entries = ledger.read(trial.ledger_path)
        print(render(entries, wp))
        page = html.write(entries, wp, out)
    outbox = out / "outbox.jsonl"
    if outbox.exists():
        print("\n## Posted to your private channel")
        for post in map(json.loads, outbox.read_text(encoding="utf-8").splitlines()):
            print(post["text"])
    print(f"\nBrief with links and copyable replies: {page.as_uri()}")
    if args.open:
        webbrowser.open(page.as_uri())


if __name__ == "__main__":
    main()
