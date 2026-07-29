# Manuscript Agent — Integration Handover
**Sentinel AI · lab/sentinel_ai**
_Written: 2026-06-08_

> **Status: implemented and extended beyond this spec.** This document is the original build plan —
> kept as historical context. For the current, accurate picture of what exists, see
> [docs/agents/manuscript.md](agents/manuscript.md) and README.md §5.16. Notably added since this
> handover: a Quote Finder tab (LLM-assisted verbatim quote extraction from the manuscript file),
> a Quote Graphics generator (Pillow, free), and a Shorts generator (TTS + ffmpeg, free by default).
> The price-sync UI, scheduled auto-refresh, and multi-book support described below are still open.

---

## 1. What This Is

A new agent called **Manuscript** that extends the existing `author` agent's writing capabilities with publishing infrastructure: live sales/royalty data from PublishDrive, KDP report ingestion, a unified metrics store, and a todo tracker for publishing tasks.

The agent sits in the **Creative** group in the left panel, alongside the existing Manuscript (author) button — or replaces/extends it depending on the approach you choose (see §6).

---

## 2. Architecture Overview

```
sentinel_ai/
├── agents/
│   └── manuscript_agent.py          ← NEW: system prompts + agent class
├── services/
│   ├── publishdrive_client.py       ← NEW: PublishDrive REST API wrapper
│   └── kdp_csv_parser.py            ← NEW: parses KDP sales report CSVs
├── config/
│   ├── agents.json                  ← EDIT: add "manuscript" entry
│   └── registry.json                ← EDIT: add "manuscript" entry
├── data/
│   └── kdp_reports/                 ← NEW folder: drop KDP CSVs here
└── main.py                          ← EDIT: panel + update_agent_ui wiring
```

The DB (`data/sentinel.db`) gets two new tables via a schema migration added to `database.py`.

---

## 3. New Files to Create

### 3.1 `agents/manuscript_agent.py`

```python
"""
Manuscript Agent — publishing metrics, platform management, and todo tracking.
Extends the author_agent with distribution intelligence.
"""

SYSTEM_PROMPT = """You are a publishing intelligence assistant embedded in Sentinel AI.
You have access to real-time sales data from PublishDrive and KDP CSV reports stored
locally in the Sentinel database. You answer questions about book performance, platform
status, and publishing tasks.

CAPABILITIES
- Sales & royalty summaries: "What did I make this week / this month / on Amazon?"
- Platform health: "Which stores are still pending?", "Any rejections?"
- Ranking & trend: "Best-selling country?", "Revenue trend last 30 days?"
- Todo management: "What's still on my publishing checklist?", "Mark IngramSpark as done."
- Metadata sync status: "Is my book description up to date on Kobo?"

RESPONSE STYLE
- Lead with the number or answer, not with an explanation of how you got it.
- Use short tables for multi-platform comparisons.
- Flag anomalies (sudden drop, a platform going inactive) proactively.
- If data is missing or stale, say so clearly rather than guessing.

DATA ACCESS
You receive structured data as JSON injected before the user's question.
Always ground your answers in the provided data. Do not fabricate figures.
"""

PUBLISHDRIVE_PROMPT = """You are analysing raw PublishDrive API data.
Extract the key metrics (units sold, revenue by currency, platform breakdown,
distribution status) and return a clean JSON summary with these keys:
  total_units, total_revenue_usd, by_platform (list), by_country (list),
  pending_stores (list), rejected_stores (list), period.
Return only valid JSON, no prose."""

KDP_PROMPT = """You are analysing a KDP sales report CSV (already parsed to JSON rows).
Extract: total_units_sold, total_royalties_usd, by_marketplace (list),
kenp_pages_read (if present), period_start, period_end.
Return only valid JSON, no prose."""


class ManuscriptAgent:
    """Publishing metrics, platform tracking, and todo management."""

    def __init__(self):
        self.name = "manuscript"

    def build_messages(self, prompt: str, context_json: str = "") -> list[dict]:
        system = SYSTEM_PROMPT
        if context_json:
            system += f"\n\nCURRENT DATA (JSON):\n{context_json}"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

    def build_publishdrive_parse_messages(self, raw_json: str) -> list[dict]:
        return [
            {"role": "system", "content": PUBLISHDRIVE_PROMPT},
            {"role": "user", "content": raw_json},
        ]

    def build_kdp_parse_messages(self, rows_json: str) -> list[dict]:
        return [
            {"role": "system", "content": KDP_PROMPT},
            {"role": "user", "content": rows_json},
        ]
```

---

### 3.2 `services/publishdrive_client.py`

```python
"""
PublishDrive REST API client for Sentinel AI.
API docs: https://publishdrive.com/api-documentation

Required env var:  PUBLISHDRIVE_API_KEY   (add to .env)
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import requests

BASE_URL = "https://api.publishdrive.com/v1"


class PublishDriveClient:
    def __init__(self):
        self.api_key = os.getenv("PUBLISHDRIVE_API_KEY", "")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(f"{BASE_URL}{path}", headers=self.headers,
                         params=params or {}, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_sales_report(self, from_date: str, to_date: str) -> dict:
        """Pull sales/royalty report. Dates: YYYY-MM-DD."""
        return self._get("/reports/sales", params={
            "dateFrom": from_date,
            "dateTo": to_date,
        })

    def get_catalog(self) -> list:
        """Return all books in the catalog with distribution status."""
        return self._get("/books")

    def get_distribution_status(self, book_id: str) -> dict:
        """Return per-store distribution status for a single title."""
        return self._get(f"/books/{book_id}/distribution")

    def update_metadata(self, book_id: str, payload: dict) -> dict:
        """Push metadata update (price, description, categories) to all stores."""
        r = requests.patch(
            f"{BASE_URL}/books/{book_id}",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    # ── Convenience wrappers ─────────────────────────────────────────────────

    def get_last_30_days(self) -> dict:
        to_date   = datetime.today().strftime("%Y-%m-%d")
        from_date = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        return self.get_sales_report(from_date, to_date)

    def get_this_month(self) -> dict:
        today = datetime.today()
        from_date = today.replace(day=1).strftime("%Y-%m-%d")
        to_date   = today.strftime("%Y-%m-%d")
        return self.get_sales_report(from_date, to_date)
```

---

### 3.3 `services/kdp_csv_parser.py`

```python
"""
KDP Sales Report CSV parser for Sentinel AI.

KDP has no public API. You download reports manually from:
  KDP Dashboard → Reports → Sales Dashboard → Download

Drop the CSV into:   data/kdp_reports/

This parser watches that folder, ingests new files, and stores rows
in the manuscript_kdp_sales table, deduplicating by filename.
"""

import csv
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from services.database import DB_PATH

KDP_REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "kdp_reports"
KDP_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


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
            continue  # already ingested

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
```

---

## 4. Database Schema — Add to `database.py`

Append to the `SCHEMA` string inside `database.py` (after the existing `settings` table):

```python
# ── Manuscript / publishing tables ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS manuscript_metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at    TEXT NOT NULL,
    source        TEXT NOT NULL,          -- 'publishdrive' | 'kdp'
    period_from   TEXT,
    period_to     TEXT,
    total_units   INTEGER NOT NULL DEFAULT 0,
    total_revenue REAL    NOT NULL DEFAULT 0.0,
    currency      TEXT    NOT NULL DEFAULT 'USD',
    raw_json      TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS manuscript_kdp_ingested (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    filename            TEXT NOT NULL UNIQUE,
    ingested_at         TEXT NOT NULL,
    total_units         INTEGER NOT NULL DEFAULT 0,
    total_royalties_usd REAL    NOT NULL DEFAULT 0.0,
    kenp_pages_read     INTEGER NOT NULL DEFAULT 0,
    raw_summary_json    TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS manuscript_todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    title       TEXT NOT NULL,
    platform    TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',   -- pending | done | blocked
    priority    TEXT NOT NULL DEFAULT 'normal',    -- low | normal | high
    due_date    TEXT,
    notes       TEXT NOT NULL DEFAULT ''
);
```

No migration script needed since `CREATE TABLE IF NOT EXISTS` is idempotent — the tables appear on next app start.

---

## 5. Config Changes

### 5.1 `config/agents.json` — add to the `"agents"` array

```json
{
  "name": "manuscript",
  "type": "agent",
  "label": "Manuscript",
  "enabled": true,
  "version": "1.0",
  "allowed_providers": ["anthropic", "openai", "deepseek", "gemini"],
  "allowed_tools": ["General Chat", "Summarize"],
  "budget_limit_eur": 2.0,
  "requires_approval": false,
  "description": "Book publishing metrics, platform distribution tracking, and todo management.",
  "log_path": "data/logs/runs.jsonl"
}
```

### 5.2 `config/registry.json` — add to the `"agents"` array

Same structure as existing entries. Copy the `author` entry and change `name` to `"manuscript"` and `description` accordingly.

### 5.3 `.env` — add API key

```
PUBLISHDRIVE_API_KEY=your_key_here
```

---

## 6. `main.py` Changes

There are **five places** to edit in `main.py`. They follow the exact pattern used by every other custom agent.

### 6.1 Import (top of file, ~line 47)
```python
from agents.manuscript_agent import ManuscriptAgent
```

### 6.2 Agent instance (inside `__init__`, ~line 365, where agent dict is built)
```python
"manuscript": ManuscriptAgent(),
```

### 6.3 Left panel — Creative group (~line 1563)

The Creative group currently reads:
```python
("Creative", ["author", "music", "webdesign", "audiobook"], False),
```
Change to:
```python
("Creative", ["author", "manuscript", "music", "webdesign", "audiobook"], False),
```

### 6.4 Panel label & subtitle (~lines 1545–1552)

In the `agent_titles` and `agent_subtitles` dicts inside `update_agent_ui`:
```python
# agent_titles
"manuscript": "PUBLISHER",

# agent_subtitles
"manuscript": "Sales metrics, platform distribution status, and publishing todo tracker.",
```

### 6.5 Panel build and visibility (inside `build_center_panel` and `update_agent_ui`)

**In `build_center_panel`** (after `self.build_author_panel()`, ~line 1961):
```python
self.build_manuscript_panel()
center_layout.addWidget(self.manuscript_panel)
```

**In `update_agent_ui`** — add the boolean flag alongside the others (~line 8679):
```python
is_manuscript = agent_name == "manuscript"
```

Add it to the `is_custom` OR chain:
```python
is_custom = (is_audiobook or is_manager or ... or is_manuscript)
```

Add visibility line alongside the others:
```python
self.manuscript_panel.setVisible(is_manuscript)
```

---

## 7. The Panel — `build_manuscript_panel()`

Add this method to `MainWindow` in `main.py`. It follows the same pattern as `build_health_panel` (simple layout, no complex splitter needed for v1).

```python
def build_manuscript_panel(self):
    self.manuscript_panel = QWidget()
    self.manuscript_panel.setObjectName("ManuscriptPanel")
    layout = QVBoxLayout(self.manuscript_panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    # ── Top bar: period selector + refresh button ─────────────────────────
    top_bar = QWidget()
    tb = QHBoxLayout(top_bar)
    tb.setContentsMargins(4, 4, 4, 4)
    tb.setSpacing(8)

    tb.addWidget(QLabel("Period:"))
    self.manuscript_period_box = QComboBox()
    self.manuscript_period_box.addItems(["Last 30 days", "This month", "Last 7 days", "All time"])
    tb.addWidget(self.manuscript_period_box)

    self.manuscript_refresh_btn = QPushButton("⟳  Refresh Data")
    self.manuscript_refresh_btn.clicked.connect(self.manuscript_refresh)
    tb.addWidget(self.manuscript_refresh_btn)

    self.manuscript_ingest_btn = QPushButton("📥  Ingest KDP CSV")
    self.manuscript_ingest_btn.clicked.connect(self.manuscript_ingest_kdp)
    tb.addWidget(self.manuscript_ingest_btn)

    tb.addStretch()
    layout.addWidget(top_bar)

    # ── Main area: metrics display + query box ───────────────────────────
    splitter = QSplitter(Qt.Horizontal)

    # Left: metrics summary display
    self.manuscript_metrics_box = QTextBrowser()
    self.manuscript_metrics_box.setPlaceholderText("Click Refresh Data to load publishing metrics…")
    splitter.addWidget(self.manuscript_metrics_box)

    # Right: Q&A sidebar
    sidebar = QWidget()
    sb = QVBoxLayout(sidebar)
    sb.setContentsMargins(8, 4, 4, 4)
    sb.setSpacing(6)
    sidebar.setMinimumWidth(220)
    sidebar.setMaximumWidth(280)

    sb.addWidget(QLabel("Ask about your book:"))
    self.manuscript_query_input = QTextEdit()
    self.manuscript_query_input.setPlaceholderText(
        "e.g. What did I earn this month?\nWhich platform is performing best?"
    )
    self.manuscript_query_input.setFixedHeight(90)
    sb.addWidget(self.manuscript_query_input)

    sb.addWidget(QLabel("Provider:"))
    self.manuscript_provider_box = QComboBox()
    self.manuscript_provider_box.addItems(["anthropic", "openai", "deepseek", "gemini"])
    sb.addWidget(self.manuscript_provider_box)

    self.manuscript_ask_btn = QPushButton("💬  Ask")
    self.manuscript_ask_btn.setMinimumHeight(34)
    self.manuscript_ask_btn.clicked.connect(self.manuscript_ask)
    sb.addWidget(self.manuscript_ask_btn)

    sb.addStretch()

    # Todos section
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet("color: #444;")
    sb.addWidget(sep)

    sb.addWidget(QLabel("Publishing Todos:"))
    self.manuscript_todo_list = QListWidget()
    self.manuscript_todo_list.setMinimumHeight(120)
    sb.addWidget(self.manuscript_todo_list)

    self.manuscript_todo_input = QLineEdit()
    self.manuscript_todo_input.setPlaceholderText("Add todo…")
    sb.addWidget(self.manuscript_todo_input)

    todo_btn_row = QHBoxLayout()
    self.manuscript_add_todo_btn = QPushButton("Add")
    self.manuscript_add_todo_btn.clicked.connect(self.manuscript_add_todo)
    self.manuscript_done_todo_btn = QPushButton("Done")
    self.manuscript_done_todo_btn.clicked.connect(self.manuscript_mark_todo_done)
    todo_btn_row.addWidget(self.manuscript_add_todo_btn)
    todo_btn_row.addWidget(self.manuscript_done_todo_btn)
    sb.addLayout(todo_btn_row)

    splitter.addWidget(sidebar)
    layout.addWidget(splitter, 1)

    # Status bar
    self.manuscript_status_label = QLabel("")
    self.manuscript_status_label.setStyleSheet("font-size: 12px; color: #888; padding: 2px 4px;")
    layout.addWidget(self.manuscript_status_label)

    self.manuscript_panel.hide()
```

---

## 8. Handler Methods to Add

Add these methods to `MainWindow` (alongside `author_write`, `author_save`, etc.):

```python
def manuscript_refresh(self):
    """Fetch PublishDrive data and display summary."""
    from services.publishdrive_client import PublishDriveClient
    import json
    self.manuscript_status_label.setText("[Fetching…]")
    try:
        client = PublishDriveClient()
        data = client.get_last_30_days()
        self.manuscript_metrics_box.setPlainText(json.dumps(data, indent=2))
        self.manuscript_status_label.setText("[Done] Data refreshed.")
        self._manuscript_last_data = json.dumps(data)
    except Exception as e:
        self.manuscript_status_label.setText(f"[Error] {e}")

def manuscript_ingest_kdp(self):
    """Ingest any new KDP CSV files from data/kdp_reports/."""
    from services.kdp_csv_parser import ingest_new_reports
    ingested = ingest_new_reports()
    if ingested:
        self.manuscript_status_label.setText(f"[Done] Ingested: {', '.join(ingested)}")
    else:
        self.manuscript_status_label.setText("[Info] No new KDP reports found.")

def manuscript_ask(self):
    """Send a query to ManuscriptAgent with current data as context."""
    query = self.manuscript_query_input.toPlainText().strip()
    if not query:
        return
    agent = self.agents.get("manuscript")
    context = getattr(self, "_manuscript_last_data", "")
    messages = agent.build_messages(query, context_json=context)
    provider = self.manuscript_provider_box.currentText()
    self.manuscript_status_label.setText("[Thinking…]")
    # Re-use the existing ChatWorker pattern:
    # worker = ChatWorker(messages, provider, model, ...)
    # wire token_signal → append to manuscript_metrics_box, etc.
    # (Follow the exact same pattern as author_write → self.author_worker)

def manuscript_add_todo(self):
    title = self.manuscript_todo_input.text().strip()
    if not title:
        return
    import sqlite3, json
    from services.database import DB_PATH
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO manuscript_todos (created_at, updated_at, title) VALUES (?, ?, ?)",
        (now, now, title)
    )
    conn.commit()
    conn.close()
    self.manuscript_todo_input.clear()
    self._load_manuscript_todos()

def manuscript_mark_todo_done(self):
    item = self.manuscript_todo_list.currentItem()
    if not item:
        return
    todo_id = item.data(Qt.UserRole)
    import sqlite3
    from services.database import DB_PATH
    from datetime import datetime
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE manuscript_todos SET status='done', updated_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), todo_id)
    )
    conn.commit()
    conn.close()
    self._load_manuscript_todos()

def _load_manuscript_todos(self):
    import sqlite3
    from services.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, title, status FROM manuscript_todos ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    self.manuscript_todo_list.clear()
    for row_id, title, status in rows:
        label = f"✅ {title}" if status == "done" else f"○ {title}"
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, row_id)
        self.manuscript_todo_list.addItem(item)
```

Call `self._load_manuscript_todos()` inside `update_agent_ui` when `is_manuscript` is true (same place `refresh_audiobook_books()` is called for audiobook).

---

## 9. Environment Setup

```bash
# No new pip packages needed — requests is already in requirements.txt.
# Just add the API key:
echo "PUBLISHDRIVE_API_KEY=your_key_here" >> lab/sentinel_ai/.env

# Create KDP drop folder:
mkdir -p lab/sentinel_ai/data/kdp_reports
```

---

## 10. Pre-built Publishing Todos (seed data)

On first run, optionally seed `manuscript_todos` with the standard publishing checklist:

```python
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
```

Add a `manuscript_seed_todos()` function to `kdp_csv_parser.py` or a new `manuscript_setup.py` and call it once on first panel activation (check if todos table is empty).

---

## 11. PublishDrive API — Getting Started

1. Sign up at publishdrive.com → Settings → API → Generate token
2. Add token to `.env` as `PUBLISHDRIVE_API_KEY`
3. Upload the book first via PublishDrive's web UI (no API upload for initial submission — same as KDP)
4. Once the book has a `book_id`, all metadata + pricing updates can be scripted via `publishdrive_client.py`

Base URL: `https://api.publishdrive.com/v1`
Auth: `Authorization: Bearer <token>` header
Rate limit: 60 req/min (standard tier)

---

## 12. KDP CSV Reports — How to Get Them

1. Log into kdp.amazon.com
2. Go to **Reports → Sales Dashboard**
3. Select a date range → click **Download** (saves as `.csv`)
4. Drop the file into `lab/sentinel_ai/data/kdp_reports/`
5. Click **Ingest KDP CSV** in the Manuscript panel — the parser deduplicates by filename so you can drop multiple reports safely

Column names in KDP reports vary slightly by report type (Summary vs. Detail). The parser reads whichever columns are present and skips missing ones gracefully.

---

## 13. Recommended Build Order

1. `services/publishdrive_client.py` — no UI dependency, testable in isolation
2. `services/kdp_csv_parser.py` — same
3. DB schema additions in `database.py` — run once, tables appear
4. `agents/manuscript_agent.py` — pure Python, no UI
5. `config/agents.json` + `config/registry.json` — config edits
6. `main.py` — import, agent dict, left panel group, titles/subtitles, panel build, update_agent_ui flags, handler methods
7. Test: activate Manuscript panel, click Refresh Data, drop a KDP CSV, add a todo

---

## 14. What's NOT Included (Future Work)

- **Scheduled auto-refresh**: use the existing `QTimer` pattern (see how resource_monitor uses it) to poll PublishDrive every N hours and write to `manuscript_metrics`
- **Price sync script**: `publishdrive_client.update_metadata()` is already wired — add a UI form to push price changes
- **Multi-book support**: current design assumes one primary title. Add a `book_id` selector to support multiple books
- **Goodreads / Storygraph ratings scrape**: no API, would need requests + BeautifulSoup (already in requirements)
- **Revenue chart**: use the existing `QTextBrowser` for now; upgrade to a matplotlib embed (same pattern as investment_agent) once data is flowing

---

_End of handover. All code above matches Sentinel AI's existing patterns: PySide6 UI, SQLite via `services/database.py`, agents as classes with `build_messages()`, `.env` for secrets, `requirements.txt` already has all needed packages._
