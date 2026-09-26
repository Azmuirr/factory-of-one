# Factory of One

A PM with agents rarely fails by building too slowly. They fail by shipping 10 things and learning from none of them.

Status: in progress. Scenario 1 runs end to end with the Signal agent and you at the gates.

## Try the sandbox

```bash
python -m venv .venv
.venv/Scripts/pip install -e .[dev]   # macOS or Linux: .venv/bin/pip
python -m sandbox.generator --seed 1
python -m pytest
```

This builds 8 weeks of data for Tallybird, a fictional AI meeting notetaker, with one problem hidden inside. See [sandbox/SPEC.md](sandbox/SPEC.md).

## Run the loop

```bash
python -m factory.loop            # Signal diagnoses the week, you decide at the gates, the world reacts
python -m factory.loop --signal-fixture ledger/examples/s01-happy-path.jsonl   # skip the agent, keep the gates
python -m factory.evals run signal --trials 3                                    # score Signal against the answer key
```

Agents run through Claude Code in headless mode on an existing subscription. See [docs/evals.md](docs/evals.md).

## Design

| Doc | What it covers |
|---|---|
| [docs/agents.md](docs/agents.md) | The 8 agents, their modes, what code owns versus the model, gates, and scoring |
| [docs/tools.md](docs/tools.md) | The simulated workplace tools each agent uses |
| [ledger/ledger.schema.json](ledger/ledger.schema.json) | Every artifact agents pass to each other. [Example: one full loop](ledger/examples/s01-happy-path.jsonl) |
| [catalogs/](catalogs/) | Registered metrics and shared dimensions |
| [docs/decisions.md](docs/decisions.md) | Choices made, options rejected, and what would reverse each one |
