"""Render onboarding steps as HTML with the Tallybird design system (sandbox/design). Markup only; the page
shell adds the stylesheet."""

from __future__ import annotations

from html import escape

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
