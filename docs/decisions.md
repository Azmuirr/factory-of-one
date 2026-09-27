# Decisions

Each entry records the options, the choice, and what would reverse it. The reasoning is part of the product: a junior PM can follow it, and a VP can challenge it.

## D1. Who the repo is for

| Reader | What they need in 10 minutes | Where they start |
|---|---|---|
| Junior PM | How a real growth problem gets diagnosed and decided | Run scenario 1 on the easy tier. Read the decision packet |
| Senior PM | An operating model and skills to reuse | `OPERATING.md` and `agents/` |
| VP or hiring manager | Evidence of judgment, and what this means for how a product org is built | The benchmark results and the org-design notes |

**Choice:** one repo, three reading paths in the README. Scenario tiers (easy, medium, hard) double as a learning ladder.

**Would change if:** readers skip their path in testing. Then split the README into separate pages.

## D2. The simulated company

| Option | Verdict |
|---|---|
| Generic AI writing assistant | Rejected. Weak viral loop, cheap AI costs |
| AI support inbox | Rejected. Its product "tickets" collide with our own support tickets |
| Async video (modeled on Loom) | Deferred. It launches later as a second product, as its own scenario |
| **AI meeting notetaker (modeled on Otter and Fathom)** | **Chosen.** B2B, product-led, trial, strong viral loop, AI costs that vary by meeting length |

**Would change if:** most scenarios in the backlog stop fitting a meeting product.

## D3. Activation event

| Candidate | Strength | Weakness |
|---|---|---|
| First meeting recorded | Easy to measure | Shows the bot ran, not that anyone got value |
| First recap opened by the creator | Shows some value | Private. Adds nothing to the viral loop |
| **Recap shared with an attendee within 7 days** | **Shows value to a team and starts the viral loop** | **Undercounts solo users who keep notes private** |
| 3 meetings recorded in week 1 | Shows habit | Too strict for small teams with few meetings |

**Choice:** a recap shared with at least 1 attendee within 7 days. Tallybird sells to teams, so shared value is the value that converts.

**Honest limit:** in the sandbox, activation predicts conversion because the model says so. A real company must prove that with cohort data. A later scenario can plant this: solo users who never share but still pay.

**Would change if:** solo workspaces grow past 40% of paid revenue.

## D4. Name

| Candidate | Result |
|---|---|
| Minutewise | Rejected. Several real AI note-taker apps use it |
| Plover | Rejected. An open-source stenography (transcription) tool uses it |
| Tern | Rejected. A travel software company ships an AI notetaker under it |
| **Tallybird** | **Chosen.** No meeting or transcription product found under this name on 2026-09-24 |

**Would change if:** a real product appears under the name.

## D5. Baseline scale

**Choice:** about 3,900 trials a week, 40% activation, 11% trial to paid, about $385K of new annual recurring revenue (ARR) a week. That's about $20M of new ARR a year, consistent with a company near Fathom's reported 2025 scale (about $30M ARR, a third-party estimate).

| Check | Result |
|---|---|
| Activation against benchmark | 40%. Above the 36% SaaS average, inside the 40% to 50% range of strong product-led companies. Plausible for a product whose value arrives at the next meeting |
| Trial to paid against benchmark | 11%. Inside the 8% to 22% range for trials that need no credit card |
| Solo workspaces | They buy Pro, not Team, because Team has a 2-seat minimum. Found in review |
| Statistical power | A 3-point activation drop is about 3 to 4 standard errors in one week of data. Detectable, but not obvious from one day |

**Would change if:** a growth leader who ran a meeting product says a number is off. Their word beats the assumption.

## D6. How agents run: no extra spend

| Option | Verdict |
|---|---|
| Anthropic API key | Rejected for now. Adds a separate pay-as-you-go bill |
| **Claude Code headless mode (`claude -p`) on the existing subscription** | **Chosen.** No added cost. Supports per-agent MCP servers (`--mcp-config`), tool allow-lists (`--allowedTools`), model choice (`--model`), and JSON output with token usage |
| A second vendor's model as judge | Deferred. It needs a paid key. Code graders and human spot checks cover v1 |

**Consequences:**
- Cost per task is reported from Claude Code's list-price estimate (`total_cost_usd`). It is an estimate, not a bill.
- Subscription rate limits cap how many eval runs fit in a day. Evals run locally, sized to fit. CI runs only code tests, because it has no login.
- A plain headless call loads about 33,000 tokens of default context. Agent runs restrict tools and MCP servers to what each agent needs, to keep runs small.

**Would change if:** eval volume outgrows the subscription's limits, or a cross-vendor judge becomes a blocker.

## D7. Agents name capabilities, not tools

| Option | Verdict |
|---|---|
| Skills call our simulated tools by name | Rejected. Nobody could run the agents on real Slack, Zendesk, or Gmail |
| Adapters that wrap every vendor API in our own contract | Rejected for most tools. Too much code, and vendors already ship MCP servers |
| **Skills name capabilities. Each install maps capabilities to real tools in one file** | **Chosen.** The sandbox and a real company run the same agents and skills |

**Exception:** numbers. `metrics.*` stays on the factory's own server, over the company's warehouse and catalog, because "code owns every number" cannot be delegated to an arbitrary vendor tool.

**Consequences:**
- Company facts move out of skills into `company/<name>/context.md`. A test fails if a skill names a company fact or a tool.
- The runner allows exactly the mapped tools. Unmapped write tools on a vendor server stay blocked.
- Evals stay on the sandbox, where an answer key exists. Real use is monitored, and sanitized failures become eval cases.

**Would change if:** a capability needs guarantees a vendor tool cannot give. Then it gets a factory adapter, like `metrics`.

## D8. Every metric number cites its query, and code replays it

| Option | Verdict |
|---|---|
| Check that each number exists somewhere in a recomputed pool | Rejected as the main check. With 528 recomputed values, almost any plausible rate matches something. It caught invented numbers but let a true number from the wrong slice through |
| Make evidence fully structured (metric, periods, segment) | Rejected. Heavy for the model to write, and a second source of truth next to the tool call |
| **The metrics tools log every answer by `query_id`. Evidence cites the `query_id`. Code replays the query on the same world** | **Chosen.** An evidence value must equal the replayed result, and a claim's prose numbers must come from its own queries |

**Also:** a signal card is recomputed exactly from its metric, periods, and segment. The size must equal the sizing tool's answer.

**What code still cannot catch:** a packet whose numbers and quotes are all true but whose causal story is wrong, such as blaming a release that shipped before the drop. That is the job of Quality's Elon Mode disproof pass, and Quality's eval suite plants exactly that case.

**Would change if:** replay becomes too slow on a real warehouse. Then log results with a hash instead of replaying.

## D9. Builder's code is graded by hidden acceptance tests

| Option | Verdict |
|---|---|
| Trust the tests Builder writes | Rejected. An agent can write a test that passes its own mistake |
| A model reads the diff and judges it | Rejected as the main grade. Useful for style, weak on behavior |
| **Rerun the team's tests, then run acceptance tests from the answer key that Builder never sees** | **Chosen.** The same idea as SWE-bench: behavior is checked by tests written before the change |

**Also:** the app is a small Python codebase in the state the release left it (`sandbox/app`), in the same language as the factory, so one toolchain runs everything. Every change is made on a copy. Code checks scope before anyone reads the logic: a new flag that ships off, a new test, no removed test, a small diff. Quality sees the rerun tests and the scope checks, never the acceptance tests.

**Would change if:** a scenario needs front-end behavior that Python cannot show. Then the app gains a browser test, run by the same Playwright the demo checks use.

