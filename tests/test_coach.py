import pytest

from factory import coach, ledger

FIXTURE_ONE_ON_ONE = {
    "moment": "one_on_one",
    "about": "p_jpm",
    "for_meeting": "cal:e_002",
    "talking_points": [{"text": "How is the SSO estimate going?", "source": "trk:PLAT-88"}],
    "open_items": [{"text": "Follow up on the interview debrief", "source": "cal:e_007", "owner": "p_jpm"}],
}


@pytest.fixture
def world(now_run):
    return now_run / "world" / "world.db"


def test_a_prep_entry_with_real_sources_and_a_real_person_has_no_problems(world):
    earlier = []
    assert coach.ref_problems(world, FIXTURE_ONE_ON_ONE, earlier) == []
    assert coach.about_problems(world, FIXTURE_ONE_ON_ONE) == []


def test_a_made_up_source_is_a_problem(world):
    bad = {**FIXTURE_ONE_ON_ONE, "talking_points": [{"text": "Made this up", "source": "cal:e_999"}]}
    problems = coach.ref_problems(world, bad, [])
    assert len(problems) == 1
    assert "cal:e_999" in problems[0]


def test_a_source_that_is_an_earlier_ledger_entry_is_fine(world):
    earlier = [{"id": "cmt_0001", "type": "commitment", "payload": {}}]
    entry = {**FIXTURE_ONE_ON_ONE, "open_items": [{"text": "Still owed", "source": "cmt_0001", "owner": "p_jpm"}]}
    assert coach.ref_problems(world, entry, earlier) == []


def test_about_must_be_a_real_person_for_a_one_on_one(world):
    bad = {**FIXTURE_ONE_ON_ONE, "about": "not_a_real_person"}
    problems = coach.about_problems(world, bad)
    assert len(problems) == 1
    assert "not_a_real_person" in problems[0]


def test_hiring_prep_does_not_require_about_to_be_a_person(world):
    hiring = {**FIXTURE_ONE_ON_ONE, "moment": "hiring", "about": "Senior PM, Growth"}
    assert coach.about_problems(world, hiring) == []


def test_the_schema_has_no_field_for_a_rating_ranking_or_score():
    entry = {"id": "prp_0001", "type": "prep", "ts": "2026-03-02T12:00:00Z",
              "author": {"kind": "agent", "name": "coach"}, "refs": [], "payload": FIXTURE_ONE_ON_ONE}
    assert ledger.errors(entry, set()) == []
    with_score = {**FIXTURE_ONE_ON_ONE, "score": 4}
    entry_with_score = {**entry, "payload": with_score}
    assert ledger.errors(entry_with_score, set()) != []  # additionalProperties: false rejects it


# The second backstop: a rating has no field (above), but prose has no structure to block it either ------------

def test_a_clean_prep_has_no_rating_language():
    assert coach.rating_language_problems(FIXTURE_ONE_ON_ONE) == []


@pytest.mark.parametrize("phrase", [
    "I'd rate her performance a 2 out of 10.",
    "This was a 6/10 interview.",
    "Worth noting: a solid 85/100 on the take-home.",
    "I'd give it 2 stars.",
    "That's a B+ rating for the debrief.",
    "Coach gave a rating of poor overall.",
    "Don't rate him on this one meeting alone.",
])
def test_rating_shaped_prose_is_caught(phrase):
    entry = {**FIXTURE_ONE_ON_ONE, "talking_points": [{"text": phrase, "source": "trk:PLAT-88"}]}
    assert coach.rating_language_problems(entry) != []


def test_a_number_that_is_not_a_rating_is_not_flagged():
    entry = {**FIXTURE_ONE_ON_ONE, "talking_points": [{"text": "The requirements doc is due March 4.", "source": "trk:PLAT-88"}]}
    assert coach.rating_language_problems(entry) == []
