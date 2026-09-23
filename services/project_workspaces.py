"""Project-scoped working documents shared through the project registry.

The project row owns stable identity; each workspace stores only its editable
working state here. This keeps an unsaved manuscript from following the user
into a different project and lets the same project be reopened after restart.
"""

from __future__ import annotations

import json

from services.database import get_connection


def load(project_id: str, workspace: str) -> dict:
    if not project_id:
        return {}
    with get_connection() as conn:
        row = conn.execute(
            "SELECT state_json FROM project_workspaces "
            "WHERE project_id = ? AND workspace = ?",
            (project_id, workspace)).fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row["state_json"])
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save(project_id: str, workspace: str, state: dict, *,
         work_title: str | None = None, byline: str | None = None) -> None:
    if not project_id or not workspace:
        raise ValueError("A project and workspace are required")
    payload = json.dumps(state, ensure_ascii=False)
    with get_connection() as conn:
        # Write the editable snapshot and its shared identity in one
        # transaction: a crash cannot leave an updated manuscript under an
        # older title in the project registry.
        conn.execute(
            """INSERT INTO project_workspaces
                 (project_id, workspace, state_json, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(project_id, workspace) DO UPDATE SET
                 state_json = excluded.state_json,
                 updated_at = CURRENT_TIMESTAMP""",
            (project_id, workspace, payload))
        fields = {key: value.strip() for key, value in (
            ("work_title", work_title), ("byline", byline)) if value is not None}
        if fields:
            assignments = ", ".join(f"{key} = ?" for key in fields)
            conn.execute(
                f"UPDATE projects SET {assignments} WHERE id = ?",
                (*fields.values(), project_id))
