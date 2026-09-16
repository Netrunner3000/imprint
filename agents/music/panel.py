"""Music workspace UI, owned by the Music agent package.

The umbrella still owns paid-request bookkeeping and the release-plan handlers.
This widget owns the arrangement and exposes its named controls to the host
until those handlers are moved behind the same package boundary.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTabWidget,
    QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from ui.forms import LG, MD, SM, combo, field, line_edit, primary, section
from ui.panels.base import AgentPanel
from ui.widgets import scrollable
from .suno_panel import SunoPanel


class MusicPanel(QWidget):
    """Release planning and user-assisted song workflow in one owned panel."""

    HOST_CONTROLS = (
        "music_artist_input", "music_genre_box", "music_release_type_box",
        "music_distributor_box", "music_audience_input", "music_query_input",
        "music_panel_base", "music_provider_box", "music_model_box",
        "music_analyse_btn", "music_save_btn", "music_clear_btn",
        "music_stop_btn", "music_status_label", "music_tabs",
        "music_profile_box", "music_release_box", "music_distribution_box",
        "music_strategy_box", "music_income_box", "music_suno_panel",
    )

    def __init__(self, host):
        super().__init__()
        self.setObjectName("MusicPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        layout.addWidget(section("Artist setup"))
        self.music_artist_input = line_edit("Nova Drift, DJ Phantom, The Hollow Road")
        self.music_genre_box = combo([
            "Pop", "Rock", "Hip-Hop", "Electronic", "Jazz", "Classical",
            "R&B", "Metal", "Indie", "Folk", "Country", "Latin", "Reggae",
            "Ambient", "World", "Other",
        ])
        self.music_release_type_box = combo(
            ["Single", "EP (3–6 tracks)", "Album (7+ tracks)", "Mixtape"])
        self.music_distributor_box = combo([
            "Not signed up yet", "DistroKid", "TuneCore", "CD Baby", "Amuse",
            "AWAL", "Other",
        ])
        self.music_audience_input = line_edit("18–25 lo-fi hip-hop fans, gym-goers")

        setup = QGridLayout()
        setup.setHorizontalSpacing(MD)
        setup.setVerticalSpacing(MD)
        setup.addWidget(field("Artist / project name", self.music_artist_input),
                        0, 0, 1, 2, Qt.AlignTop)
        setup.addWidget(field("Genre", self.music_genre_box), 0, 2, Qt.AlignTop)
        setup.addWidget(field("Release type", self.music_release_type_box),
                        1, 0, Qt.AlignTop)
        setup.addWidget(field("Distributor", self.music_distributor_box),
                        1, 1, Qt.AlignTop)
        setup.addWidget(field("Target audience", self.music_audience_input),
                        1, 2, Qt.AlignTop)
        for column in range(3):
            setup.setColumnStretch(column, 1)
        layout.addLayout(setup)

        self.music_query_input = QTextEdit()
        self.music_query_input.setPlaceholderText(
            "Your sound, influences, vibe, and anything specific about this "
            "release — e.g. dark trap beats with melodic hooks, a 4-track EP "
            "about late-night city life.")
        self.music_query_input.setFixedHeight(70)
        layout.addWidget(field("Describe your music", self.music_query_input))

        layout.addWidget(section("Model"))
        self.music_panel_base = AgentPanel(
            host, "music",
            providers=("ollama", "openai", "deepseek", "kimi", "gemini",
                       "anthropic", "qwen"),
            default_provider="anthropic")
        self.music_provider_box = self.music_panel_base.provider_box
        self.music_model_box = self.music_panel_base.model_box
        models = QGridLayout()
        models.setHorizontalSpacing(MD)
        models.setVerticalSpacing(MD)
        models.addWidget(field("Provider", self.music_provider_box),
                         0, 0, Qt.AlignTop)
        models.addWidget(field("Model", self.music_model_box),
                         0, 1, Qt.AlignTop)
        for column in range(3):
            models.setColumnStretch(column, 1)
        layout.addLayout(models)

        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.music_analyse_btn = primary("Generate Plan")
        self.music_analyse_btn.setMinimumWidth(160)
        self.music_analyse_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.music_analyse_btn.clicked.connect(host.music_analyse)
        actions.addWidget(self.music_analyse_btn)
        self.music_save_btn = QPushButton("Save Full Plan")
        self.music_save_btn.setEnabled(False)
        self.music_save_btn.clicked.connect(host.music_save)
        actions.addWidget(self.music_save_btn)
        self.music_clear_btn = QPushButton("Clear")
        self.music_clear_btn.clicked.connect(host.music_clear)
        actions.addWidget(self.music_clear_btn)
        self.music_stop_btn = QPushButton("Stop")
        self.music_stop_btn.setObjectName("DangerAction")
        self.music_stop_btn.clicked.connect(host.music_stop)
        self.music_stop_btn.hide()
        actions.addWidget(self.music_stop_btn)
        actions.addStretch()
        self.music_status_label = QLabel("")
        self.music_status_label.setObjectName("EstimateLine")
        actions.addWidget(self.music_status_label)
        layout.addLayout(actions)

        self.music_tabs = QTabWidget()
        self.music_profile_box = QTextBrowser()
        self.music_profile_box.setOpenExternalLinks(False)
        self.music_tabs.addTab(self.music_profile_box, "Artist Profile")
        self.music_release_box = QTextBrowser()
        self.music_tabs.addTab(self.music_release_box, "Release Setup")
        self.music_distribution_box = QTextBrowser()
        self.music_tabs.addTab(self.music_distribution_box, "Distribution")
        self.music_strategy_box = QTextBrowser()
        self.music_tabs.addTab(self.music_strategy_box, "Spotify Strategy")
        self.music_income_box = QTextBrowser()
        self.music_tabs.addTab(self.music_income_box, "Income Roadmap")
        self.music_suno_panel = SunoPanel(host)
        self.music_tabs.addTab(self.music_suno_panel, "Songs & Albums")
        layout.addWidget(self.music_tabs, 1)

        # Recommendation, tooltip and Suno integrations still look these up
        # on the host; the actual controls and layout belong to this widget.
        for name in self.HOST_CONTROLS:
            setattr(host, name, getattr(self, name))
        self.hide()
        self.music_panel_base.load_models()
