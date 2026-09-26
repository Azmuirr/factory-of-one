# Company context: Tallybird

Tallybird is a fictional AI meeting notetaker for teams, sold with a product-led motion: a 14-day Team trial with no credit card, then Pro, Team, Business, or Free. Shared recaps bring in new workspaces.

## Key metric

`activation_rate_7d`: share of new workspaces that share a recap of a real meeting within 7 days of signup.

## Funnel, in order

1. `calendar_connect_rate_1d`: connected a calendar within 1 day, among workspaces that saw the step
2. `first_meeting_rate_7d`: recorded a real meeting within 7 days
3. `activation_rate_7d`: shared that meeting's recap within 7 days

Revenue follows activation: `trial_to_paid_rate`, then `new_mrr`.

## Dimensions to split by

`calendar_provider`, `channel`, `company_size`. A metric rejects dimensions at the wrong grain, such as `meeting_platform`.

## Weekly check periods

- Baseline: 2026-01-05 to 2026-02-08
- Recent: 2026-02-09 to the latest data

## Glossary

- Workspace: one customer account.
- Release ids look like `rel_0412`. Ticket ids look like `t_...`.
