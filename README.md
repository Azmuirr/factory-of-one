# Factory of One

The PMs who last will be operators with strong judgment who run several agents at once. This repo is a working version of that job: four agents do the work, code owns every fact, and the PM makes the calls.

**See it first:** [a PM's Monday](site/index.html), replayed from a real run. Chief triages the morning, Signal diagnoses an activation drop, Quality tries to break the diagnosis, Builder ships a fix behind a flag, and you make two calls and get scored on them. Open `site/index.html` in a browser; nothing to install.

## What's in it

| Agent | Does | Code owns, not the model |
|---|---|---|
| **Chief**, chief of staff | Morning brief: triage, open loops, commitments, meeting prep, goal check, replies drafted in your voice. Sends nothing except one note to you | Sender weight, suspicious senders, who replied, calendar conflicts, free slots, hours per goal, stakeholder staleness |
| **Signal**, analyst | What changed and why, with numbers and customer voice. Writes a decision packet | Every number: each one cites a query that code replays |
| **Quality**, reviewer | Reviews Signal's and Builder's work before you see it, with [Elon Mode](skills/elon-mode/SKILL.md). Chief's brief is checked by code when it is written | Numbers, quotes, fields, privacy. It cannot return SHIP when a check fails |
| **Builder**, engineer and designer | A code change behind a flag, a design in the company's design system, a one-screen demo | Tests rerun by code, change scope, hidden acceptance tests, design system rules, dead clicks |

You own two gates: **decide** (approve the action and place a bet with a prediction) and **call** (ship, iterate, or kill once the data is in). Your predictions are scored.

**When you're away,** the autopilot runs the loop to your decision and stops there: Chief sends up to three urgent items to your own channel, Signal and Quality prepare the decision, and a digest waits for you. Nothing is applied without you. The rules are one file you edit: [decision rights](company/tallybird/decision_rights.yaml).

## What's real and what's simulated

| Real | Simulated |
|---|---|
| The agents: Claude, running headless through Claude Code | The company: Tallybird, a fictional AI meeting notetaker |
| Every artifact on the replay page: the agents' actual output | Its data: 8 weeks from a seeded model, with one problem planted on purpose |
| The code checks, the eval graders, and the scores | Its workplace: mail, chat, calendar, transcripts, tracker, support tickets |

The simulation is the point: because the problem was planted, every diagnosis and decision can be graded against an answer key. Change one decision and only the future changes, so the page can show the world where you declined.

## Three ways in

| You are | Start here | Then |
|---|---|---|
| A PM learning the craft | [The Monday page](site/index.html), then the [decision packet](ledger/examples/s01-happy-path.jsonl) and what was [planted](sandbox/scenarios/s01-calendar-gate/truth.yaml) | Run the loop yourself and make the calls |
| A PM who wants the operating model | [docs/agents.md](docs/agents.md) and the agents' instructions in [agents/](agents/) | [Use it with your own tools](docs/install.md) |
| A VP or hiring manager | [The Monday page](site/index.html) and [where the agents were wrong](docs/evals.md#live-runs) | [Decisions and what would reverse them](docs/decisions.md) |

## Run it

You need Python 3.10 or later. Live agents also need [Claude Code](https://docs.claude.com/en/docs/claude-code) installed and signed in; they run on your existing subscription with no API key.

```bash
git clone https://github.com/Azmuirr/factory-of-one && cd factory-of-one
python -m venv .venv
.venv/Scripts/pip install -e .[dev]        # macOS or Linux: .venv/bin/pip
.venv/Scripts/python -m playwright install chromium
```

Then, from the fastest to the fullest:

```bash
python -m factory.loop --fixture ledger/examples/s01-happy-path.jsonl   # 1 minute, no Claude: the full loop from saved agent output, you at the gates
python -m factory.chief --fixture agents/chief/evals/fixtures/reference-brief.jsonl --open   # a reference brief in your browser
python -m factory.chief --mode morning --open    # about 6 minutes: Chief live on the planted Monday
python -m factory.loop                            # about 10 minutes: every agent live, you at the gates
python -m factory.autopilot                       # a day with you away: urgent items to you, the decision queued, a digest
python -m factory.loop --resume runs/autopilot/<run>   # back at the keyboard: decide, and the loop continues
python -m factory.evals run signal --trials 3    # score an agent against the answer key
python -m pytest                                  # 162 tests, about 5 minutes, no Claude
```

On macOS or Linux, use `.venv/bin/python` in place of `python` if the venv isn't activated. Rebuild the replay page from any run with `python -m factory.replay --loop runs/loop/<run> --chief runs/chief/<run>`.

## Results so far

Live runs on scenario 1, graded by the same code graders as the evals. Every run is logged, including the failures and what changed because of them: [docs/evals.md](docs/evals.md#live-runs).

| Agent | Trials | Result |
|---|---|---|
| Chief | 2 | 36 of 36 checks, then 35 of 36: the second run relayed a planted trap as a reason for the dip. The ledger now bounces that sentence when the brief is written |
| Signal | 2 | Both at 100%, including Quality's code checks |
| Builder | 1 | 100%, including hidden acceptance tests |
| Quality | 1 | 100% on the regression built from a real mistake |
| The loop | 1 showcase | Microsoft activation 30.5% to 38.2% two weeks after the fix. The gate answers came from a file written in advance, so the Brier score and PM minutes are not a person's |

Every agent was tuned on scenario 1, and every result above is on scenario 1. Treat them as a working system, not a benchmark. A scenario the agents were never tuned on is the honest test, and it isn't built yet.

## Built and not built

| Built | Not built yet |
|---|---|
| Chief, Signal, Quality, Builder | Bet (drafting the bet), Comms (one decision for each audience), Coach and Retro (learning across loops) |
| Scenario 1 (a release that locked out Microsoft calendar users) and a quiet control scenario | Scenarios 2 to 10, harder tiers, held-out scenarios |
| The eval harness: tasks, code graders, answer keys, trials, regrading | A model judge calibrated against human graders |
| A capability map, so any install can swap in its own tools | Tested setups for specific vendors, a warehouse adapter for Signal, repo rules for Builder beyond the sandbox app |

## Design

| Doc | What it covers |
|---|---|
| [docs/agents.md](docs/agents.md) | The planned agents, what code owns versus the model, gates, and scoring |
| [docs/tools.md](docs/tools.md) | The simulated tools, each modeled on a real product |
| [docs/decisions.md](docs/decisions.md) | Choices made, options rejected, and what would reverse each one |
| [docs/evals.md](docs/evals.md) | The eval harness, every live run, and every grader bug |
| [docs/install.md](docs/install.md) | Use the agents with your own tools |
| [sandbox/SPEC.md](sandbox/SPEC.md) | How the simulated company works |
| [ledger/ledger.schema.json](ledger/ledger.schema.json) | Every artifact agents pass to each other |

## Credits and license

[Elon Mode](skills/elon-mode/SKILL.md), the review method Quality uses, is by Amir Zur. The code is under the [MIT license](LICENSE).
