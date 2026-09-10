"""OnlyFans venture intelligence, with a structured handoff to Creator."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSizePolicy, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from services.creator_trends import (
    Trend, campaign_context, filter_trends, load_trends,
    onlyfans_business_metrics,
)
from ui.forms import MD, SM, field, micro, section, stat
from ui.style import ACCENT, BORDER_STRONG, INFO, SURFACE, TEXT, TEXT_DIM, TEXT_MUTE, WARNING


class Sparkline(QWidget):
    """Small dependency-free line chart for the highest-ranked trends."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series: list[tuple[str, tuple[float, ...]]] = []
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_trends(self, trends: list[Trend]) -> None:
        self.series = [(row.name, row.history) for row in trends[:4] if row.history]
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(12, 14, max(1, self.width() - 24), max(1, self.height() - 42))
        painter.setPen(QPen(QColor(BORDER_STRONG), 1))
        for fraction in (0, .5, 1):
            y = bounds.bottom() - bounds.height() * fraction
            painter.drawLine(QPointF(bounds.left(), y), QPointF(bounds.right(), y))
        colors = (ACCENT, INFO, WARNING, TEXT_DIM)
        for index, (name, values) in enumerate(self.series):
            if len(values) < 2:
                continue
            path = QPainterPath()
            for point, value in enumerate(values):
                x = bounds.left() + bounds.width() * point / (len(values) - 1)
                y = bounds.bottom() - bounds.height() * value / 100
                path.moveTo(x, y) if point == 0 else path.lineTo(x, y)
            painter.setPen(QPen(QColor(colors[index]), 2))
            painter.drawPath(path)
            painter.setPen(QColor(colors[index]))
            painter.drawText(QPointF(bounds.left() + index * bounds.width() / 4,
                                     self.height() - 10), name[:18])


class DemandSaturationChart(QWidget):
    """Scatter plot: demand upward, saturation rightward."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trends: list[Trend] = []
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_trends(self, trends: list[Trend]) -> None:
        self.trends = trends[:12]
        self.setToolTip("Higher is more demand; farther left is less saturation.")
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(30, 12, max(1, self.width() - 44), max(1, self.height() - 40))
        painter.setPen(QPen(QColor(BORDER_STRONG), 1))
        painter.drawLine(bounds.bottomLeft(), bounds.bottomRight())
        painter.drawLine(bounds.bottomLeft(), bounds.topLeft())
        painter.setPen(QColor(TEXT_MUTE))
        painter.drawText(2, 18, "Demand")
        painter.drawText(int(bounds.right() - 62), self.height() - 8, "Saturation")
        for row in self.trends:
            x = bounds.left() + bounds.width() * row.saturation / 100
            y = bounds.bottom() - bounds.height() * row.search_interest / 100
            color = WARNING if row.risk != "Low" else ACCENT
            radius = 4 + row.opportunity / 30
            painter.setBrush(QColor(color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(x, y), radius, radius)


class OnlyFansDashboard(QWidget):
    """Business surface for OnlyFans, intentionally separate from Creator."""

    campaign_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_trends: list[Trend] = []
        self._sample = False
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(MD, MD, MD, MD)
        layout.setSpacing(MD)

        intro = QLabel(
            "OnlyFans venture intelligence: market signals, content whitespace, "
            "and your imported performance. Signal scores are directional "
            "indexes—not creator rankings, revenue forecasts, or live platform data.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        filters = QHBoxLayout()
        filters.setSpacing(SM)
        self.category_box = QComboBox()
        self.category_box.addItem("All")
        self.geography_box = QComboBox()
        self.geography_box.addItems(["Global", "United States", "United Kingdom", "Europe"])
        self.window_box = QComboBox()
        self.window_box.addItems(["7 days", "30 days", "90 days"])
        self.window_box.setCurrentText("30 days")
        self.refresh_btn = QPushButton("Refresh signals")
        filters.addWidget(field("Niche / category", self.category_box), 1)
        filters.addWidget(field("Geography", self.geography_box), 1)
        filters.addWidget(field("Time window", self.window_box), 1)
        filters.addWidget(self.refresh_btn, 0, Qt.AlignBottom)
        layout.addLayout(filters)

        self.sections = QTabWidget()
        layout.addWidget(self.sections, 1)

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(MD, MD, MD, MD)
        overview_layout.setSpacing(MD)

        summary = QHBoxLayout()
        self.top_score = stat("—", "top opportunity")
        self.rising_count = stat("—", "rising signals")
        self.low_sat_count = stat("—", "low saturation")
        summary.addWidget(self.top_score)
        summary.addWidget(self.rising_count)
        summary.addWidget(self.low_sat_count)
        summary.addStretch()
        overview_layout.addLayout(summary)

        charts = QGridLayout()
        charts.setSpacing(MD)
        self.velocity_chart = Sparkline()
        self.scatter_chart = DemandSaturationChart()
        charts.addWidget(self._chart_card("Trend velocity", self.velocity_chart), 0, 0)
        charts.addWidget(self._chart_card("Demand vs saturation", self.scatter_chart), 0, 1)
        charts.setColumnStretch(0, 1)
        charts.setColumnStretch(1, 1)
        overview_layout.addLayout(charts)

        self.source_note = QLabel()
        self.source_note.setObjectName("EstimateLine")
        self.source_note.setWordWrap(True)
        overview_layout.addWidget(self.source_note)
        self.sections.addTab(overview, "Overview")

        opportunities = QWidget()
        opportunities_layout = QVBoxLayout(opportunities)
        opportunities_layout.setContentsMargins(MD, MD, MD, MD)
        opportunities_layout.setSpacing(MD)

        opportunities_layout.addWidget(section("Trends & ranked opportunities"))
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels([
            "Opportunity", "Trend / category", "Momentum", "Demand",
            "Saturation", "Monetization", "Suggested format", "Pricing / upsell",
            "Risk", "Source", "Freshness",
        ])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setMinimumHeight(260)
        opportunities_layout.addWidget(self.table, 1)

        opportunity_actions = QHBoxLayout()
        self.selection_note = QLabel("Select a signal to inspect or hand off.")
        self.selection_note.setObjectName("EstimateLine")
        self.selection_note.setWordWrap(True)
        opportunity_actions.addWidget(self.selection_note, 1)
        self.create_campaign_btn = QPushButton("Create Campaign in Creator")
        self.create_campaign_btn.setObjectName("PrimaryAction")
        opportunity_actions.addWidget(self.create_campaign_btn)
        opportunities_layout.addLayout(opportunity_actions)
        self.sections.addTab(opportunities, "Trends & Opportunities")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(MD, MD, MD, MD)
        content_layout.setSpacing(MD)
        content_layout.addWidget(section("Content intelligence"))
        self.content_detail = QLabel()
        self.content_detail.setWordWrap(True)
        self.content_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content_layout.addWidget(self.content_detail)
        content_layout.addStretch()
        self.sections.addTab(content, "Content Intelligence")

        monetization = QWidget()
        monetization_layout = QVBoxLayout(monetization)
        monetization_layout.setContentsMargins(MD, MD, MD, MD)
        monetization_layout.setSpacing(MD)
        monetization_layout.addWidget(section("Monetization & owned analytics"))
        actuals = QHBoxLayout()
        self.net_receipts = stat("$0", "imported net receipts")
        self.attributed_revenue = stat("$0", "attributed revenue")
        self.subscribers = stat("0", "recorded subscribers")
        self.per_subscriber = stat("$0", "net per subscriber")
        for widget in (self.net_receipts, self.attributed_revenue,
                       self.subscribers, self.per_subscriber):
            actuals.addWidget(widget)
        actuals.addStretch()
        monetization_layout.addLayout(actuals)
        self.monetization_detail = QLabel()
        self.monetization_detail.setWordWrap(True)
        self.monetization_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        monetization_layout.addWidget(self.monetization_detail)
        monetization_layout.addStretch()
        self.sections.addTab(monetization, "Monetization & Analytics")

        market = QWidget()
        market_layout = QVBoxLayout(market)
        market_layout.setContentsMargins(MD, MD, MD, MD)
        market_layout.setSpacing(MD)
        market_layout.addWidget(section("Market, competitors & strategy"))
        self.market_detail = QLabel()
        self.market_detail.setWordWrap(True)
        self.market_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        market_layout.addWidget(self.market_detail)
        market_layout.addStretch()
        self.sections.addTab(market, "Market & Strategy")

        self.category_box.currentTextChanged.connect(self._render)
        self.geography_box.currentTextChanged.connect(self.refresh)
        self.window_box.currentTextChanged.connect(self.refresh)
        self.refresh_btn.clicked.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda _item: self._emit_campaign())
        self.create_campaign_btn.clicked.connect(self._emit_campaign)

    @staticmethod
    def _chart_card(title: str, chart: QWidget) -> QWidget:
        card = QFrame()
        card.setObjectName("TrendChartCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(MD, SM, MD, SM)
        box.setSpacing(SM)
        box.addWidget(micro(title))
        box.addWidget(chart, 1)
        return card

    def refresh(self) -> None:
        self._all_trends, self._sample = load_trends(
            self.geography_box.currentText(), self.window_box.currentText())
        current = self.category_box.currentText()
        categories = sorted({row.category for row in self._all_trends})
        self.category_box.blockSignals(True)
        self.category_box.clear()
        self.category_box.addItems(["All", *categories])
        self.category_box.setCurrentText(current if current in categories else "All")
        self.category_box.blockSignals(False)
        self._render()

    def _render(self, *_args) -> None:
        rows = filter_trends(self._all_trends, self.category_box.currentText())
        self.velocity_chart.set_trends(rows)
        self.scatter_chart.set_trends(rows)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                f"{row.opportunity}/100", f"{row.name}\n{row.category}",
                f"{row.momentum:.0f}", f"{row.search_interest:.0f}",
                f"{row.saturation:.0f}", f"{row.monetization:.0f}", row.format,
                row.pricing_idea, row.risk, row.source,
                row.observed_at.replace("T", " ").replace("+00:00", " UTC"),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.UserRole, row.opportunity)
                if column == 8 and row.risk != "Low":
                    item.setForeground(QColor(WARNING))
                self.table.setItem(index, column, item)
        self._refresh_actuals()
        self.table.setSortingEnabled(True)
        if rows:
            self.table.selectRow(0)
        top = rows[0].opportunity if rows else 0
        rising = sum(row.momentum >= 60 for row in rows)
        low_sat = sum(row.saturation < 50 for row in rows)
        self._set_stat(self.top_score, str(top))
        self._set_stat(self.rising_count, str(rising))
        self._set_stat(self.low_sat_count, str(low_sat))
        if self._sample:
            self.source_note.setText(
                "SAMPLE DATA · Generated locally for interface demonstration · "
                "Live search, discussion, and adult-industry adapters are not configured. "
                "Values are illustrative and must not be treated as observed demand or revenue.")
        else:
            sources = ", ".join(sorted({row.source for row in rows})) or "No sources"
            self.source_note.setText(f"Sources: {sources} · Refresh time shown per row.")
        self._selection_changed()

    def _selected_trend(self) -> Trend | None:
        row_index = self.table.currentRow()
        if row_index < 0:
            return None
        item = self.table.item(row_index, 1)
        name = item.text().splitlines()[0] if item else ""
        return next((row for row in self._all_trends if row.name == name), None)

    def _selection_changed(self) -> None:
        trend = self._selected_trend()
        self.create_campaign_btn.setEnabled(trend is not None)
        if trend is None:
            self.selection_note.setText("Select a signal to inspect or hand off.")
            self.content_detail.setText("No opportunity selected.")
            self.monetization_detail.setText(
                "Select an opportunity to see its monetization experiment beside "
                "your recorded performance.")
            self.market_detail.setText("No market signal selected.")
            return

        context = campaign_context(
            trend, self.geography_box.currentText(), self.window_box.currentText())
        self.selection_note.setText(
            f"{trend.name} · opportunity {trend.opportunity}/100 · {trend.risk} risk")
        self.content_detail.setText(
            f"Selected signal: {trend.name}\n\n"
            f"Format to test: {trend.format}\n\n"
            "Creator handoff deliverables:\n"
            + "\n".join(f"• {item}" for item in context["deliverables"])
            + "\n\nThese are planning prompts. Review every concept for consent, "
              "rights, platform policy, and accurate disclosure before production.")
        self.monetization_detail.setText(
            f"Selected experiment: {trend.pricing_idea}\n\n"
            f"Directional monetization index: {trend.monetization:.0f}/100. "
            "This index and the pricing idea are hypotheses, not expected sales.\n\n"
            f"Profit status: {self._business_metrics['profit_status']}. "
            "Imported net receipts exclude unknown costs, so Imprint does not "
            "mislabel revenue as profit.")
        competition = (
            "high" if trend.saturation >= 70 else
            "moderate" if trend.saturation >= 45 else "lower"
        )
        self.market_detail.setText(
            f"Market lens for {trend.name}\n\n"
            f"Demand index: {trend.search_interest:.0f}/100\n"
            f"Momentum index: {trend.momentum:.0f}/100\n"
            f"Competitive density proxy: {trend.saturation:.0f}/100 ({competition})\n\n"
            "Competitors here means category saturation, not named creator "
            "rankings. Imprint has no verified competitor revenue or account "
            "performance feed.\n\n"
            f"Strategy: test {trend.format.lower()} with a small reviewed batch, "
            "track actual reach, conversion and attributed receipts, then keep or "
            "discard the hypothesis based on your own results.")

    def _refresh_actuals(self) -> None:
        self._business_metrics = onlyfans_business_metrics()
        self._set_stat(self.net_receipts,
                       f"${self._business_metrics['net_receipts']:,.0f}")
        self._set_stat(self.attributed_revenue,
                       f"${self._business_metrics['attributed_revenue']:,.0f}")
        self._set_stat(self.subscribers,
                       f"{self._business_metrics['subscribers']:,}")
        self._set_stat(self.per_subscriber,
                       f"${self._business_metrics['per_subscriber']:,.2f}")

    def _emit_campaign(self) -> None:
        trend = self._selected_trend()
        if trend is None:
            return
        self.campaign_requested.emit(campaign_context(
            trend, self.geography_box.currentText(), self.window_box.currentText()))

    @staticmethod
    def _set_stat(widget: QWidget, value: str) -> None:
        label = widget.findChild(QLabel, "StatValue")
        if label:
            label.setText(value)


# Compatibility for code importing Claude's first dashboard name.  The actual
# screen now belongs to the OnlyFans venture, never to Creator's tab set.
CreatorTrendsDashboard = OnlyFansDashboard
