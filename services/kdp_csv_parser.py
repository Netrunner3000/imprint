"""
KDP Sales Report CSV parser for Sentinel AI.

KDP has no public API. You download reports manually from:
  KDP Dashboard → Reports → Sales Dashboard → Download

Drop the CSV into:   data/kdp_reports/

This parser watches that folder, ingests new files, and stores rows
in the manuscript_kdp_ingested table, deduplicating by filename.
"""

import csv
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from services.database import DB_PATH

KDP_REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "kdp_reports"
KDP_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

INITIAL_TODOS = [
    ("Upload to Amazon KDP", "kdp"),
    ("Upload to Draft2Digital", "d2d"),
    ("Upload to IngramSpark (print)", "ingram"),
    ("Set up PublishDrive account + API key", "publishdrive"),
    ("Upload cover files (3000x4500px, 300dpi)", "all"),
    ("Write Amazon book description (HTML-formatted)", "kdp"),
    ("Set categories and keywords on KDP", "kdp"),
    ("Set pricing across all territories", "all"),
    ("Request ARC copies for launch team", "marketing"),
    ("Submit to BookBub Featured Deal", "marketing"),
]


def parse_kdp_csv(filepath: Path) -> list[dict]:
    """Parse a KDP sales CSV into a list of row dicts."""
    rows = []
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k.strip(): v.strip() for k, v in row.items()})
    return rows


def summarise_kdp_rows(rows: list[dict]) -> dict:
    """Summarise parsed KDP rows into aggregate metrics."""
    total_units = 0
    total_royalties = 0.0
    by_marketplace: dict[str, dict] = {}
    kenp_pages = 0

    for row in rows:
        try:
            units = int(row.get("Units Sold", 0) or 0)
            royalty = float(row.get("Royalty", 0) or 0)
            marketplace = row.get("Marketplace", "Unknown")
            pages = int(row.get("KENP Read", 0) or 0)

            total_units += units
            total_royalties += royalty
            kenp_pages += pages

            if marketplace not in by_marketplace:
                by_marketplace[marketplace] = {"units": 0, "royalties": 0.0}
            by_marketplace[marketplace]["units"] += units
            by_marketplace[marketplace]["royalties"] += royalty
        except (ValueError, TypeError):
            continue

    return {
        "total_units": total_units,
        "total_royalties_usd": round(total_royalties, 2),
        "kenp_pages_read": kenp_pages,
        "by_marketplace": [
            {"marketplace": k, **v} for k, v in by_marketplace.items()
        ],
    }


def ingest_new_reports() -> list[str]:
    """Scan kdp_reports/ for CSV files not yet in the DB. Returns list of ingested filenames."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    ingested = []

    for csv_file in sorted(KDP_REPORTS_DIR.glob("*.csv")):
        cur.execute(
            "SELECT 1 FROM manuscript_kdp_ingested WHERE filename = ?",
            (csv_file.name,)
        )
        if cur.fetchone():
            continue

        rows = parse_kdp_csv(csv_file)
        summary = summarise_kdp_rows(rows)

        cur.execute("""
            INSERT INTO manuscript_kdp_ingested
              (filename, ingested_at, total_units, total_royalties_usd,
               kenp_pages_read, raw_summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            csv_file.name,
            datetime.utcnow().isoformat(),
            summary["total_units"],
            summary["total_royalties_usd"],
            summary["kenp_pages_read"],
            json.dumps(summary),
        ))
        conn.commit()
        ingested.append(csv_file.name)

    conn.close()
    return ingested


def manuscript_seed_todos() -> None:
    """Seed the manuscript_todos table with the standard publishing checklist if empty."""
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM manuscript_todos").fetchone()[0]
    if count == 0:
        now = datetime.utcnow().isoformat()
        for title, platform in INITIAL_TODOS:
            conn.execute(
                "INSERT INTO manuscript_todos (created_at, updated_at, title, platform) VALUES (?, ?, ?, ?)",
                (now, now, title, platform)
            )
        conn.commit()
    conn.close()
