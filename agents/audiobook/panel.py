"""Audiobook Convert and Listen workspace owned by the Audiobook agent."""

import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from services.audiobook_library import (
    format_time, load_position, mark_unfinished, scan,
)
from services.openai_client import OpenAIClientWrapper
from services.runtime_paths import is_frozen
from ui.audio_player import AudiobookPlayer
from ui.forms import CONTROL_HEIGHT, LG, MD, SM, combo, field, line_edit, primary, rule, section
from ui.widgets import scrollable

SUPPORTED_EBOOKS = {".pdf", ".epub", ".txt", ".mobi"}


class AudiobookPanel(QWidget):
    """Book selection, conversion controls and a resumable listening library.

    The host supplies shared budget authorization, usage records and the
    output log. Temporary control aliases support existing umbrella bindings.
    """

    HOST_CONTROLS = (
        "audiobook_tabs", "audiobook_book_help", "audiobook_book_list",
        "audiobook_empty_state", "audiobook_source_stack",
        "audiobook_input_path", "audiobook_open_input_btn",
        "audiobook_output_path", "audiobook_change_output_btn",
        "audiobook_voice_box", "audiobook_chunk_input",
        "audiobook_start_btn", "audiobook_refresh_btn", "stop_btn",
        "audiobook_cost_label", "tool_progress", "audiobook_status_label",
        "audiobook_convert_scroll", "audiobook_library_refresh_btn",
        "audiobook_library_table", "audiobook_play_btn",
        "audiobook_restart_btn", "audiobook_reveal_btn", "audiobook_player",
    )

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._audiobook_library = []
        self.setObjectName("AudiobookPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(MD)
        self.audiobook_tabs = QTabWidget()
        outer.addWidget(self.audiobook_tabs, 1)

        convert_page = QWidget()
        convert_page.setObjectName("Transparent")
        page = QVBoxLayout(convert_page)
        page.setContentsMargins(MD, MD, MD, MD)
        page.setSpacing(LG)
        page.addWidget(section("Book"))
        self.audiobook_book_help = QLabel(
            "Choose a PDF, EPUB, TXT, or MOBI file from the input folder. "
            "Imprint converts the selected title and remembers completed output.")
        self.audiobook_book_help.setObjectName("EstimateLine")
        self.audiobook_book_help.setWordWrap(True)
        page.addWidget(self.audiobook_book_help)

        self.audiobook_book_list = QListWidget()
        self.audiobook_book_list.setMaximumHeight(CONTROL_HEIGHT * 5 + MD)
        self.audiobook_book_list.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.audiobook_book_list.currentItemChanged.connect(
            lambda *_: self.estimate_cost_from_selection())

        self.audiobook_empty_state = QLabel(
            "No supported books found yet. Add a PDF, EPUB, TXT, or MOBI file "
            "to the input folder, then refresh the list.")
        self.audiobook_empty_state.setObjectName("InlineEmptyState")
        self.audiobook_empty_state.setWordWrap(True)
        self.audiobook_empty_state.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.audiobook_empty_state.setAccessibleName("No audiobook source files")

        self.audiobook_source_stack = QStackedWidget()
        self.audiobook_source_stack.setObjectName("AudiobookSourceStack")
        self.audiobook_source_stack.addWidget(self.audiobook_empty_state)
        self.audiobook_source_stack.addWidget(self.audiobook_book_list)
        self.audiobook_source_stack.setFixedHeight(CONTROL_HEIGHT * 2 + SM)
        page.addWidget(self.audiobook_source_stack)

        page.addWidget(rule())
        page.addWidget(section("Conversion settings"))
        self.audiobook_input_path = QLineEdit()
        self.audiobook_input_path.setReadOnly(True)
        self.audiobook_open_input_btn = QPushButton("Open input")
        self.audiobook_open_input_btn.setFixedWidth(116)
        self.audiobook_open_input_btn.clicked.connect(self.open_input_folder)
        self.audiobook_output_path = QLineEdit()
        self.audiobook_output_path.setReadOnly(True)
        self.audiobook_change_output_btn = QPushButton("Set output")
        self.audiobook_change_output_btn.setFixedWidth(116)
        self.audiobook_change_output_btn.clicked.connect(
            self.change_output_folder)
        folders = QGridLayout()
        folders.setHorizontalSpacing(SM)
        folders.setVerticalSpacing(MD)
        folders.addWidget(field("Input folder", self.audiobook_input_path),
                          0, 0, Qt.AlignTop)
        folders.addWidget(self.audiobook_open_input_btn, 0, 1, Qt.AlignBottom)
        folders.addWidget(field("Output folder", self.audiobook_output_path),
                          1, 0, Qt.AlignTop)
        folders.addWidget(self.audiobook_change_output_btn, 1, 1, Qt.AlignBottom)
        folders.setColumnStretch(0, 1)
        page.addLayout(folders)

        self.audiobook_voice_box = combo(
            ["alloy", "verse", "aria", "coral", "sage"])
        self.audiobook_voice_box.setToolTip(
            "Narration voice. Open the menu to see Imprint's best-fit default.")
        self.audiobook_chunk_input = line_edit("1400", "1400")
        self.audiobook_chunk_input.setToolTip(
            "Approximate text sent per narration request. 1400 is a stable default; "
            "smaller chunks recover more easily if a request fails.")
        options = QGridLayout()
        options.setHorizontalSpacing(MD)
        options.setVerticalSpacing(MD)
        options.addWidget(field("Voice", self.audiobook_voice_box),
                          0, 0, Qt.AlignTop)
        options.addWidget(field("Chunk size (tokens)", self.audiobook_chunk_input),
                          0, 1, Qt.AlignTop)
        for column in range(3):
            options.setColumnStretch(column, 1)
        page.addLayout(options)

        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.audiobook_start_btn = primary("Convert audiobook")
        self.audiobook_start_btn.setMinimumWidth(160)
        self.audiobook_start_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.audiobook_start_btn.clicked.connect(self.start_conversion)
        actions.addWidget(self.audiobook_start_btn)
        self.audiobook_refresh_btn = QPushButton("Refresh List")
        self.audiobook_refresh_btn.clicked.connect(self.refresh_books)
        actions.addWidget(self.audiobook_refresh_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("DangerAction")
        self.stop_btn.clicked.connect(host.stop_current_task)
        self.stop_btn.hide()
        actions.addWidget(self.stop_btn)
        actions.addStretch()
        self.audiobook_cost_label = QLabel("Estimated cost: not calculated")
        self.audiobook_cost_label.setObjectName("EstimateLine")
        actions.addWidget(self.audiobook_cost_label)
        page.addLayout(actions)

        self.tool_progress = QProgressBar()
        self.tool_progress.setRange(0, 100)
        self.tool_progress.setValue(0)
        self.tool_progress.setTextVisible(True)
        page.addWidget(self.tool_progress)
        self.audiobook_status_label = QLabel(
            "[Ready] Select a book and click Start.")
        self.audiobook_status_label.setObjectName("EstimateLine")
        self.audiobook_status_label.setWordWrap(True)
        page.addWidget(self.audiobook_status_label)

        self.audiobook_convert_scroll = scrollable(convert_page)
        self.audiobook_convert_scroll.setObjectName("AudiobookConvertScroll")
        self.audiobook_convert_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self.audiobook_convert_scroll.setAccessibleName(
            "Audiobook conversion controls")
        self.audiobook_tabs.addTab(self.audiobook_convert_scroll, "Convert")
        self.audiobook_tabs.addTab(self._build_library_tab(host), "Listen")

        for name in self.HOST_CONTROLS:
            setattr(host, name, getattr(self, name))
        host.audiobook_panel = self
        self.hide()

    # ── Conversion actions ───────────────────────────────────────────────
    # These four still live on the umbrella (`GodAI`), because the conversion
    # half of this panel has not been moved into the package yet — only the
    # listening half has. The widgets moved with the panel, so the handlers
    # reach back through `host`. Without these the panel's own constructor
    # raised AttributeError and the whole app failed to start.
    #
    # When the conversion handlers do move here, these become the real
    # implementations and `main.py` keeps thin shims, mirroring what
    # `play_selected` / `restart_selected` / `reveal_selected` already do.

    def open_input_folder(self):
        self.host.open_audiobook_input_folder()

    def change_output_folder(self):
        self.host.change_audiobook_output_folder()

    def refresh_books(self):
        self.host.refresh_audiobook_books()

    def start_conversion(self):
        self.host.start_selected_audiobook_book()

    def _build_library_tab(self, host) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.addWidget(section("Audiobooks in your output folder"))
        header.addStretch()
        self.audiobook_library_refresh_btn = QPushButton("Rescan")
        self.audiobook_library_refresh_btn.setObjectName("ChipBtn")
        self.audiobook_library_refresh_btn.clicked.connect(self.refresh_library)
        header.addWidget(self.audiobook_library_refresh_btn)
        layout.addLayout(header)

        self.audiobook_library_table = QTableWidget(0, 4)
        self.audiobook_library_table.setHorizontalHeaderLabels(
            ["Title", "Progress", "Position", "Last played"])
        self.audiobook_library_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.audiobook_library_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.audiobook_library_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.audiobook_library_table.itemSelectionChanged.connect(
            self._selection_changed)
        self.audiobook_library_table.doubleClicked.connect(
            lambda *_: self.play_selected())
        layout.addWidget(self.audiobook_library_table, 1)

        row = QHBoxLayout()
        self.audiobook_play_btn = QPushButton("Listen")
        self.audiobook_play_btn.setObjectName("PrimaryAction")
        self.audiobook_play_btn.setEnabled(False)
        self.audiobook_play_btn.clicked.connect(self.play_selected)
        row.addWidget(self.audiobook_play_btn)
        self.audiobook_restart_btn = QPushButton("Start Over")
        self.audiobook_restart_btn.setEnabled(False)
        self.audiobook_restart_btn.clicked.connect(self.restart_selected)
        row.addWidget(self.audiobook_restart_btn)
        self.audiobook_reveal_btn = QPushButton("Show in Finder")
        self.audiobook_reveal_btn.setEnabled(False)
        self.audiobook_reveal_btn.clicked.connect(self.reveal_selected)
        row.addWidget(self.audiobook_reveal_btn)
        row.addStretch()
        layout.addLayout(row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("CardDivider")
        layout.addWidget(divider)
        self.audiobook_player = AudiobookPlayer()
        self.audiobook_player.position_saved.connect(
            lambda *_: self._refresh_row())
        layout.addWidget(self.audiobook_player)
        return page

    def refresh_library(self):
        """Rescan the output folder on entry without touching conversion state."""
        defaults = self.host.get_audiobook_defaults()
        folder = Path(defaults["output"]).expanduser()
        try:
            self._audiobook_library = scan(folder)
        except Exception as exc:
            self.host._note_failure("audiobook: scan library", exc)
            self._audiobook_library = []

        table = self.audiobook_library_table
        table.setRowCount(0)
        for book in self._audiobook_library:
            row = table.rowCount()
            table.insertRow(row)
            if book.finished:
                progress = "finished"
            elif book.duration_ms:
                progress = f"{book.progress * 100:.0f}%"
            elif book.position_ms:
                progress = "started"
            else:
                progress = "—"
            position = format_time(book.position_ms) if book.position_ms else "—"
            table.setItem(row, 0, QTableWidgetItem(book.title))
            table.setItem(row, 1, QTableWidgetItem(progress))
            table.setItem(row, 2, QTableWidgetItem(position))
            table.setItem(row, 3, QTableWidgetItem(book.last_played or "—"))

        if not self._audiobook_library:
            self.audiobook_status_label.setText(
                f"[Library] No audio files in {folder}. Convert a book first.")

    def _selected_book(self):
        row = self.audiobook_library_table.currentRow()
        if row < 0 or row >= len(self._audiobook_library):
            return None
        return self._audiobook_library[row]

    def _selection_changed(self):
        book = self._selected_book()
        for button in (self.audiobook_play_btn, self.audiobook_restart_btn,
                       self.audiobook_reveal_btn):
            button.setEnabled(book is not None)
        if book and book.started:
            self.audiobook_play_btn.setText(
                f"Resume at {format_time(book.position_ms)}")
        else:
            self.audiobook_play_btn.setText("Listen")

    def _refresh_row(self):
        """Update the selected row in place without losing selection mid-listen."""
        book = self._selected_book()
        if not book:
            return
        row = self.audiobook_library_table.currentRow()
        position = load_position(book.path)
        book.position_ms = position
        self.audiobook_library_table.setItem(
            row, 2, QTableWidgetItem(format_time(position)))

    def play_selected(self):
        book = self._selected_book()
        if not book:
            return
        if not book.path.exists():
            QMessageBox.warning(
                self, "File Missing",
                f"{book.path.name} is no longer in the output folder.")
            self.refresh_library()
            return
        self.audiobook_player.load(
            book.path, title=book.title,
            resume_ms=load_position(book.path))
        self.audiobook_player.play()
        self.audiobook_status_label.setText(f"[Playing] {book.title}")

    def restart_selected(self):
        book = self._selected_book()
        if not book:
            return
        mark_unfinished(book.path)
        self.audiobook_player.load(book.path, title=book.title, resume_ms=0)
        self.audiobook_player.play()
        self.refresh_library()

    def reveal_selected(self):
        book = self._selected_book()
        if book:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(book.path.parent)))
