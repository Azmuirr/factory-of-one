"""Run Chief's daily brief and show it to a human: python -m factory.chief"""

from __future__ import annotations

import argparse
import shutil
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from factory import ledger
from factory.chief import html
from factory.evals.runner import Trial, run_claude, world_for
from factory.evals.suite import ROOT, Task, load_agent
from factory.workplace import Workplace

PROMPT = "Good morning. Write today's brief."


def render(entries: list[dict], wp: Workplace) -> str:
    brief = next((e["payload"] for e in reversed(entries) if e["type"] == "brief"), None)
    if not brief:
        return "No brief was written."
    names = html.Links(wp)
    shown: set[str] = set()

    def draft(item: dict) -> list[str]:
        if not item.get("draft_reply"):
            return []
        if item["ref"] in shown:
            return ["   Reply suggested above."]
        shown.add(item["ref"])
        return [f"   Suggested reply: {item['draft_reply']}"]

    lines = [f"# Brief for {brief['date']}", "", "## Top 3"]
    for i, t in enumerate(brief["top"], 1):
        lines += [f"{i}. {names.label(t['ref'])}", f"   Why: {t['why']}", f"   Next: {t.get('next_step', '')}", *draft(t)]
    if brief.get("needs_you"):
        lines += ["", "## Needs you in chat"]
        for n in brief["needs_you"]:
            lines += [f"- {names.label(n['ref'])}", *draft(n)]
    if brief.get("at_risk"):
        lines += ["", "## At risk"] + [f"- {names.label(a['ref'])}: {a['why']}" for a in brief["at_risk"]]
    lines += ["", "## Calendar"] + [f"- {c['flag'].replace('_', ' ')}: {names.label(c['ref'])}. {c.get('suggestion', '')}" for c in brief["calendar"]]
    if brief.get("focus_minutes") is not None:
        lines.append(f"- Focus time left today: {brief['focus_minutes']} minutes")
    lines += ["", "## Inbox"]
    for label, title in html.LABELS.items():
        items = [t for t in brief["triage"] if t["label"] == label]
        if items:
            lines.append(f"{title}: " + "; ".join(names.label(t["ref"]) + (" (suspicious)" if t.get("suspicious") else "") for t in items))
            for t in items:
                lines += draft(t)
    commitments = [e["payload"] for e in entries if e["type"] == "commitment"]
    if commitments:
        lines += ["", "## Commitments from meetings"]
        lines += [f"- [{c['status']}] {wp.person(c['owner'])['name']}: {c['task']} (due {c['due']})" for c in commitments]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.chief")
    parser.add_argument("--scenario", default="s01-calendar-gate")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--fixture", type=Path, help="Load a brief from a ledger file instead of running the agent")
    parser.add_argument("--open", action="store_true", help="Open the brief in your browser")
    args = parser.parse_args()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "runs" / "chief" / f"{args.scenario}-seed{args.seed}-{run_id}"
    (out / "world").mkdir(parents=True)
    task = Task("brief", "capability", args.scenario, args.seed, PROMPT, [])
    shutil.copy(world_for(task), out / "world" / "world.db")
    trial = Trial(task, 0, out)
    if args.fixture:
        shutil.copy(args.fixture, trial.ledger_path)
    else:
        trial.ledger_path.touch()
        run_claude(load_agent("chief"), trial)
        print(f"Chief finished in {trial.duration_s}s, {trial.turns} turns, about ${trial.cost_usd:.2f} at list price.\n")
    with Workplace(trial.world_path) as wp:
        entries = ledger.read(trial.ledger_path)
        print(render(entries, wp))
        page = html.write(entries, wp, out)
    print(f"\nBrief with links and copyable replies: {page.as_uri()}")
    if args.open:
        webbrowser.open(page.as_uri())


if __name__ == "__main__":
    main()
