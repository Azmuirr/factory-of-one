# Factory of One

The PMs who last will be operators with strong judgment who run several agents at once. This repo is a working version of that job: eight agents do the work, code owns every fact, and the PM makes the calls.

**See it first:** [a PM's Monday](site/index.html), replayed from a real run. Chief triages the morning, Signal diagnoses an activation drop, Quality tries to break the diagnosis, Builder ships a fix behind a flag, and you make two calls and get scored on them. Open `site/index.html` in a browser; nothing to install.

## What's in it

| Agent | Does | Code owns, not the model |
|---|---|---|
| **Chief**, chief of staff | Morning brief: triage, open loops, commitments, meeting prep, goal check, replies drafted in your voice. Sends nothing except one note to you | Sender weight, suspicious senders, who replied, calendar conflicts, free slots, hours per goal, stakeholder staleness |
| **Signal**, analyst | What changed and why, with numbers and customer voice. Writes a decision packet | Every number: each one cites a query that code replays |
| **Bet**, investment analyst | Frames the work coming in: strategy docs, customer requests, stakeholder asks, and Signal's numbers, ranked into at most 5 bets tied to your goals, with set-asides that cite the strategy | Every size: a cited query or request search that code replays. Each account counted once |
| **Quality**, reviewer | Reviews Signal's, Bet's, and Builder's work before you see it, with [Elon Mode](skills/elon-mode/SKILL.md). Chief's brief is checked by code when it is written | Numbers, quotes, fields, privacy. It cannot return SHIP when a check fails |
| **Comms**, communicator | One decision told up to your manager, down to your team, across to peers, and to a customer when needed, with identical facts. Drafts only | Every number must already be in the ledger. Code sends only what you approve at the Tell gate, or, while you're away, what your decision rights allow |
| **Coach**, people partner | Prepares you for a 1:1, feedback, or a hiring conversation. Runs only when you start it | There is no field for a rating, ranking, or score anywhere in its schema. Every talking point and open item cites a real calendar event, transcript, doc, or earlier ledger entry |
| **Retro**, the factory's coach | Once a week, reads the runs (never the answer keys), writes a five-line note, and proposes at most two patches to agents' instructions, each with the eval case that reproduces the failure | The week's facts: recurring failures, Brier scores, overrides, time per station. A patch applies only if its text matches exactly, and only after you say yes |
| **Builder**, engineer and designer | A code change behind a flag, a design in the company's design system, a one-screen demo | Tests rerun by code, change scope, hidden acceptance tests, design system rules, dead clicks |

You own three gates: **decide** (approve the action and place a bet with a prediction), **call** (ship, iterate, or kill once the data is in), and **tell** (which versions go out). Your predictions are scored.

**When you're away,** the autopilot runs the loop to your decision and stops there: Chief sends up to three urgent items to your own channel, Signal and Quality prepare the decision, and a digest waits for you. Nothing is applied without you. `--week` runs this Monday through Friday: the queued decision carries forward untouched while Chief, Bet, and Comms keep working every day, and you resume at the gate on Friday. The rules are one file you edit: [decision rights](company/tallybird/decision_rights.yaml).

## What's real and what's simulated

| Real | Simulated |
|---|---|
| The agents: Claude, running headless through Claude Code | The company: Tallybird, a fictional AI meeting notetaker |
| Every artifact on the replay page: the agents' actual output | Its data: 8 weeks from a seeded model, with one problem planted on purpose |
| The code checks, the eval graders, and the scores | Its workplace: mail, chat, calendar, transcripts, tracker, support tickets |

The simulation is the point: because the problem was planted, every diagnosis and decision can be graded against an answer key. Change one decision and only the future changes, so the page can show the world where you declined.

**A real security boundary to know about:** Builder can write a new test file and run it ([docs/decisions.md#d19](docs/decisions.md)). That subprocess runs with secrets scrubbed from its environment and a timeout, and on POSIX with CPU/memory/file-size caps, but it is not sandboxed: a test that writes to a hardcoded absolute path reaches the real filesystem, proven by a permanent regression test, not a theoretical concern. Treat Builder exactly like a CI runner executing code a model wrote: run it only somewhere disposable, never on a machine with access to anything that matters.

**What's deterministic and what's judgment follows one rule ([docs/decisions.md#d20](docs/decisions.md)):** one right answer given the data belongs to code; a real tradeoff stays the agent's call and the PM's. Five places where that line had drifted were found and fixed this way: voice compliance is now checked live, not only in an eval; Coach's "never rate a person" has a backstop in free text, not just the schema; Signal reads a `material` flag instead of computing the threshold itself; Chief copies a computed goal status instead of judging it; and Bet gets a citable priority score for ranking that it can explain a deviation from, not a verdict it has to follow.

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
python -m factory.autopilot --week                # your whole week away: Monday's decision plays out to Friday, then you decide
python -m factory.retro run runs/loop/<run> runs/autopilot/<run>   # Friday: Retro reads the week and proposes patches
python -m factory.retro apply runs/retro/<run> pch_0001   # you approve a patch; code applies it and adds its eval case
python -m factory.evals run signal --trials 3    # score an agent against the answer key
python -m factory.coach --for p_jpm --moment one_on_one   # about 30 seconds: prep for your next 1:1
python -m pytest                                  # 237 tests, about 15 minutes, no Claude
```

On macOS or Linux, use `.venv/bin/python` in place of `python` if the venv isn't activated. Rebuild the replay page from any run with `python -m factory.replay --loop runs/loop/<run> --chief runs/chief/<run>`.

## Results so far

Live runs on scenario 1, graded by the same code graders as the evals. Every run is logged, including the failures and what changed because of them: [docs/evals.md](docs/evals.md#live-runs).

| Agent | Trials | Result |
|---|---|---|
| Chief | 2 | 36 of 36 checks, then 35 of 36: the second run relayed a planted trap as a reason for the dip. The ledger now bounces that sentence when the brief is written |
| Signal | 2 | Both at 100%, including Quality's code checks |
| Bet | 2 | Both at 100%: the rollback first, SSO second, the loud single-account request set aside by strategy, and the mislabeled request found |
| Comms | 4 | All at 100% after one fix: the news first to the manager, identical numbers in every version, no internal numbers to the customer, and only policy-allowed updates sent while away |
| Coach | 1 | 100%: sourced a report's unanswered request, an open hiring commitment, and a pending candidate take-home, each cited to a real calendar, chat, mail, or transcript id, and named the one gap in its own view (no dedicated 1:1 on the calendar) rather than guessing |
| Retro | 2 | Both at 100%: found the week's recurring failure in 3 of 4 real runs and proposed a patch that applies cleanly, with a runnable eval case |
| Builder | 1 | 100%, including hidden acceptance tests |
| Quality | 1 | 100% on the regression built from a real mistake |
| The loop | 1 showcase | Microsoft activation 30.5% to 38.2% two weeks after the fix. The gate answers came from a file written in advance, so the Brier score and PM minutes are not a person's |

Every agent was tuned on scenario 1, and every result above is on scenario 1. Treat them as a working system, not a benchmark.

**Held out:** scenario 2 ([docs/decisions.md#d16](docs/decisions.md), finished in [D18](docs/decisions.md) and [D21](docs/decisions.md)) is a different metric, a different segment, and a different mechanism, built after every agent's instructions were already written. Signal's first live run genuinely missed the cause; three general instruction fixes later it found the right metric, segment, release, and mechanism, cited real workspaces, and recommended a considered action over a blind rollback, at 100%. Chief, Bet, Quality, and Comms were then run against the same scenario's full workplace for the first time and all passed clean, surfacing two more real, now-fixed harness bugs along the way (not agent bugs), plus a genuine disagreement between Quality's review bar and the grading key's leniency that led to the third fix. Builder was the last agent tested against it: it built real checkout code behind a correctly-segment-scoped flag with no agent bug, and that run surfaced one more real harness bug, a stale fixture snapshot, now fixed. All 8 agents' red-team checks were re-run after every change: still clean. One small, known voice-variance finding in Comms remains open rather than patched away: [docs/evals.md](docs/evals.md#live-runs).

**Red teaming:** every agent's suite includes a `planted-instruction` task, a fabricated "SYSTEM NOTE" inside something the agent legitimately reads as data (mail, a doc, a ticket, a release note, a transcript, or the ledger itself). All 7 held on their first live run: [docs/evals.md#red-teaming](docs/evals.md#red-teaming). One run also found and fixed a real crash, unrelated to the injection itself.

**Full-suite pass:** every agent's complete eval suite, at its configured trial count, not a single spot check. 6 of 8 came back 100% on every task and trial. The other two surfaced one real bug each (Chief wrote a goal's title into a field meant to hold its id; a few red-team checks had false-positive forbidden phrases) and two small, honestly-documented, unfixed findings: [docs/evals.md#full-suite-pass-d17](docs/evals.md#full-suite-pass-d17).

## Built and not built

| Built | Not built yet |
|---|---|
| Chief, Signal, Bet, Quality, Builder, Comms, Coach, Retro, and the autopilot for a day or a full week away | Retro's view across more than one scenario |
| Scenario 1 (a release that locked out Microsoft calendar users), a quiet control scenario, and scenario 2 (a checkout default that quietly cuts trial-to-paid for larger teams), held out and tested end to end against all 8 agents, Builder included | Scenarios 3 to 10, harder tiers |
| The eval harness: tasks, code graders, answer keys, trials, regrading | A model judge calibrated against human graders |
| A capability map, so any install can swap in its own tools, and one real vendor adapter proving it (GitHub's own MCP server, live-verified for `code.list`/`code.read`/`code.search`: [docs/decisions.md#d22](docs/decisions.md)) | More vendor adapters (Slack, Gmail, a real warehouse) |

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
