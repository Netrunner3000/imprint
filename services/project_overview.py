"""Read-only summary of one production Project across Imprint agents."""

from pathlib import Path

from services.database import get_connection
from services.project_artifacts import list_for_project
from services.project_workspaces import load
from services.registry import Registry


def snapshot(project_id: str) -> dict | None:
    """Return current identity, working-state counts and linked outputs.

    Paths are links to user files, not files owned by a Project. A missing path
    remains visible so the user can locate or recreate an export.
    """
    project = Registry().get_project(project_id) if project_id else None
    if not project:
        return None
    artifacts = list_for_project(project_id)
    for artifact in artifacts:
        artifact["available"] = Path(artifact["path"]).is_file()
    with get_connection() as conn:
        content = conn.execute(
            """SELECT c.id, c.title, c.kind, c.status, c.campaign,
                      c.scheduled_for, c.created_at, a.handle AS account
                 FROM creator_content c
                 JOIN creator_accounts a ON a.id = c.account_id
                WHERE c.project_id = ? ORDER BY c.id DESC""",
            (project_id,)).fetchall()
    draft = load(project_id, "author").get("draft") or ""
    return {
        "project": project,
        "artifacts": artifacts,
        "creator_content": [dict(row) for row in content],
        "draft_words": len(draft.split()),
        "missing_files": sum(not item["available"] for item in artifacts),
    }
