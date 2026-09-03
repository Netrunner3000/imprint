"""
Create & Publish — AgentPanel / AgentHost tests
===============================================
Type: Unit tests for the phase 3 refactor seam.

`ui/panels/base.py` absorbed five near-identical `*_load_models` methods. Two of
those five differed in ways that mattered, so this file pins both the shared
behaviour and the differences that had to survive:

  - manuscript offers a restricted provider list (no ollama), matching the
    allowed_providers on its registry row;
  - failures are reported through the host rather than swallowed, which the
    music panel used not to do.

Run with:  pytest tests/test_agent_panel.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui.host import AgentHost
from ui.panels.base import ALL_PROVIDERS, AgentPanel


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class FakeClient:
    def __init__(self, models):
        self._models = models

    def list_models(self):
        return list(self._models)


class ExplodingClient:
    def list_models(self):
        raise RuntimeError("provider unreachable")


class FakeHost:
    """Minimal stand-in for GodAI — only what AgentHost promises."""

    def __init__(self, **clients):
        for name in ALL_PROVIDERS:
            setattr(self, name, clients.get(name, FakeClient([f"{name}-a", f"{name}-b"])))
        self.agent_instances = {}
        self.failures = []

    def run_backend(self, backend, model, messages, prompt): ...
    def authorize_request(self, agent, provider, model, prompt, tool=None, label=None): ...
    def record_request(self, agent, response, messages=None): ...
    def abandon_request(self, agent, reason="error"): ...
    def note_request_usage(self, agent, usage): ...
    def show_agent_docs(self): ...

    def _note_failure(self, context, exc, widget=None):
        self.failures.append((context, exc))


def test_fake_host_satisfies_the_protocol():
    """The point of a runtime-checkable protocol: a stand-in can be verified."""
    assert isinstance(FakeHost(), AgentHost)


def test_provider_box_lists_every_provider_by_default(app):
    panel = AgentPanel(FakeHost(), "author")
    items = [panel.provider_box.itemText(i) for i in range(panel.provider_box.count())]
    assert items == list(ALL_PROVIDERS)


def test_restricted_provider_list_is_honoured(app):
    """manuscript must not offer ollama — the validator would refuse it."""
    panel = AgentPanel(FakeHost(), "manuscript",
                       providers=("anthropic", "openai", "deepseek", "kimi", "gemini", "qwen"))
    items = [panel.provider_box.itemText(i) for i in range(panel.provider_box.count())]
    assert "ollama" not in items
    assert items[0] == "anthropic"


def test_default_provider_is_selected(app):
    panel = AgentPanel(FakeHost(), "author", default_provider="anthropic")
    assert panel.provider_box.currentText() == "anthropic"


def test_a_default_outside_the_list_is_ignored(app):
    """Asking for a provider this agent may not use must not add it."""
    panel = AgentPanel(FakeHost(), "manuscript",
                       providers=("anthropic", "openai"), default_provider="ollama")
    assert panel.provider_box.currentText() == "anthropic"


def test_load_models_fills_the_box_from_the_selected_provider(app):
    host = FakeHost(openai=FakeClient(["gpt-4o-mini", "gpt-4.1"]))
    panel = AgentPanel(host, "author", default_provider="openai")
    panel.load_models()
    assert [panel.model_box.itemText(i) for i in range(panel.model_box.count())] == \
        ["gpt-4o-mini", "gpt-4.1"]


def test_switching_provider_reloads_the_models(app):
    host = FakeHost(openai=FakeClient(["gpt-4o-mini"]),
                    anthropic=FakeClient(["claude-sonnet-5"]))
    panel = AgentPanel(host, "author", default_provider="openai")
    panel.provider_box.setCurrentText("anthropic")
    assert panel.model == "claude-sonnet-5"


def test_reloading_does_not_duplicate_entries(app):
    panel = AgentPanel(FakeHost(), "author", default_provider="openai")
    panel.load_models()
    panel.load_models()
    assert panel.model_box.count() == 2


def test_every_listed_provider_can_load(app):
    """manuscript listed qwen but its old loader had no qwen branch, so picking
    it silently produced an empty model box. Every listed provider must load."""
    panel = AgentPanel(FakeHost(), "manuscript",
                       providers=("anthropic", "openai", "deepseek", "kimi", "gemini", "qwen"))
    for provider in ("anthropic", "openai", "deepseek", "kimi", "gemini", "qwen"):
        panel.provider_box.setCurrentText(provider)
        # Explicit: setting the box to the value it already holds emits no
        # currentTextChanged, so the first provider would never load itself.
        panel.load_models()
        assert panel.model_box.count() > 0, f"{provider} loaded nothing"


def test_a_failing_provider_is_reported_not_swallowed(app):
    """The music panel used to do `except Exception: models = []`, leaving an
    empty dropdown and no explanation."""
    host = FakeHost(openai=ExplodingClient())
    panel = AgentPanel(host, "music", default_provider="openai")
    panel.load_models()
    assert host.failures, "failure was swallowed"
    context, exc = host.failures[-1]
    assert context == "music: load models"
    assert isinstance(exc, RuntimeError)


def test_a_failing_provider_leaves_the_box_empty_rather_than_stale(app):
    host = FakeHost(openai=FakeClient(["gpt-4o-mini"]), anthropic=ExplodingClient())
    panel = AgentPanel(host, "music", default_provider="openai")
    panel.load_models()
    panel.provider_box.setCurrentText("anthropic")
    assert panel.model_box.count() == 0
