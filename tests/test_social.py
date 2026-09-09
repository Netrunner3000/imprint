"""Social mode — platform rules, scheduling arithmetic and the posting gate.

Type: unit tests, no network, no GUI.

The interesting failures here are not crashes. They are a post that silently
exceeds a platform's limit and gets rejected on submit, a schedule that stacks
a week of Reddit posts onto one morning, and a "Post now" button offered for a
platform that cannot post — each of which looks fine until the moment it costs
something.
"""

import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.social_agent import (  # noqa: E402
    ANGLES, build_clip_brief_messages, build_post_messages, over_limit,
    split_variants,
)
from services import social_platforms  # noqa: E402


CAMPAIGN = {
    "subject": "The Salt Road", "subject_kind": "book",
    "goal": "launch week sales", "audience": "literary fiction readers",
    "tone": "warm", "links": "https://example.com/salt",
}


# ── Platforms ────────────────────────────────────────────────────────────────
def test_every_platform_declares_a_format_it_supports():
    for platform in social_platforms.PLATFORMS:
        assert platform.formats, f"{platform.name} lists no formats"
        assert set(platform.formats) <= {"text", "image", "clip"}


def test_a_platform_that_cannot_post_says_why():
    """`ready_to_post=False` without an explanation is a dead end.

    The whole point of the distinction is that the user can tell the
    difference between "not wired up yet" and "needs a business account and an
    app review", and act accordingly.
    """
    for platform in social_platforms.PLATFORMS:
        if not platform.ready_to_post:
            assert len(platform.posting_note) > 40, (
                f"{platform.name} is drafting-only with no useful explanation")


def test_name_lookup_round_trips():
    for platform in social_platforms.PLATFORMS:
        assert social_platforms.key_for_name(platform.name) == platform.key


# ── Drafting ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("platform", social_platforms.PLATFORMS,
                         ids=lambda p: p.key)
def test_the_prompt_carries_the_platform_limit_and_guidance(platform):
    """A post written without the platform in the prompt is a generic post.

    The same announcement is a different piece of writing on Reddit and on
    Pinterest, and not because of length — so both the limit and the guidance
    have to reach the model, not just the platform's name.
    """
    messages = build_post_messages(CAMPAIGN, platform, "launch")
    prompt = messages[-1]["content"]
    assert platform.name in prompt
    assert platform.guidance[:40] in prompt
    if platform.limit:
        assert str(platform.limit) in prompt


def test_the_system_prompt_forbids_inventing_evidence():
    """A promotion tool that invents a testimonial is a liability, not a
    feature — and it is the user who finds out last."""
    system = build_post_messages(CAMPAIGN, social_platforms.get("x"),
                                 "launch")[0]["content"]
    for forbidden in ("testimonials", "sales figures", "engagement bait"):
        assert forbidden in system


@pytest.mark.parametrize("angle", list(ANGLES))
def test_every_angle_reaches_the_prompt(angle):
    prompt = build_post_messages(CAMPAIGN, social_platforms.get("reddit"),
                                 angle)[-1]["content"]
    assert ANGLES[angle][:30] in prompt


def test_variants_are_asked_for_only_when_more_than_one_is_wanted():
    one = build_post_messages(CAMPAIGN, social_platforms.get("x"), "launch",
                              variants=1)[-1]["content"]
    three = build_post_messages(CAMPAIGN, social_platforms.get("x"), "launch",
                                variants=3)[-1]["content"]
    assert "genuinely different" not in one
    assert "3 genuinely different" in three


def test_a_clip_brief_asks_for_one_sentence_not_a_script():
    """Social does not write the video. It writes the topic the video pipeline
    scripts from, which is why adding video cost a prompt rather than a second
    pipeline."""
    prompt = build_clip_brief_messages(
        CAMPAIGN, social_platforms.get("tiktok"), 30)[-1]["content"]
    assert "single sentence" in prompt
    assert "30 seconds" in prompt


# ── Limits and variants ──────────────────────────────────────────────────────
def test_over_limit_counts_the_overshoot():
    x = social_platforms.get("x")
    assert over_limit("short", x) == 0
    assert over_limit("y" * 300, x) == 20


def test_a_platform_without_a_limit_never_reports_an_overshoot():
    reddit = social_platforms.get("reddit")
    assert over_limit("y" * 50_000, reddit) >= 0


@pytest.mark.parametrize("response,expected", [
    ("one\n---\ntwo", ["one", "two"]),
    ("one\n---\ntwo\n---\nthree", ["one", "two", "three"]),
    ("just the one", ["just the one"]),
    ("a\n\n---\n\nb", ["a", "b"]),
])
def test_variants_split_on_the_separator(response, expected):
    assert split_variants(response) == expected


def test_a_response_that_ignored_the_separator_is_still_usable():
    """A model that ignored the formatting instruction has still written a
    usable post; dropping it for bad formatting is the worse failure."""
    assert split_variants("a perfectly good post") == ["a perfectly good post"]


# ── Scheduling ───────────────────────────────────────────────────────────────
@pytest.fixture
def store(tmp_path):
    from services import database, social_store

    original = database.DB_PATH
    database.DB_PATH = tmp_path / "social.db"
    conn = sqlite3.connect(str(database.DB_PATH))
    conn.executescript(database.SCHEMA)
    conn.commit()
    conn.close()
    try:
        yield social_store
    finally:
        database.DB_PATH = original


def test_reddit_is_scheduled_once_a_week(store):
    """Cadence is a safety property here, not a preference.

    Reddit removes promotional posts and bans accounts that post like a bot;
    the cadence table is the one place that judgement is written down.
    """
    slots = store.build_schedule(["reddit"], weeks=4, start=date(2026, 9, 14))
    assert len(slots) == 4


def test_a_platforms_weekly_allowance_is_spread_not_stacked(store):
    """Posting a week's allowance on one day is the pattern that reads as a
    bot, which is the thing this is meant to avoid."""
    slots = store.build_schedule(["x"], weeks=1, start=date(2026, 9, 14))
    days = {day for day, _ in slots}
    assert len(days) == len(slots), "two posts landed on the same day"


def test_the_schedule_is_ordered_by_date(store):
    slots = store.build_schedule(["x", "reddit", "pinterest"], weeks=2,
                                 start=date(2026, 9, 14))
    assert slots == sorted(slots, key=lambda s: (s[0], s[1]))


def test_undated_drafts_sort_after_scheduled_posts(store):
    """An empty date string sorts before every real date, which would bury the
    schedule under everything that is not on it."""
    campaign_id = store.create_campaign("c", "subject")
    store.add_post(campaign_id, "x", "undated")
    store.add_post(campaign_id, "x", "dated", scheduled_for="2026-09-20")
    bodies = [p["body"] for p in store.list_posts(campaign_id)]
    assert bodies == ["dated", "undated"]


def test_deleting_a_campaign_takes_its_posts_with_it(store):
    campaign_id = store.create_campaign("c", "subject")
    store.add_post(campaign_id, "x", "a")
    store.add_post(campaign_id, "x", "b")
    store.delete_campaign(campaign_id)
    assert store.list_posts() == []


def test_a_failed_post_records_why(store):
    campaign_id = store.create_campaign("c", "subject")
    post_id = store.add_post(campaign_id, "reddit", "body")
    store.mark_failed(post_id, "subreddit rules: no self-promotion")
    post = store.get_post(post_id)
    assert post["status"] == "failed"
    assert "self-promotion" in post["last_error"]


# ── The posting gate ─────────────────────────────────────────────────────────
def test_no_publisher_claims_to_be_ready_without_its_credentials(monkeypatch):
    """`configured` is what gates the Post button. A publisher that reports
    ready without credentials produces a failure at the moment of posting,
    which is the worst possible moment."""
    from services import social_publishing

    for name in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                 "REDDIT_USERNAME", "REDDIT_PASSWORD",
                 "PINTEREST_ACCESS_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    assert not social_publishing.PUBLISHERS["reddit"].configured
    assert not social_publishing.PUBLISHERS["pinterest"].configured


def test_an_unconfigured_publisher_names_what_is_missing(monkeypatch):
    from services import social_publishing

    for name in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                 "REDDIT_USERNAME", "REDDIT_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    why = social_publishing.PUBLISHERS["reddit"].why_not()
    assert "REDDIT_CLIENT_ID" in why


def test_status_lines_cover_every_platform_not_just_the_postable_ones():
    """The panel has to explain the drafting-only platforms too, or five of
    eight buttons look broken rather than gated."""
    from services import social_publishing

    names = {name for name, _, _ in social_publishing.status_lines()}
    assert names == set(social_platforms.names())


def test_reddit_refuses_to_post_without_a_subreddit_and_title(monkeypatch):
    """Both are required by the API, and guessing either is how a promotion
    post lands in the wrong community."""
    from services import social_publishing

    publisher = social_publishing.RedditPublisher()
    monkeypatch.setattr(publisher, "_token", lambda: "token")
    with pytest.raises(social_publishing.PublishError, match="subreddit"):
        publisher.publish("body", title="t")
    with pytest.raises(social_publishing.PublishError, match="title"):
        publisher.publish("body", subreddit="books")


def test_youtube_refuses_to_upload_without_a_file():
    from services import social_publishing

    publisher = social_publishing.YouTubePublisher()
    with pytest.raises(social_publishing.PublishError, match="clip"):
        publisher.publish("description", media_path="", title="t")
