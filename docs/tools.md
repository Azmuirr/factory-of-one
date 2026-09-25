# Simulated tools

Each tool is an MCP (Model Context Protocol) server shaped like the real product's public API. A real connector can replace a simulated one without changing the agent. Every tool must earn its place with a scenario that needs it.

## Customer voice

| Tool | Mimics | Data | First needed |
|---|---|---|---|
| `support` | Zendesk, Intercom | Tickets | v1 |
| `transcripts` | Zoom, Teams, and Meet post-meeting transcripts | A transcript after every transcribed meeting. About 20% of meetings are not transcribed | v1 |
| `surveys` | Typeform, Qualtrics | NPS and onboarding-exit free text | v1, medium tier |
| `research` | Dovetail | Interview notes, tagged insights, usability findings | Scenario 5 |
| `reviews` | G2, app stores | Public reviews, no account IDs | Later |

## Sales and field

| Tool | Mimics | Data | First needed |
|---|---|---|---|
| `crm` | Salesforce, HubSpot | Accounts, opportunities, pipeline, PQL handoffs, lost reasons | Scenario 3 |
| `field_requests` | Seller-logged customer asks, triaged into Jira or Azure DevOps | Request text, account, ARR at stake, deal stage, linked tracker item | Scenario 5 |

## Product data

| Tool | Mimics | Trust grade | First needed |
|---|---|---|---|
| `dashboards` | Amplitude, Looker, Power BI | Can be wrong: old definitions, immature cohorts | v1 |
| `metrics` | A semantic layer | Validated: one registered definition per metric | v1 |
| `warehouse` | Snowflake, BigQuery, read-only SQL | Exploratory: every answer labeled | v1 |
| `monitoring` | Sentry, Datadog | Error rates and latency | v1 |
| `billing` | Stripe | Subscriptions, MRR, failed payments | v1 |
| `experiments` | Statsig, Eppo | Assignments and exposures | Scenario 2 |
| `costs` | Cloud and model-usage billing | Cost per meeting minute | Scenario 3 |
| `marketing` | Ad platforms, web analytics | Spend and traffic by channel | Medium tier |

## Work and communication

| Tool | Mimics | First needed |
|---|---|---|
| `slack` | Slack, Teams | v1 |
| `mail` | Gmail, Outlook | v1 |
| `calendar` | Google Calendar | v1 |
| `docs` | Google Docs, Notion, Confluence | v1 |
| `tracker` | Jira, Azure DevOps, Linear | v1 |
| `directory` | Org chart and OKRs | v1 |
| `github` | GitHub and CI | v1 |
| `design` | Figma and a design system | v1 |
| `flags` | LaunchDarkly | v1 |

## Internal

| Tool | Holds |
|---|---|
| `ledger` | Every artifact the agents pass to each other. Schema: `ledger/ledger.schema.json` |

## Rules built into the servers

- Write tools only draft or propose. Human gates execute.
- No server can read `truth/` or `sandbox/scenarios/`.
- Agents read your own inbox and DMs on your behalf. Other people's private conversations are never served.

## Deleted

Community forums and social mentions. No scenario needs them.
