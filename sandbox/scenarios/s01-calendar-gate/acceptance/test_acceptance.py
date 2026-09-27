"""Hidden acceptance tests for Builder's MVP in s01. Graders copy this file into the proposed change and run it.
Agents never see it. TALLYBIRD_BASE points at the unchanged app, so the tests can find the flags the change added."""

import os
from pathlib import Path

import yaml

from tallybird.flags import Flags
from tallybird.onboarding import steps
from tallybird.screens import render_step

BASE = yaml.safe_load(Path(os.environ["TALLYBIRD_BASE"], "tallybird", "flags.yaml").read_text(encoding="utf-8")) or {}
HERE = yaml.safe_load(Path("tallybird", "flags.yaml").read_text(encoding="utf-8")) or {}
NEW = sorted(set(HERE) - set(BASE))
MICROSOFT = {"calendar_provider": "microsoft", "plan": "pro"}
GOOGLE = {"calendar_provider": "google", "plan": "free"}


def calendar(user, flags):
    return next(s for s in steps(user, flags) if s.id == "calendar_connect")


def test_the_change_ships_behind_a_new_flag():
    assert NEW, "no new flag in tallybird/flags.yaml"


def test_new_flags_ship_off():
    assert not [n for n in NEW if HERE[n].get("enabled")]


def test_with_the_flag_off_nothing_changes():
    flags = Flags.load()
    for user in (MICROSOFT, GOOGLE):
        assert not calendar(user, flags).skippable


def test_with_the_flag_on_microsoft_users_can_skip_calendar_connect():
    flags = Flags.load(overrides={n: True for n in NEW})
    step = calendar(MICROSOFT, flags)
    assert step.skippable
    assert 'data-action="skip"' in render_step(step)


def test_calendar_connect_is_still_offered():
    flags = Flags.load(overrides={n: True for n in NEW})
    assert 'data-action="connect"' in render_step(calendar(MICROSOFT, flags))
