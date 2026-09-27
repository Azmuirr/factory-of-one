import json
from pathlib import Path

import pytest

from factory import config as install
from factory.evals.runner import Trial, build_command
from factory.evals.suite import AGENTS, Task, load_agent

ROOT = Path(__file__).resolve().parents[1]
AGENT_NAMES = [p.name for p in AGENTS.iterdir() if (p / "agent.yaml").exists()]


def test_sandbox_and_live_template_use_only_known_capabilities():
    assert install.load(ROOT / "config" / "sandbox.yaml").mode == "sandbox"
    assert install.load(ROOT / "config" / "live.example.yaml").mode == "live"


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_every_agent_capability_is_mapped_in_the_sandbox(name):
    sandbox = install.load(ROOT / "config" / "sandbox.yaml")
    install.resolve(sandbox, load_agent(name).all_capabilities())


def test_an_unmapped_capability_is_named_in_the_error():
    sandbox = install.load(ROOT / "config" / "sandbox.yaml")
    with pytest.raises(ValueError, match="chat.search"):
        install.resolve(sandbox, ["metrics.get", "chat.search"])


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_skills_name_capabilities_not_company_facts(name):
    agent_dir = AGENTS / name
    for path in [agent_dir / "SKILL.md", *agent_dir.glob("*.md")]:
        text = path.read_text(encoding="utf-8")
        for fact in ("Tallybird", "calendar_provider", "2026-", "mcp__"):
            assert fact not in text, f"{path.name} contains '{fact}'"


@pytest.fixture
def signal_command(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_BIN", "claude")  # the command is only inspected, never run
    trial = Trial(Task("t", "capability", "s01-calendar-gate", 1, "Weekly check.", []), 0, tmp_path)
    cmd = build_command(load_agent("signal"), trial, install.load(ROOT / "config" / "sandbox.yaml"))
    return cmd, tmp_path


def arg(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def test_only_mapped_tools_are_allowed(signal_command):
    cmd, _ = signal_command
    allowed = cmd[cmd.index("--allowedTools") + 1: cmd.index("--permission-mode")]
    mapped = set(install.load(ROOT / "config" / "sandbox.yaml").capabilities.values())
    assert set(allowed) - {"Agent"} <= mapped
    assert "mcp__releases__flag_state" not in allowed  # mapped, but no Signal capability asks for it
    assert arg(cmd, "--tools") == "Agent"
    assert "--strict-mcp-config" in cmd


def test_mcp_config_loads_only_needed_servers_with_the_trial_paths(signal_command):
    _, trial_dir = signal_command
    servers = json.loads((trial_dir / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"ledger", "metrics", "releases", "support", "warehouse"}
    assert servers["ledger"]["env"]["FACTORY_LEDGER"] == str(trial_dir / "ledger.jsonl")
    assert servers["metrics"]["env"]["FACTORY_WORLD"] == str(trial_dir / "world" / "world.db")


def test_prompts_carry_the_tool_table_and_company_context(signal_command):
    cmd, trial_dir = signal_command
    system = arg(cmd, "--system-prompt")
    assert "## Your tools in this install" in system and "mcp__ledger__write_entry" in system
    assert "Tallybird" in system
    subagents = json.loads((trial_dir / "agents.json").read_text(encoding="utf-8"))
    assert "mcp__support__search_tickets" in subagents["qual"]["tools"]
    assert "mcp__metrics__get_metric" not in subagents["qual"]["tools"]
    assert "mcp__metrics__get_metric" in subagents["quant"]["prompt"]


def test_every_mapped_tool_is_a_real_tool_on_its_server():
    """A helper placed under @server.tool() once replaced search_tickets. Check the registrations, not the functions."""
    import asyncio
    import importlib

    sandbox = install.load(ROOT / "config" / "sandbox.yaml")
    registered = {}
    for name, spec in sandbox.servers.items():
        module = importlib.import_module(spec["args"][spec["args"].index("-m") + 1])
        registered[name] = {t.name for t in asyncio.run(module.server.list_tools())}
    missing = []
    for capability, tool in sandbox.capabilities.items():
        _, server, tool_name = tool.split("__", 2)
        if tool_name not in registered[server]:
            missing.append(f"{capability} -> {tool}")
    assert not missing, missing
