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


# Music is excluded: its whole panel scrolls (its controls sit in the main
# column, not a sidebar), and its setup grid genuinely needs more width than a
# 1100px window leaves. It scrolls rather than clipping, so nothing is
# unreachable — unlike the sidebars below, which had no scrollbar to reach for.
_NO_CLIP_AGENTS = ["author", "manuscript", "webdesign", "fiverr"]


@pytest.mark.parametrize("size", [(1900, 1200), (1500, 950), (1280, 820), (1100, 700)],
                         ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("agent", _NO_CLIP_AGENTS)
def test_control_columns_are_not_clipped(app, window, agent, size):
    """A column wider than its pane loses its right-hand edge — the fields cut
    off mid-control. Two causes, both fixed: a combo sizing itself to its
    longest item, and a QHBoxLayout reporting the sum of its children."""
    from PySide6.QtWidgets import QScrollArea
    _settle(app, window, size, agent)
    panel = getattr(window, f"{agent}_panel")
    clipped = []
    for area in panel.findChildren(QScrollArea):
        if not area.isVisible() or area.widget() is None:
            continue
        need = area.widget().minimumSizeHint().width()
        have = area.viewport().width()
        if need > have:
            clipped.append(f"needs {need}px, pane is {have}px")
    assert not clipped, f"[{agent}] control column clipped: " + "; ".join(clipped)
