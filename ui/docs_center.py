"""Searchable, contextual technical documentation for Imprint.

The Learning Centre teaches workflows.  This centre is the precise companion:
controls, execution paths, requirements, storage, and failure boundaries for
every agent.  Both are bundled and work offline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import markdown
from PySide6.QtCore import QSettings, QSize, Qt, QUrl
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from ui.learning_center_v2 import (
    DOCUMENT_CSS, _document_sections, _fit_images,
)
from ui.style import (
    ACCENT, ACCENT_LINE, ACCENT_WASH, BG, BORDER, BORDER_STRONG, ELEVATED,
    INFO, INFO_WASH, SURFACE, SUNKEN, TEXT, TEXT_DIM, TEXT_MUTE,
)


@dataclass(frozen=True)
class DocSection:
    id: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class DocPage:
    id: str
    filename: str
    title: str
    description: str
    section: str
    order: int
    agent: str = ""
    workspace: str = ""
    audience: str = "Reference"
    estimated_minutes: int = 0
    keywords: tuple[str, ...] = ()
    updated_at: str = ""


@dataclass(frozen=True)
class DocHit:
    page: DocPage
    heading: str
    anchor: str
    snippet: str
    score: int = field(default=0, compare=False)


def docs_dir(resource_dir: Path) -> Path:
    return Path(resource_dir) / "docs" / "agents"


def load_docs_manifest(base: Path) -> tuple[list[DocSection], list[DocPage]]:
    path = Path(base) / "manifest.json"
    if not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = [DocSection(**raw) for raw in data.get("sections", [])]
    pages = [DocPage(
        id=raw["id"], filename=raw["filename"], title=raw["title"],
        description=raw.get("summary", ""), section=raw.get("section", "advanced"),
        order=int(raw.get("order", 0)), agent=raw.get("agent", ""),
        workspace=raw.get("workspace", ""), audience=raw.get("audience", "Reference"),
        estimated_minutes=int(raw.get("estimated_minutes", 0)),
        keywords=tuple(raw.get("keywords", [])), updated_at=raw.get("updated_at", ""),
    ) for raw in data.get("pages", [])]
    return sections, sorted(pages, key=lambda page: page.order)


def build_docs_index(base: Path, pages: list[DocPage]) -> list[DocHit]:
    results: list[DocHit] = []
    for page in pages:
        path = Path(base) / page.filename
        if not path.exists():
            continue
        for heading, anchor, body in _document_sections(
                path.read_text(encoding="utf-8")):
            results.append(DocHit(page, heading, anchor, body[:300].rstrip()))
    return results


def search_docs(index: list[DocHit], query: str, limit: int = 60) -> list[DocHit]:
    terms = tuple(term for term in query.casefold().split() if term)
    if not terms:
        return []
    ranked: list[DocHit] = []
    for hit in index:
        title = hit.page.title.casefold()
        heading = hit.heading.casefold()
        keywords = " ".join(hit.page.keywords).casefold()
        haystack = " ".join((title, hit.page.description, keywords,
                             heading, hit.snippet)).casefold()
        if not all(term in haystack for term in terms):
            continue
        score = sum(18 if term in heading else 12 if term in title else
                    5 if term in keywords else 1 for term in terms)
        ranked.append(DocHit(hit.page, hit.heading, hit.anchor,
                             hit.snippet, score))
    ranked.sort(key=lambda item: (-item.score, item.page.order, item.heading))
    return ranked[:limit]


DOC_CSS = DOCUMENT_CSS + f"""
body {{ margin-top: 30px; }}
h1 {{ color: {TEXT}; }}
h2 {{ border-bottom-color: {BORDER_STRONG}; }}
"""


class DocsCentreDialog(QDialog):
    """Responsive reference reader with local heading-level search."""

    NAV_BREAKPOINT = 1080
    OUTLINE_BREAKPOINT = 1230

    def __init__(self, app, resource_dir: Path,
                 start_page: str | None = None, start_anchor: str = ""):
        super().__init__(app)
        self.host = app
        self.base = docs_dir(resource_dir)
        self.sections, declared = load_docs_manifest(self.base)
        self.pages = [page for page in declared if (self.base / page.filename).exists()]
        self.page_by_id = {page.id: page for page in self.pages}
        self.page_by_filename = {Path(page.filename).name: page for page in self.pages}
        self.index = build_docs_index(self.base, self.pages)
        self.settings = QSettings("Imprint", "Imprint")
        self.current_page: DocPage | None = None
        self._building_nav = False
        self._nav_forced = False

        self.setObjectName("DocsCentreDialog")
        self.setWindowTitle("Documentation · Imprint")
        self.setMinimumSize(940, 650)
        self.resize(1300, 840)
        self.setAccessibleName("Imprint documentation")
        self.setAccessibleDescription(
            "Searchable technical reference for Imprint agents and shared systems.")
        self._build_ui()
        self._repopulate()

        requested = start_page or str(self.settings.value("docs/last_page", "overview"))
        if not self.select_page(requested, start_anchor):
            self.select_page("overview" if "overview" in self.page_by_id else
                             self.pages[0].id if self.pages else "")

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        top = QFrame()
        top.setObjectName("DocsTopBar")
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(16, 10, 14, 10)
        top_row.setSpacing(10)
        self.contents_btn = QPushButton("Contents")
        self.contents_btn.setObjectName("DocsContentsToggle")
        self.contents_btn.setCheckable(True)
        top_row.addWidget(self.contents_btn)
        title = QLabel("Documentation")
        title.setObjectName("DocsTitle")
        top_row.addWidget(title)
        top_row.addStretch()
        promise = QLabel("Controls · execution paths · requirements · recovery")
        promise.setObjectName("DocsPromise")
        top_row.addWidget(promise)
        outer.addWidget(top)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.nav = QFrame()
        self.nav.setObjectName("DocsNavigation")
        nav_layout = QVBoxLayout(self.nav)
        nav_layout.setContentsMargins(0, 0, 8, 0)
        nav_layout.setSpacing(8)
        nav_layout.addWidget(self._small_title("Browse or search"))
        self.search = QLineEdit()
        self.search.setObjectName("DocsSearch")
        self.search.setPlaceholderText("Control, provider, file, or error…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search all documentation headings and text")
        nav_layout.addWidget(self.search)
        self.contents = QListWidget()
        self.contents.setObjectName("DocsContents")
        self.contents.setSpacing(2)
        self.contents.setWordWrap(True)
        self.contents.setTextElideMode(Qt.ElideRight)
        self.contents.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.contents.setAccessibleName("Documentation sections and search results")
        nav_layout.addWidget(self.contents, 1)
        self.result_note = QLabel()
        self.result_note.setObjectName("DocsHint")
        self.result_note.setWordWrap(True)
        nav_layout.addWidget(self.result_note)

        reading = QWidget()
        reading.setObjectName("DocsReading")
        reading_layout = QVBoxLayout(reading)
        reading_layout.setContentsMargins(8, 0, 0, 0)
        reading_layout.setSpacing(8)
        context = QHBoxLayout()
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("DocsBreadcrumb")
        self.meta = QLabel()
        self.meta.setObjectName("DocsMeta")
        context.addWidget(self.breadcrumb)
        context.addStretch()
        context.addWidget(self.meta)
        reading_layout.addLayout(context)

        self.reader_splitter = QSplitter(Qt.Horizontal)
        self.reader_splitter.setChildrenCollapsible(False)
        self.browser = QTextBrowser()
        self.browser.setObjectName("DocsBrowser")
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setSearchPaths([str(self.base)])
        self.browser.document().setDefaultStyleSheet(DOC_CSS)
        self.browser.setAccessibleName("Current documentation article")
        self.reader_splitter.addWidget(self.browser)

        self.outline_panel = QFrame()
        self.outline_panel.setObjectName("DocsOutlinePanel")
        outline_layout = QVBoxLayout(self.outline_panel)
        outline_layout.setContentsMargins(10, 10, 4, 10)
        outline_layout.setSpacing(7)
        outline_layout.addWidget(self._small_title("On this page"))
        self.outline = QListWidget()
        self.outline.setObjectName("DocsOutline")
        self.outline.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.outline.setAccessibleName("Headings in the current documentation article")
        outline_layout.addWidget(self.outline, 1)
        self.reader_splitter.addWidget(self.outline_panel)
        self.reader_splitter.setSizes([760, 210])
        self.outline_panel.setMinimumWidth(180)
        self.outline_panel.setMaximumWidth(240)
        reading_layout.addWidget(self.reader_splitter, 1)

        self.splitter.addWidget(self.nav)
        self.splitter.addWidget(reading)
        self.nav.setMinimumWidth(265)
        self.nav.setMaximumWidth(320)
        self.splitter.setSizes([290, 970])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        outer.addWidget(self.splitter, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.prev_btn = QPushButton("← Previous")
        self.next_btn = QPushButton("Next →")
        self.learn_btn = QPushButton("Open learning guide")
        self.learn_btn.setObjectName("DocsLearn")
        self.open_btn = QPushButton("Open agent in Imprint")
        self.open_btn.setObjectName("DocsOpen")
        close_btn = QPushButton("Close")
        footer.addWidget(self.prev_btn)
        footer.addWidget(self.next_btn)
        footer.addStretch()
        footer.addWidget(self.learn_btn)
        footer.addWidget(self.open_btn)
        footer.addWidget(close_btn)
        outer.addLayout(footer)

        self.setStyleSheet(f"""
            QDialog#DocsCentreDialog {{ background: {BG}; }}
            QFrame#DocsTopBar {{ background: {SURFACE}; border: 1px solid {BORDER};
                border-radius: 10px; }}
            QLabel#DocsTitle {{ color: {TEXT}; font-size: 20px; font-weight: 700; }}
            QLabel#DocsPromise, QLabel#DocsMeta {{ color: {TEXT_DIM}; font-size: 12px; }}
            QLabel#DocsSectionTitle {{ color: {TEXT}; font-size: 13px;
                font-weight: 650; padding: 2px 3px; }}
            QLabel#DocsBreadcrumb {{ color: {TEXT_DIM}; font-size: 12px; }}
            QLabel#DocsHint {{ color: {TEXT_MUTE}; font-size: 11px; padding: 3px; }}
            QFrame#DocsNavigation, QFrame#DocsOutlinePanel {{ background: transparent; }}
            QLineEdit#DocsSearch {{ background: {SUNKEN}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px; padding: 9px 11px; }}
            QLineEdit#DocsSearch:focus {{ border: 1px solid {ACCENT_LINE}; }}
            QListWidget#DocsContents, QListWidget#DocsOutline {{
                background: transparent; border: none; outline: none; }}
            QListWidget#DocsContents::item {{ color: {TEXT_DIM}; background: {SURFACE};
                border: 1px solid {BORDER}; border-radius: 7px; padding: 8px 10px;
                margin: 1px 0; }}
            QListWidget#DocsContents::item:hover {{ color: {TEXT};
                border: 1px solid {BORDER_STRONG}; background: {ELEVATED}; }}
            QListWidget#DocsContents::item:selected {{ color: {TEXT};
                background: {ACCENT_WASH}; border: 1px solid {ACCENT_LINE}; }}
            QListWidget#DocsOutline::item {{ color: {TEXT_DIM}; padding: 6px 7px;
                border-left: 2px solid transparent; }}
            QListWidget#DocsOutline::item:hover {{ color: {TEXT}; }}
            QListWidget#DocsOutline::item:selected {{ color: {ACCENT};
                background: {ACCENT_WASH}; border-left: 2px solid {ACCENT}; }}
            QTextBrowser#DocsBrowser {{ background: {SUNKEN}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 10px; padding: 0; }}
            QPushButton#DocsLearn {{ color: {ACCENT}; background: {ACCENT_WASH};
                border: 1px solid {ACCENT_LINE}; }}
            QPushButton#DocsOpen {{ color: {INFO}; background: {INFO_WASH}; }}
            QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {BORDER_STRONG};
                border-radius: 4px; min-height: 34px; }}
            QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTE}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self.contents_btn.clicked.connect(self._toggle_navigation)
        self.search.textChanged.connect(self._repopulate)
        self.contents.currentRowChanged.connect(self._on_selected)
        self.outline.currentRowChanged.connect(self._on_outline_selected)
        self.browser.anchorClicked.connect(self._on_link)
        self.prev_btn.clicked.connect(lambda: self._move_page(-1))
        self.next_btn.clicked.connect(lambda: self._move_page(1))
        self.learn_btn.clicked.connect(self._open_learning)
        self.open_btn.clicked.connect(self._open_agent)
        close_btn.clicked.connect(self.accept)

    @staticmethod
    def _small_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DocsSectionTitle")
        return label

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        narrow = event.size().width() < self.NAV_BREAKPOINT
        self.contents_btn.setVisible(narrow)
        promise = self.findChild(QLabel, "DocsPromise")
        if promise is not None:
            promise.setVisible(not narrow)
        if not narrow:
            self._nav_forced = False
            self.contents_btn.setChecked(False)
            self.nav.show()
        elif not self._nav_forced:
            self.nav.hide()
        self.outline_panel.setVisible(event.size().width() >= self.OUTLINE_BREAKPOINT)

    def _toggle_navigation(self, checked: bool) -> None:
        self._nav_forced = checked
        self.nav.setVisible(checked or self.width() >= self.NAV_BREAKPOINT)

    def _section_for(self, page: DocPage) -> DocSection | None:
        return next((section for section in self.sections if section.id == page.section), None)

    def _repopulate(self, query: str = "") -> None:
        selected = self.current_page.id if self.current_page else ""
        open_first_result = False
        self._building_nav = True
        self.contents.clear()
        if query.strip():
            hits = search_docs(self.index, query)
            for hit in hits:
                snippet = hit.snippet[:108]
                item = QListWidgetItem(
                    f"{hit.page.title}  ›  {hit.heading}\n{snippet}{'…' if len(hit.snippet) > 108 else ''}")
                item.setData(Qt.UserRole, hit.page.id)
                item.setData(Qt.UserRole + 1, hit.anchor)
                item.setToolTip(hit.snippet)
                item.setSizeHint(QSize(245, 76))
                self.contents.addItem(item)
            self.result_note.setText(
                f"{len(hits)} matching section{'s' if len(hits) != 1 else ''}")
            if hits:
                self.contents.setCurrentRow(0)
                open_first_result = True
            else:
                self.browser.setHtml(
                    "<h1>No matching section</h1><p>Try the exact control, provider, file, or error text.</p>")
        else:
            for section in self.sections:
                members = [page for page in self.pages if page.section == section.id]
                if not members:
                    continue
                heading = QListWidgetItem(section.title)
                heading.setFlags(Qt.NoItemFlags)
                heading.setForeground(Qt.gray)
                heading.setSizeHint(QSize(245, 34))
                self.contents.addItem(heading)
                for page in members:
                    item = QListWidgetItem(f"{page.title}\n{page.description}")
                    item.setData(Qt.UserRole, page.id)
                    item.setData(Qt.UserRole + 1, "")
                    item.setToolTip(page.description)
                    item.setSizeHint(QSize(245, 66))
                    self.contents.addItem(item)
            self.result_note.setText(
                f"{len(self.pages)} references · searchable by heading and control")
            if selected:
                self._select_item(selected)
        self._building_nav = False
        if open_first_result:
            self._on_selected(0)

    def _select_item(self, page_id: str, anchor: str = "") -> bool:
        for row in range(self.contents.count()):
            item = self.contents.item(row)
            if item.data(Qt.UserRole) == page_id:
                self.contents.setCurrentRow(row)
                if anchor:
                    self.browser.scrollToAnchor(anchor)
                return True
        return False

    def select_page(self, identifier: str, anchor: str = "") -> bool:
        page = self.page_by_id.get(identifier) or self.page_by_filename.get(
            Path(identifier).name)
        if page is None:
            return False
        if self.search.text():
            self.search.clear()
        if not self._select_item(page.id):
            self._render(page, anchor)
        elif anchor:
            self.browser.scrollToAnchor(anchor)
        return True

    def _on_selected(self, row: int) -> None:
        if self._building_nav:
            return
        item = self.contents.item(row)
        if item is None:
            return
        page = self.page_by_id.get(item.data(Qt.UserRole))
        if page is not None:
            self._render(page, item.data(Qt.UserRole + 1) or "")

    def _render(self, page: DocPage, anchor: str = "") -> None:
        path = self.base / page.filename
        raw = path.read_text(encoding="utf-8")
        html = markdown.markdown(
            raw, extensions=["tables", "fenced_code", "toc", "sane_lists"])
        html = _fit_images(html, max(self.browser.viewport().width(), 700))
        self.browser.setSearchPaths([str(path.parent), str(self.base)])
        self.browser.document().setDefaultStyleSheet(DOC_CSS)
        self.browser.setHtml(html)
        self.current_page = page
        section = self._section_for(page)
        self.breadcrumb.setText(
            f"Documentation  /  {section.title if section else 'Reference'}  /  {page.title}")
        meta = [item for item in (
            page.workspace, f"{page.estimated_minutes} min reference" if page.estimated_minutes else "",
            f"Updated {page.updated_at}" if page.updated_at else "",
        ) if item]
        self.meta.setText("  ·  ".join(meta))
        self._update_outline(raw)
        self._update_footer()
        self.settings.setValue("docs/last_page", page.id)
        if anchor:
            self.browser.scrollToAnchor(anchor)
        else:
            self.browser.verticalScrollBar().setValue(0)

    def _update_outline(self, raw: str) -> None:
        self.outline.blockSignals(True)
        self.outline.clear()
        for heading, anchor, _body in _document_sections(raw):
            if not anchor:
                continue
            item = QListWidgetItem(heading)
            item.setData(Qt.UserRole, anchor)
            self.outline.addItem(item)
        self.outline.blockSignals(False)

    def _on_outline_selected(self, row: int) -> None:
        item = self.outline.item(row)
        if item is not None:
            self.browser.scrollToAnchor(item.data(Qt.UserRole))

    def _update_footer(self) -> None:
        if self.current_page is None:
            return
        index = self.pages.index(self.current_page)
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(self.pages) - 1)
        has_agent = bool(self.current_page.agent)
        self.learn_btn.setVisible(has_agent)
        self.open_btn.setVisible(
            has_agent and hasattr(self.host, f"{self.current_page.agent}_panel"))
        if has_agent:
            self.open_btn.setText(f"Open {self.current_page.title} in Imprint")

    def _move_page(self, offset: int) -> None:
        if self.current_page is None:
            return
        index = self.pages.index(self.current_page) + offset
        if 0 <= index < len(self.pages):
            self.select_page(self.pages[index].id)

    def _open_agent(self) -> None:
        if self.current_page is None or not self.current_page.agent:
            return
        select = getattr(self.host, "select_agent", None)
        if callable(select):
            select(self.current_page.agent)
        self.accept()

    def _open_learning(self) -> None:
        if self.current_page is None or not self.current_page.agent:
            return
        agent = self.current_page.agent
        self.accept()
        from ui.learning_center import show_learning_center
        lesson = {
            "author": "draft", "manuscript": "publish",
            "audiobook": "audiobooks", "music": "music", "video": "video",
            "social": "social", "webdesign": "site-builder",
            "fiverr": "client-gigs", "creator": "creator", "onlyfans": "onlyfans",
        }.get(agent, "home")
        show_learning_center(self.host, self.base.parent.parent, start_page=lesson)

    def _on_link(self, url: QUrl) -> None:
        if url.path().endswith(".md"):
            self.select_page(Path(url.path()).name, url.fragment())
            return
        if url.scheme() in ("http", "https"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
            return
        if url.fragment():
            self.browser.scrollToAnchor(url.fragment())


def show_docs_center(app, resource_dir: Path,
                     start_page: str | None = None,
                     start_anchor: str = "") -> DocsCentreDialog:
    """Open the bundled reference centre and return it for tests."""
    dialog = DocsCentreDialog(app, resource_dir, start_page, start_anchor)
    dialog.exec()
    # Reparent off the window: a parented modal survives on the window's
    # child list for the life of the app, so every open leaked a full
    # dialog. Unparented, it is freed when the last reference drops (the
    # caller in main ignores the return; tests hold theirs).
    dialog.setParent(None)
    return dialog
