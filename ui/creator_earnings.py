"""Readable, evidence-labelled Creator earnings dashboard.

Statement net and attributed post revenue are different views of possibly
overlapping receipts. They are deliberately never added together here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHeaderView, QLabel, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.forms import MD, SM, section
from ui.style import ACCENT, BORDER, ELEVATED, SUNKEN, SURFACE, TEXT, TEXT_DIM, TEXT_MUTE


class RevenueBars(QWidget):
    """A small bar chart of recorded PPV revenue, with no forecast axis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CreatorPriceChart")
        self.setFixedHeight(110)
        self._points: list[dict] = []
        self.setAccessibleName("Recorded revenue by posted PPV price")

    def set_points(self, points: list[dict]) -> None:
        self._points = list(points[:8])
        self.setFixedHeight(max(110, min(310, len(self._points) * 34 + 24)))
        self.update()

    def paintEvent(self, _event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(12, 12, -12, -12)
        if not self._points:
            painter.setPen(QColor(TEXT_DIM))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                             "Record posted PPV results to compare price points.")
            return

        values = [max(0.0, float(p.get("total") or 0)) for p in self._points]
        peak = max(values) or 1.0
        left, right = 88, 72
        row_height = min(34.0, rect.height() / max(1, len(values)))
        chart_width = max(1.0, rect.width() - left - right)
        metrics = QFontMetrics(painter.font())
        for index, (point, total) in enumerate(zip(self._points, values)):
            top = rect.top() + index * row_height
            label = f"${float(point['price_usd']):g}"
            painter.setPen(QColor(TEXT_DIM))
            painter.drawText(QRectF(rect.left(), top, left - 12, row_height),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                             label)
            bar = QRectF(rect.left() + left, top + 6,
                         max(3.0, chart_width * total / peak), row_height - 12)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ACCENT))
            painter.drawRoundedRect(bar, 4, 4)
            painter.setPen(QColor(TEXT))
            value_label = f"${total:,.2f}"
            painter.drawText(QRectF(bar.right() + 8, top, right - 2, row_height),
                             Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(value_label, Qt.TextElideMode.ElideRight,
                                                right - 4))


def _metric(value: str, caption: str) -> QFrame:
    card = QFrame()
    card.setObjectName("CreatorEarningsMetric")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(MD, MD, MD, MD)
    layout.setSpacing(4)
    number = QLabel(value)
    number.setObjectName("CreatorEarningsValue")
    label = QLabel(caption)
    label.setObjectName("CreatorEarningsCaption")
    label.setWordWrap(True)
    layout.addWidget(number)
    layout.addWidget(label)
    return card


def _table(headers: list[str], name: str) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setObjectName(name)
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(34)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setFixedHeight(54)
    return table


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setToolTip(text)
    return item


class CreatorEarningsView(QScrollArea):
    """One scroll surface for the owner's observed receipts and content results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CreatorEarningsView")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("Transparent")
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(MD, MD, MD, MD)
        layout.setSpacing(MD)

        layout.addWidget(section("Observed earnings"))
        note = QLabel(
            "Imported statement net is receipts after platform fees, not profit. "
            "Attributed content revenue may overlap those statements, so the two are not added."
        )
        note.setObjectName("CreatorEarningsNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        metrics = QGridLayout()
        metrics.setSpacing(SM)
        self.net_metric = _metric("—", "Statement net")
        self.attributed_metric = _metric("—", "Recorded post revenue")
        self.subscribers_metric = _metric("—", "Peak subscriber count")
        self.posted_metric = _metric("—", "Posted items")
        for column, card in enumerate((self.net_metric, self.attributed_metric,
                                       self.subscribers_metric, self.posted_metric)):
            metrics.addWidget(card, 0, column)
            metrics.setColumnStretch(column, 1)
        layout.addLayout(metrics)

        layout.addWidget(section("PPV price points"))
        chart_note = QLabel(
            "Bars show recorded revenue by posted offer price, not conversion or a recommended price. "
            "A small number of offers is anecdotal."
        )
        chart_note.setObjectName("CreatorEarningsNote")
        chart_note.setWordWrap(True)
        layout.addWidget(chart_note)
        self.chart = RevenueBars()
        layout.addWidget(self.chart)
        self.price_table = _table(
            ["Price", "Posted offers", "Recorded revenue", "Revenue / offer", "Evidence"],
            "CreatorPriceTable")
        layout.addWidget(self.price_table)

        layout.addWidget(section("Content with recorded revenue"))
        self.content_table = _table(
            ["Title", "Format", "Recorded revenue"], "CreatorTopContentTable")
        layout.addWidget(self.content_table)

        layout.addWidget(section("Asset outcomes"))
        outcome_note = QLabel(
            "One row per posted asset. ROI uses only the all-in USD cost you entered; "
            "a blank ROI means cost is unknown. Compare matching sources and windows.")
        outcome_note.setObjectName("CreatorEarningsNote")
        outcome_note.setWordWrap(True)
        layout.addWidget(outcome_note)
        self.outcome_table = _table(
            ["Asset / campaign", "Channel", "Reach / clicks", "Subs / PPV",
             "Revenue / cost", "ROI*"], "CreatorOutcomeTable")
        layout.addWidget(self.outcome_table)

        layout.addWidget(section("Tested hooks"))
        hook_note = QLabel(
            "Chosen hooks with manually attributed revenue; this is not a controlled "
            "comparison unless audience, timing, and offer were held constant.")
        hook_note.setObjectName("CreatorEarningsNote")
        hook_note.setWordWrap(True)
        layout.addWidget(hook_note)
        self.hook_table = _table(
            ["Hook", "Asset", "Attributed revenue"], "CreatorHookTable")
        layout.addWidget(self.hook_table)

        layout.addWidget(section("Imported statements"))
        self.statement_table = _table(
            ["Source", "Period", "Gross", "Net", "Subscribers"],
            "CreatorStatementsTable")
        layout.addWidget(self.statement_table)

        self.empty_note = QLabel("")
        self.empty_note.setObjectName("CreatorEarningsNote")
        self.empty_note.setWordWrap(True)
        layout.addWidget(self.empty_note)
        layout.addStretch()

        self.setStyleSheet(f"""
            QFrame#CreatorEarningsMetric {{ background: {SURFACE}; border: 1px solid {BORDER};
                border-radius: 8px; }}
            QLabel#CreatorEarningsValue {{ color: {TEXT}; font-size: 19px; font-weight: 650; }}
            QLabel#CreatorEarningsCaption, QLabel#CreatorEarningsNote {{
                color: {TEXT_DIM}; font-size: 12px; }}
            QTableWidget#CreatorPriceTable, QTableWidget#CreatorTopContentTable,
            QTableWidget#CreatorStatementsTable, QTableWidget#CreatorOutcomeTable,
            QTableWidget#CreatorHookTable {{ background: {SUNKEN};
                alternate-background-color: {SURFACE}; color: {TEXT_DIM};
                border: 1px solid {BORDER}; gridline-color: transparent; }}
            QTableWidget::item:selected {{ background: {ELEVATED}; color: {TEXT}; }}
            QHeaderView::section {{ color: {TEXT_MUTE}; background: {SURFACE};
                border: none; border-bottom: 1px solid {BORDER}; padding: 6px; }}
        """)
        self.show_empty()

    @staticmethod
    def _set_metric(card: QFrame, value: str) -> None:
        card.findChild(QLabel, "CreatorEarningsValue").setText(value)

    @staticmethod
    def _fit_table(table: QTableWidget) -> None:
        visible_rows = min(6, table.rowCount())
        table.setFixedHeight(table.horizontalHeader().height() + visible_rows * 34 + 6)

    def show_empty(self) -> None:
        self._set_metric(self.net_metric, "—")
        self._set_metric(self.attributed_metric, "—")
        self._set_metric(self.subscribers_metric, "—")
        self._set_metric(self.posted_metric, "—")
        self.chart.set_points([])
        for table in (self.price_table, self.content_table, self.outcome_table,
                      self.hook_table, self.statement_table):
            table.setRowCount(0)
            self._fit_table(table)
        self.empty_note.setText(
            "No earnings imported yet. Export a statement from the platform and import its CSV. "
            "You can also record revenue on posted content manually."
        )

    def set_data(self, summary: dict, price_points: list[dict],
                 top_content: list[dict], statements: list[dict],
                 *, outcomes: list[dict] | None = None,
                 hooks: list[dict] | None = None) -> None:
        self.empty_note.setText("")
        self._set_metric(self.net_metric, f"${float(summary['net']):,.2f}")
        self._set_metric(self.attributed_metric,
                         f"${float(summary['attributed']):,.2f}")
        self._set_metric(self.subscribers_metric, f"{int(summary['subscribers']):,}")
        self._set_metric(self.posted_metric, f"{int(summary['posted']):,}")

        self.chart.set_points(price_points)
        self.price_table.setRowCount(len(price_points))
        self._fit_table(self.price_table)
        for row, point in enumerate(price_points):
            sends = int(point["sends"])
            values = (
                f"${float(point['price_usd']):.2f}", str(sends),
                f"${float(point['total']):,.2f}",
                f"${float(point['average']):,.2f}",
                "Few offers · anecdotal" if sends < 5 else "Descriptive only",
            )
            for column, value in enumerate(values):
                self.price_table.setItem(row, column, _cell(value))

        self.content_table.setRowCount(len(top_content))
        self._fit_table(self.content_table)
        for row, item in enumerate(top_content):
            for column, value in enumerate((
                item.get("title") or "Untitled", item.get("kind") or "—",
                f"${float(item['revenue_usd']):,.2f}",
            )):
                self.content_table.setItem(row, column, _cell(value))

        outcomes = outcomes or []
        self.outcome_table.setRowCount(len(outcomes))
        self._fit_table(self.outcome_table)
        for row, item in enumerate(outcomes):
            revenue = float(item.get("revenue_usd") or 0)
            cost = float(item.get("attributable_cost_usd") or 0)
            roi = f"{(revenue - cost) / cost:+.0%}" if cost > 0 else "—"
            values = (
                (item.get("title") or "Untitled")[:34]
                + (f" · {item['campaign']}" if item.get("campaign") else ""),
                item.get("channel") or "—",
                f"{int(item.get('reach') or 0):,} / {int(item.get('clicks') or 0):,}",
                f"{int(item.get('subscriptions') or 0):,} / "
                f"{int(item.get('ppv_purchases') or 0):,}",
                f"${revenue:,.2f} / " + (f"${cost:,.2f}" if cost else "?"),
                roi,
            )
            evidence = (f"Source: {item.get('metric_source') or 'not recorded'}\n"
                        f"Window: {item.get('metric_window') or 'not recorded'}\n"
                        f"Link: {item.get('permalink') or 'not recorded'}\n"
                        f"Draft generation: €{float(item.get('generation_cost_eur') or 0):.4f}\n"
                        f"Chosen hook: {item.get('hook') or 'not recorded'}")
            for column, value in enumerate(values):
                cell = _cell(value)
                cell.setToolTip(evidence)
                self.outcome_table.setItem(row, column, cell)

        hooks = hooks or []
        self.hook_table.setRowCount(len(hooks))
        self._fit_table(self.hook_table)
        for row, item in enumerate(hooks):
            for column, value in enumerate((
                    (item.get("body") or "—")[:100],
                    item.get("title") or "Untitled",
                    f"${float(item.get('revenue_usd') or 0):,.2f}")):
                self.hook_table.setItem(row, column, _cell(value))

        self.statement_table.setRowCount(len(statements))
        self._fit_table(self.statement_table)
        for row, item in enumerate(statements):
            period = f"{item['period_from']} – {item['period_to']}"
            values = (
                item["source_file"], period,
                f"${float(item['gross_usd']):,.2f}",
                f"${float(item['net_usd']):,.2f}",
                str(int(item["subscribers"])),
            )
            for column, value in enumerate(values):
                self.statement_table.setItem(row, column, _cell(value))
