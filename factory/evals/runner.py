"""Runs one trial: a fresh world copy, an empty ledger, one headless Claude Code session."""

from __future__ import annotations

import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from sandbox.generator import generate

from .suite import ROOT, AgentConfig, Task

SERVER_MODULES = {
    "metrics": "factory.servers.metrics_server",
    "warehouse": "factory.servers.warehouse_server",
    "support": "factory.servers.support_server",
    "releases": "factory.servers.releases_server",
    "ledger": "factory.servers.ledger_server",
}


@dataclass
class Trial:
    task: Task
    index: int
    dir: Path
    tool_calls: list[dict] = field(default_factory=list)  # {name, input, result}
    final_text: str = ""
    cost_usd: float = 0.0
    turns: int = 0
    duration_s: float = 0.0
    error: str | None = None

    @property
    def ledger_path(self) -> Path:
        return self.dir / "ledger.jsonl"

    @property
    def world_path(self) -> Path:
        return self.dir / "world" / "world.db"


def claude_binary() -> str:
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    found = shutil.which("claude")
    if found:
        return found
    pattern = str(Path.home() / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / "claude*")
    candidates = sorted(glob.glob(pattern))
    if not candidates:
        raise RuntimeError("Claude Code not found. Set CLAUDE_BIN.")
    return candidates[-1]


def world_for(task: Task) -> Path:
    run = ROOT / "runs" / task.scenario / f"seed-{task.seed}"
    if not (run / "world" / "world.db").exists():
        generate(task.scenario, seed=task.seed, out=run)
    return run / "world" / "world.db"


def prepare(task: Task, index: int, root: Path) -> Trial:
    trial_dir = root / task.id / f"trial-{index + 1}"
    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    (trial_dir / "world").mkdir(parents=True)
    shutil.copy(world_for(task), trial_dir / "world" / "world.db")
    trial = Trial(task, index, trial_dir)
    apply_setup(trial)
    trial.ledger_path.touch()
    return trial


def apply_setup(trial: Trial) -> None:
    conn = sqlite3.connect(trial.world_path)
    for step in trial.task.setup:
        if "insert_ticket" in step:
            t = step["insert_ticket"]
            ws, user = conn.execute(
                "SELECT w.workspace_id, u.user_id FROM workspaces w JOIN users u USING (workspace_id) "
                "WHERE w.calendar_provider = ? AND w.created_at < ? ORDER BY w.created_at DESC LIMIT 1",
                (t["calendar_provider"], t["created_at"]),
            ).fetchone()
            conn.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)",
                         (t["ticket_id"], t["created_at"], ws, user, t["subject"], t["body"], t["support_tag"]))
    conn.commit()
    conn.close()


def mcp_config(agent: AgentConfig, trial: Trial) -> Path:
    env = {
        "FACTORY_WORLD": str(trial.world_path),
        "FACTORY_LEDGER": str(trial.ledger_path),
        "FACTORY_AGENT": agent.name,
        "PYTHONIOENCODING": "utf-8",
    }
    config = {"mcpServers": {
        name: {"type": "stdio", "command": sys.executable, "args": ["-m", SERVER_MODULES[name]], "env": env}
        for name in agent.servers
    }}
    path = trial.dir / "mcp.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def subagents_file(agent: AgentConfig, trial: Trial) -> Path | None:
    if not agent.subagents:
        return None
    defined = {
        name: {
            "description": spec["description"],
            "prompt": (agent.dir / spec["prompt_file"]).read_text(encoding="utf-8"),
            "tools": spec["tools"],
            "model": spec.get("model", agent.model),
        }
        for name, spec in agent.subagents.items()
    }
    path = trial.dir / "agents.json"
    path.write_text(json.dumps(defined, indent=2), encoding="utf-8")
    return path


def run_claude(agent: AgentConfig, trial: Trial) -> None:
    allowed = [f"mcp__{s}" for s in agent.servers]
    subagents = subagents_file(agent, trial)
    cmd = [
        claude_binary(), "-p", trial.task.prompt,
        "--system-prompt", (agent.dir / agent.skill).read_text(encoding="utf-8"),
        "--model", agent.model,
        "--max-turns", str(agent.max_turns),
        "--mcp-config", str(mcp_config(agent, trial)),
        "--strict-mcp-config",
        "--tools", "Agent" if subagents else "",
        "--allowedTools", *allowed, *(["Agent"] if subagents else []),
        "--permission-mode", "dontAsk",
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
    ]
    if subagents:
        cmd += ["--agents", str(subagents)]
    started = time.time()
    proc = subprocess.run(cmd, cwd=trial.dir, capture_output=True, text=True, encoding="utf-8", timeout=1800)
    trial.duration_s = round(time.time() - started, 1)
    (trial.dir / "transcript.jsonl").write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0 and not proc.stdout:
        trial.error = proc.stderr[-2000:]
    parse_transcript(trial, proc.stdout)


def parse_transcript(trial: Trial, stream: str) -> None:
    pending: dict[str, dict] = {}
    for line in stream.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "assistant":
            for block in msg["message"].get("content", []):
                if block.get("type") == "tool_use":
                    call = {"name": block["name"], "input": block.get("input", {}), "result": ""}
                    pending[block["id"]] = call
                    trial.tool_calls.append(call)
        elif msg.get("type") == "user":
            content = msg.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                    pending[block["tool_use_id"]]["result"] = flatten(block.get("content"))
        elif msg.get("type") == "result":
            trial.final_text = msg.get("result", "") or ""
            trial.cost_usd = msg.get("total_cost_usd", 0.0) or 0.0
            trial.turns = msg.get("num_turns", 0) or 0
            if msg.get("is_error"):
                trial.error = trial.final_text or msg.get("subtype")


def flatten(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return json.dumps(content)


def run_trial(agent: AgentConfig | None, task: Task, index: int, root: Path) -> Trial:
    trial = prepare(task, index, root)
    if agent is not None:
        try:
            run_claude(agent, trial)
        except subprocess.TimeoutExpired:
            trial.error = "timeout"
    return trial
