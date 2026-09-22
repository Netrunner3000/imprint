"""Durable record of the Video workspace's direct provider renders.

Real money is committed the moment a create request reaches a provider, but
the poll loop used to live only in a QThread: closing Imprint mid-render
lost the job id, the budget reservation and the paid result.  These rows
outlive the process; ``VideoPanel.resume_pending_jobs()`` reads them back on
the next launch, restores the reservation through the host money guard and
finishes the job.  Qt-free on purpose so tests and CLI tools can use it.
"""

from datetime import datetime

from services.database import get_connection

# Every terminal spelling the three provider clients emit ("cancelled" is
# Wan, "canceled" and "nsfw" are Higgsfield), plus this table's own 'lost'.
# Anything else is still worth polling on the next launch.
TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "canceled", "nsfw", "lost"})

_TERMINAL_SQL = ", ".join(f"'{status}'" for status in sorted(TERMINAL_STATUSES))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def record_submission(*, provider: str, model: str, topic: str, slug: str,
                      output_path: str, seconds: int, aspect_ratio: str,
                      flat_cost_eur: float, project=None, run_id: str = "",
                      agent: str = "video") -> int:
    """Write the intent row just before the create POST; returns its id.

    A row that never gains a job id means the app died between the POST and
    the provider's reply — ``sweep_lost()`` surfaces those on the next
    launch rather than guessing whether money moved.
    """
    now = _now()
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO video_jobs
                 (provider, model, topic, slug, output_path, seconds,
                  aspect_ratio, status, agent, flat_cost_eur, spend_state,
                  project, run_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?, 'reserved',
                       ?, ?, ?, ?)""",
            (provider, model, topic, slug, output_path, int(seconds),
             aspect_ratio, agent, float(flat_cost_eur or 0.0), project,
             run_id or "", now, now))
        return int(cursor.lastrowid)


def update_job(row_id: int, *, job_id=None, status=None, error=None,
               status_url=None) -> None:
    """Persist a provider transition (any subset of fields)."""
    sets, params = ["updated_at = ?"], [_now()]
    for column, value in (("job_id", job_id), ("status", status),
                          ("error", error), ("status_url", status_url)):
        if value is not None:
            sets.append(f"{column} = ?")
            params.append(value)
    params.append(row_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE video_jobs SET {', '.join(sets)} WHERE id = ?", params)


def mark_terminal(row_id: int, *, spend_state: str,
                  fallback_status: str = "failed", error: str = "") -> None:
    """Close a row: settle spend_state and guarantee a terminal status.

    A status the provider already stamped (failed, nsfw, ...) is kept;
    ``fallback_status`` only applies when the row is still non-terminal.
    """
    with get_connection() as conn:
        conn.execute(
            f"""UPDATE video_jobs
                   SET spend_state = ?,
                       status = CASE WHEN status IN ({_TERMINAL_SQL})
                                     THEN status ELSE ? END,
                       error = CASE WHEN ? = '' THEN error ELSE ? END,
                       updated_at = ?
                 WHERE id = ?""",
            (spend_state, fallback_status, error, error, _now(), row_id))


def pending_rows() -> list[dict]:
    """Acknowledged jobs a previous process never finished, oldest first."""
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT * FROM video_jobs
                 WHERE job_id != '' AND status NOT IN ({_TERMINAL_SQL})
                 ORDER BY id""").fetchall()
    return [dict(row) for row in rows]


def sweep_lost() -> list[dict]:
    """Mark submissions the provider never acknowledged and return them.

    No job id means no way to poll and no evidence money moved, so the
    reservation is released and the row surfaces to the user instead of
    being silently billed or silently dropped.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM video_jobs
                WHERE job_id = '' AND status = 'submitted'
                ORDER BY id""").fetchall()
        if rows:
            now = _now()
            conn.execute(
                """UPDATE video_jobs
                      SET status = 'lost', spend_state = 'released',
                          updated_at = ?
                    WHERE job_id = '' AND status = 'submitted'""", (now,))
    return [dict(row) for row in rows]
