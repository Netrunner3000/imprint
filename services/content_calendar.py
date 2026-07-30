"""
Content calendar scheduling for the Manuscript (Publisher) agent.
Pure scheduling logic — assigns quotes to platform/day/format slots following a
simple weekly cadence, cycling quotes if there are more slots than quotes.
Caption writing is a separate LLM step (see ManuscriptAgent.build_calendar_caption_messages).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta

# platform -> (posts per week, format: "graphic" | "short" | "alternate")
CADENCE = {
    "TikTok": (4, "short"),
    "Instagram": (3, "alternate"),
    "Pinterest": (7, "graphic"),
}


@dataclass
class CalendarSlot:
    day: date
    platform: str
    format: str  # "graphic" | "short"
    quote: str
    caption: str = field(default="")


def build_calendar(
    quotes: list[str],
    weeks: int,
    start_date: date,
    platforms: list[str],
) -> list[CalendarSlot]:
    """Distribute quotes across days/platforms following CADENCE, cycling quotes if needed."""
    if not quotes or not platforms or weeks < 1:
        return []

    total_days = weeks * 7
    slots: list[CalendarSlot] = []
    quote_idx = 0

    for platform in platforms:
        per_week, fmt = CADENCE.get(platform, (3, "graphic"))
        total_posts = min(per_week * weeks, total_days)
        interval = max(1, total_days // max(total_posts, 1))

        for i in range(total_posts):
            day_offset = min(i * interval, total_days - 1)
            slot_format = fmt
            if slot_format == "alternate":
                slot_format = "graphic" if i % 2 == 0 else "short"
            quote = quotes[quote_idx % len(quotes)]
            quote_idx += 1
            slots.append(CalendarSlot(
                day=start_date + timedelta(days=day_offset),
                platform=platform,
                format=slot_format,
                quote=quote,
            ))

    slots.sort(key=lambda s: (s.day, s.platform))
    return slots
