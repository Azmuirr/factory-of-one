import argparse
import json
from datetime import datetime, timezone

from . import graders
from .runner import run_trial
from .suite import ROOT, load_agent, load_suite


def grade_task(task, trials) -> dict:
    per_trial = []
    for trial in trials:
        assertions, advisory = [], []
        for g in task.graders:
            if g.cross_trial:
                continue
            results = graders.run(g, trial, task.scenario)
            (advisory if g.advisory else assertions).extend(results)
        hard = assertions
        passed = bool(hard) and all(ok for _, ok, _ in hard) and not trial.error
        per_trial.append({
            "trial": trial.index + 1,
            "passed": passed,
            "partial": round(sum(ok for _, ok, _ in hard) / len(hard), 3) if hard else 0.0,
            "failed": [f"{n}: {d}" for n, ok, d in hard if not ok],
            "advisory": [f"{n}: {'pass' if ok else 'fail'} ({d})" for n, ok, d in advisory],
            "error": trial.error,
            "cost_usd": round(trial.cost_usd, 4),
            "turns": trial.turns,
            "duration_s": trial.duration_s,
            "transcript": str(graders.transcript_path(trial).relative_to(ROOT)),
        })
    cross = [a for g in task.graders if g.cross_trial for a in graders.run(g, trials, task.scenario)]
    cross_ok = all(ok for _, ok, _ in cross)
    return {
        "task": task.id,
        "kind": task.kind,
        "trials": per_trial,
        "cross_trial": [f"{n}: {'pass' if ok else 'fail'} ({d})" for n, ok, d in cross],
        "pass_at_k": any(t["passed"] for t in per_trial),
        "pass_pow_k": all(t["passed"] for t in per_trial) and cross_ok,
        "mean_partial": round(sum(t["partial"] for t in per_trial) / len(per_trial), 3),
    }


def markdown(report: dict) -> str:
    k = report["trials_per_task"]
    lines = [
        f"# {report['agent']} eval, {report['run_id']}",
        "",
        f"Agent mode: {report['mode']}. Trials per task: {k}. Estimated cost: ${report['cost_usd']:.2f}.",
        "",
        f"| Task | Kind | pass@{k} | pass^{k} | Partial credit | Failed assertions (first trial that failed) |",
        "|---|---|---|---|---|---|",
    ]
    for t in report["tasks"]:
        failed = next((tr["failed"] for tr in t["trials"] if tr["failed"]), [])
        lines.append(f"| {t['task']} | {t['kind']} | {'yes' if t['pass_at_k'] else 'no'} | {'yes' if t['pass_pow_k'] else 'no'} "
                     f"| {t['mean_partial']:.0%} | {'; '.join(failed[:3]) or 'none'} |")
    lines += ["", "| Suite | pass@k | pass^k |", "|---|---|---|"]
    for kind, s in report["summary"].items():
        lines.append(f"| {kind} | {s['pass_at_k']} | {s['pass_pow_k']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.evals")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run an agent's eval suite")
    run.add_argument("agent")
    run.add_argument("--trials", type=int)
    run.add_argument("--task", action="append", help="Run only these task ids")
    run.add_argument("--null", action="store_true", help="Run no model; proves graders fail an empty agent")
    args = parser.parse_args()

    suite = load_suite(args.agent)
    agent = None if args.null else load_agent(args.agent)
    k = args.trials or suite.trials
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ("-null" if args.null else "")
    trial_root = ROOT / "runs" / "evals" / args.agent / run_id

    results = []
    for task in suite.tasks:
        if args.task and task.id not in args.task:
            continue
        trials = []
        for i in range(k):
            print(f"{task.id}: trial {i + 1}/{k}", flush=True)
            trials.append(run_trial(agent, task, i, trial_root))
        results.append(grade_task(task, trials))

    summary = {}
    for kind in ("capability", "regression"):
        of_kind = [r for r in results if r["kind"] == kind]
        if of_kind:
            summary[kind] = {
                "pass_at_k": f"{sum(r['pass_at_k'] for r in of_kind)}/{len(of_kind)}",
                "pass_pow_k": f"{sum(r['pass_pow_k'] for r in of_kind)}/{len(of_kind)}",
            }
    report = {
        "agent": args.agent,
        "agent_version": agent.version if agent else None,
        "suite_version": suite.version,
        "run_id": run_id,
        "mode": "null" if args.null else "real",
        "trials_per_task": k,
        "cost_usd": round(sum(t["cost_usd"] for r in results for t in r["trials"]), 4),
        "summary": summary,
        "tasks": results,
    }
    out = ROOT / "bench" / "results" / args.agent
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{run_id}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / f"{run_id}.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))


if __name__ == "__main__":
    main()
