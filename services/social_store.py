"""Campaigns, posts and the schedule they sit on.

Storage and arithmetic only — no prompts, no API calls. `build_schedule` is
deliberately pure Python and free: deciding *when* to post is a cadence
problem, not a language problem, and paying a model to lay dates out would be
both slower and worse.

The cadence comes from `services/content_calendar.py`, which the Publish mode
has used for book quotes since before this existed. Same numbers, so a book
promoted through Social and a book promoted through Publish do not disagree
about how often to post on Instagram.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from services.database import get_connection

# Posts per week, per platform. Anything not listed gets a conservative three.
CADENCE: dict[str, int] = {
    "x": 7,
    "threads": 5,
    "tiktok": 4,
    "instagram": 3,
    "pinterest": 7,
    "reddit": 1,          # more than this on Reddit is how accounts get banned
    "linkedin": 2,
    "youtube": 1,
}
DEFAULT_CADENCE = 3

STATUSES = ("draft", "scheduled", "posted", "failed")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Campaigns ────────────────────────────────────────────────────────────────
def create_campaign(name: str, subject: str, subject_kind: str = "other",
                    goal: str = "", audience: str = "", tone: str = "",
                    links: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO social_campaigns "
            "(created_at, name, subject, subject_kind, goal, audience, tone, links) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (_now(), name, subject, subject_kind, goal, audience, tone, links))
        conn.commit()
        return int(cur.lastrowid)


def update_campaign(campaign_id: int, **fields) -> None:
    allowed = ("name", "subject", "subject_kind", "goal", "audience", "tone",
               "links")
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    assignments = ", ".join(f"{k} = ?" for k in sets)
    with get_connection() as conn:
        conn.execute(f"UPDATE social_campaigns SET {assignments} WHERE id = ?",
                     (*sets.values(), campaign_id))
        conn.commit()


def list_campaigns() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM social_campaigns ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_campaign(campaign_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM social_campaigns WHERE id = ?",
                           (campaign_id,)).fetchone()
    return dict(row) if row else None


def delete_campaign(campaign_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM social_posts WHERE campaign_id = ?",
                     (campaign_id,))
        conn.execute("DELETE FROM social_campaigns WHERE id = ?", (campaign_id,))
        conn.commit()


# ── Posts ────────────────────────────────────────────────────────────────────
def add_post(campaign_id: int, platform: str, body: str, fmt: str = "text",
             scheduled_for: str = "", media_path: str = "",
             status: str = "draft") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO social_posts "
            "(campaign_id, created_at, platform, format, body, media_path, "
            " scheduled_for, status) VALUES (?,?,?,?,?,?,?,?)",
            (campaign_id, _now(), platform, fmt, body, media_path,
             scheduled_for, status))
        conn.commit()
        return int(cur.lastrowid)


def update_post(post_id: int, **fields) -> None:
    allowed = ("platform", "format", "body", "media_path", "scheduled_for",
               "status", "posted_at", "permalink", "last_error")
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    assignments = ", ".join(f"{k} = ?" for k in sets)
    with get_connection() as conn:
        conn.execute(f"UPDATE social_posts SET {assignments} WHERE id = ?",
                     (*sets.values(), post_id))
        conn.commit()


def delete_post(post_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM social_posts WHERE id = ?", (post_id,))
        conn.commit()


def list_posts(campaign_id: int | None = None) -> list[dict]:
    query = ("SELECT p.*, c.name AS campaign_name, c.subject AS subject "
             "FROM social_posts p "
             "JOIN social_campaigns c ON c.id = p.campaign_id")
    params: tuple = ()
    if campaign_id is not None:
        query += " WHERE p.campaign_id = ?"
        params = (campaign_id,)
    # Undated drafts sort last rather than first: an empty string sorts before
    # every real date, which would bury the schedule under the unscheduled.
    query += " ORDER BY p.scheduled_for = '' ASC, p.scheduled_for ASC, p.id ASC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_post(post_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM social_posts WHERE id = ?",
                           (post_id,)).fetchone()
    return dict(row) if row else None


def mark_posted(post_id: int, permalink: str = "") -> None:
    update_post(post_id, status="posted", posted_at=_now(),
                permalink=permalink, last_error="")


def mark_failed(post_id: int, error: str) -> None:
    update_post(post_id, status="failed", last_error=error[:500])


# ── Scheduling ───────────────────────────────────────────────────────────────
def build_schedule(platforms: list[str], weeks: int,
                   start: date | None = None) -> list[tuple[date, str]]:
    """(day, platform) slots across `weeks`, following each platform's cadence.

    Spread evenly through the week rather than bunched: posting a platform's
    whole weekly allowance on one day is the pattern that reads as a bot, and
    on Reddit it is the pattern that gets an account banned.
    """
    if not platforms or weeks < 1:
        return []
    start = start or date.today()
    slots: list[tuple[date, str]] = []

    for platform in platforms:
        per_week = max(1, CADENCE.get(platform, DEFAULT_CADENCE))
        for week in range(weeks):
            for index in range(per_week):
                # Even spacing inside the week, offset per platform so two
                # platforms do not always land on the same morning.
                offset = round(index * 7 / per_week)
                day = start + timedelta(days=week * 7 + offset)
                slots.append((day, platform))

    slots.sort(key=lambda s: (s[0], s[1]))
    return slots


def schedule_summary(campaign_id: int) -> dict:
    posts = list_posts(campaign_id)
    counts = {status: 0 for status in STATUSES}
    for post in posts:
        counts[post.get("status", "draft")] = counts.get(post.get("status", "draft"), 0) + 1
    return {"total": len(posts), **counts}
