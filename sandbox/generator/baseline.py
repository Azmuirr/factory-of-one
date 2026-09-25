"""Baseline parameters. Each value mirrors a row in sandbox/SPEC.md section 4."""

from datetime import datetime, timezone

EPOCH = datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday
DAY = 86_400
WEEKS = 10

# Arrivals
NONVIRAL_PER_DAY = 412.5  # 75% of about 550 a day; recap_link fills the rest
WEEKDAY_FACTOR = [1.15, 1.20, 1.15, 1.10, 0.95, 0.65, 0.70]  # Monday first
WEEKLY_TREND = 0.01
NONVIRAL_CHANNELS = {"organic": 0.35, "paid_search": 0.20, "direct": 0.20}
VIRAL_K = 0.67  # new workspaces per activation, spread over the next 21 days
VIRAL_WINDOW_DAYS = 21
PRE_HISTORY_ACTIVATIONS_PER_DAY = 0.40 * 550

# Attributes
COMPANY_SIZE = {"solo": 0.30, "s2_10": 0.45, "s11_50": 0.18, "s51_plus": 0.07}
CALENDAR = {"google": 0.60, "microsoft": 0.35, "none": 0.05}
MEETING_PLATFORM = {
    "google": {"meet": 0.55, "zoom": 0.40, "teams": 0.05},
    "microsoft": {"teams": 0.65, "zoom": 0.30, "meet": 0.05},
    "none": {"zoom": 0.60, "meet": 0.20, "teams": 0.20},
}
ADMIN_CONSENT_SHARE = {"google": 0.02, "microsoft": 0.45, "none": 0.0}

# Activation: base rate by calendar provider, scaled by channel and size.
# The multipliers are normalized so each provider's average matches its base rate.
BASE_ACTIVATION = {"google": 0.41, "microsoft": 0.39, "none": 0.36}
CHANNEL_MULT = {"organic": 1.0, "paid_search": 0.8, "direct": 1.05, "recap_link": 1.25}
CHANNEL_NORM = 0.35 * 1.0 + 0.20 * 0.8 + 0.20 * 1.05 + 0.25 * 1.25
SIZE_MULT = {"solo": 0.9, "s2_10": 1.0, "s11_50": 1.1, "s51_plus": 1.1}
SIZE_NORM = sum(COMPANY_SIZE[s] * SIZE_MULT[s] for s in COMPANY_SIZE)

# Onboarding v1: the calendar step can be skipped
CALENDAR_ATTEMPT_V1 = {"google": 0.75, "microsoft": 0.65, "none": 0.0}
CONNECT_CANCEL_RATE = 0.05

# Trial outcome
TRIAL_DAYS = 14
PAID_IF_ACTIVATED = 0.25
PAID_IF_NOT = 0.02
BUSINESS_SHARE_OF_TEAMS = 0.10
ANNUAL_SHARE = 0.5
SEATS = {"s2_10": (2, 5), "s11_50": (4, 10), "s51_plus": (6, 16)}
PRICE = {  # per seat per month: (monthly billing, annual billing)
    "pro": (20, 16),
    "team": (19, 15),
    "business": (30, 24),
}

# Baseline support tickets
TICKETS_PER_DAY = 10.0
TICKET_THEMES = {
    "bot_didnt_join": 0.25,
    "billing": 0.20,
    "recap_quality": 0.20,
    "login": 0.15,
    "other": 0.20,
}
TICKET_TAGS = {
    "bot_didnt_join": {"integration": 0.7, "bug": 0.3},
    "billing": {"billing": 1.0},
    "recap_quality": {"quality": 0.8, "other": 0.2},
    "login": {"account": 1.0},
    "other": {"other": 1.0},
}

PROVIDER_NAME = {"google": "Google Calendar", "microsoft": "Outlook", "none": "my calendar"}
PLATFORM_NAME = {"zoom": "Zoom", "meet": "Google Meet", "teams": "Teams"}
