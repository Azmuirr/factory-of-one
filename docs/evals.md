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

## Live runs

Real headless runs on the subscription, graded with the same code graders. Costs are list-price estimates; nothing was billed beyond the subscription.

| Date | Run | Result | What it found |
|---|---|---|---|
| 2026-09-26 | Chief v0.3, morning, s01 | 30/35 | Told the VP "the dip is mostly immature cohorts", a planted trap no grader caught. Proposed moving the CEO's sync instead of the customer call. A 101-word note. "Talk soon" instead of the PM's sign-off. Read Ben's "by Thursday" as the send date |
| 2026-09-26 | Chief v0.4, morning, s01 | 36/36 | All of the above fixed. 59 turns, 6 minutes, about $0.83 |
| 2026-09-26 | Loop, s01, live-1 | Stopped | Relative run folder broke every path; then Quality returned FIX on a correct packet because the numbers check read "Microsoft 365" as data |
| 2026-09-26 | Loop, s01, live-2 | Full loop | Signal 12/13 (joined a release title and its notes into one quote; Quality caught it and returned FIX). Builder 8/8. Quality 4/4 on the planted-quote task and SHIP on the build. Microsoft activation 30.5% to 38.2%, prediction hit, Brier 0.04, 7.2 PM minutes, about $0.82 |
| 2026-09-26 | Builder v0.2, build-s01 | 100% after a grader fix | A 5-line change behind `calendar_skip_fallback_microsoft` (off), 3 new tests, all hidden acceptance tests passed. A design of the calendar step with an admin-approval banner and Skip for now, system classes only. About $0.22 |
| 2026-09-26 | Loop, s01, live-3 | Stopped at a gate | Signal's quote fix held (SHIP). Quality returned DELETE on the design and the demo because the tested code existed: it judged three builds for three readers as rivals. The scripted gates then fell through to the keyboard |
| 2026-09-26 | Quality v0.2, sibling-builds | 100% | New regression task built from live-3's real builds. SHIP on the design |
| 2026-09-26 | Loop, s01, live-4 | Full loop | All three builds SHIP. Quality returned FIX on the packet: a ruled-out claim used Microsoft's -22.25% without citing its query. Microsoft activation 30.5% to 38.2%, Brier 0.04, 7.3 PM minutes, about $0.97 |
| 2026-09-26 | Signal v0.3.2, diagnose-s01 | 100%, then 87% on regrade | Its own graders passed a card labeled "Microsoft" that held overall numbers, and a ruled-out claim with an untraced 15.46. Quality's checks caught both |
| 2026-09-26 | Signal v0.3.3, diagnose-s01 | 93% | Card fixed. Reported "12 distinct workspaces" by merging 12 separate searches itself. The search tool now takes `any_of`, so code counts across phrasings |
| 2026-09-27 | Signal v0.3.4, diagnose-s01, 2 trials | Invalid run | An edit put a helper under `@server.tool()`, so `search_tickets` stopped being a tool. Signal reported 0 customer-voice workspaces rather than invent any. A new contract test checks every mapped tool is registered on its server |
| 2026-09-27 | Signal v0.3.4, diagnose-s01, 2 trials | 2/2, 100% | Both trials pass every grader, including Quality's code checks. First pass^k run |
| 2026-09-28 | Chief v0.4, morning, s01, from a fresh clone | 35/36 | Relayed Aiko's caveat as a reason: "the dip reads worse than it is". The ledger now rejects a brief sentence that explains a metric's move without citing a decision packet |
| 2026-09-28 | Loop, s01, live-5 | Stopped at a gate | Signal's packet passed every check; its voice count (8) cites the search it came from, where the old showcase showed a merged 21. Quality returned PROVE on the code change because none of its tools showed the diff. With no scripted answer, the gate took the safe default and applied nothing. Quality's code checks now include the diff, the new flags, and the test run |
| 2026-09-28 | Loop, s01, live-6 (the showcase) | Full loop | Quality returned FIX on the packet: Signal reported 7 Microsoft workspaces, but the search it cited returned 11 across all providers. It had filtered the results by hand. The new replay check caught it. All three builds SHIP once Quality could read the diff. Microsoft activation 30.5% to 38.2%. Gate answers scripted |
| 2026-09-28 | Chief v0.5, away mode, s01 | 14/14 | Three urgent messages to the PM: Dana's readout by 10:00, Cobalt Ridge blocked, Marco's noon decision. Nothing else sent |
| 2026-09-28 | Bet v0.1.0, frame-s01 | 75%, 88% on regrade | Right ranking: the rollback first, SSO second, Northwind's webinar request set aside citing the strategy. Its consent search used long phrasings and found 1 account. Quoting Signal's packet was flagged until the quote check read the ledger |
| 2026-09-28 | Bet v0.1.1, frame-s01 | 62% | Cited ledger ids and query ids in the wrong fields. The ledger now rejects a malformed citation when it is written |
| 2026-09-28 | Autopilot, away day, s01 (live-2) | Full day | Chief, Signal, Quality, Bet, and Quality again, with nobody at the keyboard. Decision queued, nothing applied. Quality returned FIX on Signal's packet (a hyphenated "Microsoft-365" read as data) and on Bet's list (paraphrases labeled as quotes, and a sum Bet worked out itself inside one) |
| 2026-09-28 | Bet v0.1.2, frame-s01, 2 trials | 75% | Neither trial found the mislabeled Oakridge request. "140" from the tracker id ONB-140 was read as data |
| 2026-09-28 | Bet v0.1.3, frame-s01, 2 trials | 81%, one trial passing after regrade | Still searched "admin approval", which misses "admin must approve", and summed two accounts itself again. The request search now matches word forms, and the ledger runs Bet's number and quote checks when it writes |
| 2026-09-28 | Bet v0.1.3 with write-time checks, frame-s01, 2 trials | 2/2, 100% | Both trials rank the rollback first and SSO second, find the mislabeled request, and set Northwind aside citing the strategy. No write was bounced |
| 2026-09-29 | Comms v0.1.0, both tasks, 2 trials each | Decided 2/2 at 100%; away 1 of 2 | One away trial addressed the manager and Sales by name, not by directory id. Code could not confirm they were internal and held both. The ledger now asks for directory ids when the readout is written |
| 2026-09-29 | Comms v0.1.1, away status, 2 trials | 2/2, 100% | The manager gets the news with the numbers, the recommendation, and one ask dated before Tuesday's freeze. The customer note carries no internal numbers. Code sent the manager and team versions and held Sales and the customer for the PM |
| 2026-09-29 | Retro v0.1.0, week-1, 2 trials | 80% | Both found Signal's numbers failure in 3 of 4 runs and proposed a Signal patch that applies cleanly. Both computed ratios in the note ("1.5x") and named graders that do not exist, since Retro cannot read suites. It can now see grader names, and the ledger checks both when Retro writes |
| 2026-09-29 | Retro v0.1.1, week-1, 2 trials | 2/2, 100% | Same pattern found, same Signal rule patched, valid eval cases. One note line says sense took "more than every other station combined", which is false and has no number for a check to catch |
| 2026-09-30 | Autopilot, week away, s01 (week-live-1) | Stopped, session limit | Found D13: a live agent's writes during a multi-day run used the world's raw cutoff instead of the day's own label, so Friday's own brief landed on Saturday and the week page grouped it into an empty sixth day. Fixed via `FACTORY_LABEL` threaded through the MCP subprocess env |
| 2026-09-30 | Autopilot, week away, s01 (week-live-2) | Full week | Confirmed the D13 fix: labels correct all five days, Bet's query_ids change day to day per the SKILL.md v0.1.4 fix. Found a deeper bug: `frame()` re-reviewed Monday's stale candidates entry against Tuesday's world when a live Bet call wrote nothing new, failing it for numbers that were never wrong. Microsoft activation 30.24% to 42.19% by Friday. Only Friday's decided readout was delivered (manager, team, peers); the four daily status readouts were written but held, per D11. Fixed by having `frame()` skip re-review when Bet adds nothing new |

## Grader changes

Graders have bugs too. Each fix is logged, and saved transcripts are regraded with `python -m factory.evals regrade <agent> <run_id>`.

| Date | Grader | Bug | Found by | Fix |
|---|---|---|---|---|
| 2026-09-25 | `quiet-s00` task | The empty agent passed: "raise no alarm" is satisfied by doing nothing | The null-agent run | Added `signal_card_written`: the quiet task also requires the positive outcome |
| 2026-09-25 | `diagnosis_matches_truth` (answer key) | Expected `calendar_connect_rate_1d` as the mechanism. That metric rises after the release, because every user must now try the step. The first registered step that drops is `first_meeting_rate_7d` | Reading Signal's first real trial, which named the right metric | Corrected `truth.yaml` and the example ledger |
| 2026-09-25 | `quotes_grounded` | Compared quotes against raw JSON, where quotation marks are escaped. A real quote failed | The same trial | Decode JSON tool results before comparing |
| 2026-09-26 | `numbers_grounded`, `demo_numbers_grounded` | Numbers written in prose were never checked, so Builder could not reuse Signal's "39.4%" and Signal could have invented numbers in text | The reference demo failed its own check | Prose numbers are now checked with the rounding their precision implies. Signal's saved trial still scores 100% |
| 2026-09-26 | Quality's correctness pass | Pool grounding passed a planted wrong number (22.1%), because 22.1% exists elsewhere in the data | Building Quality's defect fixtures | Metric evidence cites a `query_id`; code replays it (decision D8). Pool grounding stays only as a fallback for text outside claims |
| 2026-09-26 | Numbers check (`factory/numbers.py`) | Read "Microsoft 365" as an untraced data number, so Quality had to return FIX on a correct packet | The first live loop | Known product names with numbers are skipped. "Microsoft 30 workspaces" is still checked |
| 2026-09-26 | `brief_open_loops`, `brief_meeting_prep` | Failed a brief that tracked the PM's promise through its commitment (`cmt:cmt_0004`) instead of the mail it was made in | Chief's first live brief | Commitment refs resolve to their source before grading and rendering, so the brief also links to the mail |
| 2026-09-26 | New: `no_unsourced_cause` | Chief drafted "the dip is mostly immature cohorts" to the VP, a planted trap, and no grader noticed | Reading Chief's first live brief | A sentence that blames a trap cause for the drop fails. Chief's skill now says it has no metrics and leaves the cause to the readout |
| 2026-09-26 | `mvp_change_passes` scope check | Counted `CHANGE.md`, the change description the code tool writes, as a file outside the app's folders | Builder's first live trial (94%) | The description is metadata, excluded from diffs and scope. Regraded: 100% |
| 2026-09-26 | New: `passes_quality_checks` on Signal | Signal's eval used pool grounding, weaker than the checks Quality runs before the PM sees anything. A mislabeled card scored 100% | Comparing a live trial's eval score with Quality's checks on the same entries | Signal's tasks run Quality's code checks. One definition of correct for both. Regraded: 87% |
| 2026-09-28 | Quality's voice check | Passed a voice count of 21 that no tool returned: Signal had added two searches (17 and 18). The check only required the count to stay under all accounts with any ticket | Red team of the showcase page | The count must cite the ticket search it came from (`voice_ref`), and code replays that search. Ticket searches are logged like metric queries |
| 2026-09-28 | Prose numbers | Every whole number up to 14 was skipped, so an invented "12 workspaces" in a sentence passed | Red team | Only dates, time spans, and labels are skipped ("Feb 10", "7 days", "week 6", "Step 1 of 3") |
| 2026-09-28 | `bet_ranking`, words not tags | Passed only if the consent bet cited a request search with 3 accounts. The outcome that matters is finding the mislabeled request, however it is cited | Reading Bet's second trial | Passes if the search finds 3 accounts or the mislabeled request is cited |
| 2026-09-28 | Numbers check | Read tracker ids (ONB-140) and hyphenated product names (Microsoft-365) as data | Bet's and Signal's live runs | Both are names now, in any capitalization |
| 2026-09-28 | New: numbers in Bet's prose | Only sizes and evidence values were checked, so a sum Bet computed itself in a sentence would pass | The away day, where one sat inside a quote | Every number in Bet's text must come from a query it cites, a request, doc, or message it cites, or the ledger |
| 2026-09-29 | Prose number matching | Any pool number times 100 counted as a match, so "400 accounts" matched a 4 in the ledger | Writing Comms' tests | Only rates (0 to 1) may appear as a percent |
