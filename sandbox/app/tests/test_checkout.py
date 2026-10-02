from tallybird.checkout import checkout
from tallybird.flags import Flags
from tallybird.screens import render_checkout

USERS = [{"company_size": "s2_10", "plan": "team"}, {"company_size": "s11_50", "plan": "team"}]


def test_the_monthly_price_shows_first_for_every_user():
    flags = Flags.load()
    for user in USERS:
        c = checkout("team", 5, flags, user)
        assert not c.annual_shown_first and not c.savings_shown


def test_the_annual_toggle_renders_as_a_footnote_with_no_savings_shown():
    c = checkout("team", 5, Flags.load(), USERS[0])
    html = render_checkout(c)
    assert "tb-footnote" in html
    assert "Save" not in html
