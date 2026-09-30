"""MCP server for Retro: the week's observable facts, and read-only access to the agents' instructions. Set FACTORY_WEEK."""

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from factory import retro

server = MCPServer("retro", instructions="A week of the factory's own runs, and the agents' instructions. Never answer keys.")


@server.tool()
def week_stats() -> dict:
    """Quality's reviews by agent and check, failures that recur in 2 or more runs, predictions against outcomes with Brier scores,
    times the PM approved a packet Quality sent back, and seconds per station."""
    return {"status": "value", **retro.week_stats(Path(os.environ["FACTORY_WEEK"]))}


@server.tool()
def list_skills() -> dict:
    """Every agent and its instruction files."""
    return {"status": "value", "agents": {p.name: sorted(f.name for f in p.glob("*.md")) for p in sorted(retro.AGENTS.iterdir()) if p.is_dir()}}


@server.tool()
def read_skill(agent: str, file: str) -> dict:
    """One instruction file, such as signal / SKILL.md. Copy `old` for a patch from here, exactly."""
    try:
        return {"status": "value", "agent": agent, "file": file, "text": retro.read_skill(agent, file)}
    except ValueError as e:
        return {"status": "rejection", "code": "not_allowed", "message": str(e)}


if __name__ == "__main__":
    server.run()
