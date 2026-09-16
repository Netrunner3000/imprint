"""Earnings UI must visualize observed numbers without merging evidence types."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_empty_dashboard_explains_how_to_get_observations(app):
    from ui.creator_earnings import CreatorEarningsView

    view = CreatorEarningsView()
    assert "No earnings imported" in view.empty_note.text()
    assert view.price_table.rowCount() == 0
    assert view.chart._points == []


def test_dashboard_keeps_statement_net_and_post_revenue_separate(app):
    from PySide6.QtWidgets import QLabel
    from ui.creator_earnings import CreatorEarningsView

    view = CreatorEarningsView()
    view.set_data(
        {"net": 120, "attributed": 35, "subscribers": 10, "posted": 2},
        [{"price_usd": 12, "sends": 2, "total": 35, "average": 17.5}],
        [{"title": "Sample post", "kind": "ppv", "revenue_usd": 35}],
        [{"source_file": "report.csv", "period_from": "2026-08-01",
          "period_to": "2026-08-31", "gross_usd": 140, "net_usd": 120,
          "subscribers": 10}],
        outcomes=[{"title": "Sample post", "campaign": "Launch", "channel": "X",
                   "reach": 100, "clicks": 8, "subscriptions": 1,
                   "ppv_purchases": 1, "revenue_usd": 35,
                   "attributable_cost_usd": 10, "metric_source": "export",
                   "metric_window": "week 1", "generation_cost_eur": 0.04}],
        hooks=[{"body": "A clear hook", "title": "Sample post", "revenue_usd": 35}],
    )

    assert view.net_metric.findChild(QLabel, "CreatorEarningsValue").text() == "$120.00"
    assert view.attributed_metric.findChild(QLabel, "CreatorEarningsValue").text() == "$35.00"
    assert len(view.chart._points) == 1
    assert view.price_table.item(0, 4).text() == "Few offers · anecdotal"
    assert view.content_table.item(0, 0).text() == "Sample post"
    assert view.statement_table.item(0, 0).text() == "report.csv"
    assert view.outcome_table.item(0, 5).text() == "+250%"
    assert "Source: export" in view.outcome_table.item(0, 0).toolTip()
    assert view.hook_table.item(0, 0).text() == "A clear hook"
    assert "not added" in view.findChild(QLabel, "CreatorEarningsNote").text()
