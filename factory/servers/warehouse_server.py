"""MCP server for the `warehouse` tool (read-only SQL). Set FACTORY_WORLD to a world.db path."""

import os

from mcp.server.mcpserver import MCPServer

from factory import warehouse

server = MCPServer(
    "warehouse",
    instructions="Read-only SQL. Answers are exploratory. Prefer the metrics tool for any registered metric.",
)


@server.tool()
def describe_tables() -> dict:
    """List tables and their columns."""
    return warehouse.describe(os.environ["FACTORY_WORLD"])


@server.tool()
def query(sql: str) -> dict:
    """Run one read-only SELECT. Returns at most 500 rows, labeled exploratory."""
    return warehouse.query(os.environ["FACTORY_WORLD"], sql)


if __name__ == "__main__":
    server.run()
