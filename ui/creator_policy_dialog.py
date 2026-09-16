"""A dated, source-backed policy record for one Creator platform."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QVBoxLayout,
)


class CreatorPolicyDialog(QDialog):
    def __init__(self, platform: str, policy: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Platform policy · {platform}")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Record what the platform's current written rules say. Unknown means "
            "not approved. This record is not legal advice or automatic permission to publish.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        layout.addLayout(form)
        self.synthetic = QComboBox()
        self.synthetic.addItems(["unknown", "allowed", "prohibited"])
        self.synthetic.setCurrentText(policy["synthetic_persona"])
        form.addRow("Synthetic persona", self.synthetic)
        self.owner = QComboBox()
        self.owner.addItems(["unknown", "yes", "no"])
        self.owner.setCurrentText(policy["verified_owner_required"])
        form.addRow("Verified depicted owner required", self.owner)
        self.disclosure = QLineEdit(policy["ai_disclosure"])
        self.disclosure.setPlaceholderText("Exact required AI label or disclosure, if any")
        form.addRow("Required AI disclosure", self.disclosure)
        self.publishing = QComboBox()
        self.publishing.addItems(["manual_only", "official_api", "unknown"])
        self.publishing.setCurrentText(policy["publishing_method"])
        form.addRow("Allowed publishing route", self.publishing)
        self.source = QLineEdit(policy["source_url"])
        self.source.setPlaceholderText("Official URL or logged-in help reference")
        form.addRow("Policy source", self.source)
        self.reviewed = QLineEdit(policy["reviewed_on"])
        self.reviewed.setPlaceholderText("YYYY-MM-DD")
        form.addRow("Reviewed on", self.reviewed)
        manual = QLabel(
            "Creator currently exports drafts only. Selecting official_api records "
            "a reviewed platform rule; it does not enable automated posting.")
        manual.setWordWrap(True)
        layout.addWidget(manual)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "synthetic_persona": self.synthetic.currentText(),
            "verified_owner_required": self.owner.currentText(),
            "ai_disclosure": self.disclosure.text().strip(),
            "publishing_method": self.publishing.currentText(),
            "source_url": self.source.text().strip(),
            "reviewed_on": self.reviewed.text().strip(),
        }
