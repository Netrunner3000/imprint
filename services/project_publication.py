"""Approved-version export receipts and explicitly self-reported submissions.

This module makes a local file's provenance verifiable. It does not submit to
retailers or infer a retailer's status from an exported file.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import tempfile

from agents.author.book_exporter import export_book
from services.database import get_connection
from services.project_manuscripts import get_version

FORMATS = {"epub", "docx", "pdf"}


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_approved(project_id: str, version: int, fmt: str,
                    path: Path | str) -> dict:
    """Generate and receipt a *new* file from an immutable approved version."""
    row = get_version(project_id, version)
    if row is None:
        raise ValueError("Select an approved manuscript version first")
    if not row["title"].strip() or not row["byline"].strip():
        raise ValueError(
            "The approved version needs a title and byline before export; "
            "set them in the Project and approve a new version")
    if fmt not in FORMATS:
        raise ValueError("Choose EPUB, DOCX, or PDF")
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != f".{fmt}":
        raise ValueError(f"The filename must end in .{fmt}")
    if destination.exists():
        raise FileExistsError(f"Choose a new filename; {destination.name} exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Build beside the destination and install with a no-overwrite hard link.
    # A failed export cannot leave a partial file at the user's chosen name;
    # another process creating that name meanwhile cannot be overwritten.
    with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.stem}-",
            suffix=f".{fmt}", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        export_book(row["body"], row["title"], row["byline"], fmt, temporary)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("The exporter did not create a non-empty file")
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO project_manuscript_exports "
            "(project_id, version, format, path, sha256, exported_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, version, fmt, str(destination),
             _digest(destination), stamp))
        export_id = cursor.lastrowid
        saved = conn.execute(
            "SELECT * FROM project_manuscript_exports WHERE id = ?",
            (export_id,)).fetchone()
    return dict(saved)


def list_exports(project_id: str) -> list[dict]:
    if not project_id:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT e.*, v.title, v.byline FROM project_manuscript_exports e "
            "JOIN project_manuscript_versions v "
            "ON v.project_id = e.project_id AND v.version = e.version "
            "WHERE e.project_id = ? ORDER BY e.id DESC",
            (project_id,)).fetchall()
    return [dict(row) for row in rows]


def verify_export(export_id: int) -> dict | None:
    """Read a receipt and tell whether its file still has the recorded bytes."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM project_manuscript_exports WHERE id = ?",
            (export_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    path = Path(result["path"])
    try:
        result["file_state"] = (
            "matching" if path.is_file() and _digest(path) == result["sha256"]
            else "changed" if path.is_file() else "missing")
    except OSError:
        result["file_state"] = "unreadable"
    return result


def record_submission(export_id: int, retailer: str, submitted_on: str, *,
                      reference: str = "", evidence_path: Path | str = "") -> dict:
    """Record the user's attestation; this does *not* verify retailer receipt."""
    export = verify_export(export_id)
    if export is None:
        raise ValueError("Select an approved export")
    if export["file_state"] != "matching":
        raise ValueError("The approved export is missing or changed; recreate it")
    retailer, reference = retailer.strip(), reference.strip()
    if not retailer:
        raise ValueError("Name the retailer or distributor")
    try:
        submission_date = date.fromisoformat(submitted_on.strip())
    except ValueError as exc:
        raise ValueError("Enter the submission date as YYYY-MM-DD") from exc
    if submission_date > date.today():
        raise ValueError("A future date cannot be recorded as submitted")
    evidence = Path(evidence_path).expanduser().resolve() if evidence_path else None
    if evidence and not evidence.is_file():
        raise ValueError("The evidence file is missing")
    if not reference and not evidence:
        raise ValueError("Enter a confirmation reference or attach evidence")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM project_manuscript_submissions "
            "WHERE export_id = ? AND lower(retailer) = lower(?) "
            "AND ((reference != '' AND reference = ?) OR "
            "(evidence_path != '' AND evidence_path = ?)) LIMIT 1",
            (export_id, retailer, reference,
             str(evidence) if evidence else "")).fetchone()
        if existing:
            raise ValueError("That retailer confirmation is already recorded")
        cursor = conn.execute(
            "INSERT INTO project_manuscript_submissions "
            "(export_id, retailer, submitted_on, reference, evidence_path, "
            "evidence_sha256, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (export_id, retailer, submission_date.isoformat(), reference,
             str(evidence) if evidence else "",
             _digest(evidence) if evidence else "", stamp))
        saved = conn.execute(
            "SELECT * FROM project_manuscript_submissions WHERE id = ?",
            (cursor.lastrowid,)).fetchone()
    return dict(saved)


def list_submissions(project_id: str) -> list[dict]:
    if not project_id:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT s.*, e.version, e.format, e.path, e.sha256 AS export_sha256 "
            "FROM project_manuscript_submissions s "
            "JOIN project_manuscript_exports e ON e.id = s.export_id "
            "WHERE e.project_id = ? ORDER BY s.id DESC",
            (project_id,)).fetchall()
    return [dict(row) for row in rows]
