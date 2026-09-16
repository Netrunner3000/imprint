"""Golden checks for local Income Lab worksheets."""

import pytest

from services.income_lab import (
    automation_payback, break_even, compare_variants, contribution, funnel,
    recurring_cohort, wilson_interval, workflow_cost,
)


def test_contribution_separates_cash_from_owner_time():
    result = contribution(
        revenue=540, refunds=30, fees=54, ai_media=12, fulfilment=45,
        owner_hours=7.5, hourly_value=30, accepted_outputs=3)
    assert result["cash_contribution"] == pytest.approx(399)
    assert result["economic_contribution"] == pytest.approx(174)
    assert result["cash_margin"] == pytest.approx(399 / 540)


def test_break_even_withholds_units_when_unit_is_negative():
    assert break_even(price=100, fee_rate=.1, variable_cost=20,
                      acquisition_cost=30, fixed_cost=500)["break_even_units"] == 13
    assert break_even(price=10, variable_cost=11,
                      fixed_cost=100)["break_even_units"] is None


def test_wilson_and_funnel_keep_raw_counts():
    low, high = wilson_interval(12, 200)
    assert low < .06 < high
    stages = funnel([("visits", 200), ("signups", 12), ("sales", 3)])
    assert stages[0]["events"] == 12 and stages[0]["total"] == 200
    assert stages[1]["rate"] == pytest.approx(.25)


def test_variant_comparison_does_not_declare_a_winner():
    result = compare_variants(
        baseline_events=8, baseline_total=200,
        variant_events=12, variant_total=200, minimum_effect=.02)
    assert result["absolute_difference"] == pytest.approx(.02)
    assert result["decision"] == "repeat"


def test_cohort_refuses_to_project_ltv():
    result = recurring_cohort(
        starts=20, retained=[15, 11, 9], collected_receipts=500,
        refunds=25, variable_costs=100)
    assert result["retention_rates"] == [.75, .55, .45]
    assert result["projected_ltv"] is None


def test_workflow_cost_includes_retry_correction_and_acceptance():
    result = workflow_cost(
        base_api_cost=2, retry_rate=.2, retry_cost=2,
        correction_minutes=12, hourly_value=30, acceptance_rate=.8)
    assert result["expected_cost_per_attempt"] == pytest.approx(8.4)
    assert result["effective_cost_per_accepted_output"] == pytest.approx(10.5)


def test_automation_payback_is_blocked_until_safety_gates_pass():
    blocked = automation_payback(
        build_hours=20, hourly_value=40, direct_tool_cost=100,
        minutes_saved_per_run=12, runs_per_period=50,
        exception_rate=.1, exception_minutes=30)
    assert blocked["payback_periods"] is None
    assert not blocked["promotion_allowed"]
    passed = automation_payback(
        build_hours=20, hourly_value=40, direct_tool_cost=100,
        minutes_saved_per_run=12, runs_per_period=50,
        exception_rate=.1, exception_minutes=30,
        quality_gate_passed=True, rollback_tested=True)
    assert passed["payback_periods"] == pytest.approx(3)


@pytest.mark.parametrize("kwargs", [
    {"events": -1, "total": 10},
    {"events": 11, "total": 10},
    {"events": 0, "total": 0},
])
def test_invalid_rates_are_refused(kwargs):
    with pytest.raises(ValueError):
        wilson_interval(**kwargs)


def test_interactive_worksheet_dialog_exposes_all_seven_tools(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog, QTabWidget
    from ui.income_worksheets import show_income_worksheets

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QDialog, "exec", lambda self: None)
    dialog = show_income_worksheets(start="funnel")
    tabs = dialog.findChild(QTabWidget, "WorksheetTabs")
    assert tabs is not None and tabs.count() == 7
    assert tabs.tabText(tabs.currentIndex()) == "Funnel"
