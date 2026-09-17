"""Audiobook Convert and Listen workspace owned by the Audiobook agent."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QProgressBar, QPushButton, QSizePolicy, QStackedWidget,
    QTableWidget, QTabWidget, QVBoxLayout, QWidget,
)

from ui.audio_player import AudiobookPlayer
from ui.forms import CONTROL_HEIGHT, LG, MD, SM, combo, field, line_edit, primary, rule, section
from ui.widgets import scrollable


class AudiobookPanel(QWidget):
    """Book selection, conversion controls and a resumable listening library.

    Conversion and playback handlers remain on the umbrella host for now.
    Temporary aliases let those handlers and shared tooltip bindings keep
    their current behavior while this layout moves into the agent package.
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
            lambda *_: host.estimate_audiobook_cost_from_selection())

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
        self.audiobook_open_input_btn.clicked.connect(host.open_audiobook_input_folder)
        self.audiobook_output_path = QLineEdit()
        self.audiobook_output_path.setReadOnly(True)
        self.audiobook_change_output_btn = QPushButton("Set output")
        self.audiobook_change_output_btn.setFixedWidth(116)
        self.audiobook_change_output_btn.clicked.connect(
            host.change_audiobook_output_folder)
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
        self.audiobook_start_btn.clicked.connect(host.start_selected_audiobook_book)
        actions.addWidget(self.audiobook_start_btn)
        self.audiobook_refresh_btn = QPushButton("Refresh List")
        self.audiobook_refresh_btn.clicked.connect(host.refresh_audiobook_books)
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
        host._audiobook_library = []
        host.audiobook_panel = self
        self.hide()

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
        self.audiobook_library_refresh_btn.clicked.connect(
            host.refresh_audiobook_library)
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
            host._audiobook_selection_changed)
        self.audiobook_library_table.doubleClicked.connect(
            lambda *_: host.play_selected_audiobook())
        layout.addWidget(self.audiobook_library_table, 1)

        row = QHBoxLayout()
        self.audiobook_play_btn = QPushButton("Listen")
        self.audiobook_play_btn.setObjectName("PrimaryAction")
        self.audiobook_play_btn.setEnabled(False)
        self.audiobook_play_btn.clicked.connect(host.play_selected_audiobook)
        row.addWidget(self.audiobook_play_btn)
        self.audiobook_restart_btn = QPushButton("Start Over")
        self.audiobook_restart_btn.setEnabled(False)
        self.audiobook_restart_btn.clicked.connect(host.restart_selected_audiobook)
        row.addWidget(self.audiobook_restart_btn)
        self.audiobook_reveal_btn = QPushButton("Show in Finder")
        self.audiobook_reveal_btn.setEnabled(False)
        self.audiobook_reveal_btn.clicked.connect(host.reveal_selected_audiobook)
        row.addWidget(self.audiobook_reveal_btn)
        row.addStretch()
        layout.addLayout(row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("CardDivider")
        layout.addWidget(divider)
        self.audiobook_player = AudiobookPlayer()
        self.audiobook_player.position_saved.connect(
            lambda *_: host._audiobook_refresh_row())
        layout.addWidget(self.audiobook_player)
        return page
