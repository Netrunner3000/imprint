"""Earnings CSV ingest for subscription creator accounts.

Modelled on services/kdp_csv_parser.py, and for the same reason: the platform
has no public API, so the numbers only reach the app when the user exports a
statement and imports it here.

Column names differ between platforms and change over time, so the parser
matches on substrings rather than exact headers, and records the raw row
alongside the parsed figures — a total that cannot be traced back to its source
row is not worth much when the number looks wrong.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from services.database import get_connection

# Substrings matched case-insensitively against the header, first hit wins.
_GROSS = ("gross", "amount", "total")
_NET = ("net", "payout", "earnings")
_SUBS = ("subscriber", "subs", "fans")
_FROM = ("from", "start", "period start")
_TO = ("to", "end", "period end")


def _find(header: list[str], candidates: tuple[str, ...]) -> int | None:
    lowered = [h.strip().lower() for h in header]
    for candidate in candidates:
        for index, name in enumerate(lowered):
            if candidate in name:
                return index
    return None


def _number(value: str) -> float:
    cleaned = (value or "").strip().replace("$", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_creator_csv(path: Path) -> dict:
    """Read one statement into totals plus the rows behind them."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return {"rows": 0, "gross": 0.0, "net": 0.0, "subscribers": 0,
                "period_from": "", "period_to": "", "raw": []}

    header, body = rows[0], rows[1:]
    gross_i = _find(header, _GROSS)
    net_i = _find(header, _NET)
    subs_i = _find(header, _SUBS)
    from_i = _find(header, _FROM)
    to_i = _find(header, _TO)

    gross = net = 0.0
    subscribers = 0
    period_from = period_to = ""
    for row in body:
        if not any(cell.strip() for cell in row):
            continue
        if gross_i is not None and gross_i < len(row):
            gross += _number(row[gross_i])
        if net_i is not None and net_i < len(row):
            net += _number(row[net_i])
        if subs_i is not None and subs_i < len(row):
            subscribers = max(subscribers, int(_number(row[subs_i])))
        if from_i is not None and from_i < len(row) and not period_from:
            period_from = row[from_i].strip()
        if to_i is not None and to_i < len(row):
            period_to = row[to_i].strip() or period_to

    return {
        "rows": len([r for r in body if any(c.strip() for c in r)]),
        "gross": round(gross, 2),
        "net": round(net, 2),
        "subscribers": subscribers,
        "period_from": period_from,
        "period_to": period_to,
        "raw": body[:200],
    }


def ingest_creator_csv(account_id: int, path: Path) -> dict:
    """Parse and store one statement.

    Keyed on (account_id, source_file), so importing the same export twice
    updates it rather than double-counting the revenue.
    """
    summary = parse_creator_csv(path)
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO creator_earnings
              (account_id, ingested_at, source_file, period_from, period_to,
               gross_usd, net_usd, subscribers, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(account_id, source_file) DO UPDATE SET
              ingested_at=excluded.ingested_at,
              period_from=excluded.period_from,
              period_to=excluded.period_to,
              gross_usd=excluded.gross_usd,
              net_usd=excluded.net_usd,
              subscribers=excluded.subscribers,
              raw_json=excluded.raw_json
        """, (account_id, datetime.now().isoformat(timespec="seconds"),
              path.name, summary["period_from"], summary["period_to"],
              summary["gross"], summary["net"], summary["subscribers"],
              json.dumps(summary["raw"])[:200000]))
        conn.commit()
    return summary
