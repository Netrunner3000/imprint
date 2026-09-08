"""The audiobook library, and where the listener stopped.

The Narrator converts an ebook into one merged MP3 per book and writes it to
the configured output folder. Until now the app forgot about it the moment the
conversion finished — the file existed and nothing in the tool could find it,
list it, or play it.

Resume position is stored per file path rather than per library index, because
the library is a directory scan: files get renamed, moved and re-converted, and
an index would quietly point at the wrong book. A path that disappears simply
stops being listed, and its progress row is harmless if it comes back.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from services.database import get_connection

AUDIO_SUFFIXES = {".mp3", ".m4a", ".m4b", ".wav", ".aac", ".flac", ".ogg"}

# Past this, treat the book as finished rather than resuming three seconds
# before the end and immediately stopping.
FINISHED_FRACTION = 0.99


@dataclass
class Audiobook:
    path: Path
    title: str
    size_bytes: int
    position_ms: int = 0
    duration_ms: int = 0
    finished: bool = False
    last_played: str = ""

    @property
    def progress(self) -> float:
        if not self.duration_ms:
            return 0.0
        return min(1.0, self.position_ms / self.duration_ms)

    @property
    def started(self) -> bool:
        return self.position_ms > 0 and not self.finished


def scan(folder: Path) -> list[Audiobook]:
    """Every audio file in the folder, with any saved progress attached.

    Recursive, because the converter can be pointed at a per-book subfolder.
    """
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        return []

    saved = _all_progress()
    books: list[Audiobook] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        row = saved.get(str(path), {})
        books.append(Audiobook(
            path=path,
            title=row.get("title") or path.stem.replace("_", " "),
            size_bytes=path.stat().st_size,
            position_ms=row.get("position_ms", 0),
            duration_ms=row.get("duration_ms", 0),
            finished=bool(row.get("finished", 0)),
            last_played=row.get("last_played", ""),
        ))
    return books


def _all_progress() -> dict[str, dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM audiobook_progress").fetchall()
    return {row["path"]: dict(row) for row in rows}


def load_position(path: Path) -> int:
    """Where to resume, in milliseconds. 0 for a book that is new or finished."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT position_ms, finished FROM audiobook_progress WHERE path = ?",
            (str(path),)).fetchone()
    if not row or row["finished"]:
        return 0
    return int(row["position_ms"] or 0)


def save_position(path: Path, position_ms: int, duration_ms: int = 0,
                  title: str = "") -> None:
    """Record the playhead.

    A book played to the end is marked finished rather than left parked at the
    last second, so the next play starts from the beginning instead of
    resuming and stopping immediately.
    """
    position_ms = max(0, int(position_ms))
    duration_ms = max(0, int(duration_ms))
    finished = bool(duration_ms and position_ms >= duration_ms * FINISHED_FRACTION)
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO audiobook_progress
              (path, title, position_ms, duration_ms, finished, last_played)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(path) DO UPDATE SET
              title=CASE WHEN excluded.title != '' THEN excluded.title
                         ELSE audiobook_progress.title END,
              position_ms=excluded.position_ms,
              duration_ms=CASE WHEN excluded.duration_ms > 0
                               THEN excluded.duration_ms
                               ELSE audiobook_progress.duration_ms END,
              finished=excluded.finished,
              last_played=excluded.last_played
        """, (str(path), title, position_ms, duration_ms, int(finished),
              datetime.now().isoformat(timespec="seconds")))
        conn.commit()


def mark_unfinished(path: Path) -> None:
    """Reset a finished book so it plays from the start again."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE audiobook_progress SET finished = 0, position_ms = 0 "
            "WHERE path = ?", (str(path),))
        conn.commit()


def format_time(ms: int) -> str:
    """h:mm:ss, or m:ss for anything under an hour."""
    if ms <= 0:
        return "0:00"
    seconds = int(ms // 1000)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def probe_duration_ms(path: Path) -> int:
    """Duration via ffprobe, or 0 when it is unavailable.

    Only used to show a length before the file has ever been played — once
    QMediaPlayer has loaded it, its own duration is authoritative and cheaper.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=20)
        return int(float(result.stdout.strip()) * 1000)
    except Exception:
        return 0
