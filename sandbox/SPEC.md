# Sandbox spec: world model and data schema

Status: draft for review. No generator code exists yet.

## 1. The company

Draftline is a fictional AI writing assistant for small teams. Workspaces of 1 to 50 people draft, rewrite, and summarize documents, then share or export them.

## 2. Rules

| Rule | Why |
|---|---|
| Numbers come from a seeded causal model in code | Same seed, same world. Benchmarks are reproducible |
| Text comes from templates in v1 | No API key needed to generate a world. Model-written text comes later, generated once and frozen per seed |
| The world reacts | An action changes the causal model from the next simulated day. A rollback has to show up in the data |
| Truth is separate | The generator writes `world/` for agents and `truth/` for the bench. No agent tool can read `truth/` or `sandbox/scenarios/` |
| Real gaps stay in | Real companies have unlinked store reviews, noisy support tags, and silent churn. So does the sandbox |

## 3. Clock

| Item | Value |
|---|---|
| Run length | 10 simulated weeks |
| Baseline | Weeks 1 to 5 |
| Scenario events | Week 6 or later |
| "Now" for agents | End of week 8. Agents see nothing after this point |
| After actions | Weeks 9 and 10 are generated only after the loop records its actions |
| Resolution | Generated per day. Timestamps to the second, in Coordinated Universal Time (UTC) |

## 4. Baseline numbers (please correct)

| Parameter | Value | Note |
|---|---|---|
| New workspaces per day | 550 on average | About 3,850 per week |
| Weekday factor | Mon 1.15, Tue 1.20, Wed 1.15, Thu 1.10, Fri 0.95, Sat 0.65, Sun 0.70 | Weekends run about 35% lower |
| Weekly growth trend | +1% | |
| Signup platform mix | Web 50%, desktop 15%, iOS 20%, Android 15% | Mobile is 35% |
| Channel mix | Organic search 40%, paid social 25%, direct 20%, referral 15% | Paid social carries lower intent |
| Segment mix | Solo 35%, small (2 to 10) 50%, mid (11 to 50) 15% | |
| First-run screen load, median | Web 1.4s, desktop 1.1s, iOS 2.0s, Android 2.3s | |
| 7-day activation target | Web 43%, desktop 45%, iOS 37%, Android 35%. Overall about 41% | The generator calibrates to these |
| Support tickets | About 70 per week | Billing 20%, export 20%, AI quality 25%, login 20%, other 15% |
| Store reviews | About 40 per week, mobile only | Average 4.2 stars |

**Activation** = a new workspace whose creator shares or exports a document within 7 days of signup. Generating a draft is not activation, because output alone doesn't show the user's job moved forward.

## 5. Causal model (per new workspace)

| Step | Rule |
|---|---|
| 1. Arrivals | Daily count = base × weekday factor × trend, plus Poisson noise |
| 2. Attributes | Segment, channel, and platform drawn from the mix tables |
| 3. Intent | A hidden score. Lower for paid social, higher for referral. Stored in `truth/` only |
| 4. Load time | Log-normal around the platform median × every active release multiplier |
| 5. First draft | P(draft within 7 days) = logistic(intent + segment effect − load penalty × log(load seconds)) |
| 6. Value event | P(share or export within 7 days, given a draft) = base rate by platform and segment |
| 7. Activation | Step 6 happened within 7 days of signup |

The load penalty is calibrated so that doubling mobile load time cuts mobile activation by about 25% relative, which moves overall activation by about 8%.

Retention, revenue, and costs are not modeled yet. The scenario that first needs each one adds it.

## 6. Actions (how the world reacts)

| Action | Parameters | Effect from the next simulated day |
|---|---|---|
| `rollback` | release ID, platforms (optional) | Removes the release's effects on those platforms |
| `set_flag` | flag, platform, percent | Exposes that share of new workspaces to the flagged change |
| `start_experiment` | flag, split, platforms, primary metric | Random assignment, logged in `assignments` |
| `no_action` | none | The world continues unchanged |

Every action is written to `actions` with a timestamp, so the bench can score what the loop did and when.

## 7. Data schema (`world/world.db`, SQLite)

Shared codes, used by every table and all text metadata:

| Code | Values |
|---|---|
| `platform` | `web`, `desktop`, `ios`, `android` |
| `segment` | `solo`, `small`, `mid` |
| `channel` | `organic`, `paid_social`, `direct`, `referral` |

### Tables agents can read

| Table | Fields | Notes |
|---|---|---|
| `workspaces` | workspace_id, created_at, segment, channel, signup_platform | One row per signup |
| `users` | user_id, workspace_id, role, created_at | Scenario 1 creates only the creator |
| `events` | event_id, ts, workspace_id, user_id, platform, name, props (JSON) | Names: `signup_completed`, `first_run_viewed` (props: load_ms), `draft_generated`, `doc_shared`, `doc_exported`, `session_started` |
| `releases` | release_id, ts, title, notes, platforms, flag | Written release notes, as an engineer would post them |
| `flags` | flag, platform, percent, ts | Flag state history |
| `assignments` | workspace_id, experiment_id, arm, ts | Empty until an experiment starts |
| `tickets` | ticket_id, created_at, workspace_id, user_id, platform, subject, body, support_tag | Carries workspace IDs, so it links to usage |
| `reviews` | review_id, created_at, store, platform, rating, body | **No workspace ID.** Real app stores don't link reviews to accounts |
| `messages` | message_id, ts, from_role, subject, body | Stakeholder messages in shared channels only |
| `actions` | action_id, ts, name, params (JSON), decided_by | Written by the loop, not the generator |

### Hidden tables (`truth/truth.db`, bench only)

| Table | Fields |
|---|---|
| `latents` | workspace_id, intent, true_load_ms, releases_applied |
| `planted` | scenario_id, cause, expected effect by segment and platform |

## 8. Deferred until a scenario needs it

| Item | First needed by |
|---|---|
| Pricing, plans, revenue | Scenario 3 |
| Token and infrastructure costs | Scenario 3 |
| Invited members and retention | Scenario 4 |
| Interview transcripts | Scenario 5 |
| Partner team dependencies | Scenario 6 |
| PM team artifacts (updates, specs, review comments) | Scenarios 7 to 9 |
| Private messages | Scenario 10 |

## 9. Questions for Amir

1. Are the baseline numbers in section 4 believable for a small-team writing tool?
2. The brief requires shared IDs between usage and customer text. Tickets carry them. Store reviews can't, because real stores don't. Accept the gap?
3. Activation means share or export within 7 days. Agree?
