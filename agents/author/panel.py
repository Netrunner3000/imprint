"""Book Author workspace and its guarded write/publish/market lifecycles.

Phase 4 extraction: the project bar, book profile, the Write page
(compose deck, manuscript tabs, document bar) and the Publish & Market
pages with every handler moved here from main.py. The host supplies
shared budget authorization, usage records, the chat-worker factory and
the cross-panel next-step advisor (`_refresh_next_step_tip` stays on the
umbrella — Publishing Manager shares its banner); the three workers stay
host attributes so the global Stop chain and shutdown sweep keep seeing
them.

Request tokens live on this panel: "author" is shared by the write,
publish and market flows, so nothing here resolves a request by agent
name — and a starter never replaces a still-running worker (dropping a
live QThread aborts the app).

The responsive document bar is handled by this widget's own resizeEvent
instead of the application-level event filter the umbrella used to run.
"""

import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSizePolicy, QStackedWidget, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from services.runtime_paths import user_data_base
from ui.forms import (
    LG, MD, SM, XS, combo, field, form_grid, line_edit, micro, quiet, section,
)
from ui.panels.base import AgentPanel
from ui.style import TEXT_MUTE


class AuthorPanel(QWidget):
    """The manuscript workbench: write, then publish, then market."""

    HOST_CONTROLS = (
        "author_title_input", "author_name_input", "author_content_type_box",
        "author_genre_box", "author_tone_box", "author_pov_box",
        "author_next_step_label", "author_profile_section",
        "author_profile_hook_input", "author_profile_reader_input",
        "author_profile_comps_input", "author_profile_path_box",
        "author_profile_save_btn", "author_compose_card",
        "author_direction_input", "author_direction_field", "author_task_box",
        "author_task_field", "author_panel_base", "author_provider_box",
        "author_model_box", "author_provider_field", "author_model_field",
        "author_compose_actions", "author_write_btn", "author_continue_btn",
        "author_stop_btn", "author_compose_grid", "author_tabs",
        "author_draft_box", "author_outline_box", "author_characters_box",
        "author_world_box", "author_chapters_tab",
        "author_chapters_stats_label", "author_chapters_list",
        "author_word_metric", "author_word_count_label", "author_scene_metric",
        "author_scene_count_label", "author_save_btn", "author_export_label",
        "author_export_author_input", "author_export_format_box",
        "author_export_btn", "author_clear_btn", "author_document_bar",
        "author_mode_write_btn", "author_mode_pubmkt_btn",
        "author_content_stack", "author_sub_publish_btn",
        "author_sub_market_btn", "author_sub_stack", "author_pub_type_box",
        "author_pub_wordcount_input", "author_pub_comps_input",
        "author_pub_pitch_tone_box", "author_pub_notes_input",
        "author_pub_generate_btn", "author_pub_stop_btn",
        "author_pub_copy_btn", "author_pub_save_btn", "author_pub_output",
        "author_mkt_platform_box", "author_mkt_hook_input",
        "author_mkt_comps_input", "author_mkt_tone_box",
        "author_mkt_notes_input", "author_mkt_generate_btn",
        "author_mkt_stop_btn", "author_mkt_copy_btn", "author_mkt_save_btn",
        "author_mkt_output", "author_status_label",
    )

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._write_token = None
        self._pub_token = None
        self._mkt_token = None
        self._last_response = ""
        self._is_continuing = False
        self._chapter_offsets: list = []
        self._layout_state = None
        self._project_id: str | None = None
        self._last_project_identity = ("", "")
        self._unfiled_state: dict | None = None
        self._loading_project_state = False
        self._project_save_timer = QTimer(self)
        self._project_save_timer.setSingleShot(True)
        self._project_save_timer.setInterval(700)
        self._project_save_timer.timeout.connect(self._persist_project_state)
        self.setObjectName("AuthorPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Project bar ──────────────────────────────────────────────────────
        # A grid, not a FlowLayout. FlowLayout packs each control against the
        # previous one, so "Tone:" and "POV:" landed at whatever x the row
        # before them happened to end on — which is most of why this screen
        # read as ragged. Equal column stretch puts row two's labels directly
        # under row one's.
        project_bar = QWidget()
        project_bar.setObjectName("AuthorProjectBar")

        self.author_title_input = line_edit("Project title…")
        self.author_name_input = line_edit("Pen name…")
        self.author_content_type_box = combo(["Fiction", "Non-Fiction"])
        self.author_content_type_box.currentTextChanged.connect(
            self._on_content_type_changed)
        self.author_genre_box = combo([
            "Literary Fiction", "Thriller", "Fantasy", "Sci-Fi", "Horror",
            "Romance", "Historical", "Mystery", "Short Story", "Screenplay",
            "Poetry", "Blog / Essay", "Other",
        ])
        self.author_tone_box = combo([
            "Neutral", "Dark", "Humorous", "Lyrical", "Tense", "Romantic",
            "Gritty", "Whimsical", "Philosophical", "Commercial",
        ])
        self.author_pov_box = combo([
            "Third Person Limited", "First Person",
            "Third Person Omniscient", "Second Person",
        ])

        # At desktop width these six short identity fields belong on one line.
        # The old 3×2 grid spent a quarter of the available canvas on empty
        # input width and pushed the actual manuscript below the fold.
        pb_layout = form_grid([
            ("Title", self.author_title_input),
            ("Author", self.author_name_input),
            ("Type", self.author_content_type_box),
            ("Genre", self.author_genre_box),
            ("Tone", self.author_tone_box),
            ("Point of view", self.author_pov_box),
        ], columns=6)
        pb_layout.setContentsMargins(MD, SM, MD, SM)
        project_bar.setLayout(pb_layout)

        layout.addWidget(project_bar)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        divider.setObjectName("CardDivider")
        layout.addWidget(divider)

        self.author_next_step_label = QLabel("")
        self.author_next_step_label.setWordWrap(True)
        self.author_next_step_label.setObjectName("NextStepBanner")
        layout.addWidget(self.author_next_step_label)

        # ── Book Profile (collapsed by default — persisted, injected into every mode) ──
        from ui.widgets import CollapsibleSection
        self.author_profile_section = CollapsibleSection(
            "Book Profile", expanded=False)

        self.author_profile_hook_input = QLineEdit()
        self.author_profile_hook_input.setPlaceholderText(
            "One-sentence pitch — the core promise of the book…")
        self.author_profile_reader_input = QLineEdit()
        self.author_profile_reader_input.setPlaceholderText(
            "e.g. Women 25-40 navigating modern dating apps")
        self.author_profile_comps_input = QLineEdit()
        self.author_profile_comps_input.setPlaceholderText(
            "e.g. For readers of [Title A] and [Title B]")
        self.author_profile_path_box = QComboBox()
        self.author_profile_path_box.addItems(
            ["Undecided", "Self-Publishing (KDP)", "Traditional"])

        profile_form = QWidget()
        profile_form.setObjectName("AuthorProfileForm")
        profile_grid = QGridLayout(profile_form)
        profile_grid.setContentsMargins(MD, XS, MD, SM)
        profile_grid.setHorizontalSpacing(MD)
        profile_grid.setVerticalSpacing(0)
        profile_grid.addWidget(field("Hook", self.author_profile_hook_input), 0, 0)
        profile_grid.addWidget(field("Target reader", self.author_profile_reader_input), 0, 1)
        profile_grid.addWidget(field("Comp titles", self.author_profile_comps_input), 0, 2)
        profile_grid.addWidget(field("Publishing path", self.author_profile_path_box), 0, 3)
        self.author_profile_save_btn = QPushButton("Save Profile")
        self.author_profile_save_btn.clicked.connect(self.save_profile)
        self.author_profile_save_btn.setMinimumWidth(120)
        profile_grid.addWidget(self.author_profile_save_btn, 0, 4, Qt.AlignBottom)
        for column in range(4):
            profile_grid.setColumnStretch(column, 1)
        self.author_profile_section.addWidget(profile_form)

        layout.addWidget(self.author_profile_section)

        # ── Main workspace ────────────────────────────────────────────────────
        # Compose is a shallow deck above the document, not a second vertical
        # application squeezed into a narrow scrolling sidebar. The previous
        # sidebar made Direction, Task and Model mutually invisible at laptop
        # height and stole a quarter of the writing canvas.
        write_page = QWidget()
        write_page.setObjectName("AuthorWritePage")
        write_layout = QVBoxLayout(write_page)
        write_layout.setContentsMargins(0, 0, 0, 0)
        write_layout.setSpacing(SM)

        compose_card = QFrame()
        compose_card.setObjectName("AuthorComposeCard")
        self.author_compose_card = compose_card
        compose_layout = QVBoxLayout(compose_card)
        compose_layout.setContentsMargins(MD, SM, MD, SM)
        compose_layout.setSpacing(SM)
        compose_layout.addWidget(section("Compose"))

        compose_grid = QGridLayout()
        compose_grid.setHorizontalSpacing(MD)
        compose_grid.setVerticalSpacing(0)

        self.author_direction_input = QLineEdit()
        self.author_direction_input.setPlaceholderText(
            "What happens next? One concrete instruction beats a paragraph."
        )
        self.author_direction_field = field(
            "Direction", self.author_direction_input)
        compose_grid.addWidget(self.author_direction_field, 0, 0)

        self.author_task_box = QComboBox()
        # Populated by _on_content_type_changed() after construction.
        self.author_task_field = field("Task", self.author_task_box)
        compose_grid.addWidget(self.author_task_field, 0, 1)

        self.author_panel_base = AgentPanel(
            host, "author",
            providers=("ollama", "openai", "deepseek", "kimi", "gemini",
                       "anthropic", "qwen"),
            default_provider="anthropic")
        self.author_provider_box = self.author_panel_base.provider_box
        self.author_model_box = self.author_panel_base.model_box
        self.author_provider_field = field("Provider", self.author_provider_box)
        self.author_model_field = field("Model", self.author_model_box)
        compose_grid.addWidget(self.author_provider_field, 0, 2)
        compose_grid.addWidget(self.author_model_field, 0, 3)

        self.author_compose_actions = QWidget()
        compose_actions = QHBoxLayout(self.author_compose_actions)
        compose_actions.setContentsMargins(0, 0, 0, 0)
        compose_actions.setSpacing(SM)
        self.author_write_btn = QPushButton("Write")
        self.author_write_btn.setObjectName("PrimaryAction")
        self.author_write_btn.setMinimumWidth(130)
        self.author_write_btn.clicked.connect(self.write)
        compose_actions.addWidget(self.author_write_btn)

        self.author_continue_btn = QPushButton("Continue")
        self.author_continue_btn.setObjectName("SecondaryAction")
        self.author_continue_btn.clicked.connect(self.continue_draft)
        compose_actions.addWidget(self.author_continue_btn)

        self.author_stop_btn = QPushButton("Stop")
        self.author_stop_btn.setEnabled(False)
        self.author_stop_btn.setObjectName("DangerAction")
        self.author_stop_btn.clicked.connect(self.stop)
        compose_actions.addWidget(self.author_stop_btn)
        compose_actions.addStretch()
        compose_grid.addWidget(
            self.author_compose_actions, 0, 4, Qt.AlignBottom)

        compose_grid.setColumnStretch(0, 3)
        compose_grid.setColumnStretch(1, 1)
        compose_grid.setColumnStretch(2, 1)
        compose_grid.setColumnStretch(3, 2)
        compose_grid.setColumnStretch(4, 0)
        self.author_compose_grid = compose_grid
        compose_layout.addLayout(compose_grid)
        write_layout.addWidget(compose_card)

        # The manuscript is the dominant surface and always remains visible.
        self.author_tabs = QTabWidget()

        self.author_draft_box = QTextEdit()
        self.author_draft_box.setPlaceholderText(
            "Your draft appears here. You can type and edit directly alongside the AI."
        )
        self.author_tabs.addTab(self.author_draft_box, "Draft")

        self.author_outline_box = QTextEdit()
        self.author_outline_box.setPlaceholderText("Chapter and scene outline…")
        self.author_tabs.addTab(self.author_outline_box, "Outline")

        self.author_characters_box = QTextEdit()
        self.author_characters_box.setPlaceholderText(
            "Character profiles, arcs, relationships…")
        self.author_tabs.addTab(self.author_characters_box, "Characters")

        self.author_world_box = QTextEdit()
        self.author_world_box.setPlaceholderText(
            "World-building notes, lore, setting, rules…")
        self.author_tabs.addTab(self.author_world_box, "World Notes")

        self.author_chapters_tab = QWidget()
        ct_layout = QVBoxLayout(self.author_chapters_tab)
        ct_layout.setContentsMargins(6, 6, 6, 6)
        ct_layout.setSpacing(6)

        self.author_chapters_stats_label = QLabel("No chapters detected yet.")
        self.author_chapters_stats_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_MUTE};")
        ct_layout.addWidget(self.author_chapters_stats_label)

        self.author_chapters_list = QListWidget()
        self.author_chapters_list.itemDoubleClicked.connect(self._jump_to_chapter)
        ct_layout.addWidget(self.author_chapters_list, 1)

        author_chapters_refresh_btn = QPushButton("Refresh Chapters")
        author_chapters_refresh_btn.clicked.connect(self._refresh_chapters)
        ct_layout.addWidget(author_chapters_refresh_btn)

        self.author_tabs.addTab(self.author_chapters_tab, "Chapters")
        self.author_tabs.currentChanged.connect(self._on_tab_changed)

        write_layout.addWidget(self.author_tabs, 1)

        # Document actions stay in one predictable footer. Counts are compact
        # status chips; they no longer occupy two stacked group boxes.
        document_bar = QFrame()
        document_bar.setObjectName("AuthorDocumentBar")
        document_actions = QHBoxLayout(document_bar)
        document_actions.setContentsMargins(MD, SM, MD, SM)
        document_actions.setSpacing(SM)

        self.author_word_metric = QWidget()
        self.author_word_metric.setObjectName("CompactMetric")
        word_metric_layout = QHBoxLayout(self.author_word_metric)
        word_metric_layout.setContentsMargins(SM, 0, SM, 0)
        word_metric_layout.setSpacing(SM)
        word_metric_layout.addWidget(micro("Words"))
        self.author_word_count_label = QLabel("0")
        self.author_word_count_label.setObjectName("CompactMetricValue")
        word_metric_layout.addWidget(self.author_word_count_label)
        document_actions.addWidget(self.author_word_metric)

        self.author_scene_metric = QWidget()
        self.author_scene_metric.setObjectName("CompactMetric")
        scene_metric_layout = QHBoxLayout(self.author_scene_metric)
        scene_metric_layout.setContentsMargins(SM, 0, SM, 0)
        scene_metric_layout.setSpacing(SM)
        scene_metric_layout.addWidget(micro("Scenes"))
        self.author_scene_count_label = QLabel("0")
        self.author_scene_count_label.setObjectName("CompactMetricValue")
        scene_metric_layout.addWidget(self.author_scene_count_label)
        document_actions.addWidget(self.author_scene_metric)

        self.author_save_btn = QPushButton("Save Draft")
        self.author_save_btn.setEnabled(False)
        self.author_save_btn.clicked.connect(self.save_draft)
        document_actions.addWidget(self.author_save_btn)

        document_actions.addStretch()
        self.author_export_label = micro("Export")
        document_actions.addWidget(self.author_export_label)

        self.author_export_author_input = QLineEdit()
        self.author_export_author_input.setPlaceholderText("Author name")
        self.author_export_author_input.setMinimumWidth(100)
        self.author_export_author_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed)
        document_actions.addWidget(self.author_export_author_input, 1)

        self.author_export_format_box = QComboBox()
        self.author_export_format_box.setObjectName("CompactCombo")
        self.author_export_format_box.addItems(["EPUB", "DOCX", "PDF"])
        self.author_export_format_box.setFixedWidth(100)
        document_actions.addWidget(self.author_export_format_box)
        self.author_export_btn = QPushButton("Export Book")
        self.author_export_btn.clicked.connect(self.export_book)
        document_actions.addWidget(self.author_export_btn)

        self.author_clear_btn = quiet("Clear")
        self.author_clear_btn.setFixedWidth(62)
        self.author_clear_btn.clicked.connect(self.clear)
        document_actions.addWidget(self.author_clear_btn)
        self.author_document_bar = document_bar
        self.author_document_bar.setFixedHeight(58)
        write_layout.addWidget(document_bar)

        # ── Mode toggle row: Write | Publish & Market ────────────────────────
        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)

        self.author_mode_write_btn = QPushButton("Write")
        self.author_mode_write_btn.setCheckable(True)
        self.author_mode_write_btn.setChecked(True)
        self.author_mode_write_btn.setMinimumHeight(32)
        self.author_mode_write_btn.setObjectName("WorkspaceTool")
        self.author_mode_write_btn.clicked.connect(lambda: self.set_mode("write"))
        mode_row.addWidget(self.author_mode_write_btn)

        # "&&", not "&": Qt reads a single ampersand in button text as a mnemonic
        # marker and swallows it, so this rendered as "Publish_Market" with the
        # M underlined. Same trap CollapsibleSection documents for its titles.
        self.author_mode_pubmkt_btn = QPushButton("Publish && Market")
        self.author_mode_pubmkt_btn.setCheckable(True)
        self.author_mode_pubmkt_btn.setMinimumHeight(32)
        self.author_mode_pubmkt_btn.setObjectName("WorkspaceTool")
        self.author_mode_pubmkt_btn.clicked.connect(lambda: self.set_mode("pubmkt"))
        mode_row.addWidget(self.author_mode_pubmkt_btn)
        mode_row.addStretch()

        layout.addLayout(mode_row)

        # ── Content stack (Write / Publish & Market) ─────────────────────────
        self.author_content_stack = QStackedWidget()
        self.author_content_stack.addWidget(write_page)   # page 0: write

        # ── Publish & Market composite widget ────────────────────────────────
        pubmkt_widget = QWidget()
        pm_layout = QVBoxLayout(pubmkt_widget)
        pm_layout.setContentsMargins(0, 4, 0, 0)
        pm_layout.setSpacing(6)

        # Sub-mode toggle: Publish | Market
        sub_row = QHBoxLayout()
        sub_row.setSpacing(0)

        self.author_sub_publish_btn = QPushButton("Publish")
        self.author_sub_publish_btn.setCheckable(True)
        self.author_sub_publish_btn.setChecked(True)
        self.author_sub_publish_btn.setMinimumHeight(28)
        self.author_sub_publish_btn.setObjectName("WorkspaceTool")
        self.author_sub_publish_btn.clicked.connect(
            lambda: self.set_sub_mode("publish"))
        sub_row.addWidget(self.author_sub_publish_btn)

        self.author_sub_market_btn = QPushButton("Market")
        self.author_sub_market_btn.setCheckable(True)
        self.author_sub_market_btn.setMinimumHeight(28)
        self.author_sub_market_btn.setObjectName("WorkspaceTool")
        self.author_sub_market_btn.clicked.connect(
            lambda: self.set_sub_mode("market"))
        sub_row.addWidget(self.author_sub_market_btn)
        sub_row.addStretch()

        pm_layout.addLayout(sub_row)

        self.author_sub_stack = QStackedWidget()

        # ── Publish page ──────────────────────────────────────────────────────
        publish_page = QWidget()
        pub_outer = QVBoxLayout(publish_page)
        pub_outer.setContentsMargins(0, 0, 0, 0)
        pub_outer.setSpacing(SM)

        pub_ctrl = QFrame()
        pub_ctrl.setObjectName("AuthorPubCtrl")
        pc = QVBoxLayout(pub_ctrl)
        pc.setContentsMargins(MD, SM, MD, SM)
        pc.setSpacing(SM)

        self.author_pub_type_box = QComboBox()
        self.author_pub_type_box.addItems([
            "Synopsis — 1 Page", "Synopsis — 3 Page", "Query Letter",
            "Book Proposal", "Back-Cover Blurb", "Author Bio", "Chapter Breakdown",
        ])
        self.author_pub_wordcount_input = QLineEdit()
        self.author_pub_wordcount_input.setPlaceholderText("e.g. 80,000")
        self.author_pub_comps_input = QLineEdit()
        self.author_pub_comps_input.setPlaceholderText(
            "e.g. Gone Girl meets Dark Places")
        self.author_pub_pitch_tone_box = QComboBox()
        self.author_pub_pitch_tone_box.addItems(
            ["Professional", "Conversational", "High-Concept"])
        self.author_pub_notes_input = QTextEdit()
        self.author_pub_notes_input.setPlaceholderText(
            "Target audience, themes, hook, extra context…")
        self.author_pub_notes_input.setFixedHeight(52)

        pub_fields = QGridLayout()
        pub_fields.setHorizontalSpacing(MD)
        pub_fields.setVerticalSpacing(0)
        pub_fields.addWidget(field("Output Type", self.author_pub_type_box), 0, 0)
        pub_fields.addWidget(field("Word Count Target", self.author_pub_wordcount_input), 0, 1)
        pub_fields.addWidget(field("Comp Titles", self.author_pub_comps_input), 0, 2)
        pub_fields.addWidget(field("Pitch Tone", self.author_pub_pitch_tone_box), 0, 3)
        pub_fields.addWidget(field("Extra Notes", self.author_pub_notes_input), 0, 4, 1, 2)
        for column in range(6):
            pub_fields.setColumnStretch(column, 1)
        pc.addLayout(pub_fields)

        pub_actions = QHBoxLayout()
        pub_actions.setSpacing(SM)

        self.author_pub_generate_btn = QPushButton("Generate")
        self.author_pub_generate_btn.setMinimumWidth(130)
        self.author_pub_generate_btn.setObjectName("PrimaryAction")
        self.author_pub_generate_btn.clicked.connect(self.pub_generate)
        pub_actions.addWidget(self.author_pub_generate_btn)

        self.author_pub_stop_btn = QPushButton("Stop")
        self.author_pub_stop_btn.setEnabled(False)
        self.author_pub_stop_btn.setObjectName("DangerAction")
        self.author_pub_stop_btn.clicked.connect(self.pub_stop)
        pub_actions.addWidget(self.author_pub_stop_btn)

        self.author_pub_copy_btn = QPushButton("Copy to Clipboard")
        self.author_pub_copy_btn.clicked.connect(self.pub_copy)
        pub_actions.addWidget(self.author_pub_copy_btn)

        self.author_pub_save_btn = QPushButton("Save as File")
        self.author_pub_save_btn.setEnabled(False)
        self.author_pub_save_btn.clicked.connect(self.pub_save)
        pub_actions.addWidget(self.author_pub_save_btn)
        pub_actions.addStretch()
        pc.addLayout(pub_actions)

        pub_outer.addWidget(pub_ctrl)

        self.author_pub_output = QTextEdit()
        self.author_pub_output.setPlaceholderText(
            "Generated publishing document appears here. Fully editable."
        )
        pub_outer.addWidget(self.author_pub_output, 1)

        self.author_sub_stack.addWidget(publish_page)   # sub-page 0

        # ── Market page ───────────────────────────────────────────────────────
        market_page = QWidget()
        mkt_outer = QVBoxLayout(market_page)
        mkt_outer.setContentsMargins(0, 0, 0, 0)
        mkt_outer.setSpacing(SM)

        mkt_ctrl = QFrame()
        mkt_ctrl.setObjectName("AuthorMktCtrl")
        mc = QVBoxLayout(mkt_ctrl)
        mc.setContentsMargins(MD, SM, MD, SM)
        mc.setSpacing(SM)

        self.author_mkt_platform_box = QComboBox()
        self.author_mkt_platform_box.addItems([
            "Amazon Description", "KDP Listing", "Goodreads Blurb", "Instagram Post",
            "Twitter / X Thread", "TikTok Caption", "Pinterest Pin Description",
            "YouTube Description", "Newsletter", "Press Release", "Book Club Questions",
            "ARC Outreach Email", "Launch Team Email", "Podcast Pitch", "Author Website Bio",
        ])
        self.author_mkt_hook_input = QLineEdit()
        self.author_mkt_hook_input.setPlaceholderText("One sentence that sells the book")
        self.author_mkt_comps_input = QLineEdit()
        self.author_mkt_comps_input.setPlaceholderText(
            "e.g. Reaper's Creek meets Harlan Coben")
        self.author_mkt_tone_box = QComboBox()
        self.author_mkt_tone_box.addItems(
            ["Punchy", "Literary", "Warm", "Hype", "Mysterious"])
        self.author_mkt_notes_input = QTextEdit()
        self.author_mkt_notes_input.setPlaceholderText(
            "Target audience, mood, key themes…")
        self.author_mkt_notes_input.setFixedHeight(52)

        mkt_fields = QGridLayout()
        mkt_fields.setHorizontalSpacing(MD)
        mkt_fields.setVerticalSpacing(0)
        mkt_fields.addWidget(field("Platform", self.author_mkt_platform_box), 0, 0)
        mkt_fields.addWidget(field("Hook / Logline", self.author_mkt_hook_input), 0, 1)
        mkt_fields.addWidget(field("Comp Titles", self.author_mkt_comps_input), 0, 2)
        mkt_fields.addWidget(field("Tone", self.author_mkt_tone_box), 0, 3)
        mkt_fields.addWidget(field("Extra Notes", self.author_mkt_notes_input), 0, 4, 1, 2)
        for column in range(6):
            mkt_fields.setColumnStretch(column, 1)
        mc.addLayout(mkt_fields)

        mkt_actions = QHBoxLayout()
        mkt_actions.setSpacing(SM)

        self.author_mkt_generate_btn = QPushButton("Generate")
        self.author_mkt_generate_btn.setMinimumWidth(130)
        self.author_mkt_generate_btn.setObjectName("PrimaryAction")
        self.author_mkt_generate_btn.clicked.connect(self.mkt_generate)
        mkt_actions.addWidget(self.author_mkt_generate_btn)

        self.author_mkt_stop_btn = QPushButton("Stop")
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_mkt_stop_btn.setObjectName("DangerAction")
        self.author_mkt_stop_btn.clicked.connect(self.mkt_stop)
        mkt_actions.addWidget(self.author_mkt_stop_btn)

        self.author_mkt_copy_btn = QPushButton("Copy to Clipboard")
        self.author_mkt_copy_btn.clicked.connect(self.mkt_copy)
        mkt_actions.addWidget(self.author_mkt_copy_btn)

        self.author_mkt_save_btn = QPushButton("Save as File")
        self.author_mkt_save_btn.setEnabled(False)
        self.author_mkt_save_btn.clicked.connect(self.mkt_save)
        mkt_actions.addWidget(self.author_mkt_save_btn)
        mkt_actions.addStretch()
        mc.addLayout(mkt_actions)

        mkt_outer.addWidget(mkt_ctrl)

        self.author_mkt_output = QTextEdit()
        self.author_mkt_output.setPlaceholderText(
            "Generated marketing copy appears here. Fully editable."
        )
        mkt_outer.addWidget(self.author_mkt_output, 1)

        self.author_sub_stack.addWidget(market_page)   # sub-page 1

        pm_layout.addWidget(self.author_sub_stack, 1)
        self.author_content_stack.addWidget(pubmkt_widget)   # page 1

        layout.addWidget(self.author_content_stack, 1)

        self.author_status_label = QLabel("")
        self.author_status_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_MUTE}; padding: 2px 4px;")
        layout.addWidget(self.author_status_label)

        self.author_draft_box.textChanged.connect(self._update_counts)

        # Aliases retired 2026-09-21: shared wiring resolves controls
        # through host._find_control(); HOST_CONTROLS stays as the
        # published contract of what this panel owns.
        host.author_panel = self
        host.author_worker = None
        host.author_pub_worker = None
        host.author_mkt_worker = None

        # Apply the compact state once during construction; later window
        # changes are handled by this widget's own resizeEvent.
        self._adapt_layout(self.width())

        self.hide()

        self.author_panel_base.load_models()

        self._on_content_type_changed(self.author_content_type_box.currentText())
        self._load_profile()
        for widget in (
            self.author_title_input, self.author_name_input,
            self.author_profile_hook_input, self.author_profile_reader_input,
            self.author_profile_comps_input, self.author_export_author_input,
        ):
            widget.textChanged.connect(self._schedule_project_save)
        for widget in (
            self.author_draft_box, self.author_outline_box,
            self.author_characters_box, self.author_world_box,
        ):
            widget.textChanged.connect(self._schedule_project_save)
        for widget in (
            self.author_content_type_box, self.author_genre_box,
            self.author_tone_box, self.author_pov_box,
            self.author_profile_path_box,
        ):
            widget.currentTextChanged.connect(self._schedule_project_save)

    # ── responsive footer ───────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Defer until Qt has finished the resize pass. Changing visibility
        # while a layout is calculating its geometry can otherwise leave
        # controls at their previous positions for one frame.
        width = event.size().width()
        QTimer.singleShot(0, lambda w=width: self._adapt_layout(w))

    def _adapt_layout(self, width: int):
        """Keep the document actions usable when the centre pane is narrow."""
        if not hasattr(self, "author_document_bar"):
            return

        compact = width < 660
        compose_stacked = width < 1000
        layout_state = (compact, compose_stacked)
        if layout_state == self._layout_state:
            return
        self._layout_state = layout_state

        # At desktop width Compose is one clean command strip.  On narrower
        # windows the buttons move below the fields instead of crushing model
        # names or leaving the direction box only a few pixels tall.
        if compose_stacked:
            self.author_compose_grid.addWidget(
                self.author_compose_actions, 1, 0, 1, 5, Qt.AlignLeft)
        else:
            self.author_compose_grid.addWidget(
                self.author_compose_actions, 0, 4, Qt.AlignBottom)

        # Counts and metadata are useful context at normal desktop sizes, but
        # the primary Save / format / Export path must win when rails leave the
        # workbench only a few hundred pixels wide.
        for widget in (
            self.author_word_metric,
            self.author_scene_metric,
            self.author_export_label,
            self.author_export_author_input,
            self.author_clear_btn,
        ):
            widget.setVisible(not compact)

        layout = self.author_document_bar.layout()
        if compact:
            layout.setContentsMargins(XS, SM, XS, SM)
            layout.setSpacing(XS)
            self.author_save_btn.setText("Save")
            self.author_save_btn.setFixedWidth(58)
            self.author_export_btn.setText("Export")
            self.author_export_btn.setFixedWidth(68)
            self.author_export_format_box.setFixedWidth(86)
        else:
            layout.setContentsMargins(MD, SM, MD, SM)
            layout.setSpacing(SM)
            self.author_save_btn.setText("Save Draft")
            self.author_save_btn.setMinimumWidth(0)
            self.author_save_btn.setMaximumWidth(16777215)
            self.author_export_btn.setText("Export Book")
            self.author_export_btn.setMinimumWidth(0)
            self.author_export_btn.setMaximumWidth(16777215)
            self.author_export_format_box.setFixedWidth(100)

    # ── project bar and profile ─────────────────────────────────────────
    def load_models(self) -> None:
        self.author_panel_base.load_models()

    def _on_content_type_changed(self, content_type: str):
        fiction_tasks = [
            "Write Scene", "Continue Draft", "Generate Outline",
            "Develop Characters", "Build World", "Write Dialogue", "Revise / Improve",
        ]
        nonfiction_tasks = [
            "Write Chapter", "Continue Draft", "Generate Outline",
            "Strengthen Argument", "Add Case Study / Example", "Tighten Structure", "Revise / Improve",
        ]
        tasks = nonfiction_tasks if content_type == "Non-Fiction" else fiction_tasks
        current = self.author_task_box.currentText()
        self.author_task_box.blockSignals(True)
        self.author_task_box.clear()
        self.author_task_box.addItems(tasks)
        if current in tasks:
            self.author_task_box.setCurrentText(current)
        self.author_task_box.blockSignals(False)

    def get_book_profile(self) -> dict:
        return {
            "title": self.author_title_input.text().strip(),
            "author": self.author_name_input.text().strip(),
            "content_type": self.author_content_type_box.currentText(),
            "genre": self.author_genre_box.currentText(),
            "hook": self.author_profile_hook_input.text().strip(),
            "target_reader": self.author_profile_reader_input.text().strip(),
            "comp_titles": self.author_profile_comps_input.text().strip(),
            "publishing_path": self.author_profile_path_box.currentText(),
        }

    def _capture_project_state(self) -> dict:
        return {
            "profile": self.get_book_profile(),
            "tone": self.author_tone_box.currentText(),
            "pov": self.author_pov_box.currentText(),
            "draft": self.author_draft_box.toPlainText(),
            "outline": self.author_outline_box.toPlainText(),
            "characters": self.author_characters_box.toPlainText(),
            "world": self.author_world_box.toPlainText(),
            "export_author": self.author_export_author_input.text(),
        }

    def _apply_project_state(self, state: dict, project: dict | None = None) -> None:
        """Restore one workspace without carrying another book into it."""
        self._loading_project_state = True
        try:
            profile = state.get("profile") or {}
            project = project or {}
            self.author_title_input.setText(
                project.get("work_title") if project else profile.get("title") or "")
            self.author_name_input.setText(
                project.get("byline") if project else profile.get("author") or "")
            self.author_content_type_box.setCurrentText(
                profile.get("content_type") or "Fiction")
            self.author_genre_box.setCurrentText(
                profile.get("genre") or "Literary Fiction")
            self.author_tone_box.setCurrentText(state.get("tone") or "Neutral")
            self.author_pov_box.setCurrentText(
                state.get("pov") or "Third Person Limited")
            self.author_profile_hook_input.setText(profile.get("hook") or "")
            self.author_profile_reader_input.setText(
                profile.get("target_reader") or "")
            self.author_profile_comps_input.setText(
                profile.get("comp_titles") or "")
            self.author_profile_path_box.setCurrentText(
                profile.get("publishing_path") or "Undecided")
            for widget, key in (
                (self.author_draft_box, "draft"),
                (self.author_outline_box, "outline"),
                (self.author_characters_box, "characters"),
                (self.author_world_box, "world"),
            ):
                widget.setPlainText(state.get(key) or "")
            self.author_export_author_input.setText(
                state.get("export_author") or "")
        finally:
            self._loading_project_state = False

    def _schedule_project_save(self, *_args) -> None:
        if self._project_id and not self._loading_project_state:
            self._project_save_timer.start()

    def _persist_project_state(self) -> None:
        if not self._project_id:
            return
        from services.project_workspaces import save
        title = self.author_title_input.text().strip()
        byline = self.author_name_input.text().strip()
        save(self._project_id, "author", self._capture_project_state(),
             work_title=title, byline=byline)
        self._last_project_identity = (title, byline)

    def _sync_project_identity(self, project: dict) -> None:
        """Apply identity changed in Project Manager without clearing the draft."""
        identity = (project.get("work_title") or "", project.get("byline") or "")
        if identity == self._last_project_identity:
            return
        self._loading_project_state = True
        try:
            self.author_title_input.setText(identity[0])
            self.author_name_input.setText(identity[1])
        finally:
            self._loading_project_state = False
        self._last_project_identity = identity

    def activate_project(self, project: dict | None) -> None:
        """Save outgoing work and restore the selected project's manuscript."""
        from services.project_workspaces import load

        next_id = project["id"] if project else None
        if next_id == self._project_id:
            if project:
                self._sync_project_identity(project)
            return
        for worker_name in ("author_worker", "author_pub_worker",
                            "author_mkt_worker"):
            worker = getattr(self.host, worker_name, None)
            if worker is not None and worker.isRunning():
                raise RuntimeError(
                    "Finish or stop the current Write request before switching projects.")
        self._project_save_timer.stop()
        if self._project_id:
            # Project Manager may have just deleted the active project. Its
            # workspace row was cascaded already; never recreate orphan work.
            if self.host.registry.get_project(self._project_id):
                self._persist_project_state()
        elif self._unfiled_state is None:
            self._unfiled_state = self._capture_project_state()
        self._project_id = next_id
        if next_id:
            self._apply_project_state(load(next_id, "author"), project)
            self._last_project_identity = (
                project.get("work_title") or "", project.get("byline") or "")
        else:
            self._apply_project_state(self._unfiled_state or {})
            self._last_project_identity = ("", "")

    def _build_book_profile_block(self) -> str:
        """Formats the Book Profile into a system-prompt block shared by Write/Publish/Market
        — the point being you set this once and stop re-explaining the book on every request."""
        p = self.get_book_profile()
        lines = []
        if p["title"]:
            lines.append(f"Title: {p['title']}")
        if p["author"]:
            lines.append(f"Author: {p['author']}")
        lines.append(f"Content type: {p['content_type']}")
        if p["genre"]:
            lines.append(f"Genre: {p['genre']}")
        if p["hook"]:
            lines.append(f"Hook: {p['hook']}")
        if p["target_reader"]:
            lines.append(f"Target reader: {p['target_reader']}")
        if p["comp_titles"]:
            lines.append(f"Comp titles: {p['comp_titles']}")
        if p["publishing_path"] and p["publishing_path"] != "Undecided":
            lines.append(f"Publishing path: {p['publishing_path']}")
        if not lines:
            return ""
        return (
            "BOOK CONTEXT — ground every response in this; don't ask the user to re-explain it.\n\n"
            + "\n".join(lines)
        )

    def save_profile(self):
        import json
        from services.database import save_setting
        if self._project_id:
            self._persist_project_state()
        else:
            save_setting("author_book_profile", json.dumps(self.get_book_profile()))
        self.author_status_label.setText("[Saved] Book profile.")
        self.host._refresh_next_step_tip()

    def _load_profile(self):
        import json
        from services.database import get_setting
        raw = get_setting("author_book_profile", "")
        if not raw:
            return
        try:
            profile = json.loads(raw)
        except Exception:
            return
        self.author_title_input.setText(profile.get("title", ""))
        self.author_name_input.setText(profile.get("author", ""))
        if profile.get("content_type"):
            self.author_content_type_box.setCurrentText(profile["content_type"])
        if profile.get("genre"):
            idx = self.author_genre_box.findText(profile["genre"])
            if idx >= 0:
                self.author_genre_box.setCurrentIndex(idx)
        self.author_profile_hook_input.setText(profile.get("hook", ""))
        self.author_profile_reader_input.setText(profile.get("target_reader", ""))
        self.author_profile_comps_input.setText(profile.get("comp_titles", ""))
        if profile.get("publishing_path"):
            self.author_profile_path_box.setCurrentText(profile["publishing_path"])

    # ── writing ─────────────────────────────────────────────────────────
    def _build_prompt(self, direction: str) -> str:
        task = self.author_task_box.currentText()
        genre = self.author_genre_box.currentText()
        tone = self.author_tone_box.currentText()
        pov = self.author_pov_box.currentText()
        title = self.author_title_input.text().strip()
        parts = [f"Task: {task}"]
        if title:
            parts.append(f"Project: {title}")
        parts += [f"Genre: {genre}", f"Tone: {tone}", f"POV: {pov}"]
        if direction:
            parts.append(f"Direction:\n{direction}")
        return "\n".join(parts)

    def _build_consistency_context(self, recent_draft_text: str = "") -> str:
        """Auto-inject established Characters/World + a recent-draft excerpt so every
        Write/Continue call stays consistent with the story so far."""
        characters = self.author_characters_box.toPlainText().strip()
        world = self.author_world_box.toPlainText().strip()
        sections = []
        if characters:
            sections.append(f"ESTABLISHED CHARACTERS (stay consistent — do not contradict):\n{characters}")
        if world:
            sections.append(f"ESTABLISHED WORLD (stay consistent — do not contradict):\n{world}")
        if recent_draft_text:
            sections.append(
                "RECENT STORY TEXT (end of the current draft — continue consistently, don't repeat it):\n"
                + recent_draft_text[-3000:]
            )
        if not sections:
            return ""
        return (
            "CONTINUITY CONTEXT — ground every response in this; do not contradict "
            "established characters, world rules, or recent events.\n\n" + "\n\n".join(sections)
        )

    def _start_worker(self, provider: str, model: str, prompt: str,
                      recent_draft_text: str = ""):
        agent = self.host.agent_instances["author"]
        consistency_context = self._build_consistency_context(recent_draft_text)
        book_profile_context = self._build_book_profile_block()
        content_type = self.author_content_type_box.currentText()
        messages = agent.build_messages(
            prompt, consistency_context=consistency_context,
            book_profile_context=book_profile_context, content_type=content_type,
        )
        # Never replace a worker that is still running: dropping the old
        # QThread object while its thread is alive aborts the whole app with
        # "QThread: Destroyed while thread is still running". A cancelled
        # worker can sit in a blocking backend call for a while.
        if self.host.author_worker is not None and self.host.author_worker.isRunning():
            self.author_status_label.setText(
                "[Busy] The previous request is still finishing — one moment.")
            return
        self.author_status_label.setText("[Working…]")
        self.author_write_btn.setEnabled(False)
        self.author_continue_btn.setEnabled(False)
        self.author_stop_btn.setEnabled(True)
        # Keep the token: "author" is shared by the write, publish and
        # market flows, and resolving by name pops whichever is oldest.
        token = self.host.authorize_request("author", provider, model, prompt)
        if not token:
            # Refused — re-enable the buttons disabled above.
            self.author_write_btn.setEnabled(True)
            self.author_continue_btn.setEnabled(True)
            self.author_stop_btn.setEnabled(False)
            self.author_status_label.setText("")
            return
        self._write_token = token
        worker = self.host._new_chat_worker(provider, model, messages, prompt)
        self.host.author_worker = worker
        worker.token_signal.connect(self._on_token)
        worker.finished_signal.connect(self._on_finished)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_error)
        worker.start()

    def write(self):
        direction = self.author_direction_input.text().strip()
        if not direction:
            QMessageBox.warning(self, "Missing Input", "Please enter a direction.")
            return
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        self._is_continuing = False
        existing = self.author_draft_box.toPlainText().strip()
        self.author_draft_box.clear()
        self._last_response = ""
        prompt = self._build_prompt(direction)
        self._start_worker(provider, model, prompt, recent_draft_text=existing)

    def continue_draft(self):
        direction = self.author_direction_input.text().strip()
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        existing = self.author_draft_box.toPlainText().strip()
        parts = []
        if existing:
            parts.append(f"Existing draft so far:\n\n{existing}")
        if direction:
            parts.append(f"Continue with:\n{direction}")
        else:
            parts.append("Continue from where the draft left off.")
        continuation_note = "\n\n".join(parts)
        self._is_continuing = True
        self._last_response = ""
        # Append a separator then stream new content
        if existing:
            cursor = self.author_draft_box.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText("\n\n")
            self.author_draft_box.setTextCursor(cursor)
        prompt = self._build_prompt(continuation_note)
        # Recent draft text is already embedded in full inside `continuation_note` above —
        # don't pass it again here, that would just duplicate it in the prompt.
        self._start_worker(provider, model, prompt)

    def _on_token(self, token: str):
        self._last_response += token
        cursor = self.author_draft_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_draft_box.setTextCursor(cursor)

    def _update_counts(self):
        text = self.author_draft_box.toPlainText()
        word_count = len(text.split()) if text.strip() else 0
        self.author_word_count_label.setText(str(word_count))
        scene_count = len(re.findall(
            r"^(chapter|scene|act|part|prologue|epilogue|---|\*\*\*)",
            text, re.MULTILINE | re.IGNORECASE,
        ))
        self.author_scene_count_label.setText(str(scene_count))

    def _on_finished(self, full_response: str):
        token, self._write_token = self._write_token, None
        if token:
            self.host.record_request(token, full_response)
        self._populate_tabs(full_response)
        word_count = len(self.author_draft_box.toPlainText().split())
        self.author_status_label.setText(f"[Done] {word_count:,} words")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)
        self.author_save_btn.setEnabled(True)
        self.host._refresh_next_step_tip()

    def _on_error(self, error: str):
        token, self._write_token = self._write_token, None
        if token:
            self.host.abandon_request(token)
        self.author_status_label.setText(f"[Error] {error}")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)

    def stop(self):
        worker = self.host.author_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
        # A stopped run must not leave its authorized request pending.
        token, self._write_token = self._write_token, None
        if token:
            self.host.abandon_request(token, reason="stopped")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)
        self.author_status_label.setText("[Stopped]")

    # ── document actions ────────────────────────────────────────────────
    def save_draft(self):
        text = self.author_draft_box.toPlainText()
        if not text.strip():
            return
        title = self.author_title_input.text().strip() or "author_draft"
        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Draft", str(user_data_base() / f"{safe}.txt"),
            "Text Files (*.txt);;Markdown Files (*.md)"
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.author_status_label.setText(f"[Saved] {path}")

    def export_book(self):
        text = self.author_draft_box.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Nothing to Export", "The Draft tab is empty.")
            return
        fmt = self.author_export_format_box.currentText().lower()
        title = self.author_title_input.text().strip() or "Untitled Manuscript"
        author_name = (
            self.author_export_author_input.text().strip()
            or self.author_name_input.text().strip()
            or "Unknown Author"
        )

        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        filters = {"epub": "EPUB Files (*.epub)", "docx": "DOCX Files (*.docx)",
                   "pdf": "PDF Files (*.pdf)"}
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Book", str(user_data_base() / f"{safe}.{fmt}"),
            filters[fmt]
        )
        if not path:
            return

        from agents.author.book_exporter import export_book
        try:
            export_book(text, title, author_name, fmt, Path(path))
            self.author_status_label.setText(
                f"[Done] Exported {fmt.upper()} to {Path(path).name}")
            self.host._author_export_done = True
            self.host._refresh_next_step_tip()
        except Exception as e:
            self.author_status_label.setText(f"[Error] {e}")

    def clear(self):
        self._clear_displays()
        self.author_direction_input.clear()
        self.author_title_input.clear()
        self.author_status_label.setText("")
        self._last_response = ""

    def _clear_displays(self):
        for box in (self.author_draft_box, self.author_outline_box,
                    self.author_characters_box, self.author_world_box):
            box.clear()
        self.author_word_count_label.setText("0")
        self.author_scene_count_label.setText("0")
        self.author_save_btn.setEnabled(False)

    def _populate_tabs(self, response: str):
        task = self.author_task_box.currentText()
        sections = self._parse_sections(response)
        if sections.get("outline"):
            self.author_outline_box.setPlainText(sections["outline"])
        if sections.get("characters"):
            self.author_characters_box.setPlainText(sections["characters"])
        if sections.get("world"):
            self.author_world_box.setPlainText(sections["world"])
        # Route clean content to the appropriate tab based on task
        if task == "Generate Outline" and not sections.get("outline"):
            self.author_outline_box.setPlainText(response)
        elif task == "Develop Characters" and not sections.get("characters"):
            self.author_characters_box.setPlainText(response)
        elif task == "Build World" and not sections.get("world"):
            self.author_world_box.setPlainText(response)
        elif not self._is_continuing and not sections.get("outline") and not sections.get("characters"):
            # Fresh write with no section markers — put full response in draft
            self.author_draft_box.setPlainText(sections.get("draft") or response)

    @staticmethod
    def _parse_sections(text: str) -> dict:
        patterns = {
            "draft":      r"\[DRAFT\](.*?)(?=\[OUTLINE\]|\[CHARACTER\]|\[WORLD\]|$)",
            "outline":    r"\[OUTLINE\](.*?)(?=\[DRAFT\]|\[CHARACTER\]|\[WORLD\]|$)",
            "characters": r"\[CHARACTER\](.*?)(?=\[DRAFT\]|\[OUTLINE\]|\[WORLD\]|$)",
            "world":      r"\[WORLD\](.*?)(?=\[DRAFT\]|\[OUTLINE\]|\[CHARACTER\]|$)",
        }
        result = {}
        for key, pat in patterns.items():
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            result[key] = m.group(1).strip() if m else ""
        return result

    # ── chapters ────────────────────────────────────────────────────────
    def _on_tab_changed(self, index: int):
        if self.author_tabs.widget(index) is self.author_chapters_tab:
            self._refresh_chapters()

    def _refresh_chapters(self):
        """Re-derive the chapter list from the current Draft text — chapters aren't a
        separate stored model, they're parsed live from Draft using the same heading
        detection as book export, so there's never a second source of truth to drift."""
        from agents.author.book_exporter import find_chapter_offsets, split_into_chapters

        text = self.author_draft_box.toPlainText()
        self.author_chapters_list.clear()
        self._chapter_offsets = []

        if not text.strip():
            self.author_chapters_stats_label.setText(
                "No chapters detected yet — write something in Draft first.")
            return

        chapters = split_into_chapters(text)
        heading_offsets = find_chapter_offsets(text)
        total_words = len(text.split())

        offsets = []
        oi = 0
        for heading, _body in chapters:
            if heading:
                offsets.append(heading_offsets[oi] if oi < len(heading_offsets) else 0)
                oi += 1
            else:
                offsets.append(0)
        self._chapter_offsets = offsets

        for i, (heading, body) in enumerate(chapters):
            label = heading or "(untitled opening — no chapter headings found yet)"
            words = len(body.split())
            item = QListWidgetItem(f"{i + 1}. {label}   —   {words:,} words")
            self.author_chapters_list.addItem(item)

        chapter_word = "chapter" if len(chapters) == 1 else "chapters"
        self.author_chapters_stats_label.setText(
            f"{len(chapters)} {chapter_word} · {total_words:,} words total"
        )

    def _jump_to_chapter(self, item):
        row = self.author_chapters_list.row(item)
        if row < 0 or row >= len(self._chapter_offsets):
            return
        cursor = self.author_draft_box.textCursor()
        cursor.setPosition(self._chapter_offsets[row])
        self.author_draft_box.setTextCursor(cursor)
        self.author_tabs.setCurrentWidget(self.author_draft_box)
        self.author_draft_box.ensureCursorVisible()

    # ── mode switching ──────────────────────────────────────────────────
    def set_mode(self, mode: str):
        is_write = mode == "write"
        self.author_mode_write_btn.setChecked(is_write)
        self.author_mode_pubmkt_btn.setChecked(not is_write)
        self.author_content_stack.setCurrentIndex(0 if is_write else 1)

    def set_sub_mode(self, mode: str):
        is_pub = mode == "publish"
        self.author_sub_publish_btn.setChecked(is_pub)
        self.author_sub_market_btn.setChecked(not is_pub)
        self.author_sub_stack.setCurrentIndex(0 if is_pub else 1)

    # ── publish ─────────────────────────────────────────────────────────
    def pub_generate(self):
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model",
                                "Please select a model in the Write sidebar.")
            return

        title   = self.author_title_input.text().strip()
        genre   = self.author_genre_box.currentText()
        tone    = self.author_tone_box.currentText()
        doc_type = self.author_pub_type_box.currentText()
        wc      = self.author_pub_wordcount_input.text().strip()
        comps   = self.author_pub_comps_input.text().strip()
        pitch_tone = self.author_pub_pitch_tone_box.currentText()
        notes   = self.author_pub_notes_input.toPlainText().strip()

        parts = [f"Task: Generate a {doc_type}"]
        if title:
            parts.append(f"Book Title: {title}")
        parts += [f"Genre: {genre}", f"Tone: {tone}", f"Pitch Tone: {pitch_tone}"]
        if wc:
            parts.append(f"Manuscript Word Count: {wc}")
        if comps:
            parts.append(f"Comp Titles: {comps}")
        if notes:
            parts.append(f"Additional Notes:\n{notes}")

        prompt = "\n".join(parts)
        agent = self.host.agent_instances["author"]
        messages = agent.build_publish_messages(
            prompt, book_profile_context=self._build_book_profile_block())

        self.author_pub_output.clear()
        self.author_status_label.setText(f"[Working…] Generating {doc_type}…")
        self.author_pub_generate_btn.setEnabled(False)
        self.author_pub_stop_btn.setEnabled(True)
        self.author_pub_save_btn.setEnabled(False)

        if (self.host.author_pub_worker is not None
                and self.host.author_pub_worker.isRunning()):
            self.author_status_label.setText(
                "[Busy] The previous request is still finishing — one moment.")
            return
        token = self.host.authorize_request("author", provider, model, prompt)
        if not token:
            self.author_pub_generate_btn.setEnabled(True)
            self.author_pub_stop_btn.setEnabled(False)
            self.author_status_label.setText("")
            return
        self._pub_token = token
        worker = self.host._new_chat_worker(provider, model, messages, prompt)
        self.host.author_pub_worker = worker
        worker.token_signal.connect(self._pub_on_token)
        worker.finished_signal.connect(self._pub_on_finished)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._pub_on_error)
        worker.start()

    def _pub_on_token(self, token: str):
        cursor = self.author_pub_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_pub_output.setTextCursor(cursor)

    def _pub_on_finished(self, full_response: str):
        token, self._pub_token = self._pub_token, None
        if token:
            self.host.record_request(token, full_response)
        self.author_status_label.setText(
            f"[Done] {self.author_pub_type_box.currentText()} generated"
        )
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)
        self.author_pub_save_btn.setEnabled(True)

    def _pub_on_error(self, error: str):
        token, self._pub_token = self._pub_token, None
        if token:
            self.host.abandon_request(token)
        self.author_status_label.setText(f"[Error] {error}")
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)

    def pub_stop(self):
        worker = self.host.author_pub_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
        token, self._pub_token = self._pub_token, None
        if token:
            self.host.abandon_request(token, reason="stopped")
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)
        self.author_status_label.setText("[Stopped]")

    def pub_copy(self):
        text = self.author_pub_output.toPlainText().strip()
        if text:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self.author_status_label.setText("[Copied to clipboard]")

    def pub_save(self):
        text = self.author_pub_output.toPlainText().strip()
        if not text:
            return
        title = self.author_title_input.text().strip() or "publish"
        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        doc_type = re.sub(r"\s+", "_", self.author_pub_type_box.currentText().lower())
        default_name = f"{safe}_{doc_type}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Publishing Document",
            str(user_data_base() / default_name),
            "Text Files (*.txt);;Markdown Files (*.md)"
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.author_status_label.setText(f"[Saved] {path}")

    # ── market ──────────────────────────────────────────────────────────
    def mkt_generate(self):
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model",
                                "Please select a model in the Write sidebar.")
            return

        title    = self.author_title_input.text().strip()
        genre    = self.author_genre_box.currentText()
        platform = self.author_mkt_platform_box.currentText()
        hook     = self.author_mkt_hook_input.text().strip()
        comps    = self.author_mkt_comps_input.text().strip()
        mkt_tone = self.author_mkt_tone_box.currentText()
        notes    = self.author_mkt_notes_input.toPlainText().strip()

        parts = [f"Task: Generate {platform} copy"]
        if title:
            parts.append(f"Book Title: {title}")
        parts += [f"Genre: {genre}", f"Tone: {mkt_tone}"]
        if hook:
            parts.append(f"Hook / Logline: {hook}")
        if comps:
            parts.append(f"Comp Titles: {comps}")
        if notes:
            parts.append(f"Additional Notes:\n{notes}")

        prompt = "\n".join(parts)
        agent = self.host.agent_instances["author"]
        messages = agent.build_market_messages(
            prompt, book_profile_context=self._build_book_profile_block())

        self.author_mkt_output.clear()
        self.author_status_label.setText(f"[Working…] Generating {platform} copy…")
        self.author_mkt_generate_btn.setEnabled(False)
        self.author_mkt_stop_btn.setEnabled(True)
        self.author_mkt_save_btn.setEnabled(False)

        if (self.host.author_mkt_worker is not None
                and self.host.author_mkt_worker.isRunning()):
            self.author_status_label.setText(
                "[Busy] The previous request is still finishing — one moment.")
            return
        token = self.host.authorize_request("author", provider, model, prompt)
        if not token:
            self.author_mkt_generate_btn.setEnabled(True)
            self.author_mkt_stop_btn.setEnabled(False)
            self.author_status_label.setText("")
            return
        self._mkt_token = token
        worker = self.host._new_chat_worker(provider, model, messages, prompt)
        self.host.author_mkt_worker = worker
        worker.token_signal.connect(self._mkt_on_token)
        worker.finished_signal.connect(self._mkt_on_finished)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._mkt_on_error)
        worker.start()

    def _mkt_on_token(self, token: str):
        cursor = self.author_mkt_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_mkt_output.setTextCursor(cursor)

    def _mkt_on_finished(self, full_response: str):
        token, self._mkt_token = self._mkt_token, None
        if token:
            self.host.record_request(token, full_response)
        self.author_status_label.setText(
            f"[Done] {self.author_mkt_platform_box.currentText()} copy generated"
        )
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_mkt_save_btn.setEnabled(True)

    def _mkt_on_error(self, error: str):
        token, self._mkt_token = self._mkt_token, None
        if token:
            self.host.abandon_request(token)
        self.author_status_label.setText(f"[Error] {error}")
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)

    def mkt_stop(self):
        worker = self.host.author_mkt_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
        token, self._mkt_token = self._mkt_token, None
        if token:
            self.host.abandon_request(token, reason="stopped")
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_status_label.setText("[Stopped]")

    def mkt_copy(self):
        text = self.author_mkt_output.toPlainText().strip()
        if text:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self.author_status_label.setText("[Copied to clipboard]")

    def mkt_save(self):
        text = self.author_mkt_output.toPlainText().strip()
        if not text:
            return
        title = self.author_title_input.text().strip() or "marketing"
        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        platform = re.sub(r"[\s/]+", "_", self.author_mkt_platform_box.currentText().lower())
        default_name = f"{safe}_{platform}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Marketing Copy",
            str(user_data_base() / default_name),
            "Text Files (*.txt);;Markdown Files (*.md)"
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.author_status_label.setText(f"[Saved] {path}")
