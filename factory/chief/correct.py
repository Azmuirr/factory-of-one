"""Teach Chief from a correction. Rules land in the install's lessons file and load on every run.

python -m factory.chief.correct --ref mail:m_004 --label answer_later --reason "Budget asks are never urgent"
python -m factory.chief.correct --note "Never say 'circle back'."
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from factory import config as install
from factory.evals.runner import world_for
from factory.evals.suite import Task
from factory.workplace import Workplace

LABELS = ("act_now", "delegate", "answer_later", "ignore")


def add_rule(lessons: Path, rule: dict | None = None, note: str | None = None) -> dict:
    data = yaml.safe_load(lessons.read_text(encoding="utf-8")) if lessons.exists() else None
    data = data or {"labels": [], "notes": []}
    data.setdefault("labels", [])
    data.setdefault("notes", [])
    if rule:
        data["labels"] = [r for r in data["labels"] if r["sender"] != rule["sender"]] + [rule]
    if note and note not in data["notes"]:
        data["notes"].append(note)
    lessons.parent.mkdir(parents=True, exist_ok=True)
    header = "# Rules learned from the PM's corrections. Add one with: python -m factory.chief.correct\n"
    lessons.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.chief.correct")
    parser.add_argument("--ref", help="The item Chief got wrong, for example mail:m_004")
    parser.add_argument("--label", choices=LABELS, help="The label it should have had. The rule applies to everything from that sender")
    parser.add_argument("--reason", default="", help="Why, in one sentence")
    parser.add_argument("--note", help="A free-text rule, for example about voice")
    parser.add_argument("--scenario", default="s01-calendar-gate")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    if not (args.label and args.ref) and not args.note:
        parser.error("give --ref with --label, or --note")

    cfg = install.load()
    if not cfg.lessons:
        parser.error(f"{cfg.path.name} has no lessons folder")
    rule = None
    if args.ref and args.label:
        with Workplace(world_for(Task("correct", "capability", args.scenario, args.seed, "", []))) as wp:
            message = wp.mail_get(args.ref.split(":", 1)[1])
        if not message:
            parser.error(f"no message {args.ref}")
        rule = {"sender": message["from"]["id"], "label": args.label, "reason": args.reason}
    data = add_rule(cfg.lessons / "chief.yaml", rule, args.note)
    print(f"Saved. Chief now follows {len(data['labels'])} label rules and {len(data['notes'])} notes: {cfg.lessons / 'chief.yaml'}")


if __name__ == "__main__":
    main()
