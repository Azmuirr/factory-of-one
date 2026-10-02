"""Coach prepares the PM, never rates or delivers. Code owns: every source resolves to something real, and the
schema itself has no field for a rating, ranking, or score, so Coach cannot write one."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RATING = re.compile(
    r"\b\d{1,2}\s*(?:/|out of)\s*10\b"       # "2 out of 10", "2/10"
    r"|\b\d{1,3}\s*(?:/|out of)\s*100\b"      # "60/100"
    r"|\b[1-5]\s*-?\s*stars?\b"               # "2 stars", "2-star"
    r"|\b[A-F][+-]?\s*(?:grade|rating)\b"     # "a B+ rating"
    r"|\brat(?:e|ed|es|ing)\b\s+(?:her|him|them|his|their)\b"  # "rate her", "rated them"
    r"|\b(?:a |an )?(?:score|rating|grade) of\b",             # "a score of", "rating of"
    re.I)

TABLE = {
    "cal": ("calendar", "event_id"),
    "mail": ("mail", "message_id"),
    "chat": ("chat", "message_id"),
    "doc": ("docs", "doc_id"),
    "trk": ("tracker", "issue_id"),
    "transcript": ("transcripts", "transcript_id"),
}


def known_refs(world_path: Path) -> set[str]:
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    refs = set()
    for prefix, (table, col) in TABLE.items():
        try:
            refs |= {f"{prefix}:{row[0]}" for row in conn.execute(f"SELECT {col} FROM {table}")}
        except sqlite3.OperationalError:
            pass  # an older world without this workplace table
    conn.close()
    return refs


def ref_problems(world_path: Path, payload: dict, earlier: list[dict]) -> list[str]:
    """Every source in a prep entry is a real calendar, mail, chat, doc, tracker, or transcript id, or an earlier
    ledger entry: never a source Coach made up."""
    known = known_refs(world_path) | {e["id"] for e in earlier}
    refs = [payload["for_meeting"]] if payload.get("for_meeting") else []
    refs += [p["source"] for p in payload.get("talking_points", [])]
    refs += [p["source"] for p in payload.get("open_items", [])]
    return [f"{r} is not a real calendar, mail, chat, doc, tracker, or transcript id, or an earlier ledger entry"
            for r in refs if r not in known]


def about_problems(world_path: Path, payload: dict) -> list[str]:
    """For a 1:1 or feedback prep, about must be a real person. A hiring prep names a role, not a person, so it is free text."""
    if payload.get("moment") == "hiring":
        return []
    conn = sqlite3.connect(f"file:{Path(world_path).as_posix()}?mode=ro", uri=True)
    known = {row[0] for row in conn.execute("SELECT person_id FROM people")}
    conn.close()
    about = payload.get("about")
    return [] if about in known else [f"about: {about!r} is not a person id from the directory"]


def rating_language_problems(payload: dict) -> list[str]:
    """D14 blocks a rating as a schema field; nothing stopped one from being written into free text instead.
    Catches the shape of a rating (a number out of some scale, a letter grade, "rate her"), not every possible
    phrasing: a determined rewrite could still get a judgment past a regex. The schema is the real backstop for
    the field that matters; this is a second layer for the field that has none."""
    texts = [p["text"] for p in payload.get("talking_points", [])] + [p["text"] for p in payload.get("open_items", [])]
    return [f'"{t[:80]}" reads like a rating, ranking, or score. Coach prepares; it never rates.' for t in texts if RATING.search(t)]


def main() -> None:
    """python -m factory.coach --for p_jpm --moment one_on_one   Coach prepares you for your next 1:1 with them."""
    import argparse
    import sys
    from datetime import datetime, timezone

    from factory import ledger
    from factory.evals.runner import Trial, run_claude, world_for
    from factory.evals.suite import Task, load_agent

    parser = argparse.ArgumentParser(prog="python -m factory.coach")
    parser.add_argument("--for", dest="about", required=True, help="A person id from the directory, or a role for a hiring prep")
    parser.add_argument("--moment", choices=["one_on_one", "feedback", "hiring"], default="one_on_one")
    parser.add_argument("--scenario", default="s01-calendar-gate")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--fixture", type=Path, help="Load a prep from a ledger file instead of running the agent")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    out = ROOT / "runs" / "coach" / f"{args.scenario}-seed{args.seed}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    (out / "world").mkdir(parents=True)
    prompt = f"Prepare me for a {args.moment.replace('_', ' ')} with {args.about}."
    task = Task("prep", "capability", args.scenario, args.seed, prompt, [])
    import shutil
    shutil.copy(world_for(task), out / "world" / "world.db")
    trial = Trial(task, 0, out)
    if args.fixture:
        shutil.copy(args.fixture, trial.ledger_path)
    else:
        trial.ledger_path.touch()
        run_claude(load_agent("coach"), trial)
        print(f"Coach finished in {trial.duration_s}s, {trial.turns} turns, about ${trial.cost_usd:.2f} at list price.\n")
    entries = ledger.read(trial.ledger_path)
    prep = next((e["payload"] for e in reversed(entries) if e["type"] == "prep"), None)
    if not prep:
        print("Coach wrote nothing.")
        return
    lines = [f"# Prep: {prep['moment'].replace('_', ' ')} with {prep['about']}", ""]
    if prep.get("talking_points"):
        lines += ["## Talking points"] + [f"- {p['text']} ({p['source']})" for p in prep["talking_points"]]
    if prep.get("open_items"):
        lines += ["", "## Open items"] + [f"- {p['text']} ({p['source']})" + (f", {p['owner']}" if p.get("owner") else "")
                                           for p in prep["open_items"]]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
