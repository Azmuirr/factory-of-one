"""Runs one trial: a fresh world copy, an empty ledger, one headless Claude Code session."""

from __future__ import annotations

import glob
import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from factory import config as install
from sandbox.generator import generate

from .suite import ROOT, AgentConfig, Task


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
    trial.ledger_path.touch()
    apply_setup(trial)
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
        if "copy_files" in step:
            source, target = ROOT / step["copy_files"]["from"], trial.dir / step["copy_files"]["to"]
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, target)
        if "seed_ledger" in step:
            seed = step["seed_ledger"]
            rows = [json.loads(line) for line in (ROOT / seed["file"]).read_text(encoding="utf-8").splitlines() if line.strip()]
            wanted = seed.get("ids")
            with trial.ledger_path.open("a", encoding="utf-8") as f:
                for row in rows:
                    if wanted is None or row["id"] in wanted:
                        f.write(json.dumps(row, sort_keys=True))
                        f.write("\n")
    conn.commit()
    conn.close()


def slots(agent: AgentConfig, trial: Trial) -> dict:
    return {"world": trial.world_path, "ledger": trial.ledger_path, "agent": agent.name, "demos": trial.dir / "demos"}


def system_prompt(agent: AgentConfig, config: install.Config, text: str, capabilities: list[str]) -> str:
    company = config.company.read_text(encoding="utf-8")
    references = [(ROOT / r).read_text(encoding="utf-8").strip() for r in agent.references]
    parts = [text.strip(), *references, install.tools_section(install.resolve(config, capabilities)), company.strip()]
    return "\n\n".join(parts)


def build_command(agent: AgentConfig, trial: Trial, config: install.Config | None = None) -> list[str]:
    """The exact headless Claude Code command for a trial. Writes mcp.json and agents.json into the trial folder."""
    config = config or install.load()
    mapping = install.resolve(config, agent.all_capabilities())
    tools = sorted(set(mapping.values()))
    mcp_path = trial.dir / "mcp.json"
    mcp_path.write_text(json.dumps({"mcpServers": install.mcp_servers(config, tools, slots(agent, trial))}, indent=2), encoding="utf-8")

    cmd = [
        claude_binary(), "-p", trial.task.prompt,
        "--system-prompt", system_prompt(agent, config, (agent.dir / agent.skill).read_text(encoding="utf-8"), agent.capabilities),
        "--model", agent.model,
        "--max-turns", str(agent.max_turns),
        "--mcp-config", str(mcp_path),
        "--strict-mcp-config",
        "--tools", "Agent" if agent.subagents else "",
        "--allowedTools", *tools, *(["Agent"] if agent.subagents else []),
        "--permission-mode", "dontAsk",
        "--output-format", "stream-json", "--verbose",
        "--no-session-persistence",
    ]
    if agent.subagents:
        defined = {}
        for name, spec in agent.subagents.items():
            sub_map = install.resolve(config, spec["capabilities"])
            defined[name] = {
                "description": spec["description"],
                "prompt": system_prompt(agent, config, (agent.dir / spec["prompt_file"]).read_text(encoding="utf-8"), spec["capabilities"]),
                "tools": sorted(set(sub_map.values())),
                "model": spec.get("model", agent.model),
            }
        agents_path = trial.dir / "agents.json"
        agents_path.write_text(json.dumps(defined, indent=2), encoding="utf-8")
        cmd += ["--agents", str(agents_path)]
    return cmd


def run_claude(agent: AgentConfig, trial: Trial) -> None:
    cmd = build_command(agent, trial)
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
