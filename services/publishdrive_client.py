"""
PublishDrive REST API client for Create & Publish.
API docs: https://publishdrive.com/api-documentation

Required env var:  PUBLISHDRIVE_API_KEY   (add to .env)
"""

import os
from datetime import datetime, timedelta
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
