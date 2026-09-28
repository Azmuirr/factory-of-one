"""Build the replay site from one loop run and one Chief run. Every number on the site is copied from the run's
ledger or computed here by the metrics engine; the page does no math except the visitor's own Brier score.

python -m factory.replay --loop runs/loop/live-4 --chief runs/chief/<run> [--out site]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

import yaml

from collections import Counter

from factory import code, ledger
from factory import config as install
from factory.chief.html import Links
from factory.evals.runner import Trial, parse_transcript
from factory.evals.suite import Task
from factory.metrics import World, catalog
from factory.workplace import Workplace
from sandbox.generator.run import generate

ROOT = Path(__file__).resolve().parents[2]
METRIC = "activation_rate_7d"
FIRST_WEEK = date(2026, 1, 5)


def weekly(world_path: Path, weeks: int) -> dict[str, list[float | None]]:
    """Weekly signup cohorts, by calendar provider. Immature weeks are None, as the metrics engine refuses them."""
    world = World(world_path)
    out: dict[str, list[float | None]] = {"microsoft": [], "google": [], "all": []}
    for i in range(weeks):
        start = FIRST_WEEK + timedelta(weeks=i)
        r = world.get_metric(METRIC, start.isoformat(), (start + timedelta(days=6)).isoformat(), None, ["calendar_provider"])
        rows = {row["group"]["calendar_provider"]: row["value"] for row in r.get("rows", [])} if r["status"] == "value" else {}
        out["microsoft"].append(rows.get("microsoft"))
        out["google"].append(rows.get("google"))
        out["all"].append(r.get("value") if r["status"] == "value" else None)
    return out


def live_runs_table() -> list[dict]:
    """The 'Live runs' table from docs/evals.md: every real run, including the ones that went wrong."""
    text = (ROOT / "docs" / "evals.md").read_text(encoding="utf-8")
    section = text.split("## Live runs", 1)[1].split("\n## ", 1)[0]
    rows = [l for l in section.splitlines() if l.startswith("| 20")]
    keys = ["date", "run", "result", "found"]
    return [dict(zip(keys, [c.strip() for c in r.strip("|").split("|")])) for r in rows]


SUBAGENT = "Handed one focused question to a sub-agent: quant for numbers, qual for customer voice"


def usage(transcript: Path) -> dict:
    """What an agent actually did in a run, from its transcript: turns, time, and each tool with what it is for."""
    if not transcript.is_file():
        return {}
    trial = Trial(Task("replay", "capability", "", 1, "", []), 0, transcript.parent)
    text = transcript.read_text(encoding="utf-8")
    parse_transcript(trial, text)
    results = [json.loads(l) for l in text.splitlines() if l.startswith("{") and '"type":"result"' in l.replace(" ", "")]
    capability_of = {tool: cap for cap, tool in install.load(ROOT / "config" / "sandbox.yaml").capabilities.items()}
    vocab = install.vocabulary()
    tools = []
    for name, n in Counter(c["name"] for c in trial.tool_calls).most_common():
        cap = capability_of.get(name)
        tools.append({"tool": name.split("__")[-1], "capability": cap or ("sub-agent" if name == "Agent" else name),
                      "what": vocab[cap]["description"] if cap else SUBAGENT if name == "Agent" else "", "calls": n})
    rejected = sum(1 for c in trial.tool_calls if c["name"].endswith("write_entry") and '"rejection"' in c["result"])
    return {"turns": trial.turns, "seconds": round((results[-1].get("duration_ms") or 0) / 1000, 1) if results else None,
            "cost_usd": round(trial.cost_usd, 4), "tools": tools, "calls": len(trial.tool_calls), "rejected_writes": rejected}


def chief_facts(chief_dir: Path) -> dict:
    """What Chief had to get through, and what it made of it."""
    entries = ledger.read(chief_dir / "ledger.jsonl")
    brief = [e for e in entries if e["type"] == "brief"][-1]["payload"]
    with Workplace(chief_dir / "world" / "world.db", goals_path=ROOT / "company" / "tallybird" / "goals.yaml") as wp:
        inputs = {"emails": len(wp.mail_list()), "chats": len(wp.chat_list()), "meetings_today": len(wp.calendar_list(brief["date"], "2026-03-03")["events"]),
                  "transcripts": len(wp.transcripts_list()), "tracker_issues": len(wp.tracker_search())}
        names = {pid: p["name"] for pid, p in wp.people.items()}
        links = Links(wp)
        labels = {ref: links.label(ref) for ref in sorted(set(re.findall(r"\b(?:mail|chat|cal|tr|trk):[a-z0-9_]+", json.dumps(brief))))}
    drafts = {x.get("ref") or x.get("person") for sec in ("top", "needs_you", "triage", "followups", "stale") for x in brief.get(sec, []) if x.get("draft_reply")}
    drafts |= {x["ref"] for side in brief.get("open_loops", {}).values() for x in side if x.get("draft_reply")}
    commitments = [e["payload"] for e in entries if e["type"] == "commitment"]
    return {"inputs": inputs, "brief": brief, "names": names, "labels": labels,
            "triage": dict(Counter(t["label"] for t in brief["triage"])), "suspicious": sum(1 for t in brief["triage"] if t.get("suspicious")),
            "drafts": len(drafts), "commitments": commitments,
            "overdue_promises": [c for c in commitments if c["owner"] == "p_me" and c["status"] == "open" and c["due"] < brief["date"]]}


def copy(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    else:
        shutil.copy(src, dst)
    return dst.as_posix()


def build(loop_dir: Path, chief_dir: Path | None, out: Path) -> dict:
    entries = ledger.read(loop_dir / "ledger.jsonl")
    by_type = lambda t: [e for e in entries if e["type"] == t]  # noqa: E731
    first = lambda t: (by_type(t) or [None])[0]  # noqa: E731
    summary = json.loads((loop_dir / "summary.json").read_text(encoding="utf-8"))
    trace = [json.loads(l) for l in (loop_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    scenario_dir = ROOT / "sandbox" / "scenarios" / summary["scenario"]
    scenario = yaml.safe_load((scenario_dir / "scenario.yaml").read_text(encoding="utf-8"))
    truth = yaml.safe_load((scenario_dir / "truth.yaml").read_text(encoding="utf-8"))
    data = out / "data"
    if data.exists():
        shutil.rmtree(data)
    data.mkdir(parents=True)

    # The world with the action, and the same world without it: same users, same randomness, one decision apart.
    weeks = 10
    with_action = weekly(loop_dir / "world" / "world.db", weeks)
    with tempfile.TemporaryDirectory() as tmp:
        no_action = weekly(generate(summary["scenario"], summary["seed"], through="end", out=Path(tmp)) / "world" / "world.db", weeks)

    builds = []
    for b in by_type("build"):
        p, site_path, diff_text = b["payload"], None, None
        src = loop_dir / p["location"]
        if p["kind"] == "prototype":
            site_path = copy(src.parent, data / "demo") + "/" + src.name
        elif p["kind"] == "design":
            site_path = copy(src.parent / "screen.png", data / "design.png")
        elif p["kind"] == "mvp":
            diff_text = code.diff(code.APP, src)
            (data / "change.diff").write_text(diff_text, encoding="utf-8")
            site_path = (data / "change.diff").as_posix()
        review = next((r["payload"] for r in by_type("review") if b["id"] in r["refs"]), None)
        builds.append({"id": b["id"], "kind": p["kind"], "honesty": p["honesty_label"], "checks": p.get("checks", {}),
                       "path": Path(site_path).relative_to(out).as_posix() if site_path else None,
                       "message": (src / "CHANGE.md").read_text(encoding="utf-8").strip() if (src / "CHANGE.md").is_file() else None,
                       "diff": diff_text, "review": review,
                       "new_flags": re.findall(r"^\+([a-z0-9_]+):\s*$", diff_text or "", re.M),
                       "new_tests": len(re.findall(r"^\+def test_", diff_text or "", re.M))})

    # How every value of the diagnosed dimension moved, from the world as the agents saw it on Monday.
    monday = loop_dir / "world-before" / "world.db"
    world = World(monday if monday.exists() else loop_dir / "world" / "world.db")
    card_p = (first("signal_card") or {}).get("payload", {})
    providers = []
    if card_p:
        b, a = card_p["before"]["period"], card_p["after"]["period"]
        for dim in (card_p.get("segment") or {"calendar_provider": []}):
            for value in catalog()[1][dim]["values"]:
                r = world.compare_periods(card_p["metric"], b["start"], b["end"], a["start"], a["end"], {dim: [value]})
                if r["status"] == "value":
                    providers.append({"dimension": dim, "value": value, "before": r["before"], "after": r["after"],
                                      "relative": r["relative"], "p_value": r.get("p_value")})

    releases = {r["id"]: r for r in scenario["releases"]}
    release = releases[truth["cause"]["release"]]
    agents = {}
    for t in trace:
        m = re.match(r"(\w+) finished", t.get("event", ""))
        if m:
            a = agents.setdefault(m.group(1), {"runs": 0, "turns": 0, "seconds": 0.0, "cost_usd": 0.0})
            a["runs"] += 1
            a["turns"] += t.get("turns", 0)
            a["seconds"] = round(a["seconds"] + t.get("seconds", 0), 1)
            a["cost_usd"] = round(a["cost_usd"] + t.get("cost_usd", 0), 4)

    chief = None
    if chief_dir:
        copy(chief_dir / "brief.html", data / "chief" / "brief.html")
        copy(chief_dir / "workplace.html", data / "chief" / "workplace.html")
        outbox = chief_dir / "outbox.jsonl"
        note = [json.loads(l)["text"] for l in outbox.read_text(encoding="utf-8").splitlines() if l.strip()] if outbox.exists() else []
        chief = {"brief_page": "data/chief/brief.html", "note": note[0] if note else None,
                 "usage": usage(chief_dir / "transcript.jsonl"), **chief_facts(chief_dir)}

    run = {
        "scenario": summary["scenario"], "seed": summary["seed"],
        "company": (ROOT / "company" / "tallybird" / "context.md").read_text(encoding="utf-8").split("\n\n")[1],
        "today": "2026-03-02",
        "messages": scenario.get("messages", []),
        "weeks": [(FIRST_WEEK + timedelta(weeks=i)).isoformat() for i in range(weeks)],
        "series": {"with_action": with_action, "no_action": no_action},
        "release": {"id": release["id"], "title": release["title"], "notes": release["notes"],
                    "date": (FIRST_WEEK + timedelta(weeks=release["at"]["week"] - 1, days=release["at"]["day"] - 1)).isoformat()},
        "card": first("signal_card"), "packet": first("decision_packet"), "providers": providers,
        "reviews": {r["refs"][0]: {"id": r["id"], "author": r["author"], **r["payload"]} for r in by_type("review")},
        "bet": first("bet"), "actions": by_type("action"), "builds": builds,
        "verdict": first("verdict"), "call": first("call"),
        "summary": summary, "agents": agents, "trace": trace,
        "usage": {"signal": usage(loop_dir / "transcript-signal-sense.jsonl"), "quality_packet": usage(loop_dir / "transcript-quality-review.jsonl"),
                  "builder": usage(loop_dir / "transcript-builder-build.jsonl"), "quality_build": usage(loop_dir / "transcript-quality-build.jsonl")},
        "truth": {"cause": truth["cause"], "findings": truth["expected_findings"], "decision": truth["decision"],
                  "traps": truth.get("traps_in_data", [])},
        "chief": chief,
        "live_runs": live_runs_table(),
    }
    (data / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    # A script copy, so the page also opens straight from disk, where browsers block fetch().
    (data / "run.js").write_text("window.RUN = " + json.dumps(run) + ";\n", encoding="utf-8")
    return run


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.replay")
    parser.add_argument("--loop", type=Path, required=True, help="A finished loop run folder, such as runs/loop/live-4")
    parser.add_argument("--chief", type=Path, help="A Chief run folder with brief.html")
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    run = build(args.loop.resolve(), args.chief.resolve() if args.chief else None, args.out.resolve())
    print(f"Replay data written to {args.out / 'data'}: {len(run['builds'])} builds, verdict {run['verdict']['payload']['outcome']}.")
    print(f"Open {(args.out / 'index.html').resolve().as_uri()}")


if __name__ == "__main__":
    main()
