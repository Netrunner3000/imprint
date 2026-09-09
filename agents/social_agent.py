"""Social agent — the public funnel for whatever the studio just made.

Every other mode in Imprint produces something that then needs an audience: a
book, a release, a site, a client gig. Each of them grew its own half of a
promotion story — the Publish mode schedules quote graphics, Creator drafts a
promo post — and none of them owned the funnel itself. This does.

## What it writes for

A **campaign** is one subject and its goal. The subject is free text plus a
kind (book, release, product, gig), because the modes do not yet share a
Project record — see `SUGGESTIONS.md` #42, which is the thing that would make
this a lookup instead of retyping. The kind shapes the prompt and nothing else.

## Why the platform matters to the prompt

The same announcement is a different piece of writing on each platform, and not
because of length. Reddit removes a post that reads as marketing; Pinterest is
a search engine wearing a mood board; X gives you seven words before someone
scrolls. `services/social_platforms.py` carries that guidance per platform and
it goes into the prompt verbatim, so the model is writing *for* somewhere
rather than writing once and being truncated.

## What it will not do

It does not write engagement bait, does not fabricate reviews, testimonials or
numbers, and does not impersonate anyone. Those are in the system prompt rather
than left to chance, because a promotion tool that invents a quote from a happy
customer is not a feature with an off switch — it is a liability the user does
not find out about until someone else does.
"""

from __future__ import annotations

from services.social_platforms import Platform

SUBJECT_KINDS = {
    "book": "a book the user wrote",
    "release": "a music release the user made",
    "product": "a product or digital download the user sells",
    "gig": "a freelance service the user offers",
    "other": "something the user made",
}

# What a post is *for*. A launch and a re-share of an old piece are different
# writing jobs and the drafter treated them as one until these existed.
ANGLES = {
    "launch": "It is out now. Say what it is and where to get it, once.",
    "behind_the_scenes": (
        "How it was made, or something that went wrong on the way. No product "
        "pitch — the link earns its place by the story being worth reading."),
    "excerpt": (
        "Lead with the best actual line, passage or clip from the work itself "
        "and let it stand almost alone."),
    "value": (
        "Teach one useful thing from the subject that stands entirely on its "
        "own, so it is worth reading by someone who never clicks the link."),
    "question": (
        "Ask something the audience can answer from their own experience. The "
        "subject is context, not the point."),
    "milestone": (
        "A concrete number or moment worth marking. Specific, not triumphal."),
}

SYSTEM = (
    "You write social posts for an independent creator promoting their own "
    "work. You write like a person, not a brand account.\n\n"
    "Absolute rules:\n"
    "- Never invent reviews, testimonials, endorsements, sales figures, chart "
    "positions, follower counts or press quotes. If a number would help and "
    "you were not given one, write the post without a number.\n"
    "- Never claim to be anyone other than the creator, and never write in the "
    "voice of a named third party.\n"
    "- No engagement bait: no 'comment YES', no 'tag someone who', no fake "
    "urgency, no invented scarcity.\n"
    "- No hashtag walls. Where hashtags belong on the platform, three or four "
    "specific ones beat twenty generic ones.\n"
    "- Respect the character limit you are given. It is a hard ceiling, not a "
    "target.\n\n"
    "Return the post text only — no preamble, no explanation, no quotation "
    "marks around the whole thing, no markdown headings."
)


def _campaign_block(campaign: dict) -> str:
    kind = SUBJECT_KINDS.get(campaign.get("subject_kind", "other"),
                             SUBJECT_KINDS["other"])
    lines = [f"SUBJECT: {campaign.get('subject', '')} — {kind}"]
    for key, label in (("goal", "Goal"), ("audience", "Audience"),
                       ("tone", "Tone"), ("links", "Link(s)")):
        value = (campaign.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def build_post_messages(campaign: dict, platform: Platform, angle: str,
                        notes: str = "", variants: int = 1) -> list[dict]:
    """One post for one platform, or several variants of it."""
    angle_text = ANGLES.get(angle, ANGLES["launch"])
    limit = (f"Hard limit: {platform.limit} characters."
             if platform.limit else "No hard character limit.")

    parts = [
        _campaign_block(campaign),
        "",
        f"PLATFORM: {platform.name}",
        f"How to write well there: {platform.guidance}",
        limit,
        "",
        f"ANGLE: {angle_text}",
    ]
    if notes.strip():
        parts += ["", f"SPECIFICS TO USE: {notes.strip()}"]
    if variants > 1:
        parts += [
            "",
            f"Write {variants} genuinely different versions — different "
            "openings and different approaches, not the same post reworded. "
            "Separate them with a line containing only ---",
        ]

    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n".join(parts)},
    ]


def build_clip_brief_messages(campaign: dict, platform: Platform,
                              seconds: int, notes: str = "") -> list[dict]:
    """A one-line topic for the video pipeline to script from.

    Social does not write the video — it asks the Video mode for one, and the
    Video mode's own script stage does the writing. What it needs from here is
    a topic sentence with the subject and angle already in it, which is why
    this returns a brief rather than a script.
    """
    parts = [
        _campaign_block(campaign),
        "",
        f"PLATFORM: {platform.name}",
        f"LENGTH: about {seconds} seconds of narration.",
        "",
        "Write a single sentence describing what this short video should "
        "cover. It will be handed to a video script writer as its topic, so it "
        "must be concrete and self-contained: a specific claim, story or "
        "explanation, not a category. No title, no formatting, one sentence.",
    ]
    if notes.strip():
        parts += ["", f"SPECIFICS TO USE: {notes.strip()}"]
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n".join(parts)},
    ]


def split_variants(response: str) -> list[str]:
    """Split a multi-variant response on its `---` separators.

    Falls back to the whole response as one variant: a model that ignored the
    separator instruction has still written a usable post, and dropping it
    because the formatting was wrong would be the worse failure.
    """
    chunks = [c.strip() for c in response.split("\n---") ]
    if len(chunks) == 1:
        chunks = [c.strip() for c in response.split("---")]
    cleaned = [c.strip().strip("-").strip() for c in chunks]
    cleaned = [c for c in cleaned if c]
    return cleaned or [response.strip()]


def over_limit(text: str, platform: Platform) -> int:
    """Characters over the platform's ceiling. 0 when it fits.

    Checked rather than trusted: the limit is in the prompt, and models
    overshoot it often enough that posting an over-length draft would be a
    rejected API call at the worst possible moment.
    """
    if not platform.limit:
        return 0
    return max(0, len(text.strip()) - platform.limit)
