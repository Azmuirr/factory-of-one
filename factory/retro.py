"""Retro's facts, owned by code: what a real company could observe across a week of runs. No answer keys are read.
Also applies a patch the PM approved: an exact edit to one agent's instructions, plus the eval case that reproduces the failure."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def week_stats(week: Path) -> dict:
    """Quality's reviews, predictions against outcomes, overrides, and time per station, across every run folder in `week`."""
    runs = sorted(p for p in Path(week).iterdir() if (p / "ledger.jsonl").exists())
    failures, reviews, predictions, overrides, seconds = [], [], [], 0, Counter()
    for run in runs:
        entries = read_jsonl(run / "ledger.jsonl")
        by_id = {e["id"]: e for e in entries}
        for e in entries:
            if e["type"] != "review":
                continue
            target = by_id.get(e["refs"][0], {})
            agent = target.get("author", {}).get("name", "unknown")
            review = {"run": run.name, "review": e["id"], "entry": target.get("id"), "type": target.get("type"), "agent": agent,
                      "verdict": e["payload"]["verdict"],
                      "failed_checks": [k for k, v in e["payload"]["correctness"].items() if v == "fail"],
                      "findings": [{"claim": f["claim"], "smallest_action": f["smallest_action"]} for f in e["payload"]["findings"]]}
            reviews.append(review)
            failures += [{"run": run.name, "agent": agent, "check": c, "review": e["id"]} for c in review["failed_checks"]]
        packets_sent_back = {r["entry"] for r in reviews if r["run"] == run.name and r["type"] == "decision_packet" and r["verdict"] != "SHIP"}
        bets = [e for e in entries if e["type"] == "bet"]
        overrides += sum(1 for b in bets if set(b["refs"]) & packets_sent_back)
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8")) if (run / "summary.json").exists() else {}
        for b in bets:
            predictions.append({"run": run.name, "bet": b["id"], "expected": b["payload"]["prediction"]["expected"],
                                "confidence": b["payload"]["confidence"], "hit": summary.get("prediction_hit"), "brier": summary.get("brier")})
        for t in read_jsonl(run / "trace.jsonl"):
            seconds[t["station"]] += t.get("seconds") or 0
    grouped = defaultdict(set)
    for f in failures:
        grouped[(f["agent"], f["check"])].add(f["run"])
    recurring = [{"agent": a, "check": c, "runs": len(r), "run_names": sorted(r)} for (a, c), r in sorted(grouped.items()) if len(r) >= 2]
    scored = [p for p in predictions if p["brier"] is not None]
    return {"runs": len(runs), "run_names": [r.name for r in runs], "reviews": reviews, "recurring": recurring, "overrides": overrides,
            "predictions": predictions, "scored_bets": len(scored),
            "mean_brier": round(sum(p["brier"] for p in scored) / len(scored), 3) if scored else None,
            "seconds_by_station": dict(seconds.most_common()), "slowest_station": seconds.most_common(1)[0][0] if seconds else None}


def stats_numbers(stats: dict) -> set[float]:
    """Every number Retro may cite: each field in the week's stats, and each number written in the findings it carries."""
    from factory import numbers as nums
    pool: set[float] = set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            pool.add(float(v))
        elif isinstance(v, str):
            pool.update(float(d.replace(",", "")) for d, _ in nums.TEXT_NUMBER.findall(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(stats)
    return pool


def suite_graders(agent: str, agents_root: Path = AGENTS) -> list[str]:
    """The names of the graders in an agent's own suite. Names only: never the tasks' answer keys."""
    path = agents_root / agent / "evals" / "suite.yaml"
    if not path.exists():
        return []
    suite = yaml.safe_load(path.read_text(encoding="utf-8"))
    return sorted({g if isinstance(g, str) else g["name"] for t in suite["tasks"] for g in t["graders"]})


def instructions_path(agent: str, name: str, agents_root: Path = AGENTS) -> Path:
    """Only an agent's own instruction files: never its evals, fixtures, or anything outside agents/."""
    folder = (agents_root / agent).resolve()
    path = (folder / name).resolve()
    if agent in ("", ".", "..") or "/" in agent or "\\" in agent or path.parent != folder or path.suffix != ".md" or not path.is_file():
        raise ValueError(f"{agent}/{name} is not one of an agent's instructions files")
    return path


def read_skill(agent: str, name: str, agents_root: Path = AGENTS) -> str:
    return instructions_path(agent, name, agents_root).read_text(encoding="utf-8")


def apply_patch(patch: dict, agents_root: Path = AGENTS) -> Path:
    """Apply an approved patch: replace `old` with `new` (it must appear exactly once) and add the eval case to the suite."""
    path = instructions_path(patch["agent"], patch["file"], agents_root)
    text = path.read_text(encoding="utf-8")
    if text.count(patch["old"]) != 1:
        raise ValueError(f"`old` must appear exactly once in {patch['agent']}/{patch['file']}; it appears {text.count(patch['old'])} times")
    suite_path = agents_root / patch["agent"] / "evals" / "suite.yaml"
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    if patch["eval_case"]["id"] in {t["id"] for t in suite["tasks"]}:
        raise ValueError(f"the suite already has a task {patch['eval_case']['id']}")
    path.write_text(text.replace(patch["old"], patch["new"]), encoding="utf-8")
    case = {"id": patch["eval_case"]["id"], "kind": "regression", "scenario": patch["eval_case"]["scenario"],
            "prompt": patch["eval_case"]["prompt"], "graders": patch["eval_case"]["graders"]}
    with suite_path.open("a", encoding="utf-8") as f:
        f.write("\n  # Added by Retro, approved by the PM. Failure: " + patch["failure"]["summary"].replace("\n", " ")[:160] + "\n")
        f.write("".join("  " + line + "\n" for line in yaml.safe_dump([case], sort_keys=False).splitlines()))
    return path


def main() -> None:
    """python -m factory.retro run <run folders...>      Retro reads those runs and proposes patches.
    python -m factory.retro apply <retro run> <patch id>  Shows the change and applies it only if the PM says yes."""
    import argparse
    import shutil
    import sys
    from datetime import datetime, timezone

    from factory import ledger
    from factory.evals.runner import Trial, run_claude, world_for
    from factory.evals.suite import Task, load_agent

    parser = argparse.ArgumentParser(prog="python -m factory.retro")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("runs", nargs="+", type=Path)
    run.add_argument("--scenario", default="s01-calendar-gate")
    ap = sub.add_parser("apply")
    ap.add_argument("folder", type=Path)
    ap.add_argument("patch")
    ap.add_argument("--yes", action="store_true", help="Approve without asking")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.command == "run":
        out = ROOT / "runs" / "retro" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for r in args.runs:
            (out / "week" / f"{r.parent.name}-{r.name}").mkdir(parents=True)
            for name in ("ledger.jsonl", "summary.json", "trace.jsonl"):
                if (r / name).exists():
                    shutil.copy(r / name, out / "week" / f"{r.parent.name}-{r.name}" / name)
        task = Task("retro", "capability", args.scenario, 1, "It is Friday. Write this week's retro.", [])
        (out / "world").mkdir()
        shutil.copy(world_for(task), out / "world" / "world.db")
        trial = Trial(task, 0, out)
        trial.ledger_path.touch()
        run_claude(load_agent("retro"), trial)
        for e in ledger.read(trial.ledger_path):
            if e["type"] == "retro":
                print("\n".join(["# Retro", *[f"- {l}" for l in e["payload"]["lines"]]]))
            if e["type"] == "patch":
                p = e["payload"]
                print(f"\n## {e['id']}: {p['agent']}/{p['file']}\n{p['failure']['summary']}\n- {p['old']}\n+ {p['new']}\n"
                      f"Eval case: {p['eval_case']['id']}\nTo apply: python -m factory.retro apply {out} {e['id']}")
        return

    entries = ledger.read(args.folder / "ledger.jsonl")
    patch = next(e for e in entries if e["id"] == args.patch)["payload"]
    print(f"{patch['agent']}/{patch['file']}\n- {patch['old']}\n+ {patch['new']}\nEval case: {patch['eval_case']['id']}")
    if not args.yes and input("Apply this patch? (yes/no) [no]: ").strip().lower() not in ("y", "yes"):
        print("Not applied.")
        return
    path = apply_patch(patch)
    ledger.append(args.folder / "ledger.jsonl", {"id": ledger.next_id(args.folder / "ledger.jsonl", "patch"), "type": "patch",
                                                 "ts": entries[-1]["ts"], "author": {"kind": "human", "name": "pm"}, "refs": [args.patch],
                                                 "payload": {**patch, "status": "approved"}})
    print(f"Applied to {path}. Run its evals: python -m factory.evals run {patch['agent']} --task {patch['eval_case']['id']}")


if __name__ == "__main__":
    main()
