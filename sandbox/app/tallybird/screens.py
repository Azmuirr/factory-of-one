"""Render onboarding steps and the checkout screen as HTML with the Tallybird design system (sandbox/design).
Markup only; the page shell adds the stylesheet."""

from __future__ import annotations

from html import escape

from .checkout import Checkout
from .onboarding import Step

PRIMARY = {"calendar_connect": ("connect", "Connect calendar"), "welcome": ("next", "Continue"),
           "first_meeting": ("record", "Start recording")}


def render_step(step: Step, index: int = 1, total: int = 3) -> str:
    action, label = PRIMARY.get(step.id, ("next", "Continue"))
    skip = '<button class="tb-btn tb-btn--ghost" data-action="skip">Skip for now</button>' if step.skippable else ""
    return (
        f'<section class="tb-card" data-step="{escape(step.id)}">'
        f'<p class="tb-eyebrow">Step {index} of {total}</p>'
        f'<h1 class="tb-title">{escape(step.title)}</h1>'
        f'<p class="tb-body">{escape(step.body)}</p>'
        f'<div class="tb-actions"><button class="tb-btn tb-btn--primary" data-action="{action}">{label}</button>{skip}</div>'
        "</section>"
    )


def render_checkout(c: Checkout) -> str:
    monthly_total = c.monthly_per_seat * c.seats
    savings_pct = round(100 * (1 - c.annual_per_seat / c.monthly_per_seat))
    savings = f" Save {savings_pct}% billed annually." if c.savings_shown else ""
    annual_toggle = (
        f'<button class="tb-btn tb-btn--secondary" data-action="toggle-annual">Switch to annual</button>{escape(savings)}'
    )
    top = (
        f'<section class="tb-card" data-step="checkout">'
        f'<p class="tb-eyebrow">{escape(c.plan.title())}, {c.seats} seats</p>'
        f'<h1 class="tb-title">${monthly_total:,.0f} a month</h1>'
    )
    if c.annual_shown_first:
        return top + f'<div class="tb-actions">{annual_toggle}<button class="tb-btn tb-btn--primary" data-action="subscribe">Subscribe</button></div></section>'
    return (top + '<div class="tb-actions"><button class="tb-btn tb-btn--primary" data-action="subscribe">Subscribe</button></div>'
            f'<p class="tb-footnote">{annual_toggle}</p></section>')
