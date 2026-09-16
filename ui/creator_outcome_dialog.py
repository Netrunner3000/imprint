"""Manual, source-labelled outcome entry for one Creator calendar asset."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QLabel, QLineEdit, QMessageBox, QSpinBox, QVBoxLayout,
)


class CreatorOutcomeDialog(QDialog):
    def __init__(self, asset: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record Creator outcome")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Enter numbers from one actual posted asset and one measurement window. "
            "Revenue is attributed manually and may also appear in imported statements. "
            "Do not add the two totals.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        layout.addLayout(form)

        self.campaign = QLineEdit(asset.get("campaign") or "")
        self.channel = QLineEdit(asset.get("channel") or "")
        self.permalink = QLineEdit(asset.get("permalink") or "")
        self.source = QLineEdit(asset.get("metric_source") or "")
        self.source.setPlaceholderText("e.g. platform analytics export + sales ledger")
        self.window = QLineEdit(asset.get("metric_window") or "")
        self.window.setPlaceholderText("e.g. 2026-09-01 to 2026-09-07")
        for label, control in (
            ("Campaign", self.campaign), ("Channel", self.channel),
            ("Post link", self.permalink), ("Source", self.source),
            ("Measurement window", self.window),
        ):
            form.addRow(label, control)

        self.counts: dict[str, QSpinBox] = {}
        for name, label in (
            ("reach", "Accounts reached"), ("clicks", "Link clicks"),
            ("subscriptions", "New subscriptions"),
            ("ppv_purchases", "PPV purchases"),
        ):
            box = QSpinBox()
            box.setRange(0, 1_000_000_000)
            box.setValue(int(asset.get(name) or 0))
            form.addRow(label, box)
            self.counts[name] = box

        self.revenue = QDoubleSpinBox()
        self.revenue.setRange(0, 100_000_000)
        self.revenue.setDecimals(2)
        self.revenue.setPrefix("$ ")
        self.revenue.setValue(float(asset.get("revenue_usd") or 0))
        form.addRow("Attributed revenue (USD)", self.revenue)

        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 100_000_000)
        self.cost.setDecimals(2)
        self.cost.setPrefix("$ ")
        self.cost.setValue(float(asset.get("attributable_cost_usd") or 0))
        self.cost.setToolTip(
            "Your all-in attributable cost in USD: convert AI spend from EUR "
            "and include other production, fees, promotion, and human time.")
        form.addRow("All-in cost (USD)", self.cost)

        measured = float(asset.get("generation_cost_eur") or 0)
        cost_note = QLabel(
            f"Imprint measured €{measured:.4f} for the draft. It is not converted "
            "or added to the USD cost automatically; include it after conversion.")
        cost_note.setWordWrap(True)
        layout.addWidget(cost_note)

        self.confirm_posted = QCheckBox("I confirm this asset was actually posted")
        self.confirm_posted.setChecked(asset.get("status") == "posted")
        layout.addWidget(self.confirm_posted)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_checked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_checked(self):
        if not self.confirm_posted.isChecked():
            QMessageBox.warning(self, "Confirm publication",
                                "Outcomes belong only to actually posted assets.")
            return
        if not self.source.text().strip() or not self.window.text().strip():
            QMessageBox.warning(self, "Evidence required",
                                "Name the source and measurement window.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "campaign": self.campaign.text().strip(),
            "channel": self.channel.text().strip(),
            "permalink": self.permalink.text().strip(),
            "source": self.source.text().strip(),
            "window": self.window.text().strip(),
            "revenue_usd": self.revenue.value(),
            "attributable_cost_usd": self.cost.value(),
            **{name: box.value() for name, box in self.counts.items()},
        }
