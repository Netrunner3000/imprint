"""The Learning Centre dialog.

Renders `docs/learn/*.md` — a contents list on the left, the rendered page on
the right. Kept out of main.py because it is self-contained: it needs the app
only as a dialog parent and as the source of `RESOURCE_DIR`.

Two things it deliberately does that `show_docs` does not:

* **Images resolve.** QTextBrowser looks relative paths up against its search
  paths, so `img/foo.png` in the markdown needs `docs/learn` registered or every
  screenshot silently renders as a broken-image box.
* **Cross-page links work.** The pages link to each other by filename
  (`03-profit.md`). Those are intercepted and switched to, rather than handed
  to a browser that would try to open them as URLs.
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QTextBrowser, QVBoxLayout, QWidget,
)

# Ordered, with the titles shown in the contents list. Filenames rather than a
# directory scan so the order is the reading order, not alphabetical luck.
PAGES: list[tuple[str, str]] = [
    ("01-getting-started.md", "Getting started"),
    ("02-agents.md", "The agents"),
    ("03-profit.md", "Making money"),
    ("04-workflows.md", "Workflows"),
    ("05-best-practices.md", "Best practices"),
]


def learn_dir(resource_dir: Path) -> Path:
    return Path(resource_dir) / "docs" / "learn"


def _fit_images(html: str, viewport_width: int) -> str:
    """Constrain screenshots to the reading pane.

    The screenshots are grabbed at 1760px so they stay legible when opened on
    their own, which is far wider than this dialog. QTextBrowser honours an
    img `width` attribute but ignores CSS max-width, so the width is written in
    rather than styled — otherwise every page scrolls sideways.
    """
    width = max(360, min(viewport_width - 48, 900))
    return re.sub(r"<img ", f'<img width="{width}" ', html)


def show_learning_center(app, resource_dir: Path,
                         start_page: str | None = None) -> QDialog:
    """Open the Learning Centre.

    `app` is the main window (dialog parent); `resource_dir` is the project root
    in development and the bundled resource root when frozen, so the pages are
    found in both.
    """
    base = learn_dir(resource_dir)

    dialog = QDialog(app)
    dialog.setWindowTitle("Learning Centre")
    dialog.resize(1120, 780)

    outer = QVBoxLayout(dialog)
    body = QHBoxLayout()
    outer.addLayout(body, 1)

    contents = QListWidget()
    contents.setMaximumWidth(210)
    contents.setObjectName("LearnContents")

    browser = QTextBrowser()
    browser.setOpenLinks(False)
    browser.setOpenExternalLinks(False)
    # Without this, every img/*.png in the markdown renders as a broken box.
    browser.setSearchPaths([str(base)])

    body.addWidget(contents)
    body.addWidget(browser, 1)

    available = [(f, t) for f, t in PAGES if (base / f).exists()]
    for filename, title in available:
        item = QListWidgetItem(title)
        item.setData(Qt.UserRole, filename)
        contents.addItem(item)

    def render(filename: str) -> None:
        path = base / filename
        if not path.exists():
            browser.setHtml(
                f"<h2>Missing page</h2><p>Expected <code>{path}</code>.</p>")
            return
        html = markdown.markdown(
            path.read_text(encoding="utf-8"),
            extensions=["tables", "fenced_code", "toc"],
        )
        html = _fit_images(html, browser.viewport().width())
        browser.setSearchPaths([str(base)])
        browser.setHtml(html)
        browser.verticalScrollBar().setValue(0)

    def on_selected(row: int) -> None:
        if 0 <= row < len(available):
            render(available[row][0])

    contents.currentRowChanged.connect(on_selected)

    def on_link(url: QUrl) -> None:
        """Keep in-app links in the app; hand real URLs to the browser."""
        target = url.toString()
        if target.endswith(".md"):
            name = target.split("/")[-1]
            for index, (filename, _) in enumerate(available):
                if filename == name:
                    contents.setCurrentRow(index)
                    return
            return
        if url.scheme() in ("http", "https"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
            return
        if url.fragment():
            browser.scrollToAnchor(url.fragment())

    browser.anchorClicked.connect(on_link)

    close_row = QHBoxLayout()
    close_row.addStretch()
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    close_row.addWidget(close_btn)
    outer.addLayout(close_row)

    if available:
        start = 0
        if start_page:
            for index, (filename, _) in enumerate(available):
                if filename == start_page:
                    start = index
                    break
        contents.setCurrentRow(start)
        render(available[start][0])
    else:
        browser.setHtml(
            "<h2>No learning pages found</h2>"
            f"<p>Expected markdown files in <code>{base}</code>.</p>")

    dialog.exec()
    return dialog
