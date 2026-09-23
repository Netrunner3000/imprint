"""Project links to finished files, without taking ownership of those files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from services.database import get_connection


def record(project_id: str, agent: str, kind: str, path: Path | str,
           label: str = "") -> int:
    if not project_id or not agent or not kind:
        raise ValueError("Project, agent and artifact kind are required")
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Project output is missing: {resolved}")
    now = datetime.now().isoformat(timespec="microseconds")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO project_artifacts
                 (project_id, agent, kind, label, path, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, path) DO UPDATE SET
                 agent = excluded.agent, kind = excluded.kind,
                 label = excluded.label, recorded_at = excluded.recorded_at""",
            (project_id, agent, kind, label.strip(), str(resolved), now))
        row = conn.execute(
            "SELECT id FROM project_artifacts WHERE project_id = ? AND path = ?",
            (project_id, str(resolved))).fetchone()
    return int(row["id"])


def list_for_project(project_id: str, *, kinds: tuple[str, ...] = ()) -> list[dict]:
    if not project_id:
        return []
    query = "SELECT * FROM project_artifacts WHERE project_id = ?"
    params: list = [project_id]
    if kinds:
        query += " AND kind IN (" + ",".join("?" for _ in kinds) + ")"
        params.extend(kinds)
    query += " ORDER BY recorded_at DESC, id DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
