"""Site Builder workspace and its guarded generation lifecycle."""

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSizePolicy, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from services.runtime_paths import user_data_base
from ui.forms import LG, MD, SM, StatBlock, combo, field, line_edit, primary, section
from ui.panels.base import AgentPanel
from ui.widgets import scrollable


class WebdesignPanel(QWidget):
    """A web brief, provider choice and separated HTML/CSS/JS result."""

    HOST_CONTROLS = (
        "webdesign_type_box", "webdesign_style_box", "webdesign_palette_input",
        "webdesign_framework_box", "webdesign_brief_input",
        "webdesign_panel_base", "webdesign_provider_box", "webdesign_model_box",
        "webdesign_generate_btn", "webdesign_copy_btn", "webdesign_save_btn",
        "webdesign_clear_btn", "webdesign_stop_btn", "webdesign_status_label",
        "webdesign_responsive_label", "webdesign_framework_label",
        "webdesign_lines_label", "webdesign_tabs", "webdesign_html_box",
        "webdesign_css_box", "webdesign_js_box",
    )

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.last_response = ""
        self.setObjectName("WebdesignPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        layout.addWidget(section("Page"))
        self.webdesign_type_box = combo([
            "Landing Page", "Portfolio", "Dashboard", "Form", "Blog",
            "Component / Widget", "Other",
        ])
        self.webdesign_style_box = combo(
            ["Minimal", "Dark", "Corporate", "Playful", "Brutalist"])
        self.webdesign_palette_input = line_edit("#1a1a2e, #e94560  ·  ocean blues")
        self.webdesign_framework_box = combo(["Vanilla", "Tailwind", "Bootstrap"])
        setup = QGridLayout()
        setup.setHorizontalSpacing(MD)
        setup.setVerticalSpacing(MD)
        setup.addWidget(field("Page type", self.webdesign_type_box), 0, 0, Qt.AlignTop)
        setup.addWidget(field("Style", self.webdesign_style_box), 0, 1, Qt.AlignTop)
        setup.addWidget(field("Framework", self.webdesign_framework_box), 0, 2, Qt.AlignTop)
        setup.addWidget(field("Colour palette", self.webdesign_palette_input),
                        1, 0, 1, 3, Qt.AlignTop)
        for column in range(3):
            setup.setColumnStretch(column, 1)
        layout.addLayout(setup)

        self.webdesign_brief_input = QTextEdit()
        self.webdesign_brief_input.setPlaceholderText(
            "What to build — sections, features, content, interactions.")
        self.webdesign_brief_input.setFixedHeight(70)
        layout.addWidget(field("Brief", self.webdesign_brief_input))

        layout.addWidget(section("Model"))
        self.webdesign_panel_base = AgentPanel(
            host, "webdesign",
            providers=("ollama", "openai", "deepseek", "kimi", "gemini",
                       "anthropic", "qwen"),
            default_provider="anthropic",
        )
        self.webdesign_provider_box = self.webdesign_panel_base.provider_box
        self.webdesign_model_box = self.webdesign_panel_base.model_box
        models = QGridLayout()
        models.setHorizontalSpacing(MD)
        models.setVerticalSpacing(MD)
        models.addWidget(field("Provider", self.webdesign_provider_box),
                         0, 0, Qt.AlignTop)
        models.addWidget(field("Model", self.webdesign_model_box),
                         0, 1, Qt.AlignTop)
        for column in range(3):
            models.setColumnStretch(column, 1)
        layout.addLayout(models)

        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.webdesign_generate_btn = primary("Generate")
        self.webdesign_generate_btn.setMinimumWidth(160)
        self.webdesign_generate_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.webdesign_generate_btn.clicked.connect(self.generate)
        actions.addWidget(self.webdesign_generate_btn)
        self.webdesign_copy_btn = QPushButton("Copy All")
        self.webdesign_copy_btn.setEnabled(False)
        self.webdesign_copy_btn.clicked.connect(self.copy_all)
        actions.addWidget(self.webdesign_copy_btn)
        self.webdesign_save_btn = QPushButton("Save .html")
        self.webdesign_save_btn.setEnabled(False)
        self.webdesign_save_btn.clicked.connect(self.save)
        actions.addWidget(self.webdesign_save_btn)
        self.webdesign_clear_btn = QPushButton("Clear")
        self.webdesign_clear_btn.clicked.connect(self.clear)
        actions.addWidget(self.webdesign_clear_btn)
        self.webdesign_stop_btn = QPushButton("Stop")
        self.webdesign_stop_btn.setObjectName("DangerAction")
        self.webdesign_stop_btn.clicked.connect(self.stop)
        self.webdesign_stop_btn.hide()
        actions.addWidget(self.webdesign_stop_btn)
        actions.addStretch()
        self.webdesign_status_label = QLabel("")
        self.webdesign_status_label.setObjectName("EstimateLine")
        actions.addWidget(self.webdesign_status_label)
        layout.addLayout(actions)

        layout.addWidget(section("Output"))
        stats = QHBoxLayout()
        stats.setSpacing(LG)
        responsive_stat = StatBlock("responsive", "—")
        framework_stat = StatBlock("framework used", "—")
        lines_stat = StatBlock("lines of code", "—")
        self.webdesign_responsive_label = responsive_stat.value_label
        self.webdesign_framework_label = framework_stat.value_label
        self.webdesign_lines_label = lines_stat.value_label
        for block in (responsive_stat, framework_stat, lines_stat):
            stats.addWidget(block)
        stats.addStretch()
        layout.addLayout(stats)

        self.webdesign_tabs = QTabWidget()
        self.webdesign_html_box = QTextEdit()
        self.webdesign_html_box.setReadOnly(True)
        self.webdesign_tabs.addTab(self.webdesign_html_box, "HTML")
        self.webdesign_css_box = QTextEdit()
        self.webdesign_css_box.setReadOnly(True)
        self.webdesign_tabs.addTab(self.webdesign_css_box, "CSS")
        self.webdesign_js_box = QTextEdit()
        self.webdesign_js_box.setReadOnly(True)
        self.webdesign_tabs.addTab(self.webdesign_js_box, "JS")
        layout.addWidget(self.webdesign_tabs, 1)

        # Aliases retired 2026-09-21: shared wiring resolves controls
        # through host._find_control(); HOST_CONTROLS stays as the
        # published contract of what this panel owns.
        host.webdesign_panel = self
        self.hide()
        self.webdesign_panel_base.load_models()

    def generate(self):
        brief = self.webdesign_brief_input.toPlainText().strip()
        if not brief:
            QMessageBox.warning(self, "Missing Input", "Please enter a brief describing what you want built.")
            return
        provider = self.webdesign_provider_box.currentText()
        model = self.webdesign_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        prompt_parts = [
            f"Page Type: {self.webdesign_type_box.currentText()}",
            f"Style: {self.webdesign_style_box.currentText()}",
            f"Framework: {self.webdesign_framework_box.currentText()}",
        ]
        palette = self.webdesign_palette_input.text().strip()
        if palette:
            prompt_parts.append(f"Colour Palette: {palette}")
        prompt_parts.append(f"\nBrief:\n{brief}")
        prompt = "\n".join(prompt_parts)

        # A denied or cancelled paid request must not strand Generate disabled.
        if not self.host.authorize_request("webdesign", provider, model, prompt):
            return
        messages = self.host.agent_instances["webdesign"].build_messages(prompt)
        self._clear_displays()
        self.last_response = ""
        self.webdesign_status_label.setText("Generating...")
        self.webdesign_generate_btn.setEnabled(False)
        self.webdesign_stop_btn.setEnabled(True)
        self.webdesign_stop_btn.show()

        try:
            worker = self.host._new_chat_worker(provider, model, messages, prompt)
            self.host.webdesign_worker = worker
            worker.token_signal.connect(self._on_token)
            worker.finished_signal.connect(self._on_finished)
            worker.usage_signal.connect(
                lambda usage: self.host.note_request_usage("webdesign", usage))
            worker.error_signal.connect(self._on_error)
            worker.start()
        except Exception as error:
            self._on_error(str(error))

    def _on_token(self, token: str):
        self.last_response += token
        self.webdesign_html_box.setPlainText(self.last_response)
        self.webdesign_html_box.moveCursor(QTextCursor.End)

    def _on_finished(self, response: str):
        self.host.record_request("webdesign", response)
        self.last_response = response
        self._populate_tabs(response)
        self._update_indicators(response)
        self.webdesign_status_label.setText("Generation complete.")
        self._set_idle()
        self.webdesign_save_btn.setEnabled(True)
        self.webdesign_copy_btn.setEnabled(True)

    def _on_error(self, error: str):
        self.host.abandon_request("webdesign")
        self.webdesign_html_box.setPlainText(f"[Error] {error}")
        self.webdesign_status_label.setText("Error.")
        self._set_idle()

    def _set_idle(self):
        self.webdesign_generate_btn.setEnabled(True)
        self.webdesign_stop_btn.setEnabled(False)
        self.webdesign_stop_btn.hide()

    def stop(self):
        worker = self.host.webdesign_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
        self.webdesign_status_label.setText("Stopped.")
        self._set_idle()

    def save(self):
        if not self.last_response:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save HTML File",
            str(user_data_base() / "data" / f"webdesign_{timestamp}.html"),
            "HTML files (*.html);;All files (*)",
        )
        if path:
            Path(path).write_text(self.extract_full_html(self.last_response), encoding="utf-8")

    def copy_all(self):
        if not self.last_response:
            return
        QApplication.clipboard().setText(self.extract_full_html(self.last_response))
        self.webdesign_status_label.setText("Copied to clipboard.")

    def clear(self):
        self._clear_displays()
        self.webdesign_brief_input.clear()
        self.webdesign_status_label.setText("")
        self.last_response = ""

    def _clear_displays(self):
        self.webdesign_html_box.clear()
        self.webdesign_css_box.clear()
        self.webdesign_js_box.clear()
        self.webdesign_responsive_label.setText("—")
        self.webdesign_framework_label.setText("—")
        self.webdesign_lines_label.setText("—")
        self.webdesign_save_btn.setEnabled(False)
        self.webdesign_copy_btn.setEnabled(False)

    @staticmethod
    def extract_full_html(text: str) -> str:
        match = re.search(r"```(?:html)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else text.strip()

    def _populate_tabs(self, text: str):
        full = self.extract_full_html(text)
        self.webdesign_html_box.setPlainText(full)
        css_parts = re.findall(r"<style[^>]*>(.*?)</style>", full,
                               re.DOTALL | re.IGNORECASE)
        self.webdesign_css_box.setPlainText(
            "\n\n".join(part.strip() for part in css_parts))
        js_parts = re.findall(r"<script[^>]*>(.*?)</script>", full,
                              re.DOTALL | re.IGNORECASE)
        self.webdesign_js_box.setPlainText(
            "\n\n".join(part.strip() for part in js_parts))

    def _update_indicators(self, text: str):
        full = self.extract_full_html(text)
        self.webdesign_responsive_label.setText(
            "Mobile-first" if "viewport" in full.lower() or "@media" in full.lower()
            else "Desktop")
        self.webdesign_framework_label.setText(
            self.webdesign_framework_box.currentText())
        self.webdesign_lines_label.setText(str(len(full.splitlines())))
