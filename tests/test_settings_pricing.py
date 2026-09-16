"""Regression coverage for the complete Settings pricing catalog."""

from __future__ import annotations

import os
import sqlite3

import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _pricing_connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE pricing (
            backend TEXT NOT NULL,
            model TEXT NOT NULL,
            input_per_1m_usd REAL NOT NULL DEFAULT 0,
            output_per_1m_usd REAL NOT NULL DEFAULT 0,
            cached_input_per_1m_usd REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (backend, model)
        )
    """)
    return conn


def test_catalog_exposes_every_provider_even_when_database_only_has_anthropic():
    from services.pricing_catalog import build_token_price_catalog

    conn = _pricing_connection()
    conn.execute(
        "INSERT INTO pricing VALUES ('anthropic', 'default', 3, 15, 0)"
    )
    entries = build_token_price_catalog(conn)

    providers = {entry.provider for entry in entries}
    assert providers == {
        "openai", "anthropic", "deepseek", "kimi", "gemini", "qwen", "ollama"
    }
    assert any(entry.provider == "openai" and entry.model == "gpt-4.1" for entry in entries)
    assert any(entry.provider == "ollama" and entry.status == "Local compute" for entry in entries)


def test_unpriced_models_are_unknown_not_free():
    from services.pricing_catalog import build_token_price_catalog

    conn = _pricing_connection()
    entries = build_token_price_catalog(conn)
    openai = next(entry for entry in entries if entry.provider == "openai")
    assert openai.input_usd is None
    assert openai.output_usd is None
    assert openai.status == "Price unknown"


def test_settings_dialog_has_searchable_complete_pricing_tables(app, monkeypatch):
    from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QTableWidget, QWidget
    from services.database import init_db
    from services.registry import Registry
    from ui.dialogs import show_settings

    init_db()
    monkeypatch.setattr(QDialog, "exec", lambda self: None)

    class Host(QWidget):
        def __init__(self):
            super().__init__()
            self.registry = Registry()
            self.session_budget_eur = 1.0
            self.daily_budget_eur = 5.0

        def update_usage_labels(self): ...

    dialog = show_settings(Host())
    table = dialog.findChild(QTableWidget, "SettingsPricingTable")
    per_unit = dialog.findChild(QTableWidget, "SettingsPerUnitTable")
    provider_filter = dialog.findChild(QComboBox, "PricingProviderFilter")
    search = dialog.findChild(QLineEdit, "PricingSearch")

    assert table is not None and table.rowCount() >= 20
    assert per_unit is not None and per_unit.rowCount() >= 6
    assert search is not None
    assert {provider_filter.itemText(i) for i in range(provider_filter.count())} >= {
        "OpenAI", "Anthropic", "DeepSeek", "Kimi", "Gemini", "Qwen", "Ollama"
    }

    provider_filter.setCurrentText("OpenAI")
    shown = [row for row in range(table.rowCount()) if not table.isRowHidden(row)]
    assert shown
    assert {table.item(row, 0).text() for row in shown} == {"OpenAI"}

    search.setText("gpt-4.1")
    shown = [row for row in range(table.rowCount()) if not table.isRowHidden(row)]
    assert shown
    assert all("gpt-4.1" in table.item(row, 1).text() for row in shown)

