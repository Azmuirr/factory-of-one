"""The onboarding flow a new user walks through.

Onboarding v2 (rel_0412, 2026-02-10) puts calendar connect first, so the notetaker joins the user's next
meeting on its own. It removed the skip button. It shipped without a flag.
"""

from __future__ import annotations

from dataclasses import dataclass

from .flags import Flags


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    body: str
    skippable: bool = False


def steps(user: dict, flags: Flags) -> list[Step]:
    """The steps for this user, in order. `user` carries calendar_provider (google or microsoft) and plan."""
    return [
        Step("calendar_connect", "Connect your calendar",
             "Tallybird joins the meetings on your calendar and writes the notes for you."),
        Step("welcome", "Welcome to Tallybird", "Here is what a recap looks like."),
        Step("first_meeting", "Record your first meeting", "Start a meeting, or paste a meeting link."),
    ]
