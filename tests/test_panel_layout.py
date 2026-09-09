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

AGENTS = ["author", "manuscript", "music", "webdesign", "fiverr"]

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


# ── Conditional fields ───────────────────────────────────────────────────────
CREATOR_KINDS = [
    ("post", 2),        # kind + audience
    ("ppv", 3),         # kind + price + audience
    ("promo", 2),       # kind + promo channel
    ("bio", 1),         # kind only
    ("campaign", 1),
    ("hooks", 1),
    ("welcome", 2),     # kind + audience
]


@pytest.mark.parametrize("kind,expected", CREATOR_KINDS, ids=[k for k, _ in CREATOR_KINDS])
def test_creator_compose_grid_has_no_empty_cells(app, window, kind, expected):
    """Fields that do not apply give up their cell instead of leaving a hole.

    Three of the four compose fields only apply to some kinds of post. Hiding
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
