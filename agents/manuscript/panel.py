"""Publishing Manager workspace and its guarded flows.

Phase 4 extraction: the Overview (metrics, Ask, publishing todos), Quote
Finder, Quote Graphics, Shorts and Calendar tabs and every handler moved
here from main.py. The host supplies shared budget authorization, usage
records, the chat-worker factory, the provider clients (for the
Connections status), and the cross-panel next-step banner; the workers
stay host attributes so the umbrella's shutdown sweep keeps seeing them.

Request tokens live on this panel: "manuscript" is shared by four paid
flows (Ask, quote suggestions, calendar captions, ElevenLabs narration),
so nothing here resolves a request by agent name.
"""

import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from services.runtime_paths import user_data_base
from agents.manuscript.book_widgets import (
    make_size_box, make_theme_box, make_voice_source_box, populate_voice_box,
    size_key, theme_key, unique_output_path,
)
from ui.forms import MD, SM, combo, field, line_edit, micro, primary, section
from ui.panels.base import AgentPanel
from ui.style import ACCENT
from ui.widgets import CollapsibleSection, FlowLayout, scrollable


class ManuscriptPanel(QWidget):
    """Metrics, Q&A, todos, and the quote-to-asset production tabs."""

    HOST_CONTROLS = (
        "manuscript_period_box", "manuscript_refresh_btn",
        "manuscript_ingest_btn", "manuscript_next_step_label",
        "manuscript_tabs", "manuscript_metrics_box", "manuscript_query_input",
        "manuscript_panel_base", "manuscript_provider_box",
        "manuscript_model_box", "manuscript_ask_btn", "manuscript_todo_list",
        "manuscript_todo_input", "manuscript_add_todo_btn",
        "manuscript_done_todo_btn", "manuscript_status_label",
        "quote_finder_text", "quote_finder_load_btn", "quote_finder_count_box",
        "quote_finder_project_btn",
        "quote_finder_theme_box", "quote_finder_voice_source_box",
        "quote_finder_voice_box", "quote_finder_attribution",
        "quote_finder_suggest_btn", "quote_finder_list",
        "quote_graphic_text", "quote_graphic_attribution",
        "quote_graphic_theme_box", "quote_graphic_size_box",
        "quote_graphic_generate_btn", "quote_graphic_open_folder_btn",
        "quote_graphic_preview",
        "shorts_quote_text", "shorts_attribution", "shorts_theme_box",
        "shorts_voice_source_box", "shorts_voice_box", "shorts_generate_btn",
        "shorts_play_btn", "shorts_open_folder_btn", "shorts_preview",
        "calendar_weeks_box", "calendar_start_date", "calendar_tiktok_check",
        "calendar_instagram_check", "calendar_pinterest_check",
        "calendar_theme_box", "calendar_voice_source_box", "calendar_voice_box",
        "calendar_attribution", "calendar_generate_btn", "calendar_export_btn",
        "calendar_table",
    )

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._last_data: str = ""
        self._last_short_path: str = ""
        self._ask_token = None
        self._quote_finder_token = None
        self._calendar_captions_token = None
        self._shorts_token = None
        self.setObjectName("ManuscriptPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(MD)

        # ── Top bar: period selector + data actions ───────────────────────────
        # The buttons sit on the field's baseline, not the label's, so the row
        # reads as one line instead of a control stepping up over a caption.
        top_bar = QWidget()
        top_bar.setObjectName("Transparent")
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(SM)

        self.manuscript_period_box = combo(
            ["Last 30 days", "This month", "Last 7 days", "All time"])
        period_field = field("Period", self.manuscript_period_box)
        period_field.setFixedWidth(180)
        tb.addWidget(period_field)

        self.manuscript_refresh_btn = QPushButton("Refresh Data")
        self.manuscript_refresh_btn.clicked.connect(self.refresh_data)
        tb.addWidget(self.manuscript_refresh_btn, 0, Qt.AlignBottom)

        self.manuscript_ingest_btn = QPushButton("Ingest KDP CSV")
        self.manuscript_ingest_btn.clicked.connect(self.ingest_kdp)
        tb.addWidget(self.manuscript_ingest_btn, 0, Qt.AlignBottom)

        tb.addStretch()
        layout.addWidget(top_bar)

        self.manuscript_next_step_label = QLabel("")
        self.manuscript_next_step_label.setWordWrap(True)
        self.manuscript_next_step_label.setObjectName("NextStepBanner")
        layout.addWidget(self.manuscript_next_step_label)

        # ── Connections: which 3rd-party services are actually configured ─────
        connections_section = CollapsibleSection("Connections", expanded=False)
        self.manuscript_connections_layout = QVBoxLayout()
        self.manuscript_connections_layout.setContentsMargins(4, 2, 4, 2)
        self.manuscript_connections_layout.setSpacing(3)
        connections_container = QWidget()
        connections_container.setLayout(self.manuscript_connections_layout)
        connections_section.addWidget(connections_container)

        connections_refresh_btn = QPushButton("Refresh Status")
        connections_refresh_btn.clicked.connect(self.refresh_connections_status)
        connections_section.addWidget(connections_refresh_btn)

        layout.addWidget(connections_section)

        self.manuscript_tabs = QTabWidget()
        layout.addWidget(self.manuscript_tabs, 1)

        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(0, 0, 0, 0)

        # ── Main area: metrics display + Q&A sidebar ─────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Left: metrics summary display
        self.manuscript_metrics_box = QTextBrowser()
        self.manuscript_metrics_box.setPlaceholderText(
            "Click Refresh Data to load publishing metrics…")
        splitter.addWidget(self.manuscript_metrics_box)

        # Right: Q&A and todos. Section labels and fields rather than a stack
        # of "Ask about your book:" / "Provider:" / "Model:" colon captions,
        # each of which set its own left edge.
        sidebar = QWidget()
        sidebar.setObjectName("Transparent")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(MD, 0, 0, 0)
        sb.setSpacing(MD)
        sidebar.setFixedWidth(300)

        sb.addWidget(section("Ask"))
        self.manuscript_query_input = QTextEdit()
        self.manuscript_query_input.setPlaceholderText(
            "What did I earn this month? Which platform performs best?")
        self.manuscript_query_input.setFixedHeight(76)
        sb.addWidget(self.manuscript_query_input)

        # No ollama: the manuscript registry row restricts providers, and a box
        # offering one the validator refuses is a dead option.
        self.manuscript_panel_base = AgentPanel(
            host, "manuscript",
            providers=("anthropic", "openai", "deepseek", "kimi", "gemini", "qwen"))
        self.manuscript_provider_box = self.manuscript_panel_base.provider_box
        self.manuscript_model_box = self.manuscript_panel_base.model_box
        sb.addWidget(field("Provider", self.manuscript_provider_box))
        sb.addWidget(field("Model", self.manuscript_model_box))

        self.manuscript_ask_btn = primary("Ask")
        self.manuscript_ask_btn.clicked.connect(self.ask)
        sb.addWidget(self.manuscript_ask_btn)

        sb.addWidget(section("Publishing todos"))
        self.manuscript_todo_list = QListWidget()
        self.manuscript_todo_list.setMinimumHeight(120)
        sb.addWidget(self.manuscript_todo_list, 1)

        self.manuscript_todo_input = line_edit("Add todo…")
        sb.addWidget(self.manuscript_todo_input)

        todo_btn_row = QHBoxLayout()
        todo_btn_row.setSpacing(SM)
        self.manuscript_add_todo_btn = QPushButton("Add")
        self.manuscript_add_todo_btn.clicked.connect(self.add_todo)
        self.manuscript_done_todo_btn = QPushButton("Done")
        self.manuscript_done_todo_btn.clicked.connect(self.mark_todo_done)
        todo_btn_row.addWidget(self.manuscript_add_todo_btn)
        todo_btn_row.addWidget(self.manuscript_done_todo_btn)
        sb.addLayout(todo_btn_row)

        splitter.addWidget(scrollable(sidebar, min_width=300, max_width=320))
        overview_layout.addWidget(splitter)
        self.manuscript_tabs.addTab(overview_tab, "Overview")

        self._build_quote_finder_tab()
        self.manuscript_tabs.addTab(self.manuscript_quote_finder_tab, "Quote Finder")

        self._build_graphics_tab()
        self.manuscript_tabs.addTab(self.manuscript_graphics_tab, "Quote Graphics")

        self._build_shorts_tab()
        self.manuscript_tabs.addTab(self.manuscript_shorts_tab, "Shorts")

        self._build_calendar_tab()
        self.manuscript_tabs.addTab(self.manuscript_calendar_tab, "Calendar")

        # Status bar
        self.manuscript_status_label = QLabel("")
        self.manuscript_status_label.setObjectName("EstimateLine")
        layout.addWidget(self.manuscript_status_label)

        # Aliases retired 2026-09-21: shared wiring resolves controls
        # through host._find_control(); HOST_CONTROLS stays as the
        # published contract of what this panel owns.
        host.manuscript_panel = self
        self.refresh_connections_status()
        self.hide()

    # ── sub-tab builders ────────────────────────────────────────────────
    def _build_quote_finder_tab(self):
        self.manuscript_quote_finder_tab = QWidget()
        layout = QVBoxLayout(self.manuscript_quote_finder_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.quote_finder_text = QTextEdit()
        self.quote_finder_text.setPlaceholderText(
            "Paste a chapter or excerpt here, or load a file below…"
        )
        self.quote_finder_text.setFixedHeight(140)
        layout.addWidget(field("Manuscript text", self.quote_finder_text))

        load_row = QHBoxLayout()
        self.quote_finder_load_btn = QPushButton("Load File…")
        self.quote_finder_load_btn.clicked.connect(self.quote_finder_load_file)
        load_row.addWidget(self.quote_finder_load_btn)
        self.quote_finder_project_btn = QPushButton("Use Project Draft")
        self.quote_finder_project_btn.setToolTip(
            "Load the selected project's current Write draft into Quote Finder.")
        self.quote_finder_project_btn.clicked.connect(self.use_project_draft)
        load_row.addWidget(self.quote_finder_project_btn)
        load_row.addWidget(QLabel("Supports .txt, .pdf, .epub, .mobi"))
        load_row.addStretch()
        layout.addLayout(load_row)

        settings_row_container = QWidget()
        settings_row = FlowLayout(settings_row_container, spacing=6)
        self.quote_finder_count_box = QComboBox()
        self.quote_finder_count_box.addItems(["5", "10", "15", "20"])
        self.quote_finder_count_box.setCurrentText("10")
        settings_row.addWidget(field("Quotes", self.quote_finder_count_box))

        self.quote_finder_theme_box = make_theme_box()
        settings_row.addWidget(field("Theme", self.quote_finder_theme_box))

        self.quote_finder_voice_source_box = make_voice_source_box()
        self.quote_finder_voice_source_box.currentTextChanged.connect(
            self.quote_finder_load_voices)
        settings_row.addWidget(field("Voice", self.quote_finder_voice_source_box))

        self.quote_finder_voice_box = QComboBox()
        settings_row.addWidget(self.quote_finder_voice_box)

        self.quote_finder_attribution = QLineEdit()
        self.quote_finder_attribution.setPlaceholderText("You Don't Chase")
        settings_row.addWidget(field("Attribution", self.quote_finder_attribution))

        layout.addWidget(settings_row_container)

        self.quote_finder_suggest_btn = QPushButton("Suggest Quotes")
        self.quote_finder_suggest_btn.setMinimumHeight(34)
        self.quote_finder_suggest_btn.clicked.connect(self.quote_finder_suggest)
        layout.addWidget(self.quote_finder_suggest_btn)

        layout.addWidget(micro("Candidates"))
        self.quote_finder_list = QListWidget()
        layout.addWidget(self.quote_finder_list, 1)

        self._quote_finder_short_buttons: list = []
        self._quote_finder_busy = False
        self.quote_finder_load_voices()

    def _build_graphics_tab(self):
        self.manuscript_graphics_tab = QWidget()
        row = QHBoxLayout(self.manuscript_graphics_tab)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(12)

        # Left: controls
        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        controls.setMaximumWidth(280)

        self.quote_graphic_text = QTextEdit()
        self.quote_graphic_text.setPlaceholderText(
            "You over-text. You explain yourself. You wait.")
        self.quote_graphic_text.setFixedHeight(90)
        cl.addWidget(field("Quote", self.quote_graphic_text))

        self.quote_graphic_attribution = QLineEdit()
        self.quote_graphic_attribution.setPlaceholderText("You Don't Chase")
        cl.addWidget(field("Attribution (optional)", self.quote_graphic_attribution))

        self.quote_graphic_theme_box = make_theme_box()
        cl.addWidget(field("Theme", self.quote_graphic_theme_box))

        self.quote_graphic_size_box = make_size_box()
        cl.addWidget(field("Size", self.quote_graphic_size_box))

        self.quote_graphic_generate_btn = QPushButton("Generate Graphic")
        self.quote_graphic_generate_btn.setMinimumHeight(34)
        self.quote_graphic_generate_btn.clicked.connect(
            self.generate_quote_graphic)
        cl.addWidget(self.quote_graphic_generate_btn)

        self.quote_graphic_open_folder_btn = QPushButton("Open Folder")
        self.quote_graphic_open_folder_btn.clicked.connect(
            self.open_graphics_folder)
        cl.addWidget(self.quote_graphic_open_folder_btn)

        cl.addStretch()
        row.addWidget(controls)

        # Right: preview
        self.quote_graphic_preview = QLabel("Preview will appear here.")
        self.quote_graphic_preview.setAlignment(Qt.AlignCenter)
        self.quote_graphic_preview.setStyleSheet(
            "background: #1a1a1a; border: 1px solid #333; color: #666;"
        )
        self.quote_graphic_preview.setMinimumSize(320, 320)
        row.addWidget(self.quote_graphic_preview, 1)

    def _build_shorts_tab(self):
        self.manuscript_shorts_tab = QWidget()
        row = QHBoxLayout(self.manuscript_shorts_tab)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(12)

        # Left: controls
        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        controls.setMaximumWidth(280)

        self.shorts_quote_text = QTextEdit()
        self.shorts_quote_text.setPlaceholderText(
            "You over-text. You explain yourself. You wait.")
        self.shorts_quote_text.setFixedHeight(90)
        cl.addWidget(field("Quote (also narrated)", self.shorts_quote_text))

        self.shorts_attribution = QLineEdit()
        self.shorts_attribution.setPlaceholderText("You Don't Chase")
        cl.addWidget(field("Attribution (optional)", self.shorts_attribution))

        self.shorts_theme_box = make_theme_box()
        cl.addWidget(field("Theme", self.shorts_theme_box))

        self.shorts_voice_source_box = make_voice_source_box()
        self.shorts_voice_source_box.currentTextChanged.connect(
            self.shorts_load_voices)
        cl.addWidget(field("Voice source", self.shorts_voice_source_box))

        self.shorts_voice_box = QComboBox()
        cl.addWidget(self.shorts_voice_box)

        self.shorts_generate_btn = QPushButton("Generate Short")
        self.shorts_generate_btn.setMinimumHeight(34)
        self.shorts_generate_btn.clicked.connect(self.generate_short)
        cl.addWidget(self.shorts_generate_btn)

        btn_row = QHBoxLayout()
        self.shorts_play_btn = QPushButton("Play")
        self.shorts_play_btn.setEnabled(False)
        self.shorts_play_btn.clicked.connect(self.play_short)
        self.shorts_open_folder_btn = QPushButton("Folder")
        self.shorts_open_folder_btn.clicked.connect(self.open_shorts_folder)
        btn_row.addWidget(self.shorts_play_btn)
        btn_row.addWidget(self.shorts_open_folder_btn)
        cl.addLayout(btn_row)

        cl.addStretch()
        row.addWidget(controls)

        # Right: preview (static frame of the short — no inline video player)
        self.shorts_preview = QLabel("Preview will appear here.")
        self.shorts_preview.setAlignment(Qt.AlignCenter)
        self.shorts_preview.setStyleSheet(
            "background: #1a1a1a; border: 1px solid #333; color: #666;"
        )
        self.shorts_preview.setMinimumSize(320, 320)
        row.addWidget(self.shorts_preview, 1)

        self.shorts_load_voices()

    def _build_calendar_tab(self):
        self.manuscript_calendar_tab = QWidget()
        layout = QVBoxLayout(self.manuscript_calendar_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(QLabel(
            "Builds a posting schedule from the candidates on the Quote Finder "
            "tab — run Suggest Quotes there first."
        ))

        settings_row = QHBoxLayout()
        self.calendar_weeks_box = QComboBox()
        self.calendar_weeks_box.addItems(["1", "2", "4"])
        settings_row.addWidget(field("Weeks", self.calendar_weeks_box))

        self.calendar_start_date = QDateEdit()
        self.calendar_start_date.setDate(QDate.currentDate())
        self.calendar_start_date.setCalendarPopup(True)
        settings_row.addWidget(field("Start", self.calendar_start_date))

        # Grouped under one caption and pinned to the controls' baseline: bare
        # checkboxes in a row of label-above-input fields otherwise float a
        # label's height above everything beside them.
        platforms = QHBoxLayout()
        platforms.setContentsMargins(0, 0, 0, 0)
        platforms.setSpacing(MD)
        self.calendar_tiktok_check = QCheckBox("TikTok")
        self.calendar_tiktok_check.setChecked(True)
        self.calendar_instagram_check = QCheckBox("Instagram")
        self.calendar_instagram_check.setChecked(True)
        self.calendar_pinterest_check = QCheckBox("Pinterest")
        self.calendar_pinterest_check.setChecked(True)
        for check in (self.calendar_tiktok_check, self.calendar_instagram_check,
                      self.calendar_pinterest_check):
            platforms.addWidget(check)
        platform_box = QWidget()
        platform_box.setObjectName("Transparent")
        platform_box.setLayout(platforms)
        settings_row.addWidget(field("Platforms", platform_box))

        settings_row.addStretch()
        layout.addLayout(settings_row)

        settings_row2 = QHBoxLayout()
        self.calendar_theme_box = make_theme_box()
        settings_row2.addWidget(field("Theme", self.calendar_theme_box))

        self.calendar_voice_source_box = make_voice_source_box()
        self.calendar_voice_source_box.currentTextChanged.connect(
            self.calendar_load_voices)
        settings_row2.addWidget(field("Voice", self.calendar_voice_source_box))

        self.calendar_voice_box = QComboBox()
        settings_row2.addWidget(field("Narrator", self.calendar_voice_box))

        self.calendar_attribution = QLineEdit()
        self.calendar_attribution.setPlaceholderText("You Don't Chase")
        settings_row2.addWidget(field("Attribution", self.calendar_attribution))

        settings_row2.addStretch()
        layout.addLayout(settings_row2)

        btn_row = QHBoxLayout()
        self.calendar_generate_btn = QPushButton("Generate Calendar")
        self.calendar_generate_btn.setMinimumHeight(34)
        self.calendar_generate_btn.clicked.connect(self.generate_calendar)
        btn_row.addWidget(self.calendar_generate_btn)

        self.calendar_export_btn = QPushButton("Export Calendar (CSV)")
        self.calendar_export_btn.clicked.connect(self.export_calendar_csv)
        btn_row.addWidget(self.calendar_export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.calendar_table = QTableWidget(0, 6)
        self.calendar_table.setHorizontalHeaderLabels(
            ["Date", "Platform", "Format", "Quote", "Caption", ""])
        self.calendar_table.setColumnWidth(0, 90)
        self.calendar_table.setColumnWidth(1, 80)
        self.calendar_table.setColumnWidth(2, 70)
        self.calendar_table.setColumnWidth(3, 260)
        self.calendar_table.setColumnWidth(5, 40)
        self.calendar_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.calendar_table, 1)

        self._calendar_slots = []
        self.calendar_load_voices()

    # ── shared helpers ──────────────────────────────────────────────────
    def load_models(self) -> None:
        self.manuscript_panel_base.load_models()

    def refresh_connections_status(self):
        """Shows which 3rd-party API keys are actually configured (checked from
        the running process's environment — restart the app after editing .env
        for changes to appear). Services with no API at all (KDP,
        Draft2Digital, IngramSpark, BookBub, TikTok/IG/Pinterest) aren't listed
        here since there's nothing to check — their account-creation steps are
        on the Publishing Todos list below (hover an item for its notes)."""
        while self.manuscript_connections_layout.count():
            item = self.manuscript_connections_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        note = QLabel(
            "API-key-based services only — KDP/Draft2Digital/IngramSpark/"
            "BookBub/social accounts have no API to check; see the Publishing "
            "Todos below for those."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #777; font-size: 11px;")
        self.manuscript_connections_layout.addWidget(note)

        host = self.host
        checks = [
            ("PublishDrive", bool(os.environ.get("PUBLISHDRIVE_API_KEY", "").strip()),
             "publishdrive.com → Settings → API", False),
            ("ElevenLabs", bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()),
             "elevenlabs.io → Profile → API Keys", True),
            ("Anthropic", host.anthropic.key_available(),
             "console.anthropic.com → API Keys", False),
            ("OpenAI", host.openai.key_available(),
             "platform.openai.com → API Keys", False),
            ("DeepSeek", host.deepseek.key_available(),
             "platform.deepseek.com → API Keys", False),
            ("Gemini", host.gemini.key_available(),
             "aistudio.google.com → API Keys", False),
        ]
        for name, connected, where, optional in checks:
            opt_tag = " (optional)" if optional else ""
            if connected:
                text = f"{name}{opt_tag} — connected"
                color = ACCENT
            else:
                text = f"{name}{opt_tag} — not connected · get a key at {where}"
                color = "#999999"
            row = QLabel(text)
            row.setStyleSheet(f"color: {color}; font-size: 12px;")
            self.manuscript_connections_layout.addWidget(row)

    # ── overview: data, ask, todos ──────────────────────────────────────
    def refresh_data(self):
        """Fetch PublishDrive data and display summary."""
        import json
        from agents.manuscript.publishdrive_client import PublishDriveClient
        self.manuscript_status_label.setText("[Fetching…]")
        try:
            client = PublishDriveClient()
            data = client.get_last_30_days()
            self.manuscript_metrics_box.setPlainText(json.dumps(data, indent=2))
            self.manuscript_status_label.setText("[Done] Data refreshed.")
            self._last_data = json.dumps(data)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def ingest_kdp(self):
        """Ingest any new KDP CSV files from data/kdp_reports/."""
        from agents.manuscript.kdp_csv_parser import ingest_new_reports
        ingested = ingest_new_reports()
        if ingested:
            self.manuscript_status_label.setText(
                f"[Done] Ingested: {', '.join(ingested)}")
        else:
            self.manuscript_status_label.setText("[Info] No new KDP reports found.")

    def ask(self):
        """Send a query to ManuscriptAgent with current data as context."""
        query = self.manuscript_query_input.toPlainText().strip()
        if not query:
            return
        provider = self.manuscript_provider_box.currentText()
        model = self.manuscript_model_box.currentText()
        if not model:
            self.manuscript_status_label.setText("[Error] Please select a model.")
            return
        agent = self.host.agent_instances["manuscript"]
        messages = agent.build_messages(query, context_json=self._last_data)
        self.manuscript_status_label.setText("[Thinking…]")
        self.manuscript_ask_btn.setEnabled(False)
        # Keep the token: "manuscript" is shared with the quote-finder and
        # calendar-caption flows. And on refusal, re-enable the button
        # disabled above.
        token = self.host.authorize_request("manuscript", provider, model, query)
        if not token:
            self.manuscript_ask_btn.setEnabled(True)
            self.manuscript_status_label.setText("")
            return
        self._ask_token = token
        worker = self.host._new_chat_worker(provider, model, messages, query)
        self.host.manuscript_worker = worker
        worker.token_signal.connect(self._on_ask_token)
        worker.finished_signal.connect(self._on_ask_finished)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_ask_error)
        worker.start()

    def _on_ask_token(self, token: str):
        cursor = self.manuscript_metrics_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.manuscript_metrics_box.setTextCursor(cursor)

    def _on_ask_finished(self, _full_response: str):
        token, self._ask_token = self._ask_token, None
        if token:
            self.host.record_request(token, _full_response)
        self.manuscript_status_label.setText("[Done]")
        self.manuscript_ask_btn.setEnabled(True)

    def _on_ask_error(self, error: str):
        token, self._ask_token = self._ask_token, None
        if token:
            self.host.abandon_request(token)
        self.manuscript_status_label.setText(f"[Error] {error}")
        self.manuscript_ask_btn.setEnabled(True)

    def add_todo(self):
        title = self.manuscript_todo_input.text().strip()
        if not title:
            return
        from services.database import DB_PATH
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO manuscript_todos (created_at, updated_at, title) "
            "VALUES (?, ?, ?)",
            (now, now, title)
        )
        conn.commit()
        conn.close()
        self.manuscript_todo_input.clear()
        self.load_todos()

    def mark_todo_done(self):
        item = self.manuscript_todo_list.currentItem()
        if not item:
            return
        todo_id = item.data(Qt.UserRole)
        from services.database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE manuscript_todos SET status='done', updated_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), todo_id)
        )
        conn.commit()
        conn.close()
        self.load_todos()

    def load_todos(self):
        from services.database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, title, status, platform, notes FROM manuscript_todos "
            "ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        self.manuscript_todo_list.clear()
        for row_id, title, status, platform, notes in rows:
            # A checkbox glyph pair, not emoji: ✓ and ○ share a baseline and an
            # optical weight, so the list has one left edge. The ℹ️ that used
            # to mark a note sat at the end of the line, at a different size,
            # and only repeated what the tooltip already says.
            check = "✓" if status == "done" else "○"
            tag = f"[{platform}] " if platform else ""
            item = QListWidgetItem(f"{check}  {tag}{title}")
            item.setData(Qt.UserRole, row_id)
            if notes:
                item.setToolTip(notes)
            self.manuscript_todo_list.addItem(item)
        self.host._refresh_next_step_tip()

    # ── quote graphics ──────────────────────────────────────────────────
    def generate_quote_graphic(self):
        quote = self.quote_graphic_text.toPlainText().strip()
        if not quote:
            QMessageBox.warning(self, "Missing Quote", "Please enter a quote.")
            return
        from agents.manuscript.quote_graphics import GRAPHICS_DIR, render_quote_graphic

        attribution = self.quote_graphic_attribution.text().strip()
        theme = theme_key(self.quote_graphic_theme_box)
        size_name = size_key(self.quote_graphic_size_box)
        output_path = unique_output_path(GRAPHICS_DIR, "quote", ".png")
        try:
            render_quote_graphic(quote, output_path, theme=theme,
                                 size_name=size_name, attribution=attribution)
            pixmap = QPixmap(str(output_path))
            scaled = pixmap.scaled(320, 480, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
            self.quote_graphic_preview.setPixmap(scaled)
            self.manuscript_status_label.setText(f"[Done] Saved {output_path.name}")
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def open_graphics_folder(self):
        from agents.manuscript.quote_graphics import GRAPHICS_DIR
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(GRAPHICS_DIR)))

    # ── shorts (ElevenLabs guard shared by three flows) ─────────────────
    def shorts_load_voices(self):
        populate_voice_box(self.shorts_voice_box,
                           self.shorts_voice_source_box.currentText())

    def _authorize_short_narration(self, quote: str, use_elevenlabs: bool) -> bool:
        """Guard the paid branch of a shorts render.

        The default narrator is the free on-device voice; only ElevenLabs
        costs money (billed per character against the account's quota). A
        missing/0 rate means unknown → refuse, like every other per-unit
        path. Keeps the token rather than resolving by agent name —
        "manuscript" is shared by other flows.
        """
        self._shorts_token = None
        if not (use_elevenlabs and os.environ.get("ELEVENLABS_API_KEY")):
            return True   # free on-device narrator, nothing to bill
        from services.per_unit_pricing import elevenlabs_tts_cost_eur
        cost = elevenlabs_tts_cost_eur(len(quote))
        if cost is None:
            QMessageBox.warning(
                self, "No Price Configured",
                "ElevenLabs narration has no per-1k-character rate in "
                "config/pricing.json (elevenlabs_tts_per_1k_chars; 0 means "
                "unknown), so it cannot be billed against the budget caps. "
                "Add a rate, or switch the voice source to the free "
                "on-device narrator.")
            return False
        token = self.host.authorize_request(
            "manuscript", "elevenlabs", "elevenlabs-tts",
            f"short narration · {len(quote)} characters: {quote[:200]}",
            label="short narration", flat_cost_eur=cost)
        if not token:
            return False
        self._shorts_token = token
        return True

    def _shorts_resolve_request(self, completed: bool, detail: str = ""):
        """Close out the narration authorized above, by its own token."""
        token, self._shorts_token = self._shorts_token, None
        if not token:
            return
        if completed:
            self.host.record_request(token, detail or "short narration rendered")
        else:
            self.host.abandon_request(token)

    def generate_short(self):
        quote = self.shorts_quote_text.toPlainText().strip()
        if not quote:
            QMessageBox.warning(self, "Missing Quote", "Please enter a quote.")
            return
        from agents.manuscript.quote_graphics import render_quote_graphic
        from agents.manuscript.shorts_generator import SHORTS_DIR
        from agents.manuscript.workers import ShortsWorker

        attribution = self.shorts_attribution.text().strip()
        theme = theme_key(self.shorts_theme_box)
        use_elevenlabs = self.shorts_voice_source_box.currentText() == "ElevenLabs"
        voice_id = self.shorts_voice_box.currentData() or "default"

        output_path = unique_output_path(SHORTS_DIR, "short", ".mp4")
        image_path = output_path.with_suffix(".png")

        try:
            render_quote_graphic(quote, image_path, theme=theme,
                                 size_name="vertical", attribution=attribution)
            pixmap = QPixmap(str(image_path))
            scaled = pixmap.scaled(320, 480, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
            self.shorts_preview.setPixmap(scaled)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if not self._authorize_short_narration(quote, use_elevenlabs):
            return

        self.shorts_generate_btn.setEnabled(False)
        self.shorts_play_btn.setEnabled(False)
        self._last_short_path = ""
        self.manuscript_status_label.setText("[Narrating…]")

        worker = ShortsWorker(quote, image_path, output_path,
                              use_elevenlabs, voice_id)
        self.host.shorts_worker = worker
        worker.status_signal.connect(self.manuscript_status_label.setText)
        worker.done_signal.connect(self._on_short_done)
        worker.error_signal.connect(self._on_short_error)
        worker.start()

    def _on_short_done(self, output_path: str):
        self._shorts_resolve_request(True, f"saved {Path(output_path).name}")
        self._last_short_path = output_path
        self.manuscript_status_label.setText(
            f"[Done] Saved {Path(output_path).name}")
        self.shorts_generate_btn.setEnabled(True)
        self.shorts_play_btn.setEnabled(True)

    def _on_short_error(self, error: str):
        self._shorts_resolve_request(False)
        self.manuscript_status_label.setText(f"[Error] {error}")
        self.shorts_generate_btn.setEnabled(True)

    def play_short(self):
        if self._last_short_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_short_path))

    def open_shorts_folder(self):
        from agents.manuscript.shorts_generator import SHORTS_DIR
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(SHORTS_DIR)))

    # ── quote finder ────────────────────────────────────────────────────
    def quote_finder_load_voices(self):
        populate_voice_box(self.quote_finder_voice_box,
                           self.quote_finder_voice_source_box.currentText())

    def quote_finder_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Manuscript File", "",
            "Text / Ebook Files (*.txt *.pdf *.epub *.mobi)"
        )
        if not path:
            return
        from services.narrator.converter import load_text
        try:
            text = load_text(Path(path))
            self.quote_finder_text.setPlainText(text)
            self.manuscript_status_label.setText(
                f"[Loaded] {Path(path).name} ({len(text):,} chars)")
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def use_project_draft(self):
        """Explicitly bring Write's current project manuscript into Publish."""
        from services.project_workspaces import load
        from services.project_artifacts import list_for_project

        project = self.host._active_project()
        if not project:
            QMessageBox.information(
                self, "Choose a project", "Select a named Project first.")
            return
        author_panel = getattr(self.host, "author_panel", None)
        if author_panel is not None and author_panel._project_id == project["id"]:
            # A rapid Write → Publish click can arrive before the 700ms
            # autosave fires; read the actual editor, not yesterday's row.
            author_panel._project_save_timer.stop()
            author_panel._persist_project_state()
        text = (load(project["id"], "author").get("draft") or "").strip()
        source = "Write draft"
        if not text:
            for artifact in list_for_project(project["id"], kinds=("draft",)):
                path = Path(artifact["path"])
                if path.is_file():
                    text = path.read_text(encoding="utf-8").strip()
                    source = path.name
                    break
        if not text:
            QMessageBox.information(
                self, "No project draft",
                "This project has no saved Write draft yet. Write in the "
                "Draft tab, or use Load File here.")
            return
        self.quote_finder_text.setPlainText(text)
        if project.get("byline"):
            self.quote_finder_attribution.setText(project["byline"])
        self.manuscript_status_label.setText(
            f"[Loaded] {source} from {project['name']} ({len(text):,} chars)")

    def quote_finder_suggest(self):
        text = self.quote_finder_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Missing Text",
                                "Paste or load manuscript text first.")
            return
        provider = self.manuscript_provider_box.currentText()
        model = self.manuscript_model_box.currentText()
        if not model:
            self.manuscript_status_label.setText(
                "[Error] Select a model on the Overview tab.")
            return
        count = int(self.quote_finder_count_box.currentText())
        # Cap input to keep cost bounded — plenty of text to find a strong
        # batch of quotes.
        truncated = text[:30000]

        agent = self.host.agent_instances["manuscript"]
        messages = agent.build_quote_suggestions_messages(truncated, count=count)
        self.manuscript_status_label.setText("[Finding quotes…]")
        self.quote_finder_suggest_btn.setEnabled(False)
        token = self.host.authorize_request(
            "manuscript", provider, model, truncated)
        if not token:
            self.quote_finder_suggest_btn.setEnabled(True)
            self.manuscript_status_label.setText("")
            return
        self._quote_finder_token = token
        worker = self.host._new_chat_worker(provider, model, messages, truncated)
        self.host.quote_finder_worker = worker
        worker.finished_signal.connect(self._on_quotes_found)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_quotes_error)
        worker.start()

    def _on_quotes_found(self, full_response: str):
        token, self._quote_finder_token = self._quote_finder_token, None
        if token:
            self.host.record_request(token, full_response)
        self.quote_finder_suggest_btn.setEnabled(True)
        quotes = self._parse_quote_list(full_response)
        self.quote_finder_list.clear()
        self._quote_finder_short_buttons = []
        if not quotes:
            self.manuscript_status_label.setText(
                "[Error] Could not parse quotes from response.")
            return
        for q in quotes:
            item = QListWidgetItem()
            row = self._build_quote_suggestion_row(q)
            item.setSizeHint(row.sizeHint())
            self.quote_finder_list.addItem(item)
            self.quote_finder_list.setItemWidget(item, row)
        self.manuscript_status_label.setText(f"[Done] Found {len(quotes)} quotes.")

    def _on_quotes_error(self, error: str):
        token, self._quote_finder_token = self._quote_finder_token, None
        if token:
            self.host.abandon_request(token)
        self.quote_finder_suggest_btn.setEnabled(True)
        self.manuscript_status_label.setText(f"[Error] {error}")

    def _parse_quote_list(self, text: str) -> list:
        from agents.manuscript.llm_parsing import parse_string_list
        return parse_string_list(text)

    def _build_quote_suggestion_row(self, quote: str) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)

        label = QLabel(quote)
        label.setWordWrap(True)
        h.addWidget(label, 1)

        graphic_btn = QPushButton("Graphic")
        graphic_btn.setFixedWidth(78)
        graphic_btn.setToolTip("Generate quote graphic")
        graphic_btn.clicked.connect(
            lambda checked=False, q=quote: self.quote_finder_generate_graphic(q))
        h.addWidget(graphic_btn)

        short_btn = QPushButton("Short")
        short_btn.setFixedWidth(70)
        short_btn.setToolTip("Generate narrated short")
        short_btn.clicked.connect(
            lambda checked=False, q=quote, b=short_btn:
            self.quote_finder_generate_short(q, b))
        h.addWidget(short_btn)
        self._quote_finder_short_buttons.append(short_btn)

        return row

    def quote_finder_generate_graphic(self, quote: str):
        from agents.manuscript.quote_graphics import GRAPHICS_DIR, render_quote_graphic
        theme = theme_key(self.quote_finder_theme_box)
        attribution = self.quote_finder_attribution.text().strip()
        output_path = unique_output_path(GRAPHICS_DIR, "quote", ".png")
        try:
            render_quote_graphic(quote, output_path, theme=theme,
                                 size_name="square", attribution=attribution)
            self.manuscript_status_label.setText(f"[Done] Saved {output_path.name}")
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def quote_finder_generate_short(self, quote: str, button: QPushButton):
        if self._quote_finder_busy:
            QMessageBox.information(
                self, "Busy",
                "A short is already generating — please wait for it to finish.")
            return
        from agents.manuscript.quote_graphics import render_quote_graphic
        from agents.manuscript.shorts_generator import SHORTS_DIR
        from agents.manuscript.workers import ShortsWorker

        theme = theme_key(self.quote_finder_theme_box)
        attribution = self.quote_finder_attribution.text().strip()
        use_elevenlabs = (
            self.quote_finder_voice_source_box.currentText() == "ElevenLabs")
        voice_id = self.quote_finder_voice_box.currentData() or "default"

        output_path = unique_output_path(SHORTS_DIR, "short", ".mp4")
        image_path = output_path.with_suffix(".png")
        try:
            render_quote_graphic(quote, image_path, theme=theme,
                                 size_name="vertical", attribution=attribution)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if not self._authorize_short_narration(quote, use_elevenlabs):
            return

        self._quote_finder_busy = True
        for b in self._quote_finder_short_buttons:
            b.setEnabled(False)
        button.setText("…")
        self.manuscript_status_label.setText("[Narrating…]")

        worker = ShortsWorker(quote, image_path, output_path,
                              use_elevenlabs, voice_id)
        self.host.shorts_worker = worker
        worker.status_signal.connect(self.manuscript_status_label.setText)
        worker.done_signal.connect(
            lambda path, b=button: self._quote_finder_short_done(path, b))
        worker.error_signal.connect(
            lambda err, b=button: self._quote_finder_short_error(err, b))
        worker.start()

    def _quote_finder_short_done(self, output_path: str, button: QPushButton):
        self._shorts_resolve_request(True, f"saved {Path(output_path).name}")
        self._last_short_path = output_path
        self.manuscript_status_label.setText(
            f"[Done] Saved {Path(output_path).name}")
        button.setText("Short")
        self._quote_finder_busy = False
        for b in self._quote_finder_short_buttons:
            b.setEnabled(True)

    def _quote_finder_short_error(self, error: str, button: QPushButton):
        self._shorts_resolve_request(False)
        self.manuscript_status_label.setText(f"[Error] {error}")
        button.setText("⚠")
        self._quote_finder_busy = False
        for b in self._quote_finder_short_buttons:
            b.setEnabled(True)

    # ── calendar ────────────────────────────────────────────────────────
    def calendar_load_voices(self):
        populate_voice_box(self.calendar_voice_box,
                           self.calendar_voice_source_box.currentText())

    def _calendar_quotes_from_finder(self) -> list:
        quotes = []
        for i in range(self.quote_finder_list.count()):
            widget = self.quote_finder_list.itemWidget(self.quote_finder_list.item(i))
            if widget:
                label = widget.findChild(QLabel)
                if label:
                    quotes.append(label.text())
        return quotes

    def generate_calendar(self):
        import json
        quotes = self._calendar_quotes_from_finder()
        if not quotes:
            QMessageBox.warning(
                self, "No Quotes",
                "Run 'Suggest Quotes' on the Quote Finder tab first.")
            return

        platforms = []
        if self.calendar_tiktok_check.isChecked():
            platforms.append("TikTok")
        if self.calendar_instagram_check.isChecked():
            platforms.append("Instagram")
        if self.calendar_pinterest_check.isChecked():
            platforms.append("Pinterest")
        if not platforms:
            QMessageBox.warning(self, "No Platforms",
                                "Select at least one platform.")
            return

        provider = self.manuscript_provider_box.currentText()
        model = self.manuscript_model_box.currentText()
        if not model:
            self.manuscript_status_label.setText(
                "[Error] Select a model on the Overview tab.")
            return

        weeks = int(self.calendar_weeks_box.currentText())
        start_date = self.calendar_start_date.date().toPython()

        from agents.manuscript.content_calendar import build_calendar
        slots = build_calendar(quotes, weeks, start_date, platforms)
        if not slots:
            self.manuscript_status_label.setText(
                "[Error] Could not build a calendar.")
            return
        self._calendar_slots = slots

        items = [{"quote": s.quote, "platform": s.platform.lower()} for s in slots]
        items_json = json.dumps(items)
        agent = self.host.agent_instances["manuscript"]
        messages = agent.build_calendar_caption_messages(items_json)
        self.manuscript_status_label.setText("[Writing captions…]")
        self.calendar_generate_btn.setEnabled(False)
        token = self.host.authorize_request(
            "manuscript", provider, model, items_json)
        if not token:
            self.calendar_generate_btn.setEnabled(True)
            self.manuscript_status_label.setText("")
            return
        self._calendar_captions_token = token
        worker = self.host._new_chat_worker(provider, model, messages, items_json)
        self.host.calendar_worker = worker
        worker.finished_signal.connect(self._on_captions_done)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_captions_error)
        worker.start()

    def _on_captions_done(self, full_response: str):
        token = self._calendar_captions_token
        self._calendar_captions_token = None
        if token:
            self.host.record_request(token, full_response)
        self.calendar_generate_btn.setEnabled(True)
        captions = self._parse_quote_list(full_response)
        for i, slot in enumerate(self._calendar_slots):
            slot.caption = captions[i] if i < len(captions) else ""
        self._populate_calendar_table()
        self.manuscript_status_label.setText(
            f"[Done] {len(self._calendar_slots)}-post calendar generated.")

    def _on_captions_error(self, error: str):
        token = self._calendar_captions_token
        self._calendar_captions_token = None
        if token:
            self.host.abandon_request(token)
        self.calendar_generate_btn.setEnabled(True)
        self._populate_calendar_table()
        self.manuscript_status_label.setText(
            f"[Error] Captions failed ({error}) — schedule shown, captions blank.")

    def _populate_calendar_table(self):
        self.calendar_table.setRowCount(len(self._calendar_slots))
        for row, slot in enumerate(self._calendar_slots):
            self.calendar_table.setItem(row, 0, QTableWidgetItem(
                slot.day.strftime("%Y-%m-%d")))
            self.calendar_table.setItem(row, 1, QTableWidgetItem(slot.platform))
            self.calendar_table.setItem(row, 2, QTableWidgetItem(slot.format))
            self.calendar_table.setItem(row, 3, QTableWidgetItem(slot.quote))
            self.calendar_table.setItem(row, 4, QTableWidgetItem(slot.caption))

            btn = QPushButton(
                "Graphic" if slot.format == "graphic" else "Short")
            btn.setFixedWidth(78)
            btn.clicked.connect(
                lambda checked=False, r=row, b=btn:
                self.calendar_generate_asset(r, b))
            self.calendar_table.setCellWidget(row, 5, btn)

    def calendar_generate_asset(self, row: int, button: QPushButton):
        if row >= len(self._calendar_slots):
            return
        slot = self._calendar_slots[row]
        from agents.manuscript.quote_graphics import render_quote_graphic

        theme = theme_key(self.calendar_theme_box)
        attribution = self.calendar_attribution.text().strip()

        if slot.format == "graphic":
            from agents.manuscript.quote_graphics import GRAPHICS_DIR
            output_path = unique_output_path(GRAPHICS_DIR, "quote", ".png")
            try:
                render_quote_graphic(slot.quote, output_path, theme=theme,
                                     size_name="square", attribution=attribution)
                self.manuscript_status_label.setText(
                    f"[Done] Saved {output_path.name}")
            except Exception as e:
                self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if self._quote_finder_busy:
            QMessageBox.information(
                self, "Busy",
                "A short is already generating — please wait for it to finish.")
            return
        from agents.manuscript.shorts_generator import SHORTS_DIR
        from agents.manuscript.workers import ShortsWorker
        use_elevenlabs = (
            self.calendar_voice_source_box.currentText() == "ElevenLabs")
        voice_id = self.calendar_voice_box.currentData() or "default"
        output_path = unique_output_path(SHORTS_DIR, "short", ".mp4")
        image_path = output_path.with_suffix(".png")
        try:
            render_quote_graphic(slot.quote, image_path, theme=theme,
                                 size_name="vertical", attribution=attribution)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if not self._authorize_short_narration(slot.quote, use_elevenlabs):
            return

        self._quote_finder_busy = True
        button.setEnabled(False)
        self.manuscript_status_label.setText("[Narrating…]")
        worker = ShortsWorker(slot.quote, image_path, output_path,
                              use_elevenlabs, voice_id)
        self.host.shorts_worker = worker
        worker.status_signal.connect(self.manuscript_status_label.setText)
        worker.done_signal.connect(
            lambda path, b=button: self._calendar_short_done(path, b))
        worker.error_signal.connect(
            lambda err, b=button: self._calendar_short_error(err, b))
        worker.start()

    def _calendar_short_done(self, output_path: str, button: QPushButton):
        self._shorts_resolve_request(True, f"saved {Path(output_path).name}")
        self._last_short_path = output_path
        self.manuscript_status_label.setText(
            f"[Done] Saved {Path(output_path).name}")
        button.setEnabled(True)
        self._quote_finder_busy = False

    def _calendar_short_error(self, error: str, button: QPushButton):
        self._shorts_resolve_request(False)
        self.manuscript_status_label.setText(f"[Error] {error}")
        button.setEnabled(True)
        self._quote_finder_busy = False

    def export_calendar_csv(self):
        if not self._calendar_slots:
            QMessageBox.warning(self, "No Calendar", "Generate a calendar first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Calendar",
            str(user_data_base() / "content_calendar.csv"), "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Platform", "Format", "Quote", "Caption"])
            for slot in self._calendar_slots:
                writer.writerow([slot.day.strftime("%Y-%m-%d"), slot.platform,
                                 slot.format, slot.quote, slot.caption])
        self.manuscript_status_label.setText(
            f"[Done] Exported calendar to {Path(path).name}")
