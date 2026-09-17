"""Site Builder panel behavior without a network call or paid provider."""

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QFileDialog

from agents.webdesign import WebdesignAgent, WebdesignPanel


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
        self.agent_instances = {"webdesign": WebdesignAgent()}
        self.webdesign_worker = None
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


def test_denied_site_request_leaves_generate_usable(app):
    host = FakeHost()
    panel = WebdesignPanel(host)
    try:
        assert host.webdesign_panel is panel
        assert host.webdesign_model_box is panel.webdesign_model_box
        panel.webdesign_brief_input.setPlainText("A three-section landing page")
        panel.generate()
        assert host.authorized[0][:3] == ("webdesign", "anthropic", "test-model")
        assert host.webdesign_worker is None
        assert panel.webdesign_generate_btn.isEnabled()
        assert not panel.webdesign_save_btn.isEnabled()
    finally:
        panel.close()


def test_generated_site_splits_tabs_and_saves_clean_html(app, tmp_path, monkeypatch):
    host = FakeHost()
    host.allowed = True
    panel = WebdesignPanel(host)
    try:
        panel.webdesign_brief_input.setPlainText("A three-section landing page")
        panel.generate()
        worker = host.webdesign_worker
        assert worker.started
        assert host.workers[0][2][0]["role"] == "system"
        html = (
            '<html><head><meta name="viewport" content="width=device-width">'
            '<style>h1 { color: red; }</style></head>'
            '<body><h1>Hello</h1><script>console.log(1)</script></body></html>'
        )
        response = f"```html\n{html}\n```"
        worker.finished_signal.emit(response)
        app.processEvents()
        assert host.recorded == [("webdesign", response)]
        assert panel.webdesign_html_box.toPlainText() == html
        assert panel.webdesign_css_box.toPlainText() == "h1 { color: red; }"
        assert panel.webdesign_js_box.toPlainText() == "console.log(1)"
        assert panel.webdesign_responsive_label.text() == "Mobile-first"
        assert panel.webdesign_generate_btn.isEnabled()
        assert panel.webdesign_save_btn.isEnabled()

        output = tmp_path / "site.html"
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName",
            staticmethod(lambda *_args: (str(output), "HTML files (*.html)")),
        )
        panel.save()
        assert output.read_text(encoding="utf-8") == html
        panel.clear()
        assert panel.webdesign_html_box.toPlainText() == ""
        assert not panel.webdesign_save_btn.isEnabled()
    finally:
        panel.close()
