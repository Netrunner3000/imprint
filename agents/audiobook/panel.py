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
        self._text_cache = {}
        self._request_token = None
        self.process = None
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
        self.stop_btn.clicked.connect(self.stop_conversion)
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

        # Aliases retired 2026-09-21: shared wiring resolves controls
        # through host._find_control(); HOST_CONTROLS stays as the
        # published contract of what this panel owns.
        host.audiobook_panel = self
        self.hide()

    # ── Conversion actions ───────────────────────────────────────────────

    def defaults(self):
        tool = self.host.tool_runner.tools["audiobook"]
        return {
            "input": tool["default_input"],
            "output": tool["default_output"],
            "voice": tool.get("default_voice", "alloy"),
            "chunk_tokens": tool.get("default_chunk_tokens", 1400),
        }

    def _update_source_state(self, empty_message: str = "") -> None:
        count = self.audiobook_book_list.count()
        if count == 0:
            if empty_message:
                self.audiobook_empty_state.setText(empty_message)
            self.audiobook_source_stack.setCurrentWidget(
                self.audiobook_empty_state)
            self.audiobook_source_stack.setFixedHeight(
                CONTROL_HEIGHT * 2 + SM)
            return

        self.audiobook_source_stack.setCurrentWidget(self.audiobook_book_list)
        rows = min(4, count)
        row_height = self.audiobook_book_list.sizeHintForRow(0)
        if row_height <= 0:
            row_height = CONTROL_HEIGHT
        height = min(
            CONTROL_HEIGHT * 5 + MD,
            max(CONTROL_HEIGHT * 2 + SM, rows * row_height + MD),
        )
        self.audiobook_source_stack.setFixedHeight(height)

    def refresh_books(self):
        defaults = self.defaults()
        input_folder = Path(defaults["input"]).expanduser()
        output_folder = Path(defaults["output"]).expanduser()
        self.audiobook_input_path.setText(str(input_folder))
        self.audiobook_output_path.setText(str(output_folder))
        self.audiobook_voice_box.setCurrentText(defaults["voice"])
        self.audiobook_chunk_input.setText(str(defaults["chunk_tokens"]))
        self.audiobook_book_list.clear()
        self.tool_progress.setValue(0)

        if not input_folder.exists():
            self._update_source_state(
                "The input folder does not exist yet. Set it up, add a PDF, "
                "EPUB, TXT, or MOBI file, then refresh the list.")
            self.host.output_box.setPlainText(
                f"[Error] Input folder does not exist:\n{input_folder}")
            self.audiobook_status_label.setText(
                "Choose an input folder to add your first book.")
            return

        books = sorted(
            item for item in input_folder.iterdir()
            if item.is_file() and item.suffix.lower() in SUPPORTED_EBOOKS)
        if not books:
            self._update_source_state(
                "No supported books found in the input folder. Add a PDF, "
                "EPUB, TXT, or MOBI file, then refresh the list.")
            self.host.output_box.setPlainText(
                f"[Info] No supported ebooks found in:\n{input_folder}")
            self.audiobook_status_label.setText(
                "No books yet — add a PDF, EPUB, TXT, or MOBI file.")
            return

        for book in books:
            item = QListWidgetItem(book.name)
            item.setData(Qt.UserRole, str(book))
            self.audiobook_book_list.addItem(item)
        self._update_source_state()
        if len(books) == 1:
            self.audiobook_book_list.setCurrentRow(0)
        self.host.output_box.setPlainText(
            f"[Ready] Found {len(books)} book(s). Select one and click Start.")
        self.audiobook_status_label.setText(
            f"[Ready] Found {len(books)} book(s).")
        self.estimate_cost_from_selection()

    def open_input_folder(self):
        folder = self.audiobook_input_path.text().strip()
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def change_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Audiobook Output Folder")
        if folder:
            self.audiobook_output_path.setText(folder)

    def _text(self, path: Path) -> str:
        from services.narrator.converter import load_text

        key = (str(path), path.stat().st_mtime_ns)
        if key not in self._text_cache:
            self._text_cache.clear()
            self._text_cache[key] = load_text(path)
        return self._text_cache[key]

    def _estimate(self, path: Path) -> dict | None:
        from services.narrator.converter import (
            count_text_tokens, estimate_audio_seconds_from_text,
            estimate_audio_tokens_from_seconds, estimate_costs_usd,
        )
        from services.per_unit_pricing import eur_per_usd

        try:
            text = self._text(path)
        except Exception:
            return None
        if not text.strip():
            return None
        text_tokens = count_text_tokens(text)
        seconds = estimate_audio_seconds_from_text(text)
        audio_tokens = estimate_audio_tokens_from_seconds(seconds)
        usd = estimate_costs_usd(text_tokens, audio_tokens)["total_usd"]
        return {
            "characters": len(text), "seconds": seconds,
            "eur": round(usd * eur_per_usd(), 4),
        }

    def estimate_cost_from_selection(self):
        item = self.audiobook_book_list.currentItem()
        if not item:
            self.audiobook_cost_label.setText("Select a book")
            return
        estimate = self._estimate(Path(item.data(Qt.UserRole)))
        if estimate is None:
            self.audiobook_cost_label.setText("Cost: could not read this file")
            return
        self.audiobook_cost_label.setText(
            f"~{estimate['seconds'] / 60:.0f} min audio · "
            f"≈ €{estimate['eur']:.2f}")

    def start_conversion(self):
        item = self.audiobook_book_list.currentItem()
        if not item:
            self.host.output_box.setPlainText(
                "[Error] Please select a book first.")
            return
        book_path = item.data(Qt.UserRole)
        output_path = self.audiobook_output_path.text().strip()
        voice = self.audiobook_voice_box.currentText().strip()
        if not OpenAIClientWrapper.key_available():
            self.audiobook_status_label.setText(
                "[Error] OPENAI_API_KEY not set.")
            QMessageBox.critical(
                self, "OpenAI API Key Required",
                "Audiobook conversion uses OpenAI's text-to-speech API, but "
                "OPENAI_API_KEY is not set.\n\nAdd your key in Settings, then "
                "restart Imprint and try again.")
            return
        try:
            chunk_tokens = int(self.audiobook_chunk_input.text().strip())
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Value", "Chunk tokens must be a number.")
            return
        estimate = self._estimate(Path(book_path))
        if estimate is None:
            QMessageBox.warning(
                self, "Unreadable Book",
                f"No text could be extracted from {Path(book_path).name}, so "
                "the conversion cost cannot be estimated.")
            return
        token = self.host.authorize_request(
            "audiobook", "openai", "gpt-4o-mini-tts",
            f"{Path(book_path).name} · {estimate['characters']} characters",
            label="audiobook", flat_cost_eur=estimate["eur"])
        if not token:
            return
        self._request_token = token
        self.host._audiobook_request_token = token
        config = {
            "input": book_path, "output": output_path, "voice": voice,
            "chunk_tokens": chunk_tokens,
        }
        self.host.output_box.setPlainText(
            f"[Starting]\nBook: {Path(book_path).name}\nOutput: {output_path}"
            f"\nVoice: {voice}\nChunk tokens: {chunk_tokens}\n\n")
        self.audiobook_status_label.setText(
            f"[Running] {Path(book_path).name}")
        self.run_conversion(config)

    def run_conversion(self, config):
        self.tool_progress.setValue(0)
        self.stop_btn.setEnabled(True)
        self.stop_btn.show()
        self.audiobook_start_btn.setEnabled(False)
        self.audiobook_refresh_btn.setEnabled(False)
        tool = self.host.tool_runner.tools["audiobook"]
        project_root = str(Path(__file__).resolve().parents[2])
        self.process = QProcess(self)
        self.host.audiobook_process = self.process
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.setWorkingDirectory(project_root)
        conv_args = [
            "--input", config["input"], "--output", config["output"],
            "--voice", config["voice"], "--chunk-tokens",
            str(config["chunk_tokens"]),
        ]
        arguments = (["--narrator-worker"] + conv_args if is_frozen() else
                     ["-u", "-m", tool.get(
                         "module", "services.narrator.converter")] + conv_args)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.finished.connect(self.handle_finished)
        self.process.errorOccurred.connect(self.handle_error)
        self.process.start(sys.executable, arguments)

    def handle_error(self, error):
        reason = {
            QProcess.FailedToStart: "The converter process failed to start "
                                    "(interpreter or module not found).",
            QProcess.Crashed: "The converter process crashed.",
            QProcess.Timedout: "The converter process timed out.",
        }.get(error, "The converter process encountered an unknown error.")
        self._reset_conversion_controls()
        self.tool_progress.setValue(0)
        self.audiobook_status_label.setText(
            "[Error] Converter could not run.")
        self.host.output_box.append(f"\n[Error] {reason}")
        if error == QProcess.FailedToStart:
            self._close_request(False)
        QMessageBox.critical(self, "Audiobook Conversion Failed", reason)

    def handle_stdout(self):
        if self.process is None:
            return
        data = self.process.readAll().data().decode(
            "utf-8", errors="replace")
        if not data:
            return
        self.host.output_box.moveCursor(QTextCursor.End)
        self.host.output_box.insertPlainText(data)
        self.host.output_box.ensureCursorVisible()
        matches = re.findall(r"(\d+(?:\.\d+)?)%\s+\((\d+)/(\d+)\)", data)
        if matches:
            percent = float(matches[-1][0])
            done, total = matches[-1][1:]
            self.tool_progress.setValue(int(percent))
            self.audiobook_status_label.setText(
                f"[Running] {percent:.1f}% ({done}/{total})")

    def handle_finished(self, *_args):
        self._reset_conversion_controls()
        process = self.process or getattr(self.host, "audiobook_process", None)
        exit_code = process.exitCode() if process else 0
        exit_status = (process.exitStatus() if process
                       else QProcess.NormalExit)
        output_text = self.host.output_box.toPlainText()
        crashed = exit_status == QProcess.CrashExit
        success = exit_code == 0 and not crashed
        quota_hit = any(marker in output_text for marker in (
            "insufficient_quota", "exceeded your current quota",
            "Billing hard limit"))
        paused = ("Conversion paused" in output_text or
                  "⏸️" in output_text)
        self._close_request(success)

        if quota_hit:
            self.tool_progress.setValue(0)
            self.audiobook_status_label.setText(
                "[Blocked] OpenAI quota exceeded — top up your account.")
            self.host.output_box.append(
                "\n[Blocked] Your OpenAI account has run out of quota.\n"
                "Top up your account at platform.openai.com/settings/billing,\n"
                "then click Start on the same book to resume automatically.")
            QMessageBox.warning(
                self, "OpenAI Quota Exceeded",
                "Your OpenAI account has run out of quota. Top up at "
                "platform.openai.com/settings/billing, then click Start to resume.")
        elif paused and exit_code != 0:
            self.tool_progress.setValue(0)
            self.audiobook_status_label.setText(
                "[Paused] Incomplete — click Start to resume.")
            self.host.output_box.append(
                "\n[Paused] Some chunks were not completed.\n"
                "Click Start on the same book to resume automatically.")
        elif crashed or exit_code != 0:
            reason = self.extract_error(output_text)
            self.tool_progress.setValue(0)
            self.audiobook_status_label.setText("[Error] Conversion failed.")
            self.host.output_box.append(
                f"\n[Error] Conversion failed (exit code {exit_code}).\n{reason}")
            QMessageBox.critical(
                self, "Audiobook Conversion Failed",
                f"The conversion did not complete.\n\n{reason}")
        else:
            self.tool_progress.setValue(100)
            self.audiobook_status_label.setText(
                "[Done] Audiobook created successfully.")
            self.host.output_box.append(
                "\n[Done] Audiobook created successfully.")
        self.refresh_books()

    def _close_request(self, success: bool):
        token = self._request_token or getattr(
            self.host, "_audiobook_request_token", None)
        self._request_token = None
        self.host._audiobook_request_token = None
        if token and success:
            self.host.record_request(token, "conversion complete")
        elif token:
            self.host.abandon_request(token)

    def _reset_conversion_controls(self):
        self.stop_btn.setEnabled(False)
        self.stop_btn.hide()
        self.audiobook_start_btn.setEnabled(True)
        self.audiobook_refresh_btn.setEnabled(True)

    def stop_conversion(self):
        process = self.process or getattr(self.host, "audiobook_process", None)
        if process is not None and process.state() != QProcess.NotRunning:
            process.kill()
            self.host.output_box.append(
                "\n[Stopped] Current task stopped by user.")
            self.audiobook_status_label.setText("[Stopped]")
        else:
            self.host.output_box.append("\n[Info] No running task to stop.")
        self._reset_conversion_controls()

    @staticmethod
    def extract_error(output_text: str) -> str:
        lines = [line.strip() for line in output_text.splitlines()
                 if line.strip()]
        specific = (
            "not found", "not set", "Fatal error", "Traceback", "Exception",
            "quota", "Authentication", "401", "Failed to read",
        )
        for line in reversed(lines):
            if any(marker in line for marker in specific):
                return line
        for line in reversed(lines):
            if "❌" in line or "Error" in line:
                return line
        return lines[-1] if lines else "No output was produced by the converter."

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
