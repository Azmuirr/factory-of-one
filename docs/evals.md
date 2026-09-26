# Evals

The eval harness is code, not an agent. It follows Anthropic's framework in [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).

## Terms

| Term | In the factory |
|---|---|
| Task | A scenario, tier, and seed, plus a prompt, the agent's tools, a reference solution, and graders |
| Trial | One fresh headless Claude Code session on a fresh copy of the world and an empty ledger |
| Grader | Code, model, or human. Each grader holds one or more assertions |
| Transcript | Every message and tool call in a trial, saved as JSON Lines |
| Outcome | What the agent wrote to the ledger, checked against the scenario's answer key. Not what it said |
| Agent harness | `claude -p` with the agent's skill as the system prompt, its MCP servers only, and no built-in tools |
| Eval harness | `factory/evals`: runner, graders, aggregator, reports |
| Suite | `agents/<agent>/evals/suite.yaml` |
| Capability suite | Starts at a low pass rate. A hill to climb |
| Regression suite | Must stay near 100% |
| pass@k, pass^k | At least 1 of k trials passes; all k trials pass. k = 3. pass^3 is the bar for anything that runs unattended |

## Where tasks come from

| Source | How |
|---|---|
| Scenario answer keys | Each `truth.yaml` has a `grading` block. Graders read it directly |
| The agent's spec | Each "Scored on" line in `docs/agents.md` maps to at least one task |
| Real failures | Every failure found in a transcript or by Retro becomes a regression task |
| Drafted by a model | `evals author <agent>` drafts candidates. A human approves them (planned) |

Every "should happen" task has a "shouldn't happen" twin. Signal's twin is a quiet world with no planted problem.

## Choosing graders

| What is checked | Grader |
|---|---|
| Final state: ledger entries, actions, required fields | Code |
| Numbers and quotes match what the tools returned | Code, on the transcript |
| Tool rules: allowed tools only, turns, stopping | Code, on the transcript |
| Reasoning quality | Model rubric through the subscription. Advisory until it agrees with human grades on a sample |
| Design and demo taste | Human spot check |

Grade outcomes, not paths. No check requires a sequence of tool calls. Checks only forbid tools.

## Running

```bash
python -m factory.evals run signal --trials 3
python -m factory.evals run signal --null   # no model calls; proves the graders fail an empty agent
```

Each trial gets a fresh temporary directory. Regression tasks use fixed seeds. Results go to `bench/results/<agent>/`. Transcripts stay under `runs/evals/` and are not committed.

## Reports

Per task: pass or fail per trial, partial credit, and the failed assertions with a transcript path. Per suite: pass@3 and pass^3, split by capability and regression, plus estimated cost, turns, and duration. A suite that passes 95% or more on 3 runs in a row is flagged saturated: its tasks move to regression and harder tiers get added.

Read transcripts. Graders are only trustworthy if someone reads the trials they graded.
