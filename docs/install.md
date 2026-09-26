# Use it at your own company

The agents never name a tool. They name capabilities, such as `support.search` or `metrics.get`. Each install maps capabilities to real tools in one file. The sandbox is one install. Your company is another.

## Steps

1. Copy `config/live.example.yaml` to `factory.yaml` at the repo root. The factory uses `FACTORY_CONFIG` if set, then `factory.yaml`, then the sandbox.
2. Write `company/<your-company>/context.md`: product, key metric, funnel in order, dimensions to split by, and the periods for the weekly check. Use `company/tallybird/context.md` as the model.
3. Write your metric catalog in `company/<your-company>/catalogs/`, in the same format as `catalogs/`.
4. Add your vendors' MCP servers under `servers`. Put credentials in environment variables and reference them as `${NAME}`.
5. Map each capability to one of those servers' tools: `mcp__<server>__<tool>`. Map read tools only.

## Rules the install cannot change

| Rule | How it is enforced |
|---|---|
| Numbers are computed by code | `metrics.*` stays on the factory's own server, over your warehouse and your catalog |
| An agent gets only the tools its capabilities map to | The runner allows exactly those tools. A Slack server's "post message" is blocked unless you map it |
| Anything that writes goes through a human gate | Write capabilities are `propose` only |
| No agent reads the eval answer keys | Agents have no file or shell tools |

## What is not built yet

| Piece | Status |
|---|---|
| Warehouse adapter for Postgres, BigQuery, or Snowflake | Planned. Today `metrics` and `warehouse` read a SQLite world |
| Live loop scheduling (daily runs, waiting for review dates) | Planned. Today the loop advances a simulated world |
| A tested setup for specific vendor MCP servers | Planned. Each vendor gets verified when wired in |
