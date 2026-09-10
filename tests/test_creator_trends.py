"""Creator trend normalization, scoring, fallbacks and dashboard wiring."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.creator_trends import (
    Trend, campaign_context, filter_trends, format_creator_brief, load_trends,
)


def trend(**changes):
    values = dict(
        name="Test signal", category="Format", geography="Global",
        momentum=70, search_interest=80, saturation=30, monetization=75,
        format="short video", pricing_idea="bundle", source="Test adapter",
        observed_at="2026-09-09T10:00+00:00", risk="Low",
        history=(40, 50, 70), confidence="indicative")
    values.update(changes)
    return Trend(**values)


def test_opportunity_rewards_demand_and_low_saturation():
    strong = trend(search_interest=90, saturation=20)
    weak = trend(search_interest=20, saturation=90)
    assert strong.opportunity > weak.opportunity
    assert 0 <= strong.opportunity <= 100


def test_high_risk_is_penalized_but_not_hidden():
    low = trend(risk="Low")
    high = trend(risk="High")
    assert high.opportunity < low.opportunity


def test_adapter_failure_does_not_break_the_feed():
    class Broken:
        def fetch(self, geography, window):
            raise RuntimeError("source unavailable")

    rows, sample = load_trends(adapters=[Broken()])
    assert sample is True
    assert rows
    assert {row.source for row in rows} == {"Demonstration dataset"}


def test_available_adapter_prevents_sample_data():
    class Working:
        def fetch(self, geography, window):
            return [trend(geography=geography)]

    rows, sample = load_trends("Europe", adapters=[Working()])
    assert sample is False
    assert rows[0].geography == "Europe"


def test_category_filter_also_ranks_opportunities():
    rows = filter_trends([
        trend(name="lower", category="A", search_interest=10),
        trend(name="other", category="B"),
        trend(name="higher", category="A", search_interest=99),
    ], "A")
    assert [row.name for row in rows] == ["higher", "lower"]


def test_campaign_handoff_is_structured_and_preserves_evidence():
    context = campaign_context(trend(), "Europe", "30 days")
    assert context["venture"] == "OnlyFans"
    assert context["platform"] == "OnlyFans"
    assert context["source"] == "Test adapter"
    assert context["observed_at"] == "2026-09-09T10:00+00:00"
    assert len(context["deliverables"]) == 4
    brief = format_creator_brief(context)
    assert "Directional indexes" in brief
    assert "not a forecast" in brief
    assert "Test adapter" in brief


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_dashboard_has_filters_charts_and_ranked_table(app):
    from ui.creator_trends import OnlyFansDashboard
    dashboard = OnlyFansDashboard()
    assert dashboard.category_box.count() > 1
    assert dashboard.geography_box.count() >= 3
    assert dashboard.window_box.count() == 3
    assert dashboard.table.rowCount() > 0
    assert dashboard.table.columnCount() == 11
    assert dashboard.velocity_chart.series
    assert dashboard.scatter_chart.trends
    assert [dashboard.sections.tabText(i)
            for i in range(dashboard.sections.count())] == [
        "Overview", "Trends & Opportunities", "Content Intelligence",
        "Monetization & Analytics", "Market & Strategy",
    ]


def test_dashboard_emits_selected_campaign_context(app):
    from ui.creator_trends import OnlyFansDashboard
    dashboard = OnlyFansDashboard()
    emitted = []
    dashboard.campaign_requested.connect(emitted.append)
    dashboard.table.selectRow(0)
    dashboard.create_campaign_btn.click()
    assert emitted
    assert emitted[0]["venture"] == "OnlyFans"
    assert emitted[0]["suggested_format"]
