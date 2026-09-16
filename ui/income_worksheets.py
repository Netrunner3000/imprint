"""Interactive, local worksheets for the Learning Centre Income Lab."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from services.income_lab import (
    automation_payback, break_even, compare_variants, contribution, funnel,
    recurring_cohort, workflow_cost,
)
from ui.style import (
    ACCENT, ACCENT_LINE, ACCENT_WASH, BG, BORDER, ELEVATED, SURFACE, SUNKEN,
    TEXT, TEXT_DIM, TEXT_MUTE,
)


def _number(value: str, label: str) -> float:
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be a number") from exc


def _integer(value: str, label: str) -> int:
    number = _number(value, label)
    if not number.is_integer():
        raise ValueError(f"{label} must be a whole number")
    return int(number)


def _percent(value: str, label: str) -> float:
    return _number(value, label) / 100


def _money(value: float | int | None) -> str:
    return "Unavailable" if value is None else f"{value:,.2f}"


def _rate(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value * 100:.2f}%"


class IncomeWorksheetsDialog(QDialog):
    """Seven calculators that never fetch, predict, or silently fill data."""

    def __init__(self, parent=None, start: str = "contribution"):
        super().__init__(parent)
        self.setObjectName("IncomeWorksheetsDialog")
        self.setWindowTitle("Income Lab worksheets · Imprint")
        self.setMinimumSize(880, 650)
        self.resize(1040, 760)
        self.setAccessibleName("Income Lab interactive worksheets")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)
        title = QLabel("Income Lab worksheets")
        title.setObjectName("WorksheetTitle")
        outer.addWidget(title)
        note = QLabel(
            "Enter owned observations or explicitly hypothetical scenarios. "
            "These tools calculate; they do not forecast. Keep source, period, "
            "population, currency, and evidence label with every result.")
        note.setObjectName("WorksheetNote")
        note.setWordWrap(True)
        outer.addWidget(note)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("WorksheetTabs")
        outer.addWidget(self.tabs, 1)
        self._add_contribution()
        self._add_break_even()
        self._add_funnel()
        self._add_variant()
        self._add_cohort()
        self._add_workflow()
        self._add_automation()

        actions = QHBoxLayout()
        actions.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        outer.addLayout(actions)

        labels = [self.tabs.tabText(index).casefold()
                  for index in range(self.tabs.count())]
        target = start.replace("-", " ").casefold()
        index = next((i for i, label in enumerate(labels)
                      if target in label or label in target), 0)
        self.tabs.setCurrentIndex(index)

        self.setStyleSheet(f"""
            QDialog#IncomeWorksheetsDialog {{ background: {BG}; }}
            QLabel#WorksheetTitle {{ color: {TEXT}; font-size: 23px; font-weight: 700; }}
            QLabel#WorksheetNote {{ color: {TEXT_DIM}; background: {ACCENT_WASH};
                border: 1px solid {ACCENT_LINE}; border-radius: 8px; padding: 10px 12px; }}
            QWidget#WorksheetPage, QWidget#WorksheetForm {{ background: {SURFACE}; }}
            QLabel {{ color: {TEXT_DIM}; background: transparent; }}
            QLabel#WorksheetIntro {{ color: {TEXT_DIM}; font-size: 13px; }}
            QTabWidget#WorksheetTabs::pane {{ background: {SURFACE};
                border: 1px solid {BORDER}; border-radius: 8px; top: -1px; }}
            QTabBar::tab {{ background: {BG}; color: {TEXT_DIM};
                border: 1px solid {BORDER}; border-bottom: none;
                padding: 9px 13px; min-width: 76px; }}
            QTabBar::tab:first {{ border-top-left-radius: 7px; }}
            QTabBar::tab:last {{ border-top-right-radius: 7px; }}
            QTabBar::tab:selected {{ color: {ACCENT}; background: {SURFACE};
                border-bottom: 2px solid {ACCENT}; }}
            QTabBar::tab:hover:!selected {{ color: {TEXT}; background: {ELEVATED}; }}
            QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
                background: {SURFACE}; border: none; }}
            QLineEdit {{ background: {SUNKEN}; color: {TEXT}; border: 1px solid {BORDER};
                border-radius: 7px; padding: 8px 10px; min-height: 20px; }}
            QTextBrowser#WorksheetOutput {{ background: {SUNKEN}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px; padding: 10px; }}
            QPushButton {{ background: {ELEVATED}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 7px; padding: 8px 14px; }}
            QPushButton:hover {{ border: 1px solid {ACCENT_LINE}; }}
            QPushButton#PrimaryAction {{ background: {ACCENT}; color: {BG};
                border: 1px solid {ACCENT}; font-weight: 650; }}
            QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {TEXT_MUTE};
                border-radius: 4px; min-height: 34px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def _worksheet(self, title: str, intro: str,
                   fields: list[tuple[str, str, str]],
                   calculate: Callable[[dict[str, str]], list[tuple[str, str]]]) -> None:
        page = QWidget()
        page.setObjectName("WorksheetPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        intro_label = QLabel(intro)
        intro_label.setObjectName("WorksheetIntro")
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        form_widget = QWidget()
        form_widget.setObjectName("WorksheetForm")
        form = QFormLayout(form_widget)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        inputs: dict[str, QLineEdit] = {}
        for key, label, default in fields:
            edit = QLineEdit(default)
            edit.setAccessibleName(label)
            form.addRow(label, edit)
            inputs[key] = edit
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.NoFrame)
        area.setWidget(form_widget)
        layout.addWidget(area, 2)

        button = QPushButton("Calculate")
        button.setObjectName("PrimaryAction")
        layout.addWidget(button, 0, Qt.AlignLeft)
        output = QTextBrowser()
        output.setObjectName("WorksheetOutput")
        output.setAccessibleName(f"{title} result")
        output.setMinimumHeight(145)
        layout.addWidget(output, 1)

        def run() -> None:
            raw = {key: edit.text() for key, edit in inputs.items()}
            try:
                rows = calculate(raw)
            except ValueError as exc:
                output.setHtml(f"<b>Cannot calculate</b><p>{exc}</p>")
                return
            body = "".join(
                f"<tr><td>{label}</td><td><b>{value}</b></td></tr>"
                for label, value in rows)
            output.setHtml(
                "<p><b>Calculated description — not a forecast</b></p>"
                f"<table cellspacing='8'>{body}</table>")

        button.clicked.connect(run)
        self.tabs.addTab(page, title)

    def _add_contribution(self) -> None:
        fields = [
            ("revenue", "Collected revenue", "540"), ("refunds", "Refunds", "30"),
            ("fees", "Platform/payment fees", "54"), ("ai", "AI/media cost", "12"),
            ("fulfilment", "Direct fulfilment", "45"),
            ("acquisition", "Paid acquisition", "0"),
            ("contractors", "Contractors", "0"), ("hours", "Owner hours", "7.5"),
            ("hourly", "Owner hourly value", "30"),
            ("accepted", "Accepted outputs", "3"),
        ]
        def calc(v):
            r = contribution(
                revenue=_number(v["revenue"], "Collected revenue"),
                refunds=_number(v["refunds"], "Refunds"), fees=_number(v["fees"], "Fees"),
                ai_media=_number(v["ai"], "AI/media cost"),
                fulfilment=_number(v["fulfilment"], "Direct fulfilment"),
                acquisition=_number(v["acquisition"], "Paid acquisition"),
                contractors=_number(v["contractors"], "Contractors"),
                owner_hours=_number(v["hours"], "Owner hours"),
                hourly_value=_number(v["hourly"], "Hourly value"),
                accepted_outputs=_number(v["accepted"], "Accepted outputs"))
            return [("Cash contribution", _money(r["cash_contribution"])),
                    ("Economic contribution", _money(r["economic_contribution"])),
                    ("Cash contribution margin", _rate(r["cash_margin"])),
                    ("Cash contribution / owner hour", _money(r["cash_contribution_per_hour"])),
                    ("Effective cost / accepted output", _money(r["effective_cost_per_accepted_output"]))]
        self._worksheet("Contribution", "Use one currency and matching period. Include failures and correction time.", fields, calc)

    def _add_break_even(self) -> None:
        fields = [("price", "Price", "100"), ("fee", "Fee rate (%)", "10"),
                  ("variable", "Other variable cost / unit", "20"),
                  ("acquisition", "Acquisition cost / unit", "30"),
                  ("fixed", "Fixed test/build cost", "500")]
        def calc(v):
            r = break_even(price=_number(v["price"], "Price"),
                           fee_rate=_percent(v["fee"], "Fee rate"),
                           variable_cost=_number(v["variable"], "Variable cost"),
                           acquisition_cost=_number(v["acquisition"], "Acquisition cost"),
                           fixed_cost=_number(v["fixed"], "Fixed cost"))
            return [("Unit contribution", _money(r["unit_contribution"])),
                    ("Maximum CAC at zero margin", _money(r["maximum_acquisition_cost_at_zero_margin"])),
                    ("Break-even units", str(r["break_even_units"] or "Unavailable"))]
        self._worksheet("Break-even", "A scenario threshold, not a sales prediction.", fields, calc)

    def _add_funnel(self) -> None:
        fields = [("names", "Stage names (comma-separated)", "Visits,Signups,Sales"),
                  ("counts", "Raw counts (comma-separated)", "200,12,3")]
        def calc(v):
            names = [item.strip() for item in v["names"].split(",") if item.strip()]
            counts = [_integer(item, "Stage count")
                      for item in v["counts"].split(",") if item.strip()]
            if len(names) != len(counts):
                raise ValueError("Stage names and counts must have the same length")
            rows = []
            for stage in funnel(list(zip(names, counts))):
                low, high = stage["interval"]
                rows.append((f"{stage['from']} → {stage['to']}",
                             f"{stage['events']}/{stage['total']} = {_rate(stage['rate'])} "
                             f"(95% interval {_rate(low)}–{_rate(high)})"))
            return rows
        self._worksheet("Funnel", "Counts must describe the same eligible cohort and decrease through stages.", fields, calc)

    def _add_variant(self) -> None:
        fields = [("be", "Baseline events", "8"), ("bt", "Baseline eligible total", "200"),
                  ("ve", "Variant events", "12"), ("vt", "Variant eligible total", "200"),
                  ("effect", "Minimum meaningful change (%)", "2")]
        def calc(v):
            r = compare_variants(
                baseline_events=_integer(v["be"], "Baseline events"),
                baseline_total=_integer(v["bt"], "Baseline total"),
                variant_events=_integer(v["ve"], "Variant events"),
                variant_total=_integer(v["vt"], "Variant total"),
                minimum_effect=_percent(v["effect"], "Minimum effect"))
            return [("Baseline", _rate(r["baseline_rate"])),
                    ("Variant", _rate(r["variant_rate"])),
                    ("Observed absolute difference", _rate(r["absolute_difference"])),
                    ("Minimum effect reached observationally", "Yes" if r["meets_minimum_observed_effect"] else "No"),
                    ("Default next decision", "Repeat; do not declare a winner from this worksheet alone")]
        self._worksheet("Variant comparison", "Use comparable allocation. Intervals do not repair biased or confounded samples.", fields, calc)

    def _add_cohort(self) -> None:
        fields = [("starts", "Cohort starts", "20"),
                  ("retained", "Retained by period (comma-separated)", "15,11,9"),
                  ("receipts", "Collected receipts", "500"),
                  ("refunds", "Refunds", "25"),
                  ("costs", "Matching variable costs", "100")]
        def calc(v):
            retained = [_integer(item, "Retained count") for item in v["retained"].split(",")]
            r = recurring_cohort(
                starts=_integer(v["starts"], "Cohort starts"), retained=retained,
                collected_receipts=_number(v["receipts"], "Receipts"),
                refunds=_number(v["refunds"], "Refunds"),
                variable_costs=_number(v["costs"], "Variable costs"))
            rows = [(f"Retention period {i + 1}", _rate(rate))
                    for i, rate in enumerate(r["retention_rates"])]
            return rows + [("Observed cash contribution", _money(r["cash_contribution"])),
                           ("Projected LTV", "Unavailable — mature observed cohorts required")]
        self._worksheet("Recurring cohort", "Use starts and retained buyers from the same cohort; current subscriber count is not retention.", fields, calc)

    def _add_workflow(self) -> None:
        fields = [("api", "Base API/media cost", "2"),
                  ("retry_rate", "Retry rate (%)", "20"),
                  ("retry_cost", "Cost per retry", "2"),
                  ("minutes", "Correction minutes / attempt", "12"),
                  ("hourly", "Hourly value", "30"),
                  ("acceptance", "Acceptance rate (%)", "80")]
        def calc(v):
            r = workflow_cost(
                base_api_cost=_number(v["api"], "API/media cost"),
                retry_rate=_percent(v["retry_rate"], "Retry rate"),
                retry_cost=_number(v["retry_cost"], "Retry cost"),
                correction_minutes=_number(v["minutes"], "Correction minutes"),
                hourly_value=_number(v["hourly"], "Hourly value"),
                acceptance_rate=_percent(v["acceptance"], "Acceptance rate"))
            return [("Expected cost / attempt", _money(r["expected_cost_per_attempt"])),
                    ("Effective cost / accepted output", _money(r["effective_cost_per_accepted_output"]))]
        self._worksheet("Workflow cost", "Compare routes on accepted output, not token or request price alone.", fields, calc)

    def _add_automation(self) -> None:
        fields = [("hours", "Build hours", "20"), ("hourly", "Hourly value", "40"),
                  ("tool", "Direct tool cost", "100"),
                  ("maintenance", "Maintenance / period", "0"),
                  ("saved", "Minutes saved / run", "12"),
                  ("runs", "Runs / period", "50"),
                  ("exception_rate", "Exception rate (%)", "10"),
                  ("exception_minutes", "Recovery minutes / exception", "30"),
                  ("quality", "Quality gate passed? (yes/no)", "no"),
                  ("rollback", "Rollback tested? (yes/no)", "no")]
        def yes(value): return value.strip().casefold() in {"yes", "y", "true", "1"}
        def calc(v):
            r = automation_payback(
                build_hours=_number(v["hours"], "Build hours"),
                hourly_value=_number(v["hourly"], "Hourly value"),
                direct_tool_cost=_number(v["tool"], "Tool cost"),
                maintenance_per_period=_number(v["maintenance"], "Maintenance"),
                minutes_saved_per_run=_number(v["saved"], "Minutes saved"),
                runs_per_period=_number(v["runs"], "Runs"),
                exception_rate=_percent(v["exception_rate"], "Exception rate"),
                exception_minutes=_number(v["exception_minutes"], "Recovery minutes"),
                quality_gate_passed=yes(v["quality"]), rollback_tested=yes(v["rollback"]))
            return [("Build cost", _money(r["build_cost"])),
                    ("Net hours saved / period", _money(r["net_hours_saved_per_period"])),
                    ("Net value / period", _money(r["net_value_per_period"])),
                    ("Payback periods", _money(r["payback_periods"])),
                    ("Promotion allowed", "Yes" if r["promotion_allowed"] else f"No — {r['blocked_reason']}")]
        self._worksheet("Automation payback", "Payback is withheld until quality and rollback gates pass.", fields, calc)


def show_income_worksheets(parent=None, start: str = "contribution") -> QDialog:
    dialog = IncomeWorksheetsDialog(parent, start)
    dialog.exec()
    return dialog
