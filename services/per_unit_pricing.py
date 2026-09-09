"""Prices for work that is not billed per token.

The budget guard is denominated in tokens. That is correct for chat and wrong
for everything else this app does: an image is priced per image, a video render
per image and per audio-minute, speech per thousand characters. None of those
can be expressed as an input/output token pair, so every one of them counted as
€0.00 against the session and daily caps regardless of what it actually cost.

This module is the other half of the cost model. Rates live in
`config/pricing.json` under `per_unit_usd`, so they are data the user can
correct rather than constants buried in a client.

**Zero means unknown, not free.** A provider whose rate has never been filled
in returns `None` from `rate()`, and the callers say "cost unknown" and warn
rather than billing nothing — the failure mode that let Gemini, DALL·E and
Higgsfield all silently bill zero for months.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "pricing.json"

DEFAULT_EUR_PER_USD = 0.92


def _table() -> dict:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def eur_per_usd() -> float:
    try:
        return float(_table().get("eur_per_usd") or DEFAULT_EUR_PER_USD)
    except (TypeError, ValueError):
        return DEFAULT_EUR_PER_USD


def rate_usd(*path: str) -> float | None:
    """Look up a per-unit rate. `None` means the rate is unknown.

    A rate of exactly 0 in the file is treated as unknown rather than free —
    an unfilled placeholder and a genuinely free service look identical in
    JSON, and of the two, silently billing nothing is the expensive mistake.
    """
    node = _table().get("per_unit_usd") or {}
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    try:
        value = float(node)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def to_eur(usd: float | None) -> float | None:
    return None if usd is None else round(usd * eur_per_usd(), 6)


def image_cost_eur(model: str, count: int = 1) -> float | None:
    """What `count` images from `model` will cost, or None if unpriced."""
    usd = rate_usd("openai_image", model)
    return None if usd is None else to_eur(usd * max(0, int(count)))


def tts_cost_eur(characters: int) -> float | None:
    usd = rate_usd("openai_tts_per_1k_chars")
    return None if usd is None else to_eur(usd * max(0, characters) / 1000.0)


def whisper_cost_eur(minutes: float) -> float | None:
    usd = rate_usd("openai_whisper_per_minute")
    return None if usd is None else to_eur(usd * max(0.0, minutes))


def render_cost_eur(provider: str = "higgsfield_render") -> float | None:
    return to_eur(rate_usd(provider))


def describe(cost_eur: float | None, unit: str) -> str:
    """One phrase for a cost that may not be known.

    Used verbatim next to the buttons that spend, so that an unpriced action
    says so instead of showing a confident €0.00.
    """
    if cost_eur is None:
        return f"{unit} · cost not priced yet"
    return f"{unit} · ≈ €{cost_eur:.2f}"
