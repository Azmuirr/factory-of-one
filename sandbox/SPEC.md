# Sandbox spec: world model and data schema

Status: draft for review. No generator code exists yet.

## 1. The company

**Tallybird** is a fictional AI meeting notetaker for teams. It joins calls, writes the recap and action items, and shares them with attendees. Its business model is based on public information about Otter.ai and Fathom (section 10). It uses no private data from either company.

| Attribute | Tallybird |
|---|---|
| Motion | B2B product-led growth (PLG): self-serve signup, trial, seat expansion, sales for large teams |
| Trial | Every new workspace gets a 14-day Team trial. No credit card |
| After the trial | Solo workspaces can buy Pro. Teams buy Team or Business. Everyone else drops to Free |
| Viral loop | Shared recaps reach meeting attendees. Some attendees sign up (the `recap_link` channel) |
| Sales handoff | A trial workspace with 10+ active users becomes a product-qualified lead (PQL) |
| Second product (later) | Async video, launched as its own scenario. Every table carries a `product` field from day one |

### Plans

| Plan | Price per seat per month | Limits | Anchor |
|---|---|---|---|
| Free | $0 | 300 minutes a month, 30-minute meetings | Otter Basic |
| Pro | $20 monthly, $16 annual. 1 seat | Unlimited meetings, for solo users | Fathom Premium |
| Team | $19 monthly, $15 annual. 2-seat minimum | Unlimited meetings | Fathom Team |
| Business | $30 monthly, $24 annual | Adds CRM sync, admin analytics | Between Otter Business and Fathom Business |
| Enterprise | Custom | Single sign-on (SSO), sales-led | Both |

## 2. Rules

| Rule | Why |
|---|---|
| Numbers come from a seeded causal model in code | Same seed, same world. No tokens spent |
| Text comes from templates | No tokens at run time. About 30 variants per theme, written once and committed |
| The world reacts | An action changes the causal model from the next simulated day |
| Truth is separate | The generator writes `world/` for agents and `truth/` for the bench. No agent tool can read `truth/` or `sandbox/scenarios/` |
| Real gaps stay in | Noisy support tags, correlated dimensions, and immature cohorts are part of the data |

## 3. Clock

| Item | Value |
|---|---|
| Run length | 10 simulated weeks |
| Baseline | Weeks 1 to 5 |
| Scenario events | Week 6 or later |
| "Now" for agents | End of week 8 |
| After actions | Weeks 9 and 10 are generated only after the loop records its actions |
| Resolution | Generated per day. Timestamps in Coordinated Universal Time (UTC) |

## 4. Baseline numbers

The scale matches about where Fathom was in 2025, not Otter today. Reasoning for each choice: [docs/decisions.md](../docs/decisions.md).

| Parameter | Value | Basis |
|---|---|---|
| New workspaces per week | About 3,850 | Assumption. Enough volume to detect a 3-point drop in one week |
| Weekday factor | Mon to Thu about 1.15, Fri 0.95, weekends 0.65 | Assumption: business product |
| Channel mix | Organic search 35%, `recap_link` 25%, paid search 20%, direct 20% | Assumption |
| Company size | Solo 30%, 2 to 10: 45%, 11 to 50: 18%, 51+: 7% | Assumption |
| Calendar provider | Google 60%, Microsoft 35%, none 5% | Assumption |
| Meeting platform | Depends on calendar: Google users mostly Meet and Zoom, Microsoft users mostly Teams and Zoom | Assumption. Creates a realistic confound |
| 7-day activation | About 40% overall. Google 41%, Microsoft 39%, none 36% | Benchmark average is 36%, and the best PLG companies run 40% to 50% |
| Trial to paid | About 11% of all trials. 25% if activated, 2% if not | Benchmark for no-card trials: 8% to 22%, median 14% |
| Paid mix | 25% of new paid workspaces are solo on Pro (1 seat). Teams average 5 seats | Assumption |
| Revenue per paid workspace | About $68 a month ($816 a year), blending monthly and annual billing | Derived from the plan table and paid mix |
| Viral coefficient | About 0.6 new workspaces per activated workspace, arriving over the next 3 weeks | Assumption, set so `recap_link` holds at 25% of signups |
| Support tickets | About 70 per week | Assumption. Themes: bot didn't join 25%, billing 20%, recap quality 20%, login 15%, other 20% |

**Activation** means that within 7 days of signup, the workspace shares a recap of a real meeting (2 or more participants, 5 or more minutes) with at least 1 attendee. A recording alone doesn't count, because the value is a recap someone uses. Known weakness: it undercounts solo users who keep notes private. See decision D3.

At baseline this yields about 430 new paying workspaces and about $350K of new annual recurring revenue (ARR) per week.

## 5. Causal model (per new workspace)

| Step | Rule |
|---|---|
| 1. Arrivals | Daily count = base × weekday factor × trend, plus Poisson noise. `recap_link` arrivals follow past activations |
| 2. Attributes | Channel, company size, calendar provider, and meeting platform, drawn from the mix tables |
| 3. Intent | A hidden score. Higher for `recap_link` and larger companies. Stored in `truth/` only |
| 4. Onboarding | The workspace passes the onboarding steps active that day. Each step has a pass probability by segment |
| 5. First meeting | P(recorded meeting within 7 days) = logistic(intent + size effect − onboarding friction) |
| 6. Activation | P(recap shared, given a meeting) = base rate by company size |
| 7. Trial outcome | At day 14: paid (plan, seats) or Free. Conversion depends on activation and team size |
| 8. Viral | Each shared recap reaches outside attendees. A fraction sign up over the next 3 weeks |

Retention after conversion, AI costs, and async video aren't modeled yet. The scenario that first needs each one adds it.

## 6. Actions (how the world reacts)

| Action | Parameters | Effect from the next simulated day |
|---|---|---|
| `rollback` | release ID, segment filter (optional) | Removes the release's effects for that segment |
| `set_flag` | flag, segment filter, percent | Exposes that share of new workspaces to the flagged change |
| `start_experiment` | flag, split, segment filter, primary metric | Random assignment, logged in `assignments` |
| `no_action` | none | The world continues |

Every action is written to `actions` with a timestamp.

## 7. Data schema (`world/world.db`, SQLite)

### Shared codes

| Code | Values |
|---|---|
| `product` | `notes` (later: `video`) |
| `channel` | `organic`, `recap_link`, `paid_search`, `direct` |
| `company_size` | `solo`, `s2_10`, `s11_50`, `s51_plus` |
| `calendar_provider` | `google`, `microsoft`, `none` |
| `meeting_platform` | `zoom`, `meet`, `teams` |
| `plan` | `trial`, `free`, `pro`, `team`, `business`, `enterprise` |

### Tables agents can read

| Table | Fields | Notes |
|---|---|---|
| `workspaces` | workspace_id, created_at, channel, company_size, calendar_provider, referrer_workspace_id | `referrer_workspace_id` is set for `recap_link` signups |
| `users` | user_id, workspace_id, role, created_at | Scenario 1 creates only the creator |
| `events` | event_id, ts, workspace_id, user_id, product, name, props (JSON) | See the event list below |
| `subscriptions` | workspace_id, ts, plan, seats, billing, mrr | One row per plan change |
| `releases` | release_id, ts, title, notes, flag | Release notes, as an engineer would post them |
| `flags` | flag, segment_filter, percent, ts | Flag state history |
| `assignments` | workspace_id, experiment_id, arm, ts | Empty until an experiment starts |
| `tickets` | ticket_id, created_at, workspace_id, user_id, subject, body, support_tag | Linked to usage by workspace ID |
| `messages` | message_id, ts, from_role, subject, body | Stakeholder messages in shared channels only |
| `actions` | action_id, ts, name, params (JSON), decided_by | Written by the loop, not the generator |

### Events

| Event | Props |
|---|---|
| `signup_completed` | none |
| `onboarding_step_viewed` | step |
| `calendar_connect_started` | provider |
| `calendar_connect_completed` | provider |
| `calendar_connect_failed` | provider, error_code |
| `meeting_recorded` | meeting_platform, duration_min, participants |
| `recap_shared` | recipients, external_recipients |
| `trial_ended` | outcome |

### Hidden tables (`truth/truth.db`, bench only)

| Table | Fields |
|---|---|
| `latents` | workspace_id, intent, blocked_by, releases_applied |
| `planted` | scenario_id, cause, expected effect by segment |

## 8. Deferred until a scenario needs it

| Item | First needed by |
|---|---|
| Pricing experiment mechanics | Scenario 2 |
| AI cost per meeting minute | Scenario 3 |
| Retention and seat expansion after conversion | Scenario 4 |
| Interview transcripts | Scenario 5 |
| Partner team dependencies | Scenario 6 |
| PM team artifacts | Scenarios 7 to 9 |
| Private messages | Scenario 10 |
| Async video launch | Its own scenario |

## 9. Decisions

Company model, activation event, name, and scale are decided in [docs/decisions.md](../docs/decisions.md), with the options considered and what would change each one.

## 10. Public sources

Figures below are as published. Third-party estimates are labeled.

| Fact | Source |
|---|---|
| Otter passed $100M ARR in March 2025, with under 200 employees, over 25M users, and over 1B meetings processed | [Otter.ai blog](https://otter.ai/blog/otter-ai-breaks-100m-arr-barrier-and-transforms-business-meetings-launching-industry-first-ai-meeting-agent-suite) |
| Otter plans: Basic free (300 minutes, 30-minute meetings), Pro, Business, Enterprise | [Otter.ai pricing](https://otter.ai/pricing), read 2026-09-24 |
| Fathom plans: Free, Premium, Team ($19 monthly, $15 annual, 2-seat minimum), Business ($34 monthly, $25 annual), Enterprise | [Fathom pricing](https://www.fathom.ai/pricing), read 2026-09-24 |
| Fathom at about $30M ARR in 2025, up from $10M in 2024 | [GetLatka](https://getlatka.com/companies/fathom.ai), third-party estimate |
| Superhuman acquired Fathom in September 2026 | [TechCrunch](https://techcrunch.com/2026/09/14/superhuman-acquires-yc-backed-notetaker-fathom-as-productivity-platforms-push-for-agentic-work/) |
| SaaS activation averages 36% (median 30%) across 500+ products | [Lenny's Newsletter](https://www.lennysnewsletter.com/p/what-is-a-good-activation-rate) |
| No-card trial to paid: 8% to 22%, median 14% | [Benchmark roundup](https://www.growthspreeofficial.com/blogs/b2b-saas-trial-to-paid-conversion-rate-benchmarks-2026-by-trial-type-acv-length-credit-card), secondary source. Verify before citing publicly |
