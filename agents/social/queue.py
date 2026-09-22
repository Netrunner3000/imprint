"""Durable, duplicate-safe delivery ledger for Social posts.

The platform APIs do not share an idempotency protocol.  Imprint therefore
guarantees the part it controls: one durable delivery job per saved post, an
atomic claim before the outbound call, and no automatic retry after an
ambiguous result.  A job left ``publishing`` by a crash becomes
``needs_review`` on the next launch.  The user must check the platform and
either mark it posted or explicitly accept the risk of retrying.

This module performs no network work and imports no Qt, which keeps the state
machine independently testable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from services.database import get_connection


ACTIVE = frozenset({"queued", "publishing"})
TERMINAL = frozenset({"posted"})
RETRYABLE = frozenset({"retryable", "failed"})
UNCERTAIN = "needs_review"

STATUS_LABELS = {
    "queued": "Queued",
    "publishing": "Posting…",
    "retryable": "Retry available",
    "failed": "Retry available",
    "needs_review": "Verify platform",
    "posted": "Posted",
}


class QueueError(RuntimeError):
    """A delivery job cannot make the requested state transition."""


class AlreadyPublished(QueueError):
    pass


class OutcomeUnknown(QueueError):
    pass


class PublishInProgress(QueueError):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _request_json(extra: dict) -> str:
    # Inputs such as board/subreddit/title are needed for a faithful retry.
    # Credentials are never accepted here and remain in the environment.
    return json.dumps(extra, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _idempotency_key(post: dict, request_json: str) -> str:
    payload = {
        "post_id": int(post["id"]),
        "platform": post.get("platform", ""),
        "body": post.get("body", ""),
        "media_path": post.get("media_path", ""),
        "request": json.loads(request_json),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def job_for_post(post_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM social_publish_jobs WHERE post_id = ?",
            (post_id,)).fetchone()
    return dict(row) if row else None


def request_args(job: dict) -> dict:
    try:
        value = json.loads(job.get("request_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def queue_post(post_id: int, extra: dict | None = None, *,
               allow_uncertain_retry: bool = False) -> dict:
    """Create or safely re-queue the one delivery job for ``post_id``.

    ``needs_review`` is deliberately sticky.  Only the UI's explicit,
    risk-labelled confirmation passes ``allow_uncertain_retry=True``.
    """
    extra = dict(extra or {})
    request_json = _request_json(extra)
    now = _now()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        post_row = conn.execute(
            "SELECT * FROM social_posts WHERE id = ?", (post_id,)).fetchone()
        if not post_row:
            raise QueueError("That saved post no longer exists.")
        post = dict(post_row)
        job_row = conn.execute(
            "SELECT * FROM social_publish_jobs WHERE post_id = ?",
            (post_id,)).fetchone()
        job = dict(job_row) if job_row else None

        if post.get("status") == "posted" or (job and job["status"] == "posted"):
            raise AlreadyPublished("This item is already recorded as posted.")
        if job and job["status"] == "publishing":
            raise PublishInProgress("This item already has a publish attempt in progress.")
        if job and job["status"] == UNCERTAIN and not allow_uncertain_retry:
            raise OutcomeUnknown(
                "The previous result is unknown. Check the platform before retrying.")

        key = _idempotency_key(post, request_json)
        if job:
            if job["status"] == "queued":
                return job
            conn.execute(
                """UPDATE social_publish_jobs
                      SET platform = ?, idempotency_key = ?, request_json = ?,
                          status = 'queued', requested_at = ?, updated_at = ?,
                          started_at = '', finished_at = '', last_error = ''
                    WHERE id = ?""",
                (post["platform"], key, request_json, now, now, job["id"]))
            job_id = job["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO social_publish_jobs
                     (post_id, platform, idempotency_key, request_json,
                      status, requested_at, updated_at)
                   VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
                (post_id, post["platform"], key, request_json, now, now))
            job_id = int(cursor.lastrowid)
        conn.execute(
            "UPDATE social_posts SET status = 'queued', last_error = '' WHERE id = ?",
            (post_id,))
        row = conn.execute(
            "SELECT * FROM social_publish_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


def claim(job_id: int) -> dict:
    """Atomically own a queued delivery before crossing the network boundary."""
    now = _now()
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """UPDATE social_publish_jobs
                  SET status = 'publishing', attempt_count = attempt_count + 1,
                      started_at = ?, updated_at = ?
                WHERE id = ? AND status = 'queued'""", (now, now, job_id))
        if cursor.rowcount != 1:
            raise PublishInProgress(
                "This publish job was already claimed or completed.")
        row = conn.execute(
            "SELECT * FROM social_publish_jobs WHERE id = ?", (job_id,)).fetchone()
        conn.execute(
            "UPDATE social_posts SET status = 'publishing' WHERE id = ?",
            (row["post_id"],))
    return dict(row)


def mark_posted(job_id: int, permalink: str = "") -> None:
    now = _now()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT post_id FROM social_publish_jobs WHERE id = ?",
            (job_id,)).fetchone()
        if not row:
            raise QueueError("That publish job no longer exists.")
        conn.execute(
            """UPDATE social_publish_jobs
                  SET status = 'posted', permalink = ?, last_error = '',
                      finished_at = ?, updated_at = ? WHERE id = ?""",
            (permalink, now, now, job_id))
        conn.execute(
            """UPDATE social_posts
                  SET status = 'posted', posted_at = ?, permalink = ?,
                      last_error = '' WHERE id = ?""",
            (now, permalink, row["post_id"]))


def mark_retryable(job_id: int, error: str) -> None:
    _mark_problem(job_id, "retryable", error)


def mark_uncertain(job_id: int, error: str) -> None:
    _mark_problem(job_id, UNCERTAIN, error)


def _mark_problem(job_id: int, status: str, error: str) -> None:
    now = _now()
    message = str(error)[:500]
    with get_connection() as conn:
        row = conn.execute(
            "SELECT post_id FROM social_publish_jobs WHERE id = ?",
            (job_id,)).fetchone()
        if not row:
            raise QueueError("That publish job no longer exists.")
        conn.execute(
            """UPDATE social_publish_jobs
                  SET status = ?, last_error = ?, finished_at = ?, updated_at = ?
                WHERE id = ?""", (status, message, now, now, job_id))
        conn.execute(
            "UPDATE social_posts SET status = ?, last_error = ? WHERE id = ?",
            (status, message, row["post_id"]))


def recover_interrupted() -> list[dict]:
    """Make crash-left attempts visible without ever retrying them blindly."""
    now = _now()
    note = ("Imprint closed before the platform confirmed the result. "
            "Check the platform before retrying.")
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM social_publish_jobs
                 WHERE status = 'publishing' ORDER BY id""").fetchall()
        if rows:
            ids = [int(row["id"]) for row in rows]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""UPDATE social_publish_jobs
                       SET status = 'needs_review', last_error = ?,
                           finished_at = ?, updated_at = ?
                     WHERE id IN ({placeholders})""",
                (note, now, now, *ids))
            post_ids = [int(row["post_id"]) for row in rows]
            post_placeholders = ",".join("?" for _ in post_ids)
            conn.execute(
                f"""UPDATE social_posts
                       SET status = 'needs_review', last_error = ?
                     WHERE id IN ({post_placeholders})""",
                (note, *post_ids))
    return [dict(row) for row in rows]


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").title())
