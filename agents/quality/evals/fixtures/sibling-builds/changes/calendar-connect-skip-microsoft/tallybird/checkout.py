"""The trial-end checkout screen.

The checkout redesign (rel_0501, 2026-02-10) shows one price per seat per month by default. The annual-billing
toggle moved below the fold and no longer shows the savings amount. It shipped without a flag.
"""

from __future__ import annotations

from dataclasses import dataclass

from .flags import Flags

PRICE = {"team": (19.0, 15.0), "business": (30.0, 24.0)}  # (monthly, annual) per seat per month


@dataclass(frozen=True)
class Checkout:
    plan: str
    seats: int
    monthly_per_seat: float
    annual_per_seat: float
    annual_shown_first: bool
    savings_shown: bool


def checkout(plan: str, seats: int, flags: Flags, user: dict) -> Checkout:
    """What the trial-end billing screen shows this user. `user` carries company_size and plan."""
    monthly, annual = PRICE[plan]
    return Checkout(plan, seats, monthly, annual, annual_shown_first=False, savings_shown=False)
