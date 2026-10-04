# Agents

The design has 8 agents in one loop, with you at 3 gates. All 8 are built: Chief, Signal, Bet, Quality, Builder, Comms, Retro, and Coach. Bet ranks the candidates; you still place the bet. Comms drafts; code sends (decision D11). Coach prepares you; it never delivers (decision D14). Every agent writes to one shared ledger.

Tool names below describe capabilities. Each install maps capabilities to real tools: see [install.md](install.md).

```
 SENSE → FRAME → [DECIDE] → BUILD → PROVE → [CALL] → TELL → LEARN
 [ ] = your gate. TELL also needs your approval before anything is sent.
```

## Rules for every agent

| Rule | Meaning |
|---|---|
| Code owns what a test can check | Numbers, statistics, thresholds, consistency, privacy filters |
| The model owns intent, planning, and narrative | Which question to ask, what to try, how to explain it |
| Agents propose, you apply | Tools can queue an action or a draft. Only a human gate executes it |
| Stop, don't guess | Missing data becomes `Unknown` or an escalation, never a filled gap |
| One vocabulary | Every claim is a fact, hard constraint, assumption, or unknown (FP Mode reality ledger). Evidence carries a "Does NOT prove" line |
| Truth is unreachable | No tool can read the answer key |

## Artifacts passed between agents

| Artifact | Made by | Used by |
|---|---|---|
| Signal card: what changed | Signal | Chief |
| Decision packet: cause, size, cheapest test, recommendation, what would change it | Signal, sized by Bet | You, at Decide |
| Bet entry: prediction, confidence, kill trigger, review date | You, helped by Bet | Retro |
| Action spec: rollback, flag, experiment | Builder | The simulated company |
| Build: code change, design, prototype, video | Builder | Quality, you |
| Verdict: did it work | Signal (script) | You, at Call |
| Review: SHIP, FIX, PROVE, DELETE, or STOP | Quality | The artifact's owner |
| Readout: one decision per audience | Comms | You, at Tell |
| Commitment: owner, task, due date | Chief | Chief |
| Patch: skill change plus a new eval case | Retro | You approve |

## 1. Chief: chief of staff

Protects the PM's attention and keeps promises from slipping. Reads mail, chat, calendar, transcripts, and the tracker. Sends nothing except one short note to the PM's own private channel.

| Capability | Code owns | Chief owns |
|---|---|---|
| Daily brief: top 3 tied to goals, at risk, can wait | Sender weight, deadline hints, focus minutes | The ranking and the why |
| Inbox and chat triage | Replied or not, unanswered hours, lookalike senders | The label, and what needs the PM |
| Suggested replies in the PM's voice | Writing samples; a style check in evals | The drafts. Never sent by an agent |
| One-click links | Every link built from the item's id | Nothing: links cannot be invented |
| Open loops: waiting on the PM, waiting on others, the PM's own promises | Unanswered requests, days open, "I'll ..." in the PM's messages | Which loops matter, and nudge drafts |
| Commitments from meetings and mail | Due and overdue sorting | Pulling them out, quoting the source |
| Meeting prep | Attendees, last contact, open loops and promises with them, related meetings | Purpose, context, and the ask |
| Calendar: conflicts, missing agendas, unsolicited invites, reschedule proposals | Conflicts, free slots, and a check that a proposed time is free | Which meeting to move |
| Goal alignment | Meeting hours per goal, starved goals | Tying work to goals |
| Meeting follow-ups | | Drafts that restate who does what by when |
| Stakeholder staleness | Days since direct contact against the PM's cadence | What to say |
| Modes: morning, midday, evening, weekly review, away | An "as of" time; each mode's window; the away limit on urgent messages | The content per mode; which items are urgent |
| Learning from corrections | `python -m factory.chief.correct` saves a rule; rules load on every run; evals check them | Following them |

Run it with `python -m factory.chief --mode morning|midday|evening|weekly`. Scheduling: [install.md](install.md#schedule-chief). Gate: escalations.
Scored on: 16 graders on a planted Monday (top themes, triage, needs you, calendar flags, replies, commitments, open loops, meeting prep, goals, follow-ups, reschedule, voice, staleness, one note to self, learned rules, privacy), plus a weekly review graded on Friday.

## 2. Signal: all quantitative and qualitative knowledge

One front door. You ask one question and get one answer.

| Part | Holds | Tools |
|---|---|---|
| Quant sub-agent | Metrics, funnels, experiments, verdicts | `metrics` (validated), `warehouse` (exploratory, labeled), `dashboards`, `experiments`, `monitoring`, `billing` |
| Qual sub-agent | Tickets, transcripts, research, surveys, customer threads | `support`, `transcripts`, `research`, `surveys`, `slack`, web search |
| Signal lead | Combines both through the triangulation script, grades confidence, writes the answer | The two sub-agents only |

Code owns: every number, cohort maturity, triangulation, confidence grades, the verdict script. Model owns: which slice to check next, grouping text into themes, the written diagnosis. Gate: none.
Scored on: planted findings found, false causes claimed, 0 invented numbers or quotes, the same answer across 10 runs.
Cadence: weekly, not daily (decision D12). While the PM is away for several days, Signal runs once and the queued decision carries forward; Chief, Bet, and Comms are what keep working every day.

## 3. Bet: investment analyst

Turns a problem into a bet using Signal plus docs, stakeholder opinions, tracker history, field requests, and the market. Opinions are logged as assumptions with a source, never as facts.

Tools: Signal, `docs`, `slack`, `mail`, `tracker`, `field_requests`, `crm`, `costs`, web search. Code owns: expected value, cost per successful outcome, whether a test can finish before its review date. Model owns: the cheapest-test ladder, the pre-mortem. Gate: Decide.
Scored on: size within range of the answer key, cheapest valid test chosen, kill trigger set.

## 4. Builder: engineer and designer

| Output | Tools |
|---|---|
| MVP in code, behind a flag, with tests | `code.*`: reads the app in `sandbox/app`, proposes a change on a copy, runs the tests |
| Design using the Tallybird design system | `design.*`: the system in `sandbox/design`, a rendered screenshot, code checks |
| Clickable prototype with an honesty label (live, mocked, hardcoded) | Playwright clicks every control |
| Video walkthrough, on request | Playwright recording, captions |

Code owns: the action spec matches the approved decision, the tests (rerun by code, never taken on Builder's word), the change's scope (new flag ships off, at least one new test, no test removed, under 150 changed lines), design system classes only, 0 dead clicks, the honesty label. Model owns: the change, the design, and the demo. Gate: Call.
Scored on: the action matches the decision, hidden acceptance tests on the change (Builder never sees them), the design and demo checks, and every number on the demo traced to the ledger.

## 5. Quality: reviewer

Two passes on every artifact before it reaches you.

| Pass | Checks |
|---|---|
| Correctness (code, `review.check`) | Cited queries are replayed and must match; signal cards are recomputed exactly; the size must equal the sizing tool; quotes match a ticket or release note word for word; fields are valid; no email addresses. `review.submit` fills these checks itself and refuses SHIP if one failed |
| FP Mode review ([skills/fp-mode](../skills/fp-mode/SKILL.md), by Amir Zur) | Outcome and acceptance bar, strongest counterexample, the 5-step algorithm, the required proof tier. Returns SHIP, FIX, PROVE, DELETE, or STOP with at most 3 findings |

Tools: read-only `metrics`, `support`, `transcripts`, `github`, `design`. Gate: you define the bar.
Scored on: planted defects caught, unnecessary flags raised.

## 6. Comms: communicator

One decision, rendered up, down, and across with identical facts. Up: bad news first, options, a decide-by date. Down: every change carries its reason. Across: every ask has a date and an owner.

Tools: `ledger`, `slack` and `mail` drafts. Code owns: blocks sending if any number differs between versions. Gate: Tell.

## 7. Coach: people partner

Prepares you for 1:1s, feedback, and hiring. Runs only when you start it.

Hard lines:
1. It never rates, ranks, or decides anything about a person.
2. It reads your own messages and shared spaces only. Never other people's private messages. No activity tracking.
3. Each PM can see everything the agents hold about them.
4. It never delivers feedback. It prepares you.

Tools: `calendar`, `transcripts`, `docs`, `directory`. Gate: every people call.

## 8. Retro: coach for the factory

Runs at the end of every simulated week. It never sees the answer key, so it learns only from what a real company could observe.

| Step | Does |
|---|---|
| 1. Score predictions | Prediction versus measured outcome, Brier score |
| 2. Enforce kills | Bets past review date, kill triggers fired |
| 3. Find patterns | Quality rejections, your overrides, questions Signal couldn't answer, the slowest station |
| 4. Propose a patch | A skill change plus a new eval case that reproduces the failure |
| 5. You approve | The eval harness runs. The version goes up only with the failure linked |
| 6. FP Mode on the factory | What to delete, which manual task has earned automation |

Output: a 5-line weekly note. Tools: `ledger`, eval history, scripts for Brier score, overdue bets, and rejection frequency.

## The eval harness (code, not an agent)

| Part | Does |
|---|---|
| Runner | Runs an agent or the loop on a seed in a fresh session and records a trace |
| Code graders | Findings versus the answer key, exact numbers and quotes, forbidden tools, privacy, budget, stopping |
| Model judge | A different vendor's model scores prose against a rubric, after agreeing with 2 human graders |
| PM minutes | Words read plus decisions made at each gate |
| Levels | Unit and agent evals on every push, full loop nightly, held-out scenarios monthly |
| Gate | No agent change ships without a linked failure, a new case, and passing evals |

## v1 scope (scenario 1)

| Built | Later |
|---|---|
| Chief (all modes), Signal (both sub-agents), Builder (MVP, design, prototype), Quality (both passes), Bet's sizing script, eval harness levels 1 to 3 | Bet agent, Comms, Coach, Retro, video, held-out scenarios |
