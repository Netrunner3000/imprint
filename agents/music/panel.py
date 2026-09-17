"""Music workspace, including its release-plan request and result lifecycle.

The umbrella remains responsible for shared provider execution, permissions,
spending and run history. The panel owns Music-specific controls and behavior.
"""

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSizePolicy, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from services.runtime_paths import user_data_base
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
        self.host = host
        self.last_response = ""
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
        self.music_analyse_btn.clicked.connect(self.analyse)
        actions.addWidget(self.music_analyse_btn)
        self.music_save_btn = QPushButton("Save Full Plan")
        self.music_save_btn.setEnabled(False)
        self.music_save_btn.clicked.connect(self.save)
        actions.addWidget(self.music_save_btn)
        self.music_clear_btn = QPushButton("Clear")
        self.music_clear_btn.clicked.connect(self.clear)
        actions.addWidget(self.music_clear_btn)
        self.music_stop_btn = QPushButton("Stop")
        self.music_stop_btn.setObjectName("DangerAction")
        self.music_stop_btn.clicked.connect(self.stop)
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
        host.music_panel = self
        self.hide()
        self.music_panel_base.load_models()

    def analyse(self):
        description = self.music_query_input.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Missing Input", "Please describe your music in the text box.")
            return
        provider = self.music_provider_box.currentText()
        model = self.music_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return

        artist = self.music_artist_input.text().strip()
        prompt_parts = []
        if artist:
            prompt_parts.append(f"Artist / Project Name: {artist}")
        prompt_parts += [
            f"Genre: {self.music_genre_box.currentText()}",
            f"Release Type: {self.music_release_type_box.currentText()}",
            f"Current Distributor: {self.music_distributor_box.currentText()}",
        ]
        audience = self.music_audience_input.text().strip()
        if audience:
            prompt_parts.append(f"Target Audience: {audience}")
        prompt_parts.append(f"\nMusic Description:\n{description}")
        prompt = "\n".join(prompt_parts)

        # A denied paid request must leave the panel usable. Previously this
        # guard ran after disabling Generate, with no path to re-enable it.
        if not self.host.authorize_request("music", provider, model, prompt):
            return
        messages = self.host.agent_instances["music"].build_messages(prompt)
        self._clear_displays()
        self.last_response = ""
        self.music_status_label.setText("Generating Spotify plan…")
        self.music_analyse_btn.setEnabled(False)
        self.music_stop_btn.setEnabled(True)
        self.music_stop_btn.show()
        self.music_save_btn.setEnabled(False)

        try:
            worker = self.host._new_chat_worker(provider, model, messages, prompt)
            self.host.music_worker = worker
            worker.token_signal.connect(self._on_token)
            worker.finished_signal.connect(self._on_finished)
            worker.usage_signal.connect(
                lambda usage: self.host.note_request_usage("music", usage))
            worker.error_signal.connect(self._on_error)
            worker.start()
        except Exception as error:
            self._on_error(str(error))

    def _on_token(self, token: str):
        self.last_response += token
        self.music_profile_box.setPlainText(self.last_response)
        self.music_profile_box.moveCursor(QTextCursor.End)

    def _on_finished(self, response: str):
        self.host.record_request("music", response)
        self.last_response = response
        self._populate_tabs(response)
        self.music_status_label.setText("Plan complete — tabs populated.")
        self._set_idle()
        self.music_save_btn.setEnabled(True)

    def _on_error(self, error: str):
        self.host.abandon_request("music")
        self.music_profile_box.setPlainText(f"[Error] {error}")
        self.music_status_label.setText("Error.")
        self._set_idle()

    def _set_idle(self):
        self.music_analyse_btn.setEnabled(True)
        self.music_stop_btn.setEnabled(False)
        self.music_stop_btn.hide()

    def stop(self):
        worker = self.host.music_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
        self.music_status_label.setText("Stopped.")
        self._set_idle()

    def save(self):
        if not self.last_response:
            return
        artist = self.music_artist_input.text().strip().lower().replace(" ", "_") or "artist"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"spotify_plan_{artist}_{timestamp}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Spotify Plan",
            str(user_data_base() / "data" / default_name),
            "Text files (*.txt);;All files (*)",
        )
        if path:
            Path(path).write_text(self.last_response, encoding="utf-8")
            self.music_status_label.setText(f"Saved to {Path(path).name}")

    def clear(self):
        self._clear_displays()
        self.music_query_input.clear()
        self.music_artist_input.clear()
        self.music_audience_input.clear()
        self.music_status_label.setText("")
        self.last_response = ""

    def _clear_displays(self):
        for box in (
            self.music_profile_box, self.music_release_box,
            self.music_distribution_box, self.music_strategy_box,
            self.music_income_box,
        ):
            box.clear()
        self.music_save_btn.setEnabled(False)

    def _populate_tabs(self, text: str):
        sections = self.parse_sections(text)
        self.music_profile_box.setPlainText(sections.get("profile", text))
        self.music_release_box.setPlainText(sections.get("release", ""))
        self.music_distribution_box.setPlainText(sections.get("distribution", ""))
        self.music_strategy_box.setPlainText(sections.get("strategy", ""))
        self.music_income_box.setPlainText(sections.get("income", ""))

    @staticmethod
    def parse_sections(text: str) -> dict[str, str]:
        patterns = {
            "profile": r"1\.\s*ARTIST PROFILE(.*?)(?=2\.\s*RELEASE SETUP|$)",
            "release": r"2\.\s*RELEASE SETUP(.*?)(?=3\.\s*DISTRIBUTION GUIDE|$)",
            "distribution": r"3\.\s*DISTRIBUTION GUIDE(.*?)(?=4\.\s*SPOTIFY STRATEGY|$)",
            "strategy": r"4\.\s*SPOTIFY STRATEGY(.*?)(?=5\.\s*INCOME ROADMAP|$)",
            "income": r"5\.\s*INCOME ROADMAP(.*?)$",
        }
        result = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            result[key] = match.group(1).strip() if match else ""
        return result
