"""Runs one loop on a scenario: SENSE and FRAME, DECIDE, BUILD, apply, PROVE, CALL, LEARN."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from factory import ledger
from factory.evals.runner import Trial, run_claude, world_for
from factory.evals.suite import ROOT, Task, load_agent
from factory.loop.gates import Gates
from factory.metrics import World
from factory.verdict import verdict
from sandbox.generator import generate

HUMAN = {"kind": "human", "name": "pm"}
CHIEF = {"kind": "agent", "name": "chief", "version": "0.1.0"}


class Loop:
    def __init__(self, scenario: str, seed: int, out: Path, gates: Gates, fixture: Path | None):
        self.scenario, self.seed, self.dir, self.gates = scenario, seed, out, gates
        self.fixture = fixture.resolve() if fixture else None
        self.ledger = out / "ledger.jsonl"
        self.world = out / "world" / "world.db"
        self.trace: list[dict] = []
        self.agent_cost = 0.0
        self.action_date: str | None = None

    # Bookkeeping -------------------------------------------------------------

    def log(self, station: str, event: str, **details) -> None:
        self.trace.append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "station": station, "event": event, **details})
        print(f"[{station}] {event}" + (f": {details}" if details else ""), flush=True)

    def sim_now(self) -> str:
        return World(self.world).data_through.strftime("%Y-%m-%dT%H:%M:%SZ")

    def write(self, type: str, author: dict, payload: dict, refs: list[str]) -> str:
        prefix = {"bet": "bet", "action": "act", "verdict": "ver", "call": "call"}[type]
        n = sum(1 for e in ledger.read(self.ledger) if e["type"] == type)
        entry = {"id": f"{prefix}_{n + 1:04d}", "type": type, "ts": self.sim_now(), "author": author, "refs": refs, "payload": payload}
        ledger.append(self.ledger, entry)
        return entry["id"]

    def latest(self, type: str) -> dict | None:
        found = [e for e in ledger.read(self.ledger) if e["type"] == type]
        return found[-1] if found else None

    # Stations ----------------------------------------------------------------

    def setup(self) -> None:
        if self.dir.exists():
            shutil.rmtree(self.dir)
        (self.dir / "world").mkdir(parents=True)
        shutil.copy(world_for(Task("loop", "capability", self.scenario, self.seed, "", [])), self.world)
        self.ledger.touch()
        self.log("setup", "world ready", scenario=self.scenario, seed=self.seed, data_through=self.sim_now())

    def sense_and_frame(self) -> None:
        self.log("sense", "start")
        if self.fixture:
            self.load_fixture(lambda row: row["type"] in ("signal_card", "decision_packet"))
            self.log("sense", "signal output loaded from fixture", fixture=str(self.fixture))
            return
        self.run_agent("signal", "diagnose-s01", "sense")

    def load_fixture(self, keep) -> None:
        for line in self.fixture.read_text(encoding="utf-8").splitlines():
            if line.strip() and keep(json.loads(line)):
                ledger.append(self.ledger, json.loads(line))

    def run_agent(self, name: str, task_id: str, station: str) -> None:
        suite = yaml.safe_load((ROOT / "agents" / name / "evals" / "suite.yaml").read_text(encoding="utf-8"))
        prompt = next(t["prompt"] for t in suite["tasks"] if t["id"] == task_id)
        trial = Trial(Task(station, "capability", self.scenario, self.seed, prompt, []), 0, self.dir)
        run_claude(load_agent(name), trial)
        (self.dir / "transcript.jsonl").rename(self.dir / f"transcript-{name}.jsonl")
        self.agent_cost += trial.cost_usd
        self.log(station, f"{name} finished", cost_usd=round(trial.cost_usd, 4), turns=trial.turns, seconds=trial.duration_s,
                 error=trial.error)

    def decide(self) -> bool:
        packet = self.latest("decision_packet")
        if not packet:
            self.log("decide", "no decision packet: nothing to decide")
            return False
        p = packet["payload"]
        card = self.latest("signal_card")
        briefing = "\n".join([
            f"Question: {p['question']}",
            f"Signal: {card['payload']['headline'] if card else 'none'}",
            f"Diagnosis: {json.dumps(p['diagnosis'])}",
            *[f"- {c['class'].upper()}: {c['text']}" for c in p["cause"]],
            *[f"- RULED OUT: {c['text']}" for c in p.get("ruled_out", [])],
            f"Size: {p['size']['value']} {p['size']['unit']} ({p['size']['method']})",
            f"Recommended action: {json.dumps(p['recommended_action'])}",
            f"Cheapest test: {p['cheapest_test']}",
            f"Would change if: {'; '.join(p['would_change_if'])}",
            f"Unknowns: {'; '.join(p.get('unknowns', [])) or 'none'}",
        ])
        now = date.fromisoformat(self.sim_now()[:10])
        onset = date.fromisoformat(card["payload"]["after"]["period"]["start"]) if card else now
        baseline = World(self.world).get_metric(p["diagnosis"]["metric"], "2026-01-05", (onset - timedelta(days=1)).isoformat(),
                                                p["diagnosis"]["segment"])
        default_expected = str(baseline.get("value", ""))
        a = self.gates.ask("decide", briefing, [
            ("approve", "Approve the recommended action? (yes/no)", "yes"),
            ("hypothesis", "Your hypothesis", "The recommended action restores the metric in the diagnosed segment."),
            ("expected", f"Predicted {p['diagnosis']['metric']} after the action (default: the segment's pre-onset baseline)", default_expected),
            ("tolerance", "Tolerance (+/-)", "0.02"),
            ("confidence", "Confidence the prediction lands within tolerance (0 to 1)", "0.7"),
            ("kill_trigger", "Kill trigger", "No movement in the leading metric within 3 days of the action"),
            ("review_date", "Review date", (now + timedelta(days=14)).isoformat()),
        ])
        if a["approve"].lower() not in ("y", "yes"):
            self.log("decide", "rejected by PM")
            return False
        bet_id = self.write("bet", HUMAN, {
            "hypothesis": a["hypothesis"],
            "prediction": {"metric": p["diagnosis"]["metric"], "segment": p["diagnosis"]["segment"],
                           "expected": float(a["expected"]), "tolerance": float(a["tolerance"]), "by": a["review_date"]},
            "confidence": float(a["confidence"]),
            "kill_trigger": a["kill_trigger"],
            "review_date": a["review_date"],
        }, [packet["id"]])
        self.log("decide", "bet placed", bet=bet_id)
        return True

    def build(self) -> None:
        if self.fixture:
            self.load_fixture(lambda row: row["type"] == "build" or (row["type"] == "action" and row["payload"]["status"] == "proposed"))
            demos = self.fixture.parent / "demos"
            if demos.exists():
                shutil.copytree(demos, self.dir / "demos", dirs_exist_ok=True)
            self.log("build", "builder output loaded from fixture")
            return
        self.run_agent("builder", "build-s01", "build")

    def approve(self) -> bool:
        """Code checks that Builder proposed exactly what the PM approved. A mismatch goes to the PM."""
        packet = self.latest("decision_packet")["payload"]
        proposals = [e for e in ledger.read(self.ledger) if e["type"] == "action" and e["payload"]["status"] == "proposed"]
        if not proposals:
            self.log("build", "no action proposed")
            return False
        proposed = proposals[-1]
        if ledger.action_key(proposed["payload"]) != ledger.action_key(packet["recommended_action"]):
            briefing = "\n".join([f"Builder proposed {json.dumps(proposed['payload'])}",
                                  f"You approved {json.dumps(packet['recommended_action'])}"])
            a = self.gates.ask("confirm", briefing, [("apply", "Apply Builder's proposal? (yes/no)", "no")])
            if a["apply"].lower() not in ("y", "yes"):
                self.log("build", "proposal rejected by PM")
                return False
        payload = {**proposed["payload"], "status": "approved"}
        act_id = self.write("action", CHIEF, payload, [proposed["id"]])
        self.log("build", "proposal matches the approved decision", action=act_id)
        return True

    def apply(self) -> None:
        action = self.latest("action")["payload"]
        now = datetime.strptime(self.sim_now(), "%Y-%m-%dT%H:%M:%SZ") - timedelta(seconds=1)
        self.action_date = now.date().isoformat()
        day_index = (now.date() - date(2026, 1, 5)).days
        spec = [{"at": {"week": day_index // 7 + 1, "day": day_index % 7 + 1}, "name": action["name"],
                 "params": action["params"], "decided_by": "pm"}]
        actions_file = self.dir / "actions.yaml"
        actions_file.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
        started = time.time()
        generated = generate(self.scenario, seed=self.seed, actions_path=actions_file, out=self.dir / "world-after")
        shutil.copy(generated / "world" / "world.db", self.world)
        self.write("action", CHIEF, {"name": action["name"], "params": action["params"], "status": "applied"}, [self.latest("action")["id"]])
        self.log("apply", "world advanced with the action", data_through=self.sim_now(), seconds=round(time.time() - started, 1))

    def prove(self) -> dict | None:
        bet = self.latest("bet")
        card = self.latest("signal_card")
        before_start = card["payload"]["after"]["period"]["start"]
        applied = self.latest("action")
        result = verdict(World(self.world), bet["payload"], before_start, self.action_date)
        if result["status"] != "value":
            self.log("prove", "verdict not available", detail=result)
            return None
        ver_id = self.write("verdict", {"kind": "agent", "name": "signal", "version": "verdict-script"}, result["entry"], [bet["id"], applied["id"]])
        self.log("prove", "verdict written", verdict=ver_id, outcome=result["entry"]["outcome"], before=result["entry"]["before"],
                 after=result["entry"]["after"], prediction_hit=result["prediction_hit"])
        return result

    def call(self, result: dict) -> None:
        bet = self.latest("bet")["payload"]
        v = result["entry"]
        briefing = "\n".join([
            f"Outcome: {v['outcome']}. {v['metric']} in {json.dumps(v['segment'])}: {v['before']} before, {v['after']} after.",
            f"Method: {v['method']}",
            f"Your prediction: {bet['prediction']['expected']} +/- {bet['prediction']['tolerance']} at {bet['confidence']} confidence. "
            f"{'Hit' if result['prediction_hit'] else 'Missed'}.",
            f"Does not prove: {v['does_not_prove']}",
        ])
        a = self.gates.ask("call", briefing, [
            ("decision", "Ship, kill, or iterate?", "iterate"),
            ("rationale", "Why", "The action worked. Next, retest the original change behind a flag with a fix."),
        ])
        call_id = self.write("call", HUMAN, {"decision": a["decision"], "rationale": a["rationale"]}, [self.latest("verdict")["id"]])
        self.log("call", "call made", call=call_id, decision=a["decision"])

    def tell(self) -> None:
        self.log("tell", "Comms is not built yet. Nothing is sent.")

    def learn(self, result: dict | None) -> dict:
        summary = {
            "scenario": self.scenario,
            "seed": self.seed,
            "brier": result["brier"] if result else None,
            "prediction_hit": result["prediction_hit"] if result else None,
            "pm_minutes": round(sum(r.pm_minutes for r in self.gates.records), 1),
            "gates": [{"gate": r.gate, "pm_minutes": r.pm_minutes, "words_shown": r.words_shown, "inputs": r.inputs,
                       "wall_seconds": r.wall_seconds} for r in self.gates.records],
            "agent_cost_usd": round(self.agent_cost, 4),
            "ledger_entries": len(ledger.read(self.ledger)),
        }
        self.log("learn", "loop scored", **{k: summary[k] for k in ("brier", "prediction_hit", "pm_minutes", "agent_cost_usd")})
        return summary

    def run(self) -> dict:
        self.setup()
        self.sense_and_frame()
        result = None
        if self.decide():
            self.build()
            if self.approve():
                self.apply()
                result = self.prove()
                if result:
                    self.call(result)
                    self.tell()
        summary = self.learn(result)
        (self.dir / "trace.jsonl").write_text("".join(json.dumps(t) + "\n" for t in self.trace), encoding="utf-8")
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m factory.loop")
    parser.add_argument("--scenario", default="s01-calendar-gate")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--gates", type=Path, help="YAML answers for the gates. Omit to answer at the keyboard")
    parser.add_argument("--fixture", type=Path, help="Load agent outputs from a ledger file instead of running the agents")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    script = yaml.safe_load(args.gates.read_text(encoding="utf-8")) if args.gates else None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or ROOT / "runs" / "loop" / f"{args.scenario}-seed{args.seed}-{run_id}"
    summary = Loop(args.scenario, args.seed, out, Gates(script), args.fixture).run()
    print("\n" + json.dumps(summary, indent=2))
    print(f"\nLedger, trace, and summary: {out}")


if __name__ == "__main__":
    main()
