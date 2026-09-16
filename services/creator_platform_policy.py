"""User-reviewed platform rules; unknown rules never imply permission."""

from __future__ import annotations

from datetime import date

from services.database import get_connection

STATES = ("unknown", "allowed", "prohibited")
OWNER_STATES = ("unknown", "yes", "no")
PUBLISHING = ("manual_only", "official_api", "unknown")


def _key(platform: str) -> str:
    return (platform or "General").strip().casefold()


def get_policy(platform: str) -> dict:
    key = _key(platform)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM creator_platform_policies WHERE platform=?", (key,)).fetchone()
    if row:
        return dict(row)
    return {
        "platform": key, "synthetic_persona": "unknown",
        "verified_owner_required": "unknown", "ai_disclosure": "",
        "publishing_method": "manual_only", "source_url": "", "reviewed_on": "",
    }


def save_policy(platform: str, *, synthetic_persona: str,
                verified_owner_required: str, ai_disclosure: str,
                publishing_method: str, source_url: str,
                reviewed_on: str) -> None:
    if synthetic_persona not in STATES or verified_owner_required not in OWNER_STATES:
        raise ValueError("Choose a valid platform policy state.")
    if publishing_method not in PUBLISHING:
        raise ValueError("Choose a valid publishing method.")
    # A confident permission without a verifiable policy source is worse than
    # an unknown rule. The source may be a logged-in help page reference.
    definite = synthetic_persona != "unknown" or verified_owner_required != "unknown"
    if definite and (not source_url.strip() or not reviewed_on.strip()):
        raise ValueError("A reviewed source and date are required for definitive rules.")
    if reviewed_on.strip():
        try:
            date.fromisoformat(reviewed_on.strip())
        except ValueError as exc:
            raise ValueError("Review date must be YYYY-MM-DD.") from exc
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO creator_platform_policies
              (platform, synthetic_persona, verified_owner_required,
               ai_disclosure, publishing_method, source_url, reviewed_on)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(platform) DO UPDATE SET
              synthetic_persona=excluded.synthetic_persona,
              verified_owner_required=excluded.verified_owner_required,
              ai_disclosure=excluded.ai_disclosure,
              publishing_method=excluded.publishing_method,
              source_url=excluded.source_url,
              reviewed_on=excluded.reviewed_on
        """, (_key(platform), synthetic_persona, verified_owner_required,
              ai_disclosure.strip(), publishing_method, source_url.strip(),
              reviewed_on.strip()))
        conn.commit()
