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

from factory import code, ledger
from factory.metrics import World
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
                       "diff": diff_text, "review": review})

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
        chief = {"brief": "data/chief/brief.html", "note": note[0] if note else None}

    run = {
        "scenario": summary["scenario"], "seed": summary["seed"],
        "company": (ROOT / "company" / "tallybird" / "context.md").read_text(encoding="utf-8").split("\n\n")[1],
        "today": "2026-03-02",
        "messages": scenario.get("messages", []),
        "weeks": [(FIRST_WEEK + timedelta(weeks=i)).isoformat() for i in range(weeks)],
        "series": {"with_action": with_action, "no_action": no_action},
        "release": {"id": release["id"], "title": release["title"], "notes": release["notes"],
                    "date": (FIRST_WEEK + timedelta(weeks=release["at"]["week"] - 1, days=release["at"]["day"] - 1)).isoformat()},
        "card": first("signal_card"), "packet": first("decision_packet"),
        "reviews": {r["refs"][0]: {"id": r["id"], "author": r["author"], **r["payload"]} for r in by_type("review")},
        "bet": first("bet"), "actions": by_type("action"), "builds": builds,
        "verdict": first("verdict"), "call": first("call"),
        "summary": summary, "agents": agents, "trace": trace,
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
