"""Documentation centre coverage, search, and UI regression tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs" / "agents"


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _manifest():
    return json.loads((DOCS_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_pages_are_unique_and_exist():
    pages = _manifest()["pages"]
    assert len({page["id"] for page in pages}) == len(pages)
    assert len({page["order"] for page in pages}) == len(pages)
    missing = [page["filename"] for page in pages
               if not (DOCS_DIR / page["filename"]).exists()]
    assert not missing


def test_every_documented_agent_is_in_the_reference_navigation():
    from agents.catalog import AGENT_SPECS

    documented = {path.stem for path in DOCS_DIR.glob("*.md")
                  if path.name != "overview.md"}
    listed = {page.get("agent") for page in _manifest()["pages"]
              if page.get("agent")}
    expected = {spec.key for spec in AGENT_SPECS
                if (DOCS_DIR / f"{spec.key}.md").exists()}
    assert documented == expected
    assert listed == expected


def test_search_returns_exact_anchored_sections():
    from ui.docs_center import build_docs_index, load_docs_manifest, search_docs

    _sections, pages = load_docs_manifest(DOCS_DIR)
    hits = search_docs(build_docs_index(DOCS_DIR, pages), "chunk tokens")
    assert hits
    assert hits[0].page.id == "audiobook"
    assert hits[0].anchor
    assert hits[0].snippet


def test_overview_explains_docs_learning_and_evidence_boundaries():
    text = (DOCS_DIR / "overview.md").read_text(encoding="utf-8").casefold()
    for term in (
        "learning centre", "shared systems", "provider best fit",
        "api keys", "costs and limits", "failure triage",
        "observed transaction", "sample data",
    ):
        assert term in text


@pytest.mark.parametrize(
    "agent", ["chat", "course", "fiverr", "music", "onlyfans", "webdesign"])
def test_short_reference_pages_include_an_operating_contract(agent):
    text = (DOCS_DIR / f"{agent}.md").read_text(encoding="utf-8").casefold()
    assert "before you" in text
    assert "verify the" in text
    assert "storage" in text
    assert "common failures" in text


def test_dialog_opens_on_the_active_agent_and_has_navigation(app, monkeypatch):
    from PySide6.QtWidgets import (
        QDialog, QLineEdit, QListWidget, QTextBrowser, QWidget,
    )
    from ui.docs_center import show_docs_center

    monkeypatch.setattr(QDialog, "exec", lambda self: None)

    class Host(QWidget):
        author_panel = object()
        def select_agent(self, _agent): ...

    dialog = show_docs_center(Host(), PROJECT_ROOT, start_page="author")
    assert dialog.current_page.id == "author"
    assert dialog.findChild(QLineEdit, "DocsSearch") is not None
    assert dialog.findChild(QListWidget, "DocsContents") is not None
    browser = dialog.findChild(QTextBrowser, "DocsBrowser")
    assert browser is not None and "Long-form writing studio" in browser.toPlainText()


def test_frozen_bundle_includes_the_reference_manifest_and_pages():
    spec = (PROJECT_ROOT / "Imprint.spec").read_text(encoding="utf-8")
    assert '("docs/agents", "docs/agents")' in spec
