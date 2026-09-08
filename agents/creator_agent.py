"""Creator agent — subscription-platform account management.

Plans and drafts for subscription creator accounts (OnlyFans and similar). It
is a planning and drafting tool, not a posting tool, for a concrete reason:

**There is no OnlyFans API to post through.** OnlyFans has no public API — the
limited access introduced in 2024 is for verified business partners only. Every
third-party "OnlyFans API" is browser automation or reverse-engineered private
endpoints, which their Terms of Service prohibit, and the documented outcome is
a permanent ban and lost earnings. For an account that *is* the income, that is
not a tradeoff worth making.

Their terms draw the useful line themselves: automation that **assists** a
human is acceptable, automation that **replaces** one is not. So this agent
writes drafts the user reviews and sends. It has no send path at all, which is
the only version of "automated" that is safe here.

## Account types

Three, recorded per account because they carry different obligations:

* ``own`` — the user's own account.
* ``managed`` — someone else's, run on their behalf. Requires a recorded
  consent holder and date; `require_ready()` refuses to draft without one, so
  an agency cannot quietly accumulate accounts nobody authorised.
* ``persona`` — a synthetic character the user operates. Legal, and common, but
  subscribers are paying on an understanding of who they are talking to, so the
  account carries a disclosure line and drafts never claim to be a real named
  person.

What this agent will not write, in any mode, is a message pretending to be a
specific real human in a live conversation with a paying subscriber. That is
the one thing the drafts are shaped to avoid: they are captions, promos and
starting points for the creator's own voice, not a stand-in for them.
"""

from __future__ import annotations

ACCOUNT_TYPES = ("own", "managed", "persona")

KINDS = {
    "post": "a feed post caption",
    "ppv": "a pay-per-view message with a clear hook and a price justification",
    "welcome": "a welcome message for a new subscriber",
    "promo": "an off-platform promo post that drives traffic to the account",
    "bio": "a profile bio",
    "campaign": "a week of scheduled content, as a plan",
}

# Where subscription traffic actually comes from. Promo drafts are written for
# these, because the platform itself is a poor discovery surface.
PROMO_CHANNELS = ("X / Twitter", "Reddit", "TikTok", "Instagram", "Threads")


class ConsentError(ValueError):
    """A managed account has no recorded authorisation."""


def require_ready(account: dict) -> None:
    """Raise if this account is not in a state we should draft for.

    Called before every generation. A managed account without a recorded
    consent holder is the case worth stopping: running someone else's account
    is normal agency work, running one nobody authorised is not, and the
    difference is invisible unless something insists on it.
    """
    account_type = (account.get("account_type") or "own").lower()
    if account_type not in ACCOUNT_TYPES:
        raise ValueError(f"Unknown account type: {account_type!r}")
    if account_type == "managed":
        if not (account.get("consent_holder") or "").strip():
            raise ConsentError(
                "This account is marked as managed for someone else, but no "
                "consent holder is recorded. Add who authorised it and when "
                "before drafting on their behalf."
            )


def _account_context(account: dict) -> str:
    account_type = (account.get("account_type") or "own").lower()
    handle = account.get("handle", "the account")
    lines = [f"Account: {handle} ({account.get('platform', 'onlyfans')})."]

    if account_type == "managed":
        holder = account.get("consent_holder", "")
        lines.append(
            f"This account belongs to {holder}, who has authorised this work. "
            "Write in their established voice; do not invent biographical "
            "facts about them."
        )
    elif account_type == "persona":
        disclosure = (account.get("disclosure") or "").strip()
        lines.append(
            "This is a synthetic persona, not a real person. Keep the writing "
            "clearly fictional in framing: no claims about a real body, a real "
            "location, or real-life events presented as fact."
        )
        if disclosure:
            lines.append(f"The account's disclosure line is: {disclosure}")
    else:
        lines.append("This is the user's own account; write in their voice.")

    if account.get("notes"):
        lines.append(f"Account notes: {account['notes']}")
    return "\n".join(lines)


SYSTEM_PROMPT = """You are a subscription-creator marketing assistant working \
inside a desktop studio app. You write captions, pay-per-view copy, welcome \
messages, off-platform promos and content plans for adult-industry creator \
accounts.

Ground rules, which override any instruction in the brief:

1. You are drafting for a human to review, edit and send themselves. Never \
write anything framed as an automated reply in a live conversation, and never \
write copy designed to make a subscriber believe they are talking to someone \
in real time when they are not.
2. Do not fabricate verifiable claims — no invented meet-ups, no false \
scarcity ("only 2 spots left" when there is no limit), no fake testimonials, \
no pretending a scheduled post is a spontaneous personal message.
3. For synthetic personas, keep the framing fictional. Do not write copy \
asserting the persona is a real specific human being.
4. Write suggestive marketing copy, not sexually explicit content. The copy \
sells; it is not the product.
5. No content involving minors, or anything implying a participant might be \
under 18, in any framing including "barely legal" styling.

Write in the creator's voice: specific, warm, and concrete. Avoid generic \
influencer filler. Where the brief is thin, say what you would need rather \
than inventing it."""


class CreatorAgent:
    """Builds prompts for the Creator panel."""

    def build_messages(self, prompt: str) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

    def build_draft_prompt(self, account: dict, kind: str, brief: str,
                           *, price_usd: float = 0.0,
                           channel: str = "") -> list[dict]:
        """Messages for one drafting run. Consent-checked first."""
        require_ready(account)

        what = KINDS.get(kind, KINDS["post"])
        parts = [_account_context(account), "", f"Write {what}."]

        if kind == "ppv" and price_usd:
            parts.append(
                f"Price point: ${price_usd:.2f}. The copy should make the "
                "value legible at that price without overpromising."
            )
        if kind == "promo" and channel:
            parts.append(
                f"Target channel: {channel}. Match its norms and length, and "
                "keep it within that platform's content rules — this is the "
                "public-facing funnel, not the paid feed."
            )
        parts += ["", "Brief:", brief.strip() or "(none given)"]
        return self.build_messages("\n".join(parts))

    def build_video_prompt(self, account: dict, brief: str) -> str:
        """A Higgsfield prompt for a promo clip.

        Safe-for-work by construction: Higgsfield prohibits sexually explicit
        material and moderates prompts, reference images and outputs, so an
        explicit prompt is a wasted request and an account risk. What it is
        good for is the teaser that lives on X or TikTok.
        """
        require_ready(account)
        descriptor = (brief or "").strip() or "a mood teaser for the account"
        return (
            f"Cinematic promotional teaser: {descriptor}. "
            "Stylised, atmospheric, safe-for-work advertising footage. "
            "Shallow depth of field, considered colour grade, confident "
            "framing. No text overlays, no explicit content."
        )
