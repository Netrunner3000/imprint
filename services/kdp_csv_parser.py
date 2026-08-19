"""
KDP Sales Report CSV parser for Create & Publish.

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

# (title, platform, notes) — notes carry account/login guidance, shown as a tooltip in the app.
INITIAL_TODOS = [
    ("Upload to Amazon KDP", "kdp",
     "Create a free KDP account at kdp.amazon.com using your author/pen-name identity. "
     "No API exists — upload is manual through their dashboard."),
    ("Upload to Draft2Digital", "d2d",
     "Create a free account at draft2digital.com. No API — manual upload."),
    ("Upload to IngramSpark (print)", "ingram",
     "Create an account at ingramspark.com. No API — manual upload; a small title setup fee "
     "is common but often waived with promo codes."),
    ("Set up PublishDrive account + API key", "publishdrive",
     "Sign up at publishdrive.com → Settings → API → Generate token → paste into .env as "
     "PUBLISHDRIVE_API_KEY, then restart the app. Check the 🔌 Connections panel to confirm it's live."),
    ("Upload cover files (3000x4500px, 300dpi)", "all", ""),
    ("Write Amazon book description (HTML-formatted)", "kdp",
     "No account needed to write it — the KDP Listing option in the Manuscript agent's Market mode "
     "generates this for you. Paste the result into the KDP account from the item above."),
    ("Set categories and keywords on KDP", "kdp",
     "Same KDP Listing output covers this — paste the categories/keywords into your KDP account."),
    ("Set pricing across all territories", "all", ""),
    ("Request ARC copies for launch team", "marketing", ""),
    ("Submit to BookBub Featured Deal", "marketing",
     "Create a free Partner account at partners.bookbub.com. No API — manual submission, and "
     "acceptance is competitive/not guaranteed."),
    ("Identify TikTokers/BookTokers in genre and pitch quote-clip promo", "marketing",
     "Reach out to dating/astrology-niche creators with reach; offer a free copy + a few "
     "pre-made quote graphics for a short clip of a line from the book they like."),
    ("Create TikTok, Instagram, and Pinterest accounts for the book", "marketing",
     "Manual signup on each platform's own site — no API/login through this app. Use one consistent "
     "username across all three (e.g. @yourbooktitle). Bio should name the reader + the promise, "
     "link in bio → your Amazon book page."),
    ("Set up ElevenLabs account (optional — better short narration)", "setup",
     "Sign up at elevenlabs.io → Profile → API Keys → paste into .env as ELEVENLABS_API_KEY, then "
     "restart. Optional: the free macOS system voice is used automatically if you skip this. "
     "Check the 🔌 Connections panel to confirm."),
    ("(Dev) Structured Book/Chapter data model", "engineering",
     "Code task, no external account. Chapters tab is currently a live-derived view over the Draft "
     "text, not a stored model — no per-chapter status/regeneration/reordering yet."),
    ("(Dev) Editing pass / Editor mode", "engineering",
     "Code task, no external account. Nothing currently re-reads a full draft for "
     "continuity/pacing/repetition."),
    ("(Dev) Autonomous chapter-by-chapter drive loop", "engineering",
     "Code task, no external account. Seed a premise → auto-outline → auto-draft each chapter → "
     "auto-compile."),
    ("(Dev) BookProfile auto-fill into Publish/Market fields", "engineering",
     "Code task, no external account. Publish/Market's own Hook/Comp Titles fields don't yet "
     "pre-fill from the saved Book Profile."),
    ("(Dev) Distribution integration (Buffer/Metricool)", "engineering",
     "Requires creating a Buffer or Metricool account (a paid plan for API access) and connecting "
     "each social account through their UI — this app would only push already-generated content "
     "through their API, not manage the connection itself."),
    ("(Dev) Ad-campaign briefs (Amazon Ads / Meta)", "engineering",
     "Code task to generate keyword/budget briefs. Actually running ads needs your own Amazon "
     "Advertising and/or Meta Ads Manager account — no API access planned, output would be a "
     "document you paste into their dashboards."),
    ("(Dev) Review-outreach tracking", "engineering",
     "Code task, no external account. Extend manuscript_todos into a light contact tracker."),
    ("(Dev) Multi-book support", "engineering", "Code task, no external account."),
    ("(Dev) Scheduled PublishDrive auto-refresh", "engineering",
     "Code task. Uses the PublishDrive account/API key from the item above — no new login needed."),
    ("(Dev) Price-sync UI", "engineering",
     "Code task. Uses the PublishDrive account/API key from the item above — no new login needed."),
    ("(Dev) Revenue chart visualization", "engineering", "Code task, no external account."),
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
        for title, platform, notes in INITIAL_TODOS:
            conn.execute(
                "INSERT INTO manuscript_todos (created_at, updated_at, title, platform, notes) VALUES (?, ?, ?, ?, ?)",
                (now, now, title, platform, notes)
            )
        conn.commit()
    conn.close()
