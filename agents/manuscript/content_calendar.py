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

    slots: list[CalendarSlot] = []
    quote_idx = 0

    for platform in platforms:
        per_week, fmt = CADENCE.get(platform, (3, "graphic"))
        # Distribute per week, not across the whole window. The old
        # global-interval spread (total_days // total_posts, floored) front-
        # loaded multi-week calendars: 3/week over 4 weeks became a post
        # every 2 days for 3 weeks and then silence — the cadence the labels
        # promise is N posts in *each* week.
        step = max(1, 7 // max(per_week, 1))
        post_idx = 0
        for week in range(weeks):
            for i in range(min(per_week, 7)):
                day_offset = week * 7 + min(i * step, 6)
                slot_format = fmt
                if slot_format == "alternate":
                    slot_format = "graphic" if post_idx % 2 == 0 else "short"
                quote = quotes[quote_idx % len(quotes)]
                quote_idx += 1
                post_idx += 1
                slots.append(CalendarSlot(
                    day=start_date + timedelta(days=day_offset),
                    platform=platform,
                    format=slot_format,
                    quote=quote,
                ))

    slots.sort(key=lambda s: (s.day, s.platform))
    return slots
