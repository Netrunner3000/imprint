"""Immutable approved manuscript snapshots for Publishing Manager.

The Write workspace remains editable. Approval captures its text, title and
byline together; later edits cannot mutate a version used for publication.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from services.database import get_connection


def approve(project_id: str, body: str, *, title: str = "",
            byline: str = "") -> dict:
    if not project_id or not body.strip():
        raise ValueError("Choose a Project with a non-empty Write draft")
    digest = sha256(body.encode("utf-8")).hexdigest()
    title, byline = title.strip(), byline.strip()
    with get_connection() as conn:
        # Reserve the next version atomically if another window approves at
        # the same time; a read-then-insert without this can reuse a number.
        conn.execute("BEGIN IMMEDIATE")
        latest = conn.execute(
            "SELECT * FROM project_manuscript_versions WHERE project_id = ? "
            "ORDER BY version DESC LIMIT 1", (project_id,)).fetchone()
        if latest and (latest["sha256"], latest["title"], latest["byline"]) == (
                digest, title, byline):
            return dict(latest)
        version = int(latest["version"]) + 1 if latest else 1
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO project_manuscript_versions "
            "(project_id, version, title, byline, body, sha256, approved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, version, title, byline, body, digest, stamp))
        row = conn.execute(
            "SELECT * FROM project_manuscript_versions "
            "WHERE project_id = ? AND version = ?",
            (project_id, version)).fetchone()
    return dict(row)


def list_versions(project_id: str) -> list[dict]:
    if not project_id:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT project_id, version, title, byline, sha256, approved_at, "
            "LENGTH(body) AS characters FROM project_manuscript_versions "
            "WHERE project_id = ? ORDER BY version DESC", (project_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_version(project_id: str, version: int) -> dict | None:
    if not project_id or version < 1:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM project_manuscript_versions "
            "WHERE project_id = ? AND version = ?",
            (project_id, version)).fetchone()
    return dict(row) if row else None
