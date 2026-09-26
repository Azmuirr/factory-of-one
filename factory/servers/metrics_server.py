"""MCP server for the `metrics` tool (a semantic layer). Set FACTORY_WORLD to a world.db path."""

import os

from mcp.server.mcpserver import MCPServer

from factory import metrics, queries, sizing

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
    args = {"metric": metric, "start": start, "end": end, "segment": segment, "group_by": group_by}
    result = world().get_metric(**args)
    queries.record("get_metric", args, result)
    return result


@server.tool()
def compare_periods(metric: str, before_start: str, before_end: str, after_start: str, after_end: str,
                    segment: dict[str, list[str]] | None = None, group_by: list[str] | None = None) -> dict:
    """Compare a metric across two cohort periods, with a significance test for rates. Cite the returned query_id as evidence."""
    args = {"metric": metric, "before_start": before_start, "before_end": before_end, "after_start": after_start,
            "after_end": after_end, "segment": segment, "group_by": group_by}
    result = world().compare_periods(**args)
    queries.record("compare_periods", args, result)
    return result


@server.tool()
def estimate_weekly_arr_impact(before_start: str, before_end: str, after_start: str, after_end: str,
                               segment: dict[str, list[str]] | None = None) -> dict:
    """Weekly new ARR at stake from an activation change in a segment. Use this for any revenue size; never compute it by hand."""
    args = {"before_start": before_start, "before_end": before_end, "after_start": after_start, "after_end": after_end, "segment": segment}
    result = sizing.weekly_arr_impact(world(), **args)
    queries.record("estimate_weekly_arr_impact", args, result)
    return result


if __name__ == "__main__":
    server.run()
