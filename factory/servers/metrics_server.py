"""MCP server for the `metrics` tool (a semantic layer). Set FACTORY_WORLD to a world.db path."""

import os

from mcp.server.mcpserver import MCPServer

from factory import metrics

server = MCPServer(
    "metrics",
    instructions="Registered metrics only. Every number is computed by code. Answers are validated.",
)


def world() -> metrics.World:
    return metrics.open_world(os.environ["FACTORY_WORLD"])


@server.tool()
def list_metrics() -> dict:
    """List registered metrics with their units, windows, allowed dimensions, and aliases."""
    return metrics.list_metrics()


@server.tool()
def get_metric(metric: str, start: str, end: str,
               segment: dict[str, list[str]] | None = None, group_by: list[str] | None = None) -> dict:
    """Compute one metric for signup cohorts from start to end (YYYY-MM-DD). Immature cohorts are excluded and reported."""
    return world().get_metric(metric, start, end, segment, group_by)


@server.tool()
def compare_periods(metric: str, before_start: str, before_end: str, after_start: str, after_end: str,
                    segment: dict[str, list[str]] | None = None, group_by: list[str] | None = None) -> dict:
    """Compare a metric across two cohort periods, with a significance test for rates."""
    return world().compare_periods(metric, before_start, before_end, after_start, after_end, segment, group_by)


if __name__ == "__main__":
    server.run()
