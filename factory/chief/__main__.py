"""Run Chief's daily brief and print it for a human: python -m factory.chief"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

from factory import ledger
from factory.evals.runner import Trial, run_claude, world_for
from factory.evals.suite import ROOT, Task, load_agent
from factory.workplace import Workplace

PROMPT = "Good morning. Write today's brief."
LABELS = {"act_now": "Act now", "delegate": "Delegate", "answer_later": "Answer later", "ignore": "Ignore"}


def describe(ref: str, wp: Workplace) -> str:
    kind, rid = ref.split(":", 1)
    if kind == "mail":
        m = wp.mail_get(rid)
        return f"{m['from']['name']}: {m['subject']}" if m else ref
    if kind == "chat":
        msgs = wp.chat_thread(rid)
        return f"{msgs[0]['author']['name']} in {msgs[0]['where']}: {msgs[0]['text'][:70]}" if msgs else ref
    if kind == "cal":
        e = wp.event_get(rid)
        return f"{e['start'][11:16]} {e['title']}" if e else ref
    return ref


def render(entries: list[dict], wp: Workplace) -> str:
    brief = next((e["payload"] for e in reversed(entries) if e["type"] == "brief"), None)
    if not brief:
        return "No brief was written."
    lines = [f"# Brief for {brief['date']}", "", "## Top 3"]
    lines += [f"{i}. {describe(t['ref'], wp)}\n   Why: {t['why']}\n   Next: {t.get('next_step', '')}" for i, t in enumerate(brief["top"], 1)]
    if brief.get("at_risk"):
        lines += ["", "## At risk"] + [f"- {describe(a['ref'], wp)}: {a['why']}" for a in brief["at_risk"]]
    lines += ["", "## Needs you in chat"] + [f"- {describe(n['ref'], wp)}" for n in brief["needs_you"]]
    lines += ["", "## Calendar"] + [f"- {c['flag'].replace('_', ' ')}: {describe(c['ref'], wp)}. {c.get('suggestion', '')}" for c in brief["calendar"]]
    if brief.get("focus_minutes") is not None:
        lines.append(f"- Focus time left today: {brief['focus_minutes']} minutes")
    lines += ["", "## Inbox"]
    for label, title in LABELS.items():
        refs = [t for t in brief["triage"] if t["label"] == label]
        if refs:
            lines.append(f"{title}: " + "; ".join(describe(t["ref"], wp) + (" (suspicious)" if t.get("suspicious") else "") for t in refs))
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
        print(render(ledger.read(trial.ledger_path), wp))
    print(f"\nLedger: {trial.ledger_path}")


if __name__ == "__main__":
    main()
