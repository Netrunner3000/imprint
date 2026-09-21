"""The platforms Social mode writes for, and what posting to each really takes.

Two jobs, kept apart on purpose:

* **Writing** works for every platform here, always. It needs no credentials
  and no approval — it is a prompt and a character limit.
* **Posting** works for the few platforms whose API will actually accept a post
  from a personal script. That is a much shorter list than it looks, and the
  honest thing is to say which is which rather than shipping seven buttons of
  which four fail.

`ready_to_post` is deliberately not "does this platform have an API". Every one
of them does. It means: can *this user*, from *this machine*, with credentials
they can obtain today, publish a post — without a business account, a company
verification, or an app review that takes weeks. Where the answer is no, the
`posting_note` says exactly what stands in the way, so nobody wires up an
integration expecting it to work and discovers the gate afterwards.

None of this is verified against the live APIs from here, and platform terms
change often. Treat `posting_note` as a starting point for your own check, not
as current fact.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    # Hard character ceiling the drafter must respect. 0 = no meaningful limit.
    limit: int
    # What a good post looks like there. Goes into the prompt verbatim, so it
    # is written as guidance to a writer rather than as a config value.
    guidance: str
    # Formats worth posting there, best first.
    formats: tuple[str, ...]
    # Can this be published from the app today?
    ready_to_post: bool
    posting_note: str


PLATFORMS: tuple[Platform, ...] = (
    Platform(
        key="youtube",
        name="YouTube",
        limit=5000,
        guidance=(
            "A title under 70 characters that states the payoff, then a "
            "description whose first two lines stand alone in search results. "
            "No 'in this video', no 'don't forget to subscribe'."),
        formats=("clip",),
        ready_to_post=True,
        posting_note=(
            "Works today. vidforge already holds a working Data API v3 "
            "uploader; it needs an OAuth client secret placed in its .secrets "
            "directory and one browser sign-in, after which the token is "
            "cached. Uploads default to private."),
    ),
    Platform(
        key="reddit",
        name="Reddit",
        limit=40000,
        guidance=(
            "Write like a person with something to share, not a brand. Lead "
            "with the substance and put the link last or in a comment. A post "
            "that reads as marketing is removed by the subreddit, not by "
            "Reddit — read the rules of the specific subreddit first."),
        formats=("text", "image"),
        ready_to_post=True,
        posting_note=(
            "Workable today. A personal 'script' app on your own account gives "
            "a client id and secret, and posting uses your normal login. Rate "
            "limits are tight and most subreddits remove promotional posts "
            "regardless of the API, so this automates the mechanics, not the "
            "judgement about where a post belongs."),
    ),
    Platform(
        key="pinterest",
        name="Pinterest",
        limit=500,
        guidance=(
            "The image does the work; the description is for search. Name the "
            "thing plainly, say who it is for, and keep it keyword-led rather "
            "than clever."),
        formats=("image", "clip"),
        ready_to_post=True,
        posting_note=(
            "Workable today. The v5 API creates pins from a business account, "
            "which is free to convert to and does not need review for your own "
            "boards. A trial token is short-lived; a standard one needs an app "
            "submission."),
    ),
    Platform(
        key="x",
        name="X / Twitter",
        limit=280,
        guidance=(
            "One idea. The first seven words decide whether the rest is read. "
            "No thread unless each post stands alone."),
        formats=("text", "image", "clip"),
        ready_to_post=False,
        posting_note=(
            "Drafting only. Posting through the v2 API has required a paid "
            "tier since the free tier was withdrawn, and the write allowance on "
            "the cheapest tier is small. Check current pricing before wiring "
            "it up — this is the one most likely to have changed."),
    ),
    Platform(
        key="instagram",
        name="Instagram",
        limit=2200,
        guidance=(
            "The caption's first line is all most people see. Front-load it, "
            "put hashtags at the end, and write for someone who is already "
            "looking at the image."),
        formats=("image", "clip"),
        ready_to_post=False,
        posting_note=(
            "Drafting only. Content publishing runs through the Instagram "
            "Graph API and needs a Business or Creator account linked to a "
            "Facebook Page, plus an app that has passed review for the "
            "publishing permissions. Not a same-day setup."),
    ),
    Platform(
        key="tiktok",
        name="TikTok",
        limit=2200,
        guidance=(
            "Written for sound-off viewing: the first frame has to carry the "
            "hook as text. The caption is a second hook, not a summary."),
        formats=("clip",),
        ready_to_post=False,
        posting_note=(
            "Drafting only. The Content Posting API requires an approved app, "
            "and direct posting specifically requires passing their audit. "
            "Unaudited apps can only upload to drafts."),
    ),
    Platform(
        key="threads",
        name="Threads",
        limit=500,
        guidance=(
            "Conversational and unpolished. A question that someone can answer "
            "from their own experience travels further than a statement."),
        formats=("text", "image"),
        ready_to_post=False,
        posting_note=(
            "Drafting only. There is a Threads API, but it is tied to the same "
            "Meta app model as Instagram and needs a linked professional "
            "account and reviewed permissions."),
    ),
    Platform(
        key="linkedin",
        name="LinkedIn",
        limit=3000,
        guidance=(
            "Concrete and specific, in the first person. What you did, what "
            "happened, what you would do differently. No engagement bait."),
        formats=("text", "image"),
        ready_to_post=False,
        posting_note=(
            "Drafting only. Posting needs the Share API, which is granted per "
            "app through their partner programme rather than on request."),
    ),
)

BY_KEY = {p.key: p for p in PLATFORMS}
POSTABLE = tuple(p for p in PLATFORMS if p.ready_to_post)


def get(key: str) -> Platform | None:
    return BY_KEY.get(key)


def names() -> tuple[str, ...]:
    return tuple(p.name for p in PLATFORMS)


def key_for_name(name: str) -> str:
    for platform in PLATFORMS:
        if platform.name == name:
            return platform.key
    return ""
