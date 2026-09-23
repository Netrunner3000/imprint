"""Small, explicit editor for saved-chat project context."""

from __future__ import annotations

import math
import uuid

from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from agents.catalog import AGENT_SPECS
from ui.panels.base import ALL_PROVIDERS
from ui.widgets import scrollable

TEXT_SETUP_AGENTS = {
    "chat", "author", "manuscript", "music", "social", "webdesign",
    "fiverr", "creator",
}


class ProjectManagerDialog(QDialog):
    def __init__(self, parent, registry, on_change=None, history=None):
        super().__init__(parent)
        self.registry = registry
        self.on_change = on_change or (lambda: None)
        self.history = history
        self.setWindowTitle("Manage Projects")
        self.resize(650, 650)

        layout = QVBoxLayout(self)
        title = QLabel("Project context")
        title.setObjectName("SettingsSectionTitle")
        layout.addWidget(title)
        help_text = QLabel(
            "Instructions are sent to the model with each request in this project. "
            "They add token cost. An optional budget caps this project's daily spend; "
            "the app-wide limits still apply. Provider/model defaults apply to text agents."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        picker_row = QHBoxLayout()
        self.picker = QComboBox()
        self.picker.currentIndexChanged.connect(self._load_selected)
        picker_row.addWidget(self.picker, 1)
        new_button = QPushButton("New")
        new_button.clicked.connect(self._new)
        picker_row.addWidget(new_button)
        layout.addLayout(picker_row)

        form_holder = QWidget()
        form = QFormLayout(form_holder)
        self.name = QLineEdit()
        form.addRow("Name", self.name)
        self.kind = QComboBox()
        for label, value in (("Choose a type", ""), ("Book", "book"),
                             ("Video", "video"), ("Music", "music"),
                             ("Venture", "venture"), ("Client work", "client"),
                             ("Other", "other")):
            self.kind.addItem(label, value)
        form.addRow("Work type", self.kind)
        self.work_title = QLineEdit()
        self.work_title.setPlaceholderText("Title of the book, video, release, or product")
        form.addRow("Work title", self.work_title)
        self.byline = QLineEdit()
        self.byline.setPlaceholderText("Author, artist, creator, or brand")
        form.addRow("Byline / brand", self.byline)
        self.brief = QTextEdit()
        self.brief.setPlaceholderText("What this project makes and who it is for")
        self.brief.setMaximumHeight(90)
        form.addRow("Creative brief", self.brief)
        self.instructions = QTextEdit()
        self.instructions.setPlaceholderText(
            "Reusable context and constraints for this project's requests."
        )
        self.instructions.setMinimumHeight(125)
        form.addRow("Instructions", self.instructions)
        self.agent = QComboBox()
        self.agent.addItem("Keep current agent", "")
        for spec in AGENT_SPECS:
            if spec.workspace:
                self.agent.addItem(spec.label, spec.key)
        self.agent.currentIndexChanged.connect(self._sync_default_fields)
        form.addRow("Default agent", self.agent)
        self.provider = QComboBox()
        self.provider.addItem("Keep current provider", "")
        for provider in ALL_PROVIDERS:
            self.provider.addItem(provider.title(), provider)
        form.addRow("Default provider", self.provider)
        self.model = QLineEdit()
        self.model.setPlaceholderText("Leave blank to keep the current model")
        form.addRow("Default model ID", self.model)
        self.budget = QLineEdit()
        self.budget.setPlaceholderText("No project limit")
        form.addRow("Daily budget (€)", self.budget)
        layout.addWidget(scrollable(form_holder), 1)

        actions = QHBoxLayout()
        self.archive_button = QPushButton("Archive")
        self.archive_button.clicked.connect(self._archive)
        actions.addWidget(self.archive_button)
        delete_button = QPushButton("Delete project")
        delete_button.clicked.connect(self._delete)
        actions.addWidget(delete_button)
        actions.addStretch()
        save_button = QPushButton("Save project")
        save_button.setObjectName("PrimaryAction")
        save_button.clicked.connect(self._save)
        actions.addWidget(save_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)

        self._refresh()

    def _refresh(self, wanted: str = ""):
        projects = self.registry.list_projects(include_archived=True)
        self.picker.blockSignals(True)
        self.picker.clear()
        for project in projects:
            label = project["name"] + (" (archived)" if project["archived"] else "")
            self.picker.addItem(label, project["id"])
        index = self.picker.findData(wanted)
        self.picker.setCurrentIndex(index if index >= 0 else 0)
        self.picker.blockSignals(False)
        self._load_selected()

    def _selected(self):
        project_id = self.picker.currentData()
        return self.registry.get_project(project_id) if project_id else None

    def _load_selected(self, _index=0):
        project = self._selected()
        enabled = bool(project)
        for widget in (self.name, self.kind, self.work_title, self.byline,
                       self.brief, self.instructions, self.agent,
                       self.provider, self.model, self.budget):
            widget.setEnabled(enabled)
        self.archive_button.setEnabled(enabled)
        if not project:
            self.name.clear()
            self.kind.setCurrentIndex(0)
            self.work_title.clear()
            self.byline.clear()
            self.brief.clear()
            self.instructions.clear()
            self.model.clear()
            self.budget.clear()
            return
        self.name.setText(project["name"])
        self.kind.setCurrentIndex(max(0, self.kind.findData(project["kind"])))
        self.work_title.setText(project["work_title"])
        self.byline.setText(project["byline"])
        self.brief.setPlainText(project["brief"])
        self.instructions.setPlainText(project["instructions"])
        self.agent.setCurrentIndex(max(0, self.agent.findData(project["default_agent"])))
        self.provider.setCurrentIndex(max(0, self.provider.findData(project["default_provider"])))
        self.model.setText(project["default_model"])
        self._sync_default_fields()
        self.budget.setText(
            "" if project["budget_eur"] is None else str(project["budget_eur"])
        )
        self.archive_button.setText("Restore" if project["archived"] else "Archive")

    def _sync_default_fields(self, _index=0):
        text_agent = self.agent.currentData() in TEXT_SETUP_AGENTS
        self.provider.setEnabled(text_agent)
        self.model.setEnabled(text_agent)

    def _new(self):
        project_id = uuid.uuid4().hex[:12]
        self.registry.upsert_project(project_id, "New Project")
        self._refresh(project_id)
        self.name.selectAll()
        self.name.setFocus()
        self.on_change()

    def _save(self):
        project = self._selected()
        if not project:
            return
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Project name needed", "Enter a project name.")
            return
        raw_budget = self.budget.text().strip()
        try:
            budget = float(raw_budget) if raw_budget else None
            if budget is not None and (not math.isfinite(budget) or budget < 0):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Invalid budget", "Use a non-negative euro amount or leave it blank.")
            return
        self.registry.upsert_project(
            project["id"], name,
            instructions=self.instructions.toPlainText().strip(),
            default_agent=self.agent.currentData() or "",
            default_provider=(self.provider.currentData() or "")
            if self.agent.currentData() in TEXT_SETUP_AGENTS else "",
            default_model=self.model.text().strip()
            if self.agent.currentData() in TEXT_SETUP_AGENTS else "",
            budget_eur=budget,
            archived=bool(project["archived"]),
            kind=self.kind.currentData() or "",
            work_title=self.work_title.text(),
            byline=self.byline.text(),
            brief=self.brief.toPlainText(),
        )
        self._refresh(project["id"])
        self.on_change()

    def _archive(self):
        project = self._selected()
        if project:
            self.registry.archive_project(project["id"], not bool(project["archived"]))
            self._refresh(project["id"])
            self.on_change()

    def _delete(self):
        project = self._selected()
        if not project:
            return
        answer = QMessageBox.question(
            self, "Delete project",
            f"Delete '{project['name']}'? Saved chats remain and become unfiled. "
            "Project-specific working drafts and identity will be removed.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if self.history is not None:
            try:
                self.history.unfile_project(project["id"])
            except Exception as exc:
                QMessageBox.warning(
                    self, "Could not unfile chats",
                    f"The project was not deleted because its chats could not be updated: {exc}",
                )
                return
        self.registry.delete_project(project["id"])
        self._refresh()
        self.on_change()
