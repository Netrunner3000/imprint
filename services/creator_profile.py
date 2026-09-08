"""Voice profiles and persona bibles for creator accounts.

Two records that answer "who is this account", kept out of the agent module so
the prompt builder stays about prompts and this stays about storage.

**Voice** is the quality lever. A model asked to write "a caption for a gym
photoset" writes the median internet caption. The same model, given five of the
creator's own posts plus their tone, emoji habits and typical length, writes
something recognisably theirs. Samples do most of the work — the rules mainly
stop it drifting.

**Persona** applies to synthetic accounts. A disclosure line records what the
account *is*; the bible is what keeps it consistent between sessions, including
a locked seed and reference images so the visuals stay on-model rather than
being a different character every render.
"""

from __future__ import annotations

from datetime import datetime

from services.database import get_connection

# How many samples are worth sending. Beyond a handful the marginal value drops
# and the prompt just gets expensive.
MAX_SAMPLES = 6

# Who a message is aimed at. A welcome, a re-engagement and a thank-you to a
# two-year subscriber are three different messages; the drafter treated them as
# one until these existed.
SEGMENTS = {
    "": "",
    "new": "A brand-new subscriber. They do not know the tone yet — set it, and "
           "make the first impression concrete rather than effusive.",
    "loyal": "A long-standing subscriber. Acknowledge the history without "
             "being saccharine; they have heard the standard lines already.",
    "lapsed": "Someone who has drifted or cancelled. Give a specific reason to "
              "come back — what is new — not guilt and not desperation.",
    "big_spender": "A high-value subscriber. Warm and unhurried; do not upsell "
                   "in the same breath as thanking them.",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Voice ────────────────────────────────────────────────────────────────────
def load_voice(account_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM creator_voice WHERE account_id = ?",
            (account_id,)).fetchone()
    return dict(row) if row else {}


def save_voice(account_id: int, **fields) -> None:
    allowed = ("samples", "tone", "emoji_style", "banned_words",
               "typical_length", "notes")
    values = {k: (fields.get(k) or "") for k in allowed}
    with get_connection() as conn:
        conn.execute(f"""
            INSERT INTO creator_voice
              (account_id, {", ".join(allowed)}, updated_at)
            VALUES (?, {", ".join("?" * len(allowed))}, ?)
            ON CONFLICT(account_id) DO UPDATE SET
              {", ".join(f"{k}=excluded.{k}" for k in allowed)},
              updated_at=excluded.updated_at
        """, (account_id, *[values[k] for k in allowed], _now()))
        conn.commit()


def voice_block(account_id: int) -> str:
    """The voice half of a prompt, or "" when nothing is recorded.

    Samples come last and are the longest part, because they are what the model
    actually imitates — the rules above them only constrain the drift.
    """
    voice = load_voice(account_id)
    if not voice:
        return ""

    lines: list[str] = []
    if voice.get("tone"):
        lines.append(f"Tone: {voice['tone']}")
    if voice.get("typical_length"):
        lines.append(f"Typical length: {voice['typical_length']}")
    if voice.get("emoji_style"):
        lines.append(f"Emoji: {voice['emoji_style']}")
    if voice.get("banned_words"):
        lines.append(
            f"Never use these words or phrases: {voice['banned_words']}")
    if voice.get("notes"):
        lines.append(f"Other notes: {voice['notes']}")

    samples = [s.strip() for s in (voice.get("samples") or "").splitlines()
               if s.strip()][:MAX_SAMPLES]
    if samples:
        lines.append("")
        lines.append(
            "Here is how this account actually writes. Match the rhythm, "
            "vocabulary and punctuation — not the subject matter:")
        lines += [f"  — {s}" for s in samples]

    if not lines:
        return ""
    return "VOICE\n" + "\n".join(lines)


# ── Persona ──────────────────────────────────────────────────────────────────
def load_persona(account_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM creator_persona WHERE account_id = ?",
            (account_id,)).fetchone()
    return dict(row) if row else {}


def save_persona(account_id: int, **fields) -> None:
    allowed = ("appearance", "backstory", "personality", "boundaries",
               "reference_images")
    values = {k: (fields.get(k) or "") for k in allowed}
    seed = fields.get("seed")
    with get_connection() as conn:
        conn.execute(f"""
            INSERT INTO creator_persona
              (account_id, {", ".join(allowed)}, seed, updated_at)
            VALUES (?, {", ".join("?" * len(allowed))}, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
              {", ".join(f"{k}=excluded.{k}" for k in allowed)},
              seed=excluded.seed,
              updated_at=excluded.updated_at
        """, (account_id, *[values[k] for k in allowed], seed, _now()))
        conn.commit()


def persona_block(account_id: int) -> str:
    """The character bible, as prompt text."""
    persona = load_persona(account_id)
    if not persona:
        return ""
    lines = []
    for key, label in (("appearance", "Appearance"),
                       ("backstory", "Backstory"),
                       ("personality", "Personality"),
                       ("boundaries", "Never does or says")):
        if persona.get(key):
            lines.append(f"{label}: {persona[key]}")
    if not lines:
        return ""
    return ("CHARACTER — this is a written character, not a real person. "
            "Keep it consistent with the following:\n" + "\n".join(lines))


def persona_seed(account_id: int) -> int | None:
    """The locked generation seed, so visuals stay the same character."""
    return (load_persona(account_id) or {}).get("seed")


def reference_images(account_id: int) -> list[str]:
    raw = (load_persona(account_id) or {}).get("reference_images") or ""
    return [line.strip() for line in raw.splitlines() if line.strip()]
