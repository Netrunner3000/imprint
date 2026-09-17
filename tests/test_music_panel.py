"""Music panel behavior without a paid request or a live provider."""

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from agents.music import MusicAgent, MusicPanel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeClient:
    def list_models(self):
        return ["test-model"]


class FakeWorker(QObject):
    token_signal = Signal(str)
    finished_signal = Signal(str)
    usage_signal = Signal(dict)
    error_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.started = False

    def start(self):
        self.started = True


class FakeHost:
    anthropic = FakeClient()

    def __init__(self):
        self.agent_instances = {"music": MusicAgent()}
        self.music_worker = None
        self.allowed = False
        self.authorized = []
        self.recorded = []
        self.abandoned = []
        self.workers = []

    def _note_failure(self, *_args):
        raise AssertionError("Model listing should not fail")

    def authorize_request(self, agent, provider, model, prompt):
        self.authorized.append((agent, provider, model, prompt))
        return self.allowed

    def _new_chat_worker(self, provider, model, messages, prompt):
        self.workers.append((provider, model, messages, prompt))
        return FakeWorker()

    def note_request_usage(self, *_args):
        pass

    def record_request(self, agent, response):
        self.recorded.append((agent, response))

    def abandon_request(self, agent):
        self.abandoned.append(agent)


def test_denied_music_request_keeps_panel_usable(app, tmp_path, monkeypatch):
    import agents.music.suno_panel as suno_module

    monkeypatch.setattr(suno_module, "user_data_base", lambda: tmp_path)
    host = FakeHost()
    panel = MusicPanel(host)
    try:
        panel.music_query_input.setPlainText("A four-track ambient release")
        panel.analyse()
        assert host.authorized[0][0:3] == ("music", "anthropic", "test-model")
        assert host.music_worker is None
        assert panel.music_analyse_btn.isEnabled()
        assert not panel.music_stop_btn.isVisible()
    finally:
        panel.close()


def test_music_response_is_saved_and_split_into_tabs(app, tmp_path, monkeypatch):
    import agents.music.suno_panel as suno_module

    monkeypatch.setattr(suno_module, "user_data_base", lambda: tmp_path)
    host = FakeHost()
    host.allowed = True
    panel = MusicPanel(host)
    try:
        panel.music_artist_input.setText("Nova")
        panel.music_query_input.setPlainText("A four-track ambient release")
        panel.analyse()
        worker = host.music_worker
        assert worker.started
        assert host.workers[0][2][0]["role"] == "system"
        assert "Nova" in host.workers[0][3]
        response = (
            "1. ARTIST PROFILE\nBio\n"
            "2. RELEASE SETUP\nTracks\n"
            "3. DISTRIBUTION GUIDE\nDistributor\n"
            "4. SPOTIFY STRATEGY\nPitch\n"
            "5. INCOME ROADMAP\nMeasure receipts"
        )
        worker.finished_signal.emit(response)
        app.processEvents()
        assert host.recorded == [("music", response)]
        assert panel.music_profile_box.toPlainText() == "Bio"
        assert panel.music_income_box.toPlainText() == "Measure receipts"
        assert panel.music_analyse_btn.isEnabled()
        assert panel.music_save_btn.isEnabled()
        panel.clear()
        assert panel.music_income_box.toPlainText() == ""
        assert not panel.music_save_btn.isEnabled()
    finally:
        panel.close()


def test_suno_handoff_uses_project_aware_host_worker(app, tmp_path, monkeypatch):
    import agents.music.suno_panel as suno_module

    monkeypatch.setattr(suno_module, "user_data_base", lambda: tmp_path)
    host = FakeHost()
    host.allowed = True
    panel = MusicPanel(host)
    try:
        suno = panel.music_suno_panel
        suno.title.setText("Night Drive")
        suno.brief.setPlainText("Four original ambient tracks")
        suno.draft()
        assert host.workers
        assert host.music_worker is suno.worker
        assert host.workers[0][2][0]["role"] == "system"
        assert host.workers[0][2][-1]["role"] == "user"
        suno.worker.finished_signal.emit("Song prompts")
        app.processEvents()
        assert host.recorded == [("music", "Song prompts")]
    finally:
        panel.close()
