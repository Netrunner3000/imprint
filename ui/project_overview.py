"""A single, read-only place to find a Project's cross-agent work."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from services.project_overview import snapshot

AGENT_NAMES = {
    "author": "Write", "audiobook": "Audiobook", "video": "Video",
    "creator": "Creator",
}


class ProjectOverviewDialog(QDialog):
    def __init__(self, parent, project_id: str):
        super().__init__(parent)
        self.project_id = project_id
        self.setWindowTitle("Project Overview")
        self.resize(850, 610)
        self.setMinimumSize(650, 450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(12)
        self.title = QLabel()
        self.title.setObjectName("SettingsSectionTitle")
        layout.addWidget(self.title)
        self.identity = QLabel()
        self.identity.setObjectName("EstimateLine")
        self.identity.setWordWrap(True)
        layout.addWidget(self.identity)
        self.brief = QLabel()
        self.brief.setWordWrap(True)
        layout.addWidget(self.brief)
        self.summary = QLabel()
        self.summary.setObjectName("EstimateLine")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.setContentsMargins(8, 12, 8, 8)
        self.files_help = QLabel()
        self.files_help.setWordWrap(True)
        files_layout.addWidget(self.files_help)
        self.files = QTreeWidget()
        self.files.setHeaderLabels(["Output", "Type", "State", "Saved"])
        self.files.header().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            self.files.header().setSectionResizeMode(
                column, QHeaderView.ResizeToContents)
        self.files.setRootIsDecorated(True)
        self.files.itemSelectionChanged.connect(self._selection_changed)
        self.files.itemDoubleClicked.connect(lambda *_: self.open_selected())
        files_layout.addWidget(self.files, 1)
        tabs.addTab(files_page, "Files")

        content_page = QWidget()
        content_layout = QVBoxLayout(content_page)
        content_layout.setContentsMargins(8, 12, 8, 8)
        self.content_help = QLabel(
            "Scheduled Creator work linked to this Project. Profiles, consent "
            "and earnings remain owned by their content account.")
        self.content_help.setWordWrap(True)
        content_layout.addWidget(self.content_help)
        self.content = QTableWidget(0, 5)
        self.content.setHorizontalHeaderLabels(
            ["Content", "Profile", "Campaign", "When", "Status"])
        self.content.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.content.setEditTriggers(QTableWidget.NoEditTriggers)
        content_layout.addWidget(self.content, 1)
        tabs.addTab(content_page, "Creator content")

        actions = QHBoxLayout()
        self.open_button = QPushButton("Open file")
        self.open_button.clicked.connect(self.open_selected)
        actions.addWidget(self.open_button)
        self.reveal_button = QPushButton("Show folder")
        self.reveal_button.clicked.connect(self.reveal_selected)
        actions.addWidget(self.reveal_button)
        actions.addStretch()
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        actions.addWidget(refresh_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self.refresh()

    def refresh(self):
        data = snapshot(self.project_id)
        if not data:
            self.reject()
            return
        project = data["project"]
        self.title.setText(project["work_title"] or project["name"])
        parts = [project["name"]]
        if project["kind"]:
            parts.append(project["kind"].replace("_", " ").title())
        if project["byline"]:
            parts.append(project["byline"])
        self.identity.setText("  ·  ".join(parts))
        self.brief.setText(project["brief"] or "No creative brief set yet.")
        self.summary.setText(
            f"Write draft: {data['draft_words']:,} words   ·   "
            f"Approved: "
            f"{('v' + str(data['latest_approved_version'])) if data['latest_approved_version'] else 'none'}"
            f"{' (Write has changed)' if data['working_differs_from_approved'] else ''}"
            f"   ·   "
            f"Linked files: {len(data['artifacts'])}   ·   "
            f"Creator items: {len(data['creator_content'])}")

        self.files.clear()
        groups = {}
        for artifact in data["artifacts"]:
            agent = artifact["agent"]
            if agent not in groups:
                groups[agent] = QTreeWidgetItem(
                    self.files, [AGENT_NAMES.get(agent, agent.title())])
                groups[agent].setExpanded(True)
            path = Path(artifact["path"])
            item = QTreeWidgetItem(groups[agent], [
                artifact["label"] or path.name,
                artifact["kind"].replace("_", " ").title(),
                "Available" if artifact["available"] else "Missing file",
                artifact["recorded_at"][:16].replace("T", " "),
            ])
            item.setData(0, Qt.UserRole, str(path))
            item.setToolTip(0, str(path))
        self.files_help.setText(
            f"{data['missing_files']} linked file(s) are missing from disk. "
            "Project links never own or delete external files."
            if data["missing_files"] else
            "Files remain at their original locations. Double-click a file "
            "to open it; deleting a Project removes links, not files.")
        self._selection_changed()

        self.content.setRowCount(0)
        for entry in data["creator_content"]:
            row = self.content.rowCount()
            self.content.insertRow(row)
            values = [entry["title"] or entry["kind"].title(),
                      entry["account"], entry["campaign"],
                      entry["scheduled_for"] or "—", entry["status"]]
            for column, value in enumerate(values):
                self.content.setItem(row, column,
                                     QTableWidgetItem(str(value)))

    def _selected_path(self) -> Path | None:
        selected = self.files.selectedItems()
        raw = selected[0].data(0, Qt.UserRole) if selected else None
        return Path(raw) if raw else None

    def _selection_changed(self):
        path = self._selected_path()
        available = bool(path and path.is_file())
        self.open_button.setEnabled(available)
        self.reveal_button.setEnabled(available)

    def open_selected(self):
        path = self._selected_path()
        if not path or not path.is_file():
            QMessageBox.information(self, "File missing",
                                    "This linked file is no longer on disk.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def reveal_selected(self):
        path = self._selected_path()
        if not path or not path.is_file():
            QMessageBox.information(self, "File missing",
                                    "This linked file is no longer on disk.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
