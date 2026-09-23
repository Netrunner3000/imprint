"""Local evidence ledger for submissions of approved manuscript exports."""

from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from services.project_publication import (
    list_exports, list_submissions, record_submission, verify_export,
)


class SubmissionLedgerDialog(QDialog):
    def __init__(self, parent, project_id: str, *, select_export_id: int = 0):
        super().__init__(parent)
        self.project_id = project_id
        self.setWindowTitle("Approved Export & Submission Ledger")
        self.resize(850, 630)
        self.setMinimumSize(680, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Approved exports")
        title.setObjectName("SettingsSectionTitle")
        layout.addWidget(title)
        help_text = QLabel(
            "Select an export made from an approved manuscript version. "
            "Imprint checks its file hash before recording a submission. "
            "This ledger never sends a file to a retailer or verifies their receipt.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        self.exports = QTableWidget(0, 4)
        self.exports.setHorizontalHeaderLabels(
            ["Version", "File", "Format", "On disk"])
        self.exports.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.exports.setSelectionBehavior(QTableWidget.SelectRows)
        self.exports.setEditTriggers(QTableWidget.NoEditTriggers)
        self.exports.verticalHeader().setVisible(False)
        layout.addWidget(self.exports, 1)

        form_holder = QWidget()
        form = QFormLayout(form_holder)
        self.retailer = QLineEdit()
        self.retailer.setPlaceholderText("e.g. KDP, PublishDrive")
        form.addRow("Retailer / distributor", self.retailer)
        self.submitted_on = QDateEdit()
        self.submitted_on.setCalendarPopup(True)
        self.submitted_on.setDisplayFormat("yyyy-MM-dd")
        self.submitted_on.setDate(QDate.currentDate())
        form.addRow("Date you submitted", self.submitted_on)
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("Confirmation or catalog reference")
        form.addRow("Reference", self.reference)
        evidence_row = QHBoxLayout()
        self.evidence = QLineEdit()
        self.evidence.setReadOnly(True)
        self.evidence.setPlaceholderText("Optional, if you have a receipt file")
        evidence_row.addWidget(self.evidence, 1)
        browse = QPushButton("Choose file…")
        browse.clicked.connect(self._choose_evidence)
        evidence_row.addWidget(browse)
        form.addRow("Evidence file", evidence_row)
        layout.addWidget(form_holder)

        actions = QHBoxLayout()
        record = QPushButton("Record self-reported submission")
        record.setObjectName("PrimaryAction")
        record.clicked.connect(self._record)
        actions.addWidget(record)
        open_export = QPushButton("Open selected export")
        open_export.clicked.connect(self._open_export)
        actions.addWidget(open_export)
        actions.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        layout.addLayout(actions)

        submissions_title = QLabel("Recorded submissions · not retailer-verified")
        submissions_title.setObjectName("SettingsSectionTitle")
        layout.addWidget(submissions_title)
        self.submissions = QTableWidget(0, 5)
        self.submissions.setHorizontalHeaderLabels(
            ["Date", "Retailer", "Version", "Reference / evidence", "State"])
        self.submissions.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch)
        self.submissions.setEditTriggers(QTableWidget.NoEditTriggers)
        self.submissions.verticalHeader().setVisible(False)
        layout.addWidget(self.submissions, 1)
        self.refresh(select_export_id)

    def refresh(self, select_export_id: int = 0):
        self.exports.setRowCount(0)
        for entry in list_exports(self.project_id):
            row = self.exports.rowCount()
            self.exports.insertRow(row)
            path = Path(entry["path"])
            state = verify_export(entry["id"])["file_state"]
            values = [f"v{entry['version']}", path.name,
                      entry["format"].upper(),
                      {"matching": "Matches receipt",
                       "changed": "Changed file",
                       "missing": "Missing file",
                       "unreadable": "Unreadable file"}[state]]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(str(path))
                if column == 0:
                    item.setData(Qt.UserRole, entry["id"])
                self.exports.setItem(row, column, item)
            if select_export_id == entry["id"]:
                self.exports.selectRow(row)
        self.submissions.setRowCount(0)
        for entry in list_submissions(self.project_id):
            row = self.submissions.rowCount()
            self.submissions.insertRow(row)
            proof = entry["reference"] or Path(entry["evidence_path"]).name
            values = [entry["submitted_on"], entry["retailer"],
                      f"v{entry['version']}", proof, "Self-reported"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3 and entry["evidence_path"]:
                    item.setToolTip(entry["evidence_path"])
                self.submissions.setItem(row, column, item)

    def _selected_export_id(self) -> int:
        row = self.exports.currentRow()
        item = self.exports.item(row, 0) if row >= 0 else None
        return int(item.data(Qt.UserRole)) if item else 0

    def _choose_evidence(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select retailer evidence")
        if path:
            self.evidence.setText(path)

    def _record(self):
        export_id = self._selected_export_id()
        if not export_id:
            QMessageBox.information(
                self, "Select an export", "Choose an approved export first.")
            return
        try:
            record_submission(
                export_id, self.retailer.text(),
                self.submitted_on.date().toString("yyyy-MM-dd"),
                reference=self.reference.text(),
                evidence_path=self.evidence.text())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot record submission", str(exc))
            return
        self.reference.clear()
        self.evidence.clear()
        self.refresh(export_id)

    def _open_export(self):
        row = self.exports.currentRow()
        item = self.exports.item(row, 1) if row >= 0 else None
        path = Path(item.toolTip()) if item else None
        if path and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                self, "Missing file", "This export is no longer at its saved path.")
