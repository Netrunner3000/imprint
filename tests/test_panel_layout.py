"""
Imprint — panel layout tests
=====================================
Type: Layout regression tests, run headless.

Every agent panel used to draw its own controls on top of each other once the
window got small enough: the direction box landed over the Task and Provider
rows beneath it, and the Client Gigs buttons overlapped one another sideways.

The cause is the one `ui/widgets.FlowLayout` already documents for the
horizontal axis — a box layout reports the sum of its children as its minimum,
and a splitter pane dropped below that compresses children past their own
minimums rather than clipping. `ui/widgets.scrollable()` is the vertical
counterpart.

These assert the property directly rather than comparing screenshots: no two
sibling widgets inside a panel may occupy the same pixels.

Run with:  pytest tests/test_panel_layout.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

AGENTS = [
    "author", "manuscript", "audiobook", "music", "webdesign", "fiverr",
    "video",
]

# Agents whose panel holds more than one page. Testing only the page that
# happens to be showing is how the Publish column's overlapping Generate button
# survived the first pass — each of these has its own control column.
SUB_MODES = {
    "author": [
        ("write", lambda w: w._author_set_mode("write")),
        ("publish", lambda w: (w._author_set_mode("pubmkt"), w._author_set_sub_mode("publish"))),
        ("market", lambda w: (w._author_set_mode("pubmkt"), w._author_set_sub_mode("market"))),
    ],
}

# Down to the window's own minimum (1000x600, set in GodAI.__init__).
SIZES = [(1900, 1200), (1500, 950), (1280, 820), (1100, 700), (1000, 600)]


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app):
    """One window for the module — building it costs ~10s."""
    from PySide6.QtWidgets import QMessageBox
    import main

    saved = (QMessageBox.warning, QMessageBox.question, QMessageBox.information)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        w = main.GodAI()
        w.show()
        app.processEvents()
        yield w
    finally:
        QMessageBox.warning, QMessageBox.question, QMessageBox.information = saved


def _settle(app, window, size, agent):
    window.resize(*size)
    for _ in range(6):
        app.processEvents()
    window.select_agent(agent)
    for _ in range(6):
        app.processEvents()


def test_music_workspace_layout_is_owned_by_music_package(window):
    from agents.music.panel import MusicPanel

    assert isinstance(window.music_panel, MusicPanel)
    assert window.music_panel.music_tabs.count() == 6
    for name in MusicPanel.HOST_CONTROLS:
        assert getattr(window, name) is getattr(window.music_panel, name)


def test_site_builder_workspace_is_owned_by_its_package(window):
    from agents.webdesign import WebdesignPanel

    assert isinstance(window.webdesign_panel, WebdesignPanel)
    assert window.webdesign_panel.webdesign_tabs.count() == 3
    for name in WebdesignPanel.HOST_CONTROLS:
        assert getattr(window, name) is getattr(window.webdesign_panel, name)


def test_audiobook_workspace_is_owned_by_its_package(window):
    from agents.audiobook import AudiobookPanel

    assert isinstance(window.audiobook_panel, AudiobookPanel)
    assert window.audiobook_panel.audiobook_tabs.count() == 2
    for name in AudiobookPanel.HOST_CONTROLS:
        assert getattr(window, name) is getattr(window.audiobook_panel, name)


def _overlapping_pairs(panel):
    """Sibling widgets sharing pixels — i.e. one drawn over the other."""
    from PySide6.QtWidgets import (
        QWidget, QLabel, QLineEdit, QComboBox, QPushButton, QTextEdit,
    )
    watch = (QLabel, QLineEdit, QComboBox, QPushButton, QTextEdit)
    kids = [c for c in panel.findChildren(QWidget)
            if isinstance(c, watch) and c.isVisible()
            and c.width() > 2 and c.height() > 2]

    found = []
    for i, a in enumerate(kids):
        for b in kids[i + 1:]:
            # Only siblings: a child sitting inside its own parent is normal.
            if a.parentWidget() is not b.parentWidget():
                continue
            if a.isAncestorOf(b) or b.isAncestorOf(a):
                continue
            rect = a.geometry().intersected(b.geometry())
            # A couple of pixels is a border touching, not an overlap.
            if rect.width() > 2 and rect.height() > 2:
                found.append((a, b, rect))
    return found


def _describe(widget):
    text = ""
    for attr in ("text", "currentText", "placeholderText"):
        if hasattr(widget, attr):
            try:
                text = getattr(widget, attr)() or text
            except Exception:
                pass
            if text:
                break
    return f"{type(widget).__name__}({text[:30]!r})"


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("agent", AGENTS)
def test_panel_controls_never_overlap(app, window, agent, size):
    _settle(app, window, size, agent)
    panel = getattr(window, f"{agent}_panel")
    bad = _overlapping_pairs(panel)
    assert not bad, "\n".join(
        f"{_describe(a)} overlaps {_describe(b)} by {r.width()}x{r.height()}px"
        for a, b, r in bad[:6]
    )


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize(
    "agent,mode",
    [(a, m) for a, modes in SUB_MODES.items() for m, _ in modes],
)
def test_sub_mode_pages_never_overlap(app, window, agent, mode, size):
    """Each page of a multi-page panel carries its own control column."""
    _settle(app, window, size, agent)
    switch = dict((m, fn) for m, fn in SUB_MODES[agent])[mode]
    switch(window)
    for _ in range(6):
        app.processEvents()
    panel = getattr(window, f"{agent}_panel")
    bad = _overlapping_pairs(panel)
    assert not bad, f"[{agent}/{mode}] " + "\n".join(
        f"{_describe(a)} overlaps {_describe(b)} by {r.width()}x{r.height()}px"
        for a, b, r in bad[:6]
    )


@pytest.mark.parametrize("agent", AGENTS)
def test_panel_controls_stay_inside_the_window(app, window, agent):
    """Overlap is not the only failure — a control pushed outside the window is
    equally unusable, and a scroll area that is not resizable causes it."""
    from PySide6.QtWidgets import QWidget, QPushButton, QComboBox
    _settle(app, window, (1100, 700), agent)
    panel = getattr(window, f"{agent}_panel")
    escaped = []
    for child in panel.findChildren(QWidget):
        if not isinstance(child, (QPushButton, QComboBox)) or not child.isVisible():
            continue
        top_left = child.mapTo(window, child.rect().topLeft())
        if top_left.x() < -2 or top_left.y() < -2:
            escaped.append(f"{_describe(child)} at {top_left.x()},{top_left.y()}")
    assert not escaped, "controls positioned outside the window: " + "; ".join(escaped[:5])


@pytest.mark.parametrize("size", [(1900, 1200), (1500, 950), (1280, 820), (1100, 700)],
                         ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("agent", AGENTS)
def test_no_control_is_unreachable(app, window, agent, size):
    """Content wider than its pane is only a bug when you cannot scroll to it.

    This replaces an earlier version that asserted "nothing is ever wider than
    its pane" and carried a growing exclusion list — music, then webdesign,
    then fiverr — as more panels were made to scroll as a whole. Excluding
    panels one by one was weakening the test to fit the code. The property
    that actually matters is that every control can be reached: a column may
    overflow, but only if it can scroll.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea
    _settle(app, window, size, agent)
    panel = getattr(window, f"{agent}_panel")
    unreachable = []
    for area in panel.findChildren(QScrollArea):
        if not area.isVisible() or area.widget() is None:
            continue
        need = area.widget().minimumSizeHint().width()
        have = area.viewport().width()
        if need > have and area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff:
            unreachable.append(f"needs {need}px in a {have}px pane with no scrollbar")
    assert not unreachable, f"[{agent}] " + "; ".join(unreachable)


def test_author_workbench_has_no_nested_control_scroller(app, window):
    """Compose, Task and Model belong in the canvas, not a tiny scroll pane."""
    from PySide6.QtWidgets import QScrollArea

    _settle(app, window, (1760, 820), "author")
    window._author_set_mode("write")
    app.processEvents()
    assert not window.author_panel.findChildren(QScrollArea)


def test_section_headings_are_readable_not_field_label_small_caps(app, window):
    from ui.forms import section

    heading = section("Conversion settings")
    assert heading.text() == "Conversion settings"
    assert heading.objectName() == "SectionLabel"


def test_audiobook_source_list_does_not_push_settings_below_the_fold(app, window):
    window.select_agent("audiobook")
    _settle(app, window, (1400, 900), "audiobook")
    assert window.audiobook_book_list.maximumHeight() <= 180
    assert window.audiobook_source_stack.height() <= 180
    assert window.audiobook_start_btn.text() == "Convert audiobook"


def test_audiobook_convert_form_is_one_vertical_scroll_surface(app, window):
    """Every convert control must scroll together instead of being compressed."""
    from PySide6.QtCore import Qt

    _settle(app, window, (1000, 600), "audiobook")
    area = window.audiobook_convert_scroll
    content = area.widget()
    assert content is not None
    assert content.isAncestorOf(window.audiobook_input_path)
    assert content.isAncestorOf(window.audiobook_output_path)
    assert content.isAncestorOf(window.audiobook_start_btn)
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert area.verticalScrollBar().maximum() > 0


def test_audiobook_refresh_controls_keep_separate_jobs(app, window):
    assert window.audiobook_refresh_btn.text() == "Refresh List"
    assert window.audiobook_library_refresh_btn.text() == "Rescan"


def test_fixed_utility_rail_never_grows_a_horizontal_scrollbar(app, window):
    """The right rail is deliberately one fixed width; only vertical travel is useful."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea, QWidget

    rail = window.findChild(QWidget, "RailRight")
    area = rail.findChild(QScrollArea)
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff


def test_author_compose_remains_whole_with_profile_open(app, window):
    """Opening Book Profile must not crop the command deck below it."""
    from PySide6.QtCore import QPoint

    _settle(app, window, (1760, 820), "author")
    window._author_set_mode("write")
    was_open = window.author_profile_section.content.isVisible()
    if not was_open:
        window.author_profile_section.header_btn.click()
    for _ in range(6):
        app.processEvents()

    card = window.author_compose_card
    for control in (
        window.author_direction_input,
        window.author_task_box,
        window.author_provider_box,
        window.author_model_box,
        window.author_write_btn,
        window.author_continue_btn,
        window.author_stop_btn,
    ):
        top_left = control.mapTo(card, QPoint(0, 0))
        bottom_right = control.mapTo(card, control.rect().bottomRight())
        assert card.rect().contains(top_left), _describe(control)
        assert card.rect().contains(bottom_right), _describe(control)

    if not was_open:
        window.author_profile_section.header_btn.click()


def test_author_footer_prioritises_primary_actions_when_narrow(app, window):
    """Low-priority metadata gives way before Save or Export can be clipped."""
    _settle(app, window, (1000, 600), "author")
    window._author_set_mode("write")
    for _ in range(6):
        app.processEvents()

    assert not window.author_word_metric.isVisible()
    assert not window.author_export_author_input.isVisible()
    assert window.author_save_btn.isVisible()
    assert window.author_export_format_box.isVisible()
    assert window.author_export_btn.isVisible()
    assert window.author_save_btn.text() == "Save"
    assert window.author_export_btn.text() == "Export"


def test_dropdowns_use_the_shared_polished_popup(app, window):
    """Dropdowns must not fall back to macOS's plain native text menu."""
    from PySide6.QtWidgets import QAbstractItemView, QStyle
    from ui.widgets import DropdownItemDelegate, POPUP_MAX_WIDTH

    _settle(app, window, (1760, 820), "author")
    combo = window.author_model_box
    view = combo.view()

    assert combo.property("imprintModernDropdown") is True
    assert combo.style().styleHint(QStyle.SH_ComboBox_Popup, None, combo) == 0
    assert isinstance(view.itemDelegate(), DropdownItemDelegate)
    assert view.objectName() == "ImprintComboPopup"
    assert view.sizeHintForRow(0) >= DropdownItemDelegate.ROW_HEIGHT
    assert view.minimumWidth() == view.maximumWidth()
    assert view.width() <= POPUP_MAX_WIDTH
    assert combo.maxVisibleItems() == 9
    assert view.verticalScrollMode() == QAbstractItemView.ScrollPerPixel
    assert "combobox-popup: 0" in window.styleSheet()
    assert "dropdown-chevron.svg" in window.styleSheet()

    spec = os.path.join(os.path.dirname(__file__), "..", "Imprint.spec")
    assert '("assets/dropdown-chevron.svg", "assets")' in open(
        spec, encoding="utf-8").read()


def test_dropdowns_created_after_startup_are_polished(app, window):
    """Dialogs created later must receive the same popup as main panels."""
    from PySide6.QtWidgets import QComboBox, QStyle
    from ui.widgets import DropdownItemDelegate

    combo = QComboBox()
    combo.addItems(["First", "Second"])
    combo.show()
    for _ in range(3):
        app.processEvents()
    try:
        assert combo.property("imprintModernDropdown") is True
        assert combo.style().styleHint(QStyle.SH_ComboBox_Popup, None, combo) == 0
        assert isinstance(combo.itemDelegate(), DropdownItemDelegate)
    finally:
        combo.close()
        combo.deleteLater()


def test_short_dropdown_popup_tracks_its_field_instead_of_defaulting_to_640(app, window):
    """A two-item selector must not span most of the author canvas."""
    _settle(app, window, (1760, 820), "author")
    combo = window.author_content_type_box
    combo.showPopup()
    for _ in range(3):
        app.processEvents()
    try:
        popup_width = combo.view().window().width()
        assert popup_width <= combo.width() + 20
        assert popup_width < 500
    finally:
        combo.hidePopup()


def test_every_provider_model_selector_has_an_explained_best_fit(app, window):
    """A newly added panel cannot silently miss recommendation integration."""
    from main import AGENT_SETUP_WIDGETS
    from ui.widgets import (
        RECOMMENDED_ROLE, RECOMMENDATION_CONFIDENCE_ROLE,
        RECOMMENDATION_REASON_ROLE,
    )

    for agent, (provider_name, model_name) in AGENT_SETUP_WIDGETS.items():
        provider = getattr(window, provider_name)
        model = getattr(window, model_name)
        window.refresh_recommendation_marks(agent)
        for kind, combo in (("provider", provider), ("model", model)):
            marked = [i for i in range(combo.count())
                      if combo.itemData(i, RECOMMENDED_ROLE)]
            assert len(marked) == 1, f"{agent} {kind}: {marked}"
            index = marked[0]
            assert combo.itemData(index, RECOMMENDATION_REASON_ROLE)
            assert combo.itemData(index, RECOMMENDATION_CONFIDENCE_ROLE) in {
                "low", "medium", "high"
            }

    window.refresh_video_recommendations()
    for combo in (window.video_visual_provider_box,
                  window.video_visual_model_box,
                  window.fiverr_image_model_box):
        assert sum(bool(combo.itemData(i, RECOMMENDED_ROLE))
                   for i in range(combo.count())) == 1


def test_model_best_fit_recomputes_inside_each_selected_provider(app, window):
    from ui.widgets import RECOMMENDED_ROLE

    window.select_agent("social")
    for provider in ("openai", "deepseek", "gemini", "anthropic", "qwen"):
        window.social_provider_box.setCurrentText(provider)
        for _ in range(3):
            app.processEvents()
        marked = [i for i in range(window.social_model_box.count())
                  if window.social_model_box.itemData(i, RECOMMENDED_ROLE)]
        assert len(marked) == 1, provider


# ── Conditional fields ───────────────────────────────────────────────────────
CREATOR_KINDS = [
    ("post", 4),       # kind + campaign + channel + audience
    ("ppv", 5),        # kind + campaign + channel + price + audience
    ("promo", 3),      # kind + campaign + channel
    ("bio", 3),        # kind + campaign + channel
    ("campaign", 3),
    ("hooks", 3),
    ("welcome", 4),    # kind + campaign + channel + audience
]


@pytest.mark.parametrize("kind,expected", CREATOR_KINDS, ids=[k for k, _ in CREATOR_KINDS])
def test_creator_compose_grid_has_no_empty_cells(app, window, kind, expected):
    """Fields that do not apply give up their cell instead of leaving a hole.

    Price and audience only apply to some kinds of post. Hiding
    a widget inside a QGridLayout leaves its cell reserved and empty, so
    switching to "post" left a gap where Price had been and pushed Audience
    into the third column on its own — the same "nothing lines up" complaint,
    produced by an empty cell rather than a misplaced one.

    Also guards the subtler bug this replaced: the first implementation asked
    the widgets whether they were hidden, and a widget that has never been
    shown reports isHidden() as True, so the grid came up empty.
    """
    window.select_agent("creator")
    window._creator_kind_changed(kind)
    _settle(app, window, (1500, 950), "creator")

    grid = window.creator_compose_grid
    positions = sorted(grid.getItemPosition(i)[:2] for i in range(grid.count()))
    assert len(positions) == expected, (
        f"[{kind}] expected {expected} fields, packed {len(positions)}")
    # Packed from (0,0) rightwards with no gaps.
    assert positions == [(i // 3, i % 3) for i in range(expected)], (
        f"[{kind}] fields are not packed contiguously: {positions}")


def test_video_provider_model_controls_only_offer_working_routes(app, window):
    """Every visible provider/model pair must change to its real constraints."""
    from services.media_catalog import RETIRED_DALLE_MODELS

    window.select_agent("video")
    offered = set()
    for provider in ("OpenAI", "Higgsfield", "Pexels", "Local"):
        window.video_visual_provider_box.setCurrentText(provider)
        app.processEvents()
        assert window.video_visual_model_box.count() > 0
        offered.update(
            window.video_visual_model_box.itemData(i).model_id
            for i in range(window.video_visual_model_box.count()))

    assert offered.isdisjoint(RETIRED_DALLE_MODELS)
    window.video_visual_provider_box.setCurrentText("OpenAI")
    sora_index = next(
        i for i in range(window.video_visual_model_box.count())
        if window.video_visual_model_box.itemData(i).model_id == "sora-2")
    window.video_visual_model_box.setCurrentIndex(sora_index)
    app.processEvents()
    assert not window.video_format_box.isEnabled()
    assert [window.video_length_box.itemText(i)
            for i in range(window.video_length_box.count())] == ["4s", "8s", "12s"]

    image_index = next(
        i for i in range(window.video_visual_model_box.count())
        if window.video_visual_model_box.itemData(i).kind == "scene_images")
    window.video_visual_model_box.setCurrentIndex(image_index)
    app.processEvents()
    assert window.video_format_box.isEnabled()


def test_no_control_label_carries_an_emoji(app, window):
    """Emoji render at a different size and baseline from the text beside them.

    A column of buttons whose labels start with one has a ragged left edge
    that no padding fixes, which is most of why the rails read as untidy. The
    audio player's transport glyphs are exempt — ▶ on a play button is a
    universal symbol, not decoration.
    """
    from PySide6.QtWidgets import QPushButton, QLabel

    transport = set("▶⏸⏹⏪⏩⏵⏴×")
    offenders = []
    widgets = list(window.findChildren(QPushButton)) + list(window.findChildren(QLabel))
    for widget in widgets:
        text = widget.text()
        for char in text:
            if char in transport:
                continue
            if 0x1F300 <= ord(char) <= 0x1FAFF or char in "✅❌⚠✨🔌🔍💬📥📅⬇⛔↻↺⬛":
                offenders.append(f"{widget.objectName() or type(widget).__name__}: {text!r}")
                break
    assert not offenders, "emoji in control labels: " + "; ".join(sorted(set(offenders))[:8])


# ── The shell ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_shell_chrome_never_overlaps(app, window, size):
    """The header and the two rails, not just the panel between them.

    The panel tests only ever looked inside `<agent>_panel`, so the rails were
    unchecked — and at the window's own 600px minimum the spend rail drew
    "€0.00" straight over the caption beneath it. Same cause the panels use
    scrollable() for: a QVBoxLayout given less height than its children need
    compresses them past their own minimums instead of clipping.
    """
    _settle(app, window, size, "fiverr")
    bad = []
    for name in ("RailLeft", "RailRight", "AppHeader"):
        chrome = window.findChild(object, name)
        if chrome is None:
            continue
        bad += [(name, a, b) for a, b, _ in _overlapping_pairs(chrome)]
    assert not bad, "\n".join(
        f"  [{where}] {_describe(a)} overlaps {_describe(b)}"
        for where, a, b in bad[:6])


def test_workspace_names_are_never_elided(app, window):
    """Product-area names must remain meaningful after the professional rename."""
    from PySide6.QtCore import Qt

    _settle(app, window, (1500, 950), "author")
    assert window.workspace_tabs.elideMode() == Qt.ElideNone
    assert [window.workspace_tabs.tabText(i)
            for i in range(window.workspace_tabs.count())] == [
        "Author", "Audio + Music", "Video + Ads", "Social", "Web",
        "Brand Design", "Brand Creator", "OF Agent", "Assistant",
    ]


def test_studio_assistant_workspace_opens_the_existing_chat_panel(app, window):
    window.select_agent("chat")
    app.processEvents()
    assert window.workspace_tabs.tabText(window.workspace_tabs.currentIndex()) == "Assistant"
    assert window.normal_panel.isVisible()
    assert window.agent_title_label.text() == "Studio Assistant"
