"""Task-first Learning Centre for Imprint.

The curriculum lives in ``docs/learn/manifest.json`` and Markdown modules.
This dialog adds local heading-level search, grouped navigation, exact anchors,
responsive reading, progress, and a bridge back to the relevant agent. It never
calls an AI provider: learning remains available offline and free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import markdown
from PySide6.QtCore import QSettings, QSize, Qt, QUrl
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSplitter, QTextBrowser, QVBoxLayout,
    QWidget,
)

from ui.style import (
    ACCENT, ACCENT_LINE, ACCENT_WASH, BG, BORDER, BORDER_STRONG, ELEVATED,
    INFO, INFO_WASH, SURFACE, SUNKEN, TEXT, TEXT_DIM, TEXT_MUTE,
)


@dataclass(frozen=True)
class LearnPage:
    """One task-sized lesson declared by the curriculum manifest."""

    filename: str
    title: str
    description: str
    id: str = ""
    section: str = ""
    order: int = 0
    outcome: str = ""
    audience: str = "Everyone"
    difficulty: str = ""
    estimated_minutes: int = 0
    prerequisites: tuple[str, ...] = ()
    workspace: str = ""
    agent: str = ""
    tab: str = ""
    keywords: tuple[str, ...] = ()
    updated_at: str = ""
    source_version: int = 1


@dataclass(frozen=True)
class LearnSection:
    id: str
    title: str
    description: str = ""


@dataclass(frozen=True)
class SearchHit:
    page: LearnPage
    heading: str
    anchor: str
    snippet: str
    score: int = field(default=0, compare=False)


def learn_dir(resource_dir: Path) -> Path:
    return Path(resource_dir) / "docs" / "learn"


def _load_manifest(base: Path) -> tuple[list[LearnSection], list[LearnPage]]:
    path = base / "manifest.json"
    if not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    sections = [LearnSection(**item) for item in data.get("sections", [])]
    pages: list[LearnPage] = []
    for raw in data.get("modules", []):
        pages.append(LearnPage(
            filename=raw["filename"], title=raw["title"],
            description=raw.get("summary", ""),
            id=raw.get("id", Path(raw["filename"]).stem),
            section=raw.get("section", "reference"),
            order=int(raw.get("order", 0)), outcome=raw.get("outcome", ""),
            audience=raw.get("audience", "Everyone"),
            difficulty=raw.get("difficulty", ""),
            estimated_minutes=int(raw.get("estimated_minutes", 0)),
            prerequisites=tuple(raw.get("prerequisites", [])),
            workspace=raw.get("workspace", ""), agent=raw.get("agent", ""),
            tab=raw.get("tab", ""), keywords=tuple(raw.get("keywords", [])),
            updated_at=raw.get("updated_at", ""),
            source_version=int(raw.get("source_version", 1)),
        ))
    return sections, sorted(pages, key=lambda page: page.order)


def _resolve_attribute(root, path: str):
    value = root
    for part in path.split("."):
        value = getattr(value, part, None)
        if value is None:
            return None
    return value


def install_learning_targets(host, resource_dir: Path) -> int:
    """Attach manifest-backed help targets to currently built controls."""
    path = learn_dir(resource_dir) / "help_map.json"
    if not path.exists():
        return 0
    mapping = json.loads(path.read_text(encoding="utf-8"))
    installed = 0
    for attribute, target in mapping.items():
        widget = _resolve_attribute(host, attribute)
        if widget is not None and hasattr(widget, "setProperty"):
            widget.setProperty("imprintLearnTarget", target)
            installed += 1
    return installed


def learning_target_for_widget(widget) -> tuple[str, str] | None:
    """Read the nearest contextual lesson from a focused widget or parent."""
    current = widget
    while current is not None:
        target = current.property("imprintLearnTarget") if hasattr(
            current, "property") else None
        if target:
            page, _, anchor = str(target).partition("#")
            return page, anchor
        current = current.parentWidget() if hasattr(current, "parentWidget") else None
    return None


_SOURCE_ROOT = Path(__file__).resolve().parent.parent
SECTIONS, PAGES = _load_manifest(_SOURCE_ROOT / "docs" / "learn")


def _plain(text: str) -> str:
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_>#|]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _anchor(text: str) -> str:
    value = _plain(text).casefold()
    value = re.sub(r"[^\w\s-]", "", value)
    return re.sub(r"[-\s]+", "-", value).strip("-")


def _document_sections(text: str) -> list[tuple[str, str, str]]:
    """Return heading, anchor and searchable body for each Markdown section."""
    results: list[tuple[str, str, str]] = []
    heading, anchor, body = "Overview", "", []

    def flush() -> None:
        content = _plain(" ".join(body))
        if content or heading != "Overview":
            results.append((heading, anchor, content))

    for line in text.splitlines():
        match = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if match:
            flush()
            heading = _plain(match.group(1))
            anchor = _anchor(match.group(1))
            body = []
        else:
            body.append(line)
    flush()
    return results


def build_search_index(base: Path, pages: list[LearnPage]) -> list[SearchHit]:
    """Build a deterministic, local, heading-level search index."""
    hits: list[SearchHit] = []
    for page in pages:
        path = base / page.filename
        if not path.exists():
            continue
        for heading, anchor, body in _document_sections(
                path.read_text(encoding="utf-8")):
            hits.append(SearchHit(page, heading, anchor, body[:280].rstrip()))
    return hits


def search_index(index: list[SearchHit], query: str,
                 limit: int = 60) -> list[SearchHit]:
    terms = tuple(term for term in query.casefold().split() if term)
    if not terms:
        return []
    ranked: list[SearchHit] = []
    for hit in index:
        page = hit.page
        title, heading = page.title.casefold(), hit.heading.casefold()
        keywords = " ".join(page.keywords).casefold()
        haystack = f"{title} {page.description} {keywords} {heading} {hit.snippet}".casefold()
        if not all(term in haystack for term in terms):
            continue
        score = sum(18 if term in heading else 12 if term in title else
                    5 if term in keywords else 1 for term in terms)
        ranked.append(SearchHit(
            hit.page, hit.heading, hit.anchor, hit.snippet, score))
    ranked.sort(key=lambda item: (-item.score, item.page.order, item.heading))
    return ranked[:limit]


DOCUMENT_CSS = f"""
body {{ color: {TEXT}; background: {SUNKEN}; font-family: -apple-system,
       BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 15px;
       line-height: 1.62; margin: 28px 34px 64px 34px; }}
h1 {{ color: {TEXT}; font-size: 29px; font-weight: 700; margin: 2px 0 14px 0; }}
h2 {{ color: {TEXT}; font-size: 20px; font-weight: 650; margin: 34px 0 11px 0;
      padding-bottom: 8px; border-bottom: 1px solid {BORDER}; }}
h3 {{ color: {TEXT}; font-size: 16px; font-weight: 650; margin: 25px 0 8px 0; }}
p, li {{ color: {TEXT_DIM}; }}
strong {{ color: {TEXT}; font-weight: 650; }}
a {{ color: {ACCENT}; text-decoration: none; }}
code {{ color: {TEXT}; background: {ELEVATED}; padding: 2px 5px;
        border-radius: 4px; font-family: 'SF Mono', Menlo, monospace; }}
pre {{ color: {TEXT}; background: {BG}; border: 1px solid {BORDER};
       border-radius: 9px; padding: 15px; white-space: pre-wrap; }}
blockquote {{ color: {TEXT_DIM}; background: {ACCENT_WASH};
              border-left: 4px solid {ACCENT}; margin: 18px 0;
              padding: 13px 16px; }}
table {{ border-collapse: collapse; margin: 17px 0 25px 0; }}
th {{ color: {TEXT}; background: {ELEVATED}; font-weight: 650;
      border: 1px solid {BORDER_STRONG}; padding: 9px 11px; }}
td {{ color: {TEXT_DIM}; border: 1px solid {BORDER}; padding: 9px 11px;
      vertical-align: top; }}
hr {{ border: 0; border-top: 1px solid {BORDER}; margin: 30px 0; }}
img {{ margin: 15px 0 9px 0; }}
"""


def _fit_images(html: str, viewport_width: int) -> str:
    width = max(360, min(viewport_width - 76, 760))
    return re.sub(r"<img ", f'<img width="{width}" ', html)


class LearningCentreDialog(QDialog):
    """Responsive curriculum browser with one primary reading scroll."""

    NAV_BREAKPOINT = 1100
    OUTLINE_BREAKPOINT = 1250

    def __init__(self, app, resource_dir: Path,
                 start_page: str | None = None,
                 start_anchor: str = ""):
        super().__init__(app)
        self.host = app
        self.base = learn_dir(resource_dir)
        sections, pages = _load_manifest(self.base)
        self.sections = sections or SECTIONS
        self.pages = [page for page in (pages or PAGES)
                      if (self.base / page.filename).exists()]
        self.page_by_id = {page.id: page for page in self.pages}
        self.page_by_filename = {page.filename: page for page in self.pages}
        self.search_documents = build_search_index(self.base, self.pages)
        self.settings = QSettings("Imprint", "Imprint")
        self.current_page: LearnPage | None = None
        self.current_anchor = ""
        self._nav_forced = False
        self._building_navigation = False

        self.setObjectName("LearningCentreDialog")
        self.setWindowTitle("Learning Centre · Imprint")
        self.setMinimumSize(980, 680)
        self.resize(1320, 860)
        self.setAccessibleName("Imprint Learning Centre")
        self.setAccessibleDescription(
            "Searchable lessons for Imprint controls, agents, income experiments, and recovery.")
        self._build_ui()
        self._repopulate()

        requested = start_page or str(
            self.settings.value("learning/last_page", "home"))
        requested_anchor = start_anchor or ("" if start_page else str(
            self.settings.value("learning/last_anchor", ""))
        )
        if not self.select_page(requested, requested_anchor):
            self.select_page("home" if "home" in self.page_by_id else
                             self.pages[0].id if self.pages else "")

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)

        top = QFrame()
        top.setObjectName("LearnTopBar")
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(16, 10, 14, 10)
        top_row.setSpacing(10)
        self.contents_btn = QPushButton("Contents")
        self.contents_btn.setObjectName("LearnContentsToggle")
        self.contents_btn.setCheckable(True)
        self.contents_btn.clicked.connect(self._toggle_navigation)
        top_row.addWidget(self.contents_btn)
        brand = QLabel("Learning Centre")
        brand.setObjectName("LearnTitle")
        top_row.addWidget(brand)
        top_row.addStretch()
        promise = QLabel("Learn a task · verify the result · decide with evidence")
        promise.setObjectName("LearnPromise")
        top_row.addWidget(promise)
        outer.addWidget(top)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("LearnSplitter")
        self.splitter.setChildrenCollapsible(False)

        self.nav = QFrame()
        self.nav.setObjectName("LearnNavigation")
        nav_layout = QVBoxLayout(self.nav)
        nav_layout.setContentsMargins(0, 0, 8, 0)
        nav_layout.setSpacing(8)
        nav_title = QLabel("Browse or search")
        nav_title.setObjectName("LearnSectionTitle")
        nav_layout.addWidget(nav_title)
        self.search = QLineEdit()
        self.search.setObjectName("LearnSearch")
        self.search.setPlaceholderText("Control, task, or error…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search all Learning Centre headings and text")
        nav_layout.addWidget(self.search)
        self.contents = QListWidget()
        self.contents.setObjectName("LearnContents")
        self.contents.setSpacing(2)
        self.contents.setWordWrap(True)
        self.contents.setTextElideMode(Qt.ElideRight)
        self.contents.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.contents.setAccessibleName("Learning paths and search results")
        nav_layout.addWidget(self.contents, 1)
        self.result_note = QLabel()
        self.result_note.setObjectName("LearnHint")
        self.result_note.setWordWrap(True)
        nav_layout.addWidget(self.result_note)

        reading = QWidget()
        reading.setObjectName("LearnReading")
        reading_layout = QVBoxLayout(reading)
        reading_layout.setContentsMargins(8, 0, 0, 0)
        reading_layout.setSpacing(8)

        context = QHBoxLayout()
        self.breadcrumb = QLabel()
        self.breadcrumb.setObjectName("LearnBreadcrumb")
        self.breadcrumb.setAccessibleName("Current lesson breadcrumb")
        self.lesson_meta = QLabel()
        self.lesson_meta.setObjectName("LearnMeta")
        context.addWidget(self.breadcrumb)
        context.addStretch()
        context.addWidget(self.lesson_meta)
        reading_layout.addLayout(context)

        self.reader_splitter = QSplitter(Qt.Horizontal)
        self.reader_splitter.setChildrenCollapsible(False)
        self.browser = QTextBrowser()
        self.browser.setObjectName("LearnBrowser")
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setAccessibleName("Current Learning Centre lesson")
        self.browser.setAccessibleDescription(
            "Read the lesson; links stay inside Imprint unless they are external.")
        self.browser.setSearchPaths([str(self.base), str(self.base / "modules")])
        self.browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
        self.reader_splitter.addWidget(self.browser)

        self.outline_panel = QFrame()
        self.outline_panel.setObjectName("LearnOutlinePanel")
        outline_layout = QVBoxLayout(self.outline_panel)
        outline_layout.setContentsMargins(10, 10, 4, 10)
        outline_layout.setSpacing(7)
        outline_title = QLabel("On this page")
        outline_title.setObjectName("LearnSectionTitle")
        outline_layout.addWidget(outline_title)
        self.outline = QListWidget()
        self.outline.setObjectName("LearnOutline")
        self.outline.setAccessibleName("Headings in the current lesson")
        self.outline.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
        self.splitter.setSizes([290, 990])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        outer.addWidget(self.splitter, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.prev_btn = QPushButton("← Previous")
        self.next_btn = QPushButton("Next →")
        self.complete_btn = QPushButton("Mark complete")
        self.complete_btn.setCheckable(True)
        self.complete_btn.setObjectName("LearnComplete")
        self.worksheet_btn = QPushButton("Open worksheet")
        self.worksheet_btn.setObjectName("LearnWorksheet")
        self.open_btn = QPushButton("Open in Imprint")
        self.open_btn.setObjectName("LearnOpen")
        close_btn = QPushButton("Close")
        footer.addWidget(self.prev_btn)
        footer.addWidget(self.next_btn)
        footer.addWidget(self.complete_btn)
        footer.addWidget(self.worksheet_btn)
        footer.addStretch()
        footer.addWidget(self.open_btn)
        footer.addWidget(close_btn)
        outer.addLayout(footer)

        self.setStyleSheet(f"""
            QDialog#LearningCentreDialog {{ background: {BG}; }}
            QFrame#LearnTopBar {{ background: {SURFACE}; border: 1px solid {BORDER};
                border-radius: 10px; }}
            QLabel#LearnTitle {{ color: {TEXT}; font-size: 20px; font-weight: 700; }}
            QLabel#LearnPromise, QLabel#LearnMeta {{ color: {TEXT_DIM}; font-size: 12px; }}
            QLabel#LearnSectionTitle {{ color: {TEXT}; font-size: 13px;
                font-weight: 650; padding: 2px 3px; }}
            QLabel#LearnBreadcrumb {{ color: {TEXT_DIM}; font-size: 12px; }}
            QLabel#LearnHint {{ color: {TEXT_MUTE}; font-size: 11px; padding: 3px; }}
            QFrame#LearnNavigation, QFrame#LearnOutlinePanel {{ background: transparent; }}
            QLineEdit#LearnSearch {{ background: {SUNKEN}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 8px; padding: 9px 11px; }}
            QLineEdit#LearnSearch:focus {{ border: 1px solid {ACCENT_LINE}; }}
            QListWidget#LearnContents, QListWidget#LearnOutline {{
                background: transparent; border: none; outline: none; }}
            QListWidget#LearnContents::item {{ color: {TEXT_DIM}; background: {SURFACE};
                border: 1px solid {BORDER}; border-radius: 7px; padding: 8px 10px;
                margin: 1px 0; }}
            QListWidget#LearnContents::item:hover {{ color: {TEXT};
                border: 1px solid {BORDER_STRONG}; background: {ELEVATED}; }}
            QListWidget#LearnContents::item:selected {{ color: {TEXT};
                background: {ACCENT_WASH}; border: 1px solid {ACCENT_LINE}; }}
            QListWidget#LearnOutline::item {{ color: {TEXT_DIM}; padding: 6px 7px;
                border-left: 2px solid transparent; }}
            QListWidget#LearnOutline::item:hover {{ color: {TEXT}; }}
            QListWidget#LearnOutline::item:selected {{ color: {ACCENT};
                background: {ACCENT_WASH}; border-left: 2px solid {ACCENT}; }}
            QTextBrowser#LearnBrowser {{ background: {SUNKEN}; color: {TEXT};
                border: 1px solid {BORDER}; border-radius: 10px; padding: 0; }}
            QPushButton#LearnContentsToggle {{ padding: 6px 11px; }}
            QPushButton#LearnComplete:checked {{ color: {ACCENT};
                background: {ACCENT_WASH}; border: 1px solid {ACCENT_LINE}; }}
            QPushButton#LearnOpen {{ color: {INFO}; background: {INFO_WASH}; }}
            QPushButton#LearnWorksheet {{ color: {ACCENT};
                background: {ACCENT_WASH}; border: 1px solid {ACCENT_LINE}; }}
            QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {BORDER_STRONG};
                border-radius: 4px; min-height: 34px; }}
            QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTE}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; background: transparent; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent; }}
        """)

        self.search.textChanged.connect(self._repopulate)
        self.search.returnPressed.connect(
            lambda: self.contents.setFocus() if self.contents.count() else None)
        self.contents.currentRowChanged.connect(self._on_selected)
        self.outline.currentRowChanged.connect(self._on_outline_selected)
        self.browser.anchorClicked.connect(self._on_link)
        self.prev_btn.clicked.connect(lambda: self._move_page(-1))
        self.next_btn.clicked.connect(lambda: self._move_page(1))
        self.complete_btn.toggled.connect(self._set_complete)
        self.worksheet_btn.clicked.connect(self._open_worksheet)
        self.open_btn.clicked.connect(self._open_in_imprint)
        close_btn.clicked.connect(self.accept)

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        narrow = event.size().width() < self.NAV_BREAKPOINT
        self.contents_btn.setVisible(narrow)
        promise = self.findChild(QLabel, "LearnPromise")
        if promise is not None:
            promise.setVisible(not narrow)
        if not narrow:
            self._nav_forced = False
            self.contents_btn.setChecked(False)
            self.nav.show()
        elif not self._nav_forced:
            self.nav.hide()
        self.outline_panel.setVisible(
            event.size().width() >= self.OUTLINE_BREAKPOINT)

    def _toggle_navigation(self, checked: bool) -> None:
        self._nav_forced = checked
        self.nav.setVisible(checked or self.width() >= self.NAV_BREAKPOINT)

    def _section_for(self, page: LearnPage) -> LearnSection | None:
        return next((section for section in self.sections
                     if section.id == page.section), None)

    def _add_section_item(self, section: LearnSection) -> None:
        item = QListWidgetItem(section.title)
        item.setData(Qt.UserRole + 3, "section")
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(Qt.gray)
        item.setSizeHint(QSize(245, 34))
        self.contents.addItem(item)

    def _add_page_item(self, page: LearnPage) -> None:
        done = bool(self.settings.value(
            f"learning/completed/{page.id}", False, type=bool))
        marker = "✓  " if done else ""
        item = QListWidgetItem(f"{marker}{page.title}\n{page.description}")
        item.setData(Qt.UserRole, page.id)
        item.setData(Qt.UserRole + 1, page.filename)
        item.setData(Qt.UserRole + 2, "")
        item.setData(Qt.UserRole + 3, "page")
        item.setToolTip(page.outcome or page.description)
        item.setSizeHint(QSize(245, 66))
        self.contents.addItem(item)

    def _add_search_item(self, hit: SearchHit) -> None:
        snippet = hit.snippet[:105]
        suffix = "…" if len(hit.snippet) > 105 else ""
        item = QListWidgetItem(
            f"{hit.page.title}  ›  {hit.heading}\n{snippet}{suffix}")
        item.setData(Qt.UserRole, hit.page.id)
        item.setData(Qt.UserRole + 1, hit.page.filename)
        item.setData(Qt.UserRole + 2, hit.anchor)
        item.setData(Qt.UserRole + 3, "result")
        item.setToolTip(hit.snippet)
        item.setSizeHint(QSize(245, 76))
        self.contents.addItem(item)

    def _repopulate(self, query: str = "") -> None:
        selected_id = self.current_page.id if self.current_page else ""
        self._building_navigation = True
        self.contents.clear()
        if query.strip():
            hits = search_index(self.search_documents, query)
            for hit in hits:
                self._add_search_item(hit)
            self.result_note.setText(
                f"{len(hits)} matching section{'s' if len(hits) != 1 else ''}")
            if hits:
                self.contents.setCurrentRow(0)
            else:
                self.browser.setHtml(
                    "<h1>No matching section</h1>"
                    "<p>Try the exact control label, agent, task, or error phrase.</p>")
        else:
            for section in self.sections:
                section_pages = [page for page in self.pages
                                 if page.section == section.id]
                if not section_pages:
                    continue
                self._add_section_item(section)
                for page in section_pages:
                    self._add_page_item(page)
            self.result_note.setText(
                f"{len(self.pages)} lessons · searchable by heading and control")
            if selected_id:
                self._select_item(selected_id)
        self._building_navigation = False

    def _select_item(self, page_id: str, anchor: str = "") -> bool:
        for row in range(self.contents.count()):
            item = self.contents.item(row)
            if item.data(Qt.UserRole) == page_id:
                self.contents.setCurrentRow(row)
                if anchor:
                    self.current_anchor = anchor
                    self.browser.scrollToAnchor(anchor)
                return True
        return False

    def select_page(self, identifier: str, anchor: str = "") -> bool:
        page = self.page_by_id.get(identifier) or self.page_by_filename.get(identifier)
        if page is None:
            page = next((candidate for candidate in self.pages
                         if Path(candidate.filename).name == Path(identifier).name), None)
        if page is None:
            return False
        if self.search.text():
            self.search.clear()
        if not self._select_item(page.id):
            self._render(page, anchor)
        elif anchor:
            self.current_anchor = anchor
            self.browser.scrollToAnchor(anchor)
        return True

    def _on_selected(self, row: int) -> None:
        if self._building_navigation:
            return
        item = self.contents.item(row)
        if item is None or not item.data(Qt.UserRole):
            return
        page = self.page_by_id.get(item.data(Qt.UserRole))
        if page is not None:
            self._render(page, item.data(Qt.UserRole + 2) or "")

    def _render(self, page: LearnPage, anchor: str = "") -> None:
        path = self.base / page.filename
        if not path.exists():
            self.browser.setHtml(
                f"<h1>Lesson unavailable</h1><p>Expected <code>{path}</code>.</p>")
            return
        raw = path.read_text(encoding="utf-8")
        html = markdown.markdown(
            raw, extensions=["tables", "fenced_code", "toc", "sane_lists"])
        html = _fit_images(html, max(self.browser.viewport().width(), 700))
        self.browser.setSearchPaths([
            str(path.parent), str(self.base), str(self.base / "modules")])
        self.browser.document().setDefaultStyleSheet(DOCUMENT_CSS)
        self.browser.setHtml(html)
        self.current_page = page
        self.current_anchor = anchor
        section = self._section_for(page)
        self.breadcrumb.setText(
            f"{section.title if section else 'Learning Centre'}  /  {page.title}")
        detail = [item for item in (
            page.difficulty,
            f"{page.estimated_minutes} min" if page.estimated_minutes else "",
            f"Updated {page.updated_at}" if page.updated_at else "",
        ) if item]
        self.lesson_meta.setText("  ·  ".join(detail))
        self.open_btn.setVisible(bool(page.agent))
        self.worksheet_btn.setVisible(page.section == "income")
        self.open_btn.setText(
            f"Open {page.title} in Imprint" if page.agent else "Open in Imprint")
        self._update_outline(raw)
        self._update_footer()
        self.settings.setValue("learning/last_page", page.id)
        self.settings.setValue("learning/last_anchor", anchor)
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
            item.setToolTip(heading)
            self.outline.addItem(item)
        self.outline.blockSignals(False)

    def _on_outline_selected(self, row: int) -> None:
        item = self.outline.item(row)
        if item is not None:
            anchor = item.data(Qt.UserRole)
            self.current_anchor = anchor
            self.settings.setValue("learning/last_anchor", anchor)
            self.browser.scrollToAnchor(anchor)

    def _update_footer(self) -> None:
        if self.current_page is None:
            return
        index = self.pages.index(self.current_page)
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(self.pages) - 1)
        complete = bool(self.settings.value(
            f"learning/completed/{self.current_page.id}", False, type=bool))
        self.complete_btn.blockSignals(True)
        self.complete_btn.setChecked(complete)
        self.complete_btn.setText("Completed ✓" if complete else "Mark complete")
        self.complete_btn.blockSignals(False)

    def _move_page(self, offset: int) -> None:
        if self.current_page is None:
            return
        index = self.pages.index(self.current_page) + offset
        if 0 <= index < len(self.pages):
            self.select_page(self.pages[index].id)

    def _set_complete(self, complete: bool) -> None:
        if self.current_page is None:
            return
        self.settings.setValue(
            f"learning/completed/{self.current_page.id}", complete)
        self.complete_btn.setText("Completed ✓" if complete else "Mark complete")
        if not self.search.text():
            self._repopulate()

    def _open_in_imprint(self) -> None:
        if self.current_page is None or not self.current_page.agent:
            return
        selector = getattr(self.host, "select_agent", None)
        if callable(selector):
            selector(self.current_page.agent)
        if self.current_page.agent == "author":
            mode = getattr(self.host, "_author_set_mode", None)
            if callable(mode):
                mode("write")
        tab_widgets = {
            "manuscript": "manuscript_tabs",
            "audiobook": "audiobook_tabs",
            "video": "video_tabs",
            "social": "social_tabs",
            "creator": "creator_tabs",
        }
        tab_widget = getattr(
            self.host, tab_widgets.get(self.current_page.agent, ""), None)
        if tab_widget is not None and self.current_page.tab:
            for index in range(tab_widget.count()):
                if tab_widget.tabText(index) == self.current_page.tab:
                    tab_widget.setCurrentIndex(index)
                    break
        self.accept()

    def _open_worksheet(self) -> None:
        if self.current_page is None or self.current_page.section != "income":
            return
        from ui.income_worksheets import show_income_worksheets
        start = {
            "evidence": "contribution", "offer": "break-even",
            "experiment": "variant comparison",
            "unit-economics": "contribution",
            "funnels-attribution": "funnel",
            "uncertainty-decisions": "variant comparison",
            "automation-review": "automation payback",
        }.get(self.current_page.id, "contribution")
        show_income_worksheets(self, start)

    def _on_link(self, url: QUrl) -> None:
        path = url.path()
        if path.endswith(".md"):
            self.select_page(Path(path).name, url.fragment())
            return
        if url.scheme() in ("http", "https"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
            return
        if url.fragment():
            self.current_anchor = url.fragment()
            self.browser.scrollToAnchor(url.fragment())


def show_learning_center(app, resource_dir: Path,
                         start_page: str | None = None,
                         start_anchor: str = "") -> QDialog:
    """Open the bundled Learning Centre and return it for tests/introspection."""
    dialog = LearningCentreDialog(app, resource_dir, start_page, start_anchor)
    dialog.exec()
    # Same reparenting as show_docs_center: parented modals accumulated on
    # the window — one full Learning Centre leaked per open.
    dialog.setParent(None)
    return dialog
