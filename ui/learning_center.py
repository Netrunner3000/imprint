"""The Learning Centre dialog.

The Learning Centre is an operating manual, not a second documentation window.
It gives each page a purpose and reading order, searches the complete handbook,
and renders the markdown with a deliberately narrow, legible reading column.

The markdown stays in ``docs/learn`` so it can be edited and tested without
touching the UI. The dialog resolves bundled images and keeps cross-page links
inside Imprint, including links to a heading on another page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import markdown
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSplitter, QTextBrowser, QVBoxLayout,
    QWidget,
)

from ui.style import (
    ACCENT, ACCENT_LINE, ACCENT_WASH, BG, BORDER, BORDER_STRONG, ELEVATED,
    SURFACE, SUNKEN, TEXT, TEXT_DIM, TEXT_MUTE,
)


@dataclass(frozen=True)
class LearnPage:
    """One chapter in the handbook and the promise shown in navigation."""

    filename: str
    title: str
    description: str


# Deliberate reading order. A directory scan would turn filename order into
# information architecture and leave no room for a useful navigation summary.
PAGES: list[LearnPage] = [
    LearnPage("01-getting-started.md", "Start here",
              "Set up, orient yourself, and complete one proof-of-work."),
    LearnPage("02-agents.md", "Controls & agents",
              "What every workspace, field, button, and output is for."),
    LearnPage("03-profit.md", "Income science",
              "Model unit economics and run bounded revenue experiments."),
    LearnPage("04-workflows.md", "Automation playbooks",
              "Turn validated offers into repeatable human-in-the-loop loops."),
    LearnPage("05-best-practices.md", "Operate safely",
              "Control quality, spend, rights, data, and provider failures."),
    LearnPage("06-measure-and-improve.md", "Measure & improve",
              "Review one scoreboard and decide what to stop, fix, or scale."),
    LearnPage("07-troubleshooting.md", "Troubleshooting",
              "Recover from missing keys, stuck jobs, empty outputs, and more."),
]


DOCUMENT_CSS = f"""
body {{ color: {TEXT}; background: {SUNKEN}; font-family: -apple-system,
       BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 15px;
       line-height: 1.55; margin: 24px 34px 54px 34px; }}
h1 {{ color: {TEXT}; font-size: 30px; font-weight: 700; margin: 4px 0 12px 0; }}
h2 {{ color: {TEXT}; font-size: 21px; font-weight: 650; margin: 34px 0 10px 0;
      padding-bottom: 8px; border-bottom: 1px solid {BORDER}; }}
h3 {{ color: {TEXT}; font-size: 17px; font-weight: 650; margin: 24px 0 8px 0; }}
p, li {{ color: {TEXT_DIM}; }}
strong {{ color: {TEXT}; font-weight: 650; }}
a {{ color: {ACCENT}; text-decoration: none; }}
code {{ color: {TEXT}; background: {ELEVATED}; padding: 2px 5px;
        border-radius: 4px; font-family: 'SF Mono', Menlo, monospace; }}
pre {{ color: {TEXT}; background: {BG}; border: 1px solid {BORDER};
       border-radius: 8px; padding: 14px; white-space: pre-wrap; }}
blockquote {{ color: {TEXT_DIM}; background: {ACCENT_WASH};
              border-left: 4px solid {ACCENT}; margin: 18px 0;
              padding: 12px 16px; }}
table {{ border-collapse: collapse; margin: 16px 0 24px 0; }}
th {{ color: {TEXT}; background: {ELEVATED}; font-weight: 650;
      border: 1px solid {BORDER_STRONG}; padding: 9px 11px; }}
td {{ color: {TEXT_DIM}; border: 1px solid {BORDER}; padding: 9px 11px;
      vertical-align: top; }}
hr {{ border: 0; border-top: 1px solid {BORDER}; margin: 30px 0; }}
img {{ margin: 14px 0 22px 0; }}
"""


def learn_dir(resource_dir: Path) -> Path:
    return Path(resource_dir) / "docs" / "learn"


def _fit_images(html: str, viewport_width: int) -> str:
    """Constrain high-resolution screenshots to a readable secondary role."""
    width = max(420, min(viewport_width - 72, 720))
    return re.sub(r"<img ", f'<img width="{width}" ', html)


def show_learning_center(app, resource_dir: Path,
                         start_page: str | None = None) -> QDialog:
    """Open the searchable, bundled Learning Centre."""
    base = learn_dir(resource_dir)
    available = [page for page in PAGES if (base / page.filename).exists()]

    dialog = QDialog(app)
    dialog.setObjectName("LearningCentreDialog")
    dialog.setWindowTitle("Learning Centre · Imprint")
    dialog.setMinimumSize(980, 680)
    dialog.resize(1280, 840)

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(24, 20, 24, 18)
    outer.setSpacing(16)

    header = QFrame()
    header.setObjectName("LearnHeader")
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(18, 14, 18, 14)
    header_copy = QVBoxLayout()
    eyebrow = QLabel("IMPRINT PLAYBOOK")
    eyebrow.setObjectName("LearnEyebrow")
    title = QLabel("Learning Centre")
    title.setObjectName("LearnTitle")
    subtitle = QLabel(
        "Operate the studio · prove the economics · automate what works")
    subtitle.setObjectName("LearnSubtitle")
    header_copy.addWidget(eyebrow)
    header_copy.addWidget(title)
    header_copy.addWidget(subtitle)
    header_layout.addLayout(header_copy)
    header_layout.addStretch()
    outer.addWidget(header)

    splitter = QSplitter(Qt.Horizontal)
    splitter.setObjectName("LearnSplitter")
    splitter.setChildrenCollapsible(False)

    nav = QWidget()
    nav.setObjectName("LearnNavigation")
    nav_layout = QVBoxLayout(nav)
    nav_layout.setContentsMargins(0, 0, 8, 0)
    nav_layout.setSpacing(10)
    nav_label = QLabel("HANDBOOK")
    nav_label.setObjectName("LearnSectionLabel")
    nav_layout.addWidget(nav_label)

    search = QLineEdit()
    search.setObjectName("LearnSearch")
    search.setPlaceholderText("Search controls, metrics, fixes…")
    search.setClearButtonEnabled(True)
    search.setAccessibleName("Search the Learning Centre")
    nav_layout.addWidget(search)

    contents = QListWidget()
    contents.setObjectName("LearnContents")
    contents.setSpacing(3)
    contents.setWordWrap(True)
    contents.setTextElideMode(Qt.ElideNone)
    contents.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    contents.setAccessibleName("Learning Centre chapters")
    nav_layout.addWidget(contents, 1)

    search_hint = QLabel("Search checks every chapter, not only the open page.")
    search_hint.setObjectName("LearnHint")
    search_hint.setWordWrap(True)
    nav_layout.addWidget(search_hint)

    reading = QWidget()
    reading.setObjectName("LearnReading")
    reading_layout = QVBoxLayout(reading)
    reading_layout.setContentsMargins(8, 0, 0, 0)
    reading_layout.setSpacing(10)

    context_row = QHBoxLayout()
    page_context = QLabel("OPERATING MANUAL")
    page_context.setObjectName("LearnPageContext")
    page_progress = QLabel()
    page_progress.setObjectName("LearnProgress")
    context_row.addWidget(page_context)
    context_row.addStretch()
    context_row.addWidget(page_progress)
    reading_layout.addLayout(context_row)

    browser = QTextBrowser()
    browser.setObjectName("LearnBrowser")
    browser.setOpenLinks(False)
    browser.setOpenExternalLinks(False)
    browser.setSearchPaths([str(base)])
    browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
    reading_layout.addWidget(browser, 1)

    splitter.addWidget(nav)
    splitter.addWidget(reading)
    nav.setMinimumWidth(300)
    nav.setMaximumWidth(340)
    splitter.setSizes([310, 890])
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    outer.addWidget(splitter, 1)

    footer = QHBoxLayout()
    footer.setSpacing(8)
    prev_btn = QPushButton("← Previous")
    prev_btn.setObjectName("LearnPrevious")
    next_btn = QPushButton("Next →")
    next_btn.setObjectName("LearnNext")
    close_btn = QPushButton("Close")
    close_btn.setObjectName("LearnClose")
    footer.addWidget(prev_btn)
    footer.addWidget(next_btn)
    footer.addStretch()
    footer.addWidget(close_btn)
    outer.addLayout(footer)

    dialog.setStyleSheet(f"""
        QDialog#LearningCentreDialog {{ background: {BG}; }}
        QFrame#LearnHeader {{ background: {SURFACE}; border: 1px solid {BORDER};
                             border-radius: 12px; }}
        QLabel#LearnEyebrow, QLabel#LearnSectionLabel, QLabel#LearnPageContext {{
            color: {ACCENT}; font-size: 10px; font-weight: 700;
            letter-spacing: 1px; }}
        QLabel#LearnTitle {{ color: {TEXT}; font-size: 24px; font-weight: 700; }}
        QLabel#LearnSubtitle, QLabel#LearnProgress {{ color: {TEXT_DIM}; }}
        QLabel#LearnHint {{ color: {TEXT_MUTE}; font-size: 11px; padding: 2px; }}
        QWidget#LearnNavigation, QWidget#LearnReading {{ background: transparent; }}
        QLineEdit#LearnSearch {{ background: {SUNKEN}; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 8px; padding: 9px 11px; }}
        QLineEdit#LearnSearch:focus {{ border: 1px solid {ACCENT_LINE}; }}
        QListWidget#LearnContents {{ background: transparent; border: none;
            padding: 0; outline: none; }}
        QListWidget#LearnContents::item {{ color: {TEXT_DIM}; background: {SURFACE};
            border: 1px solid {BORDER}; border-radius: 8px; padding: 10px 11px;
            margin: 1px 0; }}
        QListWidget#LearnContents::item:hover {{ color: {TEXT};
            border: 1px solid {BORDER_STRONG}; background: {ELEVATED}; }}
        QListWidget#LearnContents::item:selected {{ color: {TEXT};
            background: {ACCENT_WASH}; border: 1px solid {ACCENT_LINE}; }}
        QTextBrowser#LearnBrowser {{ background: {SUNKEN}; color: {TEXT};
            border: 1px solid {BORDER}; border-radius: 10px; padding: 0; }}
    """)

    def add_item(page: LearnPage) -> None:
        index = PAGES.index(page) + 1
        item = QListWidgetItem(
            f"{index:02d}  {page.title}\n{page.description}")
        item.setData(Qt.UserRole, page.filename)
        item.setData(Qt.UserRole + 1, page.title)
        item.setToolTip(page.description)
        item.setSizeHint(QSize(285, 76))
        contents.addItem(item)

    def repopulate(query: str = "") -> None:
        selected = (contents.currentItem().data(Qt.UserRole)
                    if contents.currentItem() else None)
        terms = [term for term in query.casefold().split() if term]
        contents.blockSignals(True)
        contents.clear()
        for page in available:
            text = (base / page.filename).read_text(encoding="utf-8")
            haystack = f"{page.title} {page.description} {text}".casefold()
            if all(term in haystack for term in terms):
                add_item(page)
        contents.blockSignals(False)
        if not contents.count():
            browser.setHtml(
                "<h1>No matching chapter</h1>"
                "<p>Try a control name, agent, metric, or error message.</p>")
            page_progress.setText("0 results")
            prev_btn.setEnabled(False)
            next_btn.setEnabled(False)
            return
        row = next((i for i in range(contents.count())
                    if contents.item(i).data(Qt.UserRole) == selected), 0)
        contents.setCurrentRow(row)

    def render(filename: str, anchor: str = "") -> None:
        path = base / filename
        if not path.exists():
            browser.setHtml(
                f"<h1>Missing page</h1><p>Expected <code>{path}</code>.</p>")
            return
        html = markdown.markdown(
            path.read_text(encoding="utf-8"),
            extensions=["tables", "fenced_code", "toc"],
        )
        html = _fit_images(html, max(browser.viewport().width(), 780))
        browser.setSearchPaths([str(base)])
        browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
        browser.setHtml(html)
        if anchor:
            browser.scrollToAnchor(anchor)
        else:
            browser.verticalScrollBar().setValue(0)

    def update_navigation(filename: str) -> None:
        index = next((i for i, page in enumerate(available)
                      if page.filename == filename), 0)
        page_progress.setText(f"{index + 1} of {len(available)}")
        prev_btn.setEnabled(index > 0)
        next_btn.setEnabled(index < len(available) - 1)

    def on_selected(row: int) -> None:
        item = contents.item(row)
        if item is None:
            return
        filename = item.data(Qt.UserRole)
        page_context.setText(item.data(Qt.UserRole + 1).upper())
        update_navigation(filename)
        render(filename)

    def select_filename(filename: str, anchor: str = "") -> bool:
        # Clear a filter if an internal link points to a currently hidden page.
        for attempt in range(2):
            for index in range(contents.count()):
                if contents.item(index).data(Qt.UserRole) == filename:
                    contents.setCurrentRow(index)
                    if anchor:
                        browser.scrollToAnchor(anchor)
                    return True
            if attempt == 0 and search.text():
                search.clear()
        return False

    def move_page(offset: int) -> None:
        item = contents.currentItem()
        if item is None:
            return
        filename = item.data(Qt.UserRole)
        index = next((i for i, page in enumerate(available)
                      if page.filename == filename), -1)
        target = index + offset
        if 0 <= target < len(available):
            select_filename(available[target].filename)

    def on_link(url: QUrl) -> None:
        """Keep handbook links in Imprint; open real web links externally."""
        path = url.path()
        if path.endswith(".md"):
            select_filename(Path(path).name, url.fragment())
            return
        if url.scheme() in ("http", "https"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
            return
        if url.fragment():
            browser.scrollToAnchor(url.fragment())

    contents.currentRowChanged.connect(on_selected)
    search.textChanged.connect(repopulate)
    search.returnPressed.connect(
        lambda: contents.setFocus() if contents.count() else None)
    browser.anchorClicked.connect(on_link)
    prev_btn.clicked.connect(lambda: move_page(-1))
    next_btn.clicked.connect(lambda: move_page(1))
    close_btn.clicked.connect(dialog.accept)

    repopulate()
    if available:
        select_filename(start_page or available[0].filename)
    else:
        browser.setHtml(
            "<h1>No learning pages found</h1>"
            f"<p>Expected markdown files in <code>{base}</code>.</p>")

    dialog.exec()
    return dialog
