from tallybird.flags import Flags
from tallybird.onboarding import steps
from tallybird.screens import render_step

USERS = [{"calendar_provider": "google", "plan": "free"}, {"calendar_provider": "microsoft", "plan": "pro"}]


def test_calendar_connect_comes_first_and_cannot_be_skipped():
    flags = Flags.load()
    for user in USERS:
        first = steps(user, flags)[0]
        assert first.id == "calendar_connect" and not first.skippable


def test_every_user_gets_the_same_three_steps():
    flags = Flags.load()
    for user in USERS:
        assert [s.id for s in steps(user, flags)] == ["calendar_connect", "welcome", "first_meeting"]


def test_a_skippable_step_renders_a_skip_button():
    step = steps(USERS[0], Flags.load())[0]
    assert 'data-action="skip"' not in render_step(step)
    assert 'data-action="skip"' in render_step(type(step)(step.id, step.title, step.body, skippable=True))


def test_flags_follow_their_rules():
    flags = Flags.load(overrides={"teams_bot_beta": True})
    assert flags.is_on("teams_bot_beta", {"plan": "business"})
    assert not flags.is_on("teams_bot_beta", {"plan": "pro"})
    assert flags.is_on("recap_link_preview", {"plan": "free"})
    assert not flags.is_on("no_such_flag", {"plan": "free"})
