# Use it at your own company

The agents never name a tool. They name capabilities, such as `support.search` or `metrics.get`. Each install maps capabilities to real tools in one file. The sandbox is one install. Your company is another.

## Steps

1. Copy `config/live.example.yaml` to `factory.yaml` at the repo root. The factory uses `FACTORY_CONFIG` if set, then `factory.yaml`, then the sandbox.
2. Write `company/<your-company>/context.md`: product, key metric, funnel in order, dimensions to split by, and the periods for the weekly check. Use `company/tallybird/context.md` as the model.
3. Write your metric catalog in `company/<your-company>/catalogs/`, in the same format as `catalogs/`.
4. Add your vendors' MCP servers under `servers`. Put credentials in environment variables and reference them as `${NAME}`.
5. Map each capability to one of those servers' tools: `mcp__<server>__<tool>`. Map read tools only.

## Schedule Chief

Chief has four modes. Run each on a schedule so the brief is waiting for you.

macOS or Linux, with `crontab -e`:

```text
30 7 * * 1-5  cd /path/to/factory-of-one && .venv/bin/python -m factory.chief --mode morning
0 12 * * 1-5  cd /path/to/factory-of-one && .venv/bin/python -m factory.chief --mode midday
0 18 * * 1-5  cd /path/to/factory-of-one && .venv/bin/python -m factory.chief --mode evening
0 16 * * 5    cd /path/to/factory-of-one && .venv/bin/python -m factory.chief --mode weekly
```

Windows, in PowerShell:

```powershell
schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:30 /TN "Chief morning" `
  /TR "cmd /c cd /d C:\path\to\factory-of-one && .venv\Scripts\python -m factory.chief --mode morning"
```

Chief posts its note to your own private channel through `notify.self`. In the sandbox that note lands in the run folder's `outbox.jsonl`. In a live install, map `notify.self` to a direct message to yourself.

Teach Chief when it gets something wrong:

```bash
python -m factory.chief.correct --ref mail:m_004 --label answer_later --reason "Budget asks are never urgent"
python -m factory.chief.correct --note "Never say 'circle back'."
```

The rules land in `lessons/chief.yaml` for your install and load on every run.

## Run the loop while you're away

`python -m factory.autopilot` runs a day with nobody at the keyboard: Chief's away brief, urgent items to your own channel, Signal's check, and Quality's review. Any decision waits in the ledger, and nothing is applied. Your rules are in `decision_rights.yaml`. Schedule it like Chief:

```text
30 7 * * 1-5  cd /path/to/factory-of-one && .venv/bin/python -m factory.autopilot
```

When you're back, read `digest.md` in the run folder and continue with `python -m factory.loop --resume <run folder>`.

## Friday: let Retro read the week

```bash
python -m factory.retro run runs/loop/<run> runs/autopilot/<run>
python -m factory.retro apply runs/retro/<run> pch_0001
```

Retro proposes at most two patches to agents' instructions, each with the eval case that reproduces the failure. Nothing changes until you approve one.

## Before you point Builder at a real repo

Builder's `code.propose` runs the tests of a change an agent wrote, on your machine. Those tests get only a short allowlist of environment variables (the path, temp folders, your home folder), never your tokens or keys. They still run with your file access and network. On a real repo, run the factory inside a container or a throwaway VM.

## Rules the install cannot change

| Rule | How it is enforced |
|---|---|
| Numbers are computed by code | `metrics.*` stays on the factory's own server, over your warehouse and your catalog |
| An agent gets only the tools its capabilities map to | The runner allows exactly those tools. A Slack server's "post message" is blocked unless you map it |
| Anything that writes goes through a human gate | Write capabilities are `propose` only. The one exception is `self`: a note to the PM's own private channel |
| No agent reads the eval answer keys | Agents have no file or shell tools |

## What is not built yet

| Piece | Status |
|---|---|
| Warehouse adapter for Postgres, BigQuery, or Snowflake | Planned. Today `metrics` and `warehouse` read a SQLite world |
| Live loop scheduling (daily runs, waiting for review dates) | Planned. Today the loop advances a simulated world |
| A tested setup for specific vendor MCP servers | Planned. Each vendor gets verified when wired in |
| `code` scope rules for your repo | Planned. Today the flag file and the folders a change may touch are the sandbox app's. Point `FACTORY_APP` at a clone to read and test; scope rules come next |
