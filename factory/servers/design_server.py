"""MCP server for design, modeled on Figma with a design system. Serves the system and renders designs built
from it, with a screenshot and code checks. Set FACTORY_DESIGNS (and FACTORY_DESIGN_SYSTEM to override the system)."""

import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from factory import design

server = MCPServer("design", instructions="Design with the Tallybird design system only. Every render is checked by code.")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")


@server.tool()
def get_design_system() -> dict:
    """The tokens, the component guide with examples, and the full list of classes."""
    return {"status": "value", "tokens": design.tokens(), "components": design.components(), "classes": sorted(design.classes())}


@server.tool()
def render_design(name: str, markup: str) -> dict:
    """Render body markup built from design system classes. Saves designs/<name>/index.html and screen.png and
    runs the checks. Fix and render again until passed is true."""
    if not NAME.match(name):
        return {"status": "rejection", "code": "invalid_name", "message": "Use lowercase letters, digits, and hyphens."}
    result = design.render(markup, Path(os.environ["FACTORY_DESIGNS"]) / name)
    return {"status": "value", **result, "location": f"designs/{name}/index.html", "screenshot": f"designs/{name}/screen.png"}


if __name__ == "__main__":
    server.run()
