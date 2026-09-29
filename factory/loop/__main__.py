"""Runs one loop on a scenario: SENSE and FRAME, DECIDE, BUILD, apply, PROVE, CALL, LEARN."""

from __future__ import annotations

import argparse
import sys
import json
import shutil
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from factory import ledger, review
from factory.evals.runner import Trial, run_claude, world_for
from factory.evals.suite import ROOT, Task, load_agent
from factory.loop.gates import Gates
from factory.metrics import World
from factory.verdict import verdict
from sandbox.generator import generate

HUMAN = {"kind": "human", "name": "pm"}
LOOP = {"kind": "code", "name": "loop"}  # the runner records approved and applied actions
AUTOPILOT = {"kind": "code", "name": "autopilot"}  # queues decisions while the PM is away; never applies them



def segment_text(segment: dict | None) -> str:
    return "; ".join(f"{k} = {', '.join(v)}" for k, v in (segment or {}).items()) or "everyone"

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
        prefix = {"bet": "bet", "action": "act", "verdict": "ver", "call": "call", "queue": "que"}[type]
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
            if (self.fixture.parent / "queries.jsonl").exists():
                shutil.copy(self.fixture.parent / "queries.jsonl", self.dir / "queries.jsonl")
            self.log("sense", "signal output loaded from fixture", fixture=str(self.fixture))
            return
        self.run_agent("signal", "diagnose-s01", "sense")

    def frame(self) -> None:
        """Bet ranks the work coming in: requests, docs, and Signal's packet. Quality reviews the list."""
        self.log("frame", "start")
        if self.fixture:
            self.load_fixture(lambda row: row["type"] == "candidates")
            self.log("frame", "bet output loaded from fixture")
        else:
            self.run_agent("bet", "frame-s01", "frame")
        ranked = self.latest("candidates")
        if ranked:
            self.quality_review(ranked["id"], "frame")

    def ranked_lines(self) -> list[str]:
        ranked = self.latest("candidates")
        if not ranked:
            return []
        p = ranked["payload"]
        unit = {"usd_per_week": "a week", "usd_per_year": "a year"}
        return ["Bet's ranking this week:",
                *[f"  {i['rank']}. {i['title']} (${i['size']['value']:,.0f} {unit[i['size']['unit']]}). Needs from you: {i['needs_from_pm']}"
                  for i in sorted(p["items"], key=lambda i: i["rank"])],
                *[f"  Set aside: {a['title']}. {a['why']}" for a in p.get("set_aside", [])], ""]

    def load_fixture(self, keep) -> None:
        for line in self.fixture.read_text(encoding="utf-8").splitlines():
            if line.strip() and keep(json.loads(line)):
                ledger.append(self.ledger, json.loads(line))

    def run_agent(self, name: str, task_id: str, station: str, prompt: str | None = None) -> None:
        if prompt is None:
            suite = yaml.safe_load((ROOT / "agents" / name / "evals" / "suite.yaml").read_text(encoding="utf-8"))
            prompt = next(t["prompt"] for t in suite["tasks"] if t["id"] == task_id)
        trial = Trial(Task(station, "capability", self.scenario, self.seed, prompt, []), 0, self.dir)
        run_claude(load_agent(name), trial)
        (self.dir / "transcript.jsonl").replace(self.dir / f"transcript-{name}-{station}.jsonl")
        self.agent_cost += trial.cost_usd
        self.log(station, f"{name} finished", cost_usd=round(trial.cost_usd, 4), turns=trial.turns, seconds=trial.duration_s,
                 error=trial.error)

    def quality_review(self, entry_id: str, station: str) -> dict | None:
        """Quality reviews one entry. With a fixture, a code-only review stands in for the agent."""
        if self.fixture:
            entries = ledger.read(self.ledger)
            entry = next(e for e in entries if e["id"] == entry_id)
            payload = review.code_only_review(entry, entries, self.world, self.dir)
            ledger.append(self.ledger, {"id": ledger.next_id(self.ledger, "review"), "type": "review", "ts": self.sim_now(),
                                        "author": {"kind": "code", "name": "review"},
                                        "refs": [entry_id], "payload": payload})
        else:
            self.run_agent("quality", "", station, prompt=f"Review ledger entry {entry_id} before it reaches the PM.")
        found = [e for e in ledger.read(self.ledger) if e["type"] == "review" and entry_id in e["refs"]]
        if not found:
            self.log(station, "no review written", entry=entry_id)
            return None
        r = found[-1]["payload"]
        self.log(station, "review", entry=entry_id, verdict=r["verdict"], correctness=r["correctness"])
        return r

    def decide(self) -> bool:
        packet = self.latest("decision_packet")
        if not packet:
            self.log("decide", "no decision packet: nothing to decide")
            return False
        p = packet["payload"]
        card = self.latest("signal_card")
        briefing = "\n".join([
            *self.ranked_lines(),
            f"Question: {p['question']}",
            f"Signal: {card['payload']['headline'] if card else 'none'}",
            f"Diagnosis: {p['diagnosis']['metric']} moved for {segment_text(p['diagnosis'].get('segment'))} after {p['diagnosis'].get('release_id') or 'no release'}. "
            f"Mechanism: {p['diagnosis'].get('mechanism_metric')}. Customer voice: {p['diagnosis'].get('voice_workspaces')} workspaces.",
            *[f"- {c['class'].upper()}: {c['text']}" for c in p["cause"]],
            *[f"- RULED OUT: {c['text']}" for c in p.get("ruled_out", [])],
            f"Size: {p['size']['value']} {p['size']['unit']} ({p['size']['method']})",
            f"Recommended action: {p['recommended_action']['name']} {p['recommended_action']['params'].get('release_id', '')} for {segment_text(p['recommended_action']['params'].get('segment'))}",
            f"Cheapest test: {p['cheapest_test']}",
            f"Would change if: {'; '.join(p['would_change_if'])}",
            f"Unknowns: {'; '.join(p.get('unknowns', [])) or 'none'}",
            *self.review_lines(packet["id"]),
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

    def review_lines(self, entry_id: str) -> list[str]:
        found = [e for e in ledger.read(self.ledger) if e["type"] == "review" and entry_id in e["refs"]]
        if not found:
            return ["Quality: no review."]
        r = found[-1]["payload"]
        return [f"Quality: {r['verdict']}. Checks: {r['correctness']}",
                *[f"- FINDING ({f['severity']}): {f['claim']} Smallest action: {f['smallest_action']}" for f in r["findings"]]]

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
        bet = self.latest("bet")
        builds = [e for e in ledger.read(self.ledger) if e["type"] == "build" and e["ts"] >= bet["ts"]]
        verdicts = {}
        for build in builds:
            build_review = self.quality_review(build["id"], "build")
            verdicts[build["id"]] = build_review["verdict"] if build_review else None
        not_shipped = [b for b in builds if verdicts[b["id"]] != "SHIP"]
        if not builds or not_shipped:
            lines = ["Quality did not ship every build." if builds else "Builder built nothing.",
                     *[line for b in not_shipped for line in (f"{b['payload']['kind']} {b['id']}:", *self.review_lines(b["id"]))]]
            a = self.gates.ask("confirm", "\n".join(lines), [("apply", "Apply the action anyway? (yes/no)", "no")])
            if a["apply"].lower() not in ("y", "yes"):
                self.log("build", "stopped after Quality's review")
                return False
        payload = {**proposed["payload"], "status": "approved"}
        act_id = self.write("action", LOOP, payload, [proposed["id"]])
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
        # Keep the world every earlier artifact was checked against, so its numbers can be replayed later.
        (self.dir / "world-before").mkdir(exist_ok=True)
        shutil.copy(self.world, self.dir / "world-before" / "world.db")
        shutil.copy(generated / "world" / "world.db", self.world)
        self.write("action", LOOP, {"name": action["name"], "params": action["params"], "status": "applied"}, [self.latest("action")["id"]])
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
        ver_id = self.write("verdict", {"kind": "code", "name": "verdict"}, result["entry"], [bet["id"], applied["id"]])
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

    def rights(self) -> dict:
        from factory import config as install
        from factory import policy
        cfg = install.load()
        return policy.load(cfg.decision_rights) if cfg.decision_rights else {"away": {"actions": "prepare_only", "send": {}}}

    def comms_readout(self, task_id: str, moment: str, fixture: Path | None) -> dict | None:
        source = fixture or self.fixture
        if source:
            rows = [json.loads(l) for l in source.read_text(encoding="utf-8").splitlines() if l.strip()]
            for row in rows:
                if row["type"] == "readout" and row["payload"]["moment"] == moment:
                    ledger.append(self.ledger, {**row, "id": ledger.next_id(self.ledger, "readout")})
            self.log("tell", "comms output loaded from fixture")
        else:
            self.run_agent("comms", task_id, "tell")
        return self.latest("readout")

    def tell(self) -> None:
        """Comms drafts the decision for each audience. The PM approves at the Tell gate; code checks numbers and sends."""
        from factory import comms
        readout = self.comms_readout("tell-decided-s01", "decision", None)
        if not readout:
            self.log("tell", "no readout written")
            return
        lines = [f"{v['audience'].upper()} to {', '.join(v['to'])} ({v['channel']}):\n{v['text']}" for v in readout["payload"]["versions"]]
        problems = comms.number_problems(readout["payload"], ledger.read(self.ledger))
        a = self.gates.ask("tell", "\n\n".join(lines + ([f"Numbers that do not match the ledger: {problems}"] if problems else [])),
                           [("send", "Send these versions? (yes/no)", "no")])
        if a["send"].lower() not in ("y", "yes"):
            self.log("tell", "the PM chose not to send")
            return
        results = comms.deliver(readout, ledger.read(self.ledger), self.world, self.rights(), approved_by_pm=True, out=self.dir)
        self.log("tell", "readout delivered", sent=[r["audience"] for r in results if r["sent"]], held=[r["audience"] for r in results if not r["sent"]])

    def learn(self, result: dict | None) -> dict:
        summary = {
            "scenario": self.scenario,
            "seed": self.seed,
            "brier": result["brier"] if result else None,
            "prediction_hit": result["prediction_hit"] if result else None,
            "pm_minutes": round(sum(r.pm_minutes for r in self.gates.records), 1),
            "gates": [{"gate": r.gate, "pm_minutes": r.pm_minutes, "words_shown": r.words_shown, "inputs": r.inputs, "scripted": r.scripted,
                       "wall_seconds": r.wall_seconds} for r in self.gates.records],
            "agent_cost_usd": round(self.agent_cost, 4),
            "ledger_entries": len(ledger.read(self.ledger)),
        }
        self.log("learn", "loop scored", **{k: summary[k] for k in ("brier", "prediction_hit", "pm_minutes", "agent_cost_usd")})
        return summary

    # The PM is away: prepare everything, apply nothing (decision D10) -------------

    def chief_away(self, fixture: Path | None) -> None:
        if fixture:
            rows = [json.loads(l) for l in fixture.read_text(encoding="utf-8").splitlines() if l.strip()]
            for row in rows:
                ledger.append(self.ledger, row)
            # In a replay, the urgent notes Chief would have posted are posted from its brief.
            away = next((r["payload"] for r in reversed(rows) if r["type"] == "brief" and r["payload"].get("mode") == "away"), {})
            for u in away.get("urgent", []):
                self.notify(f"{u['why']} {u['do']}")
            self.log("brief", "chief output loaded from fixture")
            return
        self.run_agent("chief", "away-monday-s01", "brief")

    def notify(self, text: str) -> bool:
        """The one message the factory may send while the PM is away: to the PM's own channel, within the daily limit."""
        from factory import config as install
        from factory import policy
        cfg = install.load()
        limit = policy.load(cfg.decision_rights)["away"]["urgent"]["max_per_day"] if cfg.decision_rights else 3
        outbox = self.dir / "outbox.jsonl"
        sent = sum(1 for l in outbox.read_text(encoding="utf-8").splitlines() if json.loads(l).get("to") == "self") if outbox.exists() else 0
        if sent >= limit:
            self.log("notify", "held for the digest: the daily limit is reached", text=text)
            return False
        with outbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": self.sim_now(), "to": "self", "text": text}) + "\n")
        return True

    def away(self, chief_fixture: Path | None = None, comms_fixture: Path | None = None) -> None:
        """Chief's away brief, Signal's check, Quality's review. A decision is queued for the PM and nothing is applied."""
        self.setup()
        self.chief_away(chief_fixture)
        self.sense_and_frame()
        packet = self.latest("decision_packet")
        if packet:
            verdict_ = self.quality_review(packet["id"], "review")
            self.frame()
            review_entry = next((e for e in reversed(ledger.read(self.ledger)) if e["type"] == "review" and packet["id"] in e["refs"]), None)
            prepared = [e["id"] for e in ledger.read(self.ledger) if e["type"] in ("signal_card", "decision_packet", "candidates")]
            self.write("queue", AUTOPILOT, {"status": "waiting_for_pm", "packet": packet["id"], "prepared": prepared,
                                            "review": review_entry["id"] if review_entry else None,
                                            "reason": "Decision rights are prepare_only: the action waits for the PM"}, [packet["id"]])
            self.log("queue", "decision waiting for the PM", packet=packet["id"])
            if verdict_ and verdict_["verdict"] == "STOP":
                self.notify(f"Quality stopped {packet['id']}. Nothing was applied. Details in the digest.")
            else:
                d = packet["payload"]["diagnosis"]
                self.notify(f"{d['metric']} moved for {segment_text(d.get('segment'))}. A decision is waiting for you; nothing was applied.")
            from factory import comms
            readout = self.comms_readout("tell-away-s01", "status", comms_fixture)
            if readout:
                results = comms.deliver(readout, ledger.read(self.ledger), self.world, self.rights(), approved_by_pm=False, out=self.dir)
                self.log("tell", "status delivered by the decision rights", sent=[r["audience"] for r in results if r["sent"]],
                         held=[r["audience"] for r in results if not r["sent"]])
        (self.dir / "trace.jsonl").write_text("".join(json.dumps(t) + "\n" for t in self.trace), encoding="utf-8")

    def resume(self) -> dict:
        """Back at the keyboard: continue from the queued decision."""
        trace = self.dir / "trace.jsonl"
        self.trace = [json.loads(l) for l in trace.read_text(encoding="utf-8").splitlines()] if trace.exists() else []
        queued = self.latest("queue")
        self.log("resume", "the PM is back", queued=queued["id"] if queued else None)
        result = None
        if self.decide():
            self.build()
            if self.approve():
                self.apply()
                result = self.prove()
                if result:
                    self.call(result)
                    self.tell()
        if queued:
            self.write("queue", AUTOPILOT, {**queued["payload"], "status": "decided", "reason": "The PM decided at the gate"}, [queued["id"]])
        summary = self.learn(result)
        (self.dir / "trace.jsonl").write_text("".join(json.dumps(t) + "\n" for t in self.trace), encoding="utf-8")
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    def run(self) -> dict:
        self.setup()
        self.sense_and_frame()
        packet = self.latest("decision_packet")
        if packet:
            self.quality_review(packet["id"], "review")
        self.frame()
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
    parser.add_argument("--resume", type=Path, help="Continue an autopilot run from its queued decision")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    script = yaml.safe_load(args.gates.read_text(encoding="utf-8")) if args.gates else None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.resume:
        out = args.resume
        summary = Loop(args.scenario, args.seed, out, Gates(script), args.fixture).resume()
        print("\n" + json.dumps(summary, indent=2))
        print(f"\nLedger, trace, and summary: {out}")
        return
    out = args.out or ROOT / "runs" / "loop" / f"{args.scenario}-seed{args.seed}-{run_id}"
    summary = Loop(args.scenario, args.seed, out, Gates(script), args.fixture).run()
    print("\n" + json.dumps(summary, indent=2))
    print(f"\nLedger, trace, and summary: {out}")


if __name__ == "__main__":
    main()
