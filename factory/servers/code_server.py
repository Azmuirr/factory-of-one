"""MCP server for the product codebase, modeled on GitHub and CI. Reads the app; proposes changes on a copy and
runs the tests there. It cannot merge, push, or change the app. Set FACTORY_CHANGES (and FACTORY_APP to override the app)."""

import os
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from factory import code

server = MCPServer("code", instructions="Read the Tallybird app and propose changes. Every proposal runs on a copy, with the tests.")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,60}$")


def changes() -> Path:
    return Path(os.environ["FACTORY_CHANGES"])


@server.tool()
def list_files() -> dict:
    """Every file in the app."""
    return {"status": "value", "files": code.files(code.APP)}


@server.tool()
def read_file(path: str) -> dict:
    """One file from the app, by its path from list_files."""
    text = code.read(code.APP, path)
    if text is None:
        return {"status": "rejection", "code": "not_found", "message": f"No file {path}. Use list_files."}
    return {"status": "value", "path": path, "text": text}


@server.tool()
def search_code(pattern: str) -> dict:
    """Lines matching a regular expression, case-insensitive, with file and line number."""
    try:
        return {"status": "value", "matches": code.search(code.APP, pattern)[:100]}
    except re.error as e:
        return {"status": "rejection", "code": "bad_pattern", "message": str(e)}


@server.tool()
def propose_change(name: str, message: str, edits: list[dict], new_files: dict[str, str] | None = None) -> dict:
    """Propose a change as a pull request would. Starts from the app every time, so send all edits together.
    edits: [{"path", "old", "new"}], where `old` is copied exactly from the file and appears once.
    new_files: {"tests/test_x.py": "..."}. Returns the test result, the diff, new flags, and scope problems."""
    if not NAME.match(name):
        return {"status": "rejection", "code": "invalid_name", "message": "Use lowercase letters, digits, and hyphens."}
    result = code.propose(code.APP, changes(), name, edits, new_files or {})
    if result["status"] == "value":
        (changes() / name / "CHANGE.md").write_text(message.strip() + "\n", encoding="utf-8")
    return result


@server.tool()
def run_tests(name: str) -> dict:
    """Run the app's tests on a proposed change."""
    folder = changes() / name
    if not folder.is_dir():
        return {"status": "rejection", "code": "not_found", "message": f"No change named {name}."}
    return {"status": "value", "tests": code.run_tests(folder)}


if __name__ == "__main__":
    server.run()
