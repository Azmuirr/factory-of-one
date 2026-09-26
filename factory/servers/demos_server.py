"""MCP server for demos: publish a one-screen HTML page and check it. Set FACTORY_DEMOS."""

import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from factory import demos

server = MCPServer("demos", instructions="Publish self-contained, one-screen HTML demos. Every publish is checked by code.")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")


def root() -> Path:
    return Path(os.environ["FACTORY_DEMOS"])


@server.tool()
def publish_demo(name: str, html: str) -> dict:
    """Save demos/<name>/index.html and run the checks. Fix and republish until passed is true."""
    if not NAME.match(name):
        return {"status": "rejection", "code": "invalid_name", "message": "Use lowercase letters, digits, and hyphens."}
    path = root() / name / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return {**demos.check(path), "location": f"demos/{name}/index.html"}


@server.tool()
def check_demo(name: str) -> dict:
    """Run the checks on an existing demo."""
    path = root() / name / "index.html"
    if not path.exists():
        return {"status": "rejection", "code": "not_found", "message": f"No demo named {name}."}
    return {**demos.check(path), "location": f"demos/{name}/index.html"}


if __name__ == "__main__":
    server.run()
