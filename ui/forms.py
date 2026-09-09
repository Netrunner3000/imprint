"""Layout primitives — one spacing scale, one form idiom.

The panels were built one at a time over a long period, and it showed: eight
different spacing values (3, 4, 5, 6, 8, 10, 12, 0), eight margin combinations
including asymmetric ones like ``(10, 6, 10, 10)``, and two competing ways to
label a field — 58 label-beside-input rows against 22 group boxes. Nothing was
individually wrong, and the result read as chaotic because no two panels agreed.

This module is the agreement. Building a panel out of these helpers makes the
rules structural rather than something to remember:

* **One scale.** ``XS/SM/MD/LG`` = 4/8/16/24. Any other gap is a bug.
* **One form idiom.** ``field()`` — a small-caps label above its input, both
  flush to the same left edge. Labels then line up down a column instead of
  landing wherever the previous widget happened to end.
* **Sections, not boxes.** ``section()`` and ``rule()`` group without adding a
  border and a title bar for every four fields.
* **One control height**, so a row of mixed inputs and buttons sits on a line.

`form_grid()` is the reason the project bar stops looking ragged: a real grid
with equal column stretch, rather than a FlowLayout that wraps to wherever the
previous widget ended.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

# The scale. Four numbers; nothing between them.
XS, SM, MD, LG = 4, 8, 16, 24

# One height for every single-line control, so a mixed row sits on one line.
CONTROL_HEIGHT = 32


def micro(text: str) -> QLabel:
    """A field label: small caps, muted, sitting above its input."""
    label = QLabel(text.upper())
    label.setObjectName("MicroLabel")
    return label


def section(text: str) -> QLabel:
    """A group heading. Replaces a QGroupBox title without the box."""
    label = QLabel(text.upper())
    label.setObjectName("SectionLabel")
    return label


def rule() -> QFrame:
    """A hairline divider — the other half of grouping without a box."""
    line = QFrame()
    line.setObjectName("CardDivider")
    line.setFrameShape(QFrame.HLine)
    return line


def field(label: str, widget: QWidget, *, stretch_label: bool = False) -> QWidget:
    """The one form idiom: label above input, both flush left.

    Returns a container so the pair can be dropped into any layout and stay
    together — which is what keeps a column of fields aligned when one of them
    wraps or is hidden.
    """
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(XS)
    label_widget = micro(label)
    if stretch_label:
        label_widget.setWordWrap(True)
    layout.addWidget(label_widget)
    layout.addWidget(widget)
    return box


def form_grid(pairs: list[tuple[str, QWidget]], *, columns: int = 3) -> QGridLayout:
    """A grid of `field()`s with equal columns.

    Equal stretch is the point: it is what makes the second row's labels sit
    directly under the first row's, instead of each row packing to its own
    content width.
    """
    grid = QGridLayout()
    grid.setHorizontalSpacing(MD)
    grid.setVerticalSpacing(MD)
    for index, (label, widget) in enumerate(pairs):
        grid.addWidget(field(label, widget), index // columns, index % columns)
    for column in range(columns):
        grid.setColumnStretch(column, 1)
    return grid


def stack(*widgets, spacing: int = MD, margins: int = 0) -> QVBoxLayout:
    """A vertical layout on the scale. `margins` is applied on all four sides —
    asymmetric margins are most of why panels failed to line up with each
    other."""
    layout = QVBoxLayout()
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        if widget is None:
            layout.addStretch()
        elif isinstance(widget, QWidget):
            layout.addWidget(widget)
        else:
            layout.addLayout(widget)
    return layout


def row(*widgets, spacing: int = SM) -> QHBoxLayout:
    """A horizontal layout on the scale. `None` inserts a stretch."""
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for widget in widgets:
        if widget is None:
            layout.addStretch()
        elif isinstance(widget, QWidget):
            layout.addWidget(widget)
        else:
            layout.addLayout(widget)
    return layout


def stat(value: str, caption: str) -> QWidget:
    """A number over its unit. Zero spacing between them is deliberate: they
    read as one object rather than two stacked labels."""
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    number = QLabel(value)
    number.setObjectName("StatValue")
    layout.addWidget(number)
    layout.addWidget(micro(caption))
    return box


def primary(text: str) -> QPushButton:
    """The one filled button on a screen."""
    button = QPushButton(text)
    button.setObjectName("PrimaryAction")
    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return button


def combo(items: list[str] | tuple[str, ...] = (), current: str = "") -> QComboBox:
    widget = QComboBox()
    if items:
        widget.addItems(list(items))
    if current:
        widget.setCurrentText(current)
    return widget


def line_edit(placeholder: str = "", text: str = "") -> QLineEdit:
    widget = QLineEdit(text)
    if placeholder:
        widget.setPlaceholderText(placeholder)
    return widget


# Style for the primitives above. Appended to the global sheet rather than set
# per widget, so a panel never carries its own copy of the type scale.
FORM_STYLES = """
        QLabel#MicroLabel {{
            color: {muted};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.1px;
        }}
        QLabel#SectionLabel {{
            color: {muted};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.4px;
        }}
        QLabel#StatValue {{
            color: {text};
            font-size: 20px;
            font-weight: 600;
        }}
        QLineEdit, QComboBox {{ min-height: {height}px; }}
        QPushButton {{ min-height: {height}px; }}
"""


def form_stylesheet(text: str, muted: str) -> str:
    return FORM_STYLES.format(text=text, muted=muted, height=CONTROL_HEIGHT)


# ── Shell primitives ─────────────────────────────────────────────────────────
# The chrome around the panels: one header bar, two fixed rails. Fixed rather
# than a QSplitter because a splitter is allowed to compress a pane past its
# children's minimum widths, and every overlapping-widget bug this app has had
# started that way. Two numbers you cannot drag are worth more than three you
# can.

HEADER_HEIGHT = 56
RAIL_LEFT_WIDTH = 236
RAIL_RIGHT_WIDTH = 268
# A form field wider than this stops being readable, so the centre column caps
# out rather than stretching a text input across a 27" display.
CONTENT_MAX_WIDTH = 1080


def nav_tab(text: str) -> QPushButton:
    """A mode tab: text with an accent underline when current.

    Checkable rather than a QTabBar so it lives in the header row beside the
    wordmark. The visual difference from `primary()` is the point — navigation
    that looks like a button competes with the buttons that actually do work.
    """
    button = QPushButton(text)
    button.setObjectName("NavTab")
    button.setCheckable(True)
    button.setFixedHeight(HEADER_HEIGHT)
    return button


def quiet(text: str) -> QPushButton:
    """A utility affordance: reads as a link, still behaves as a button.

    Used for the things that open a window and change nothing — Run Log, Cost
    History, Settings. They were full-weight buttons stacked in a card, which
    gave five inert utilities the same visual weight as "Generate".
    """
    button = QPushButton(text)
    button.setObjectName("QuietAction")
    button.setFixedHeight(30)
    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return button


class StatBlock(QWidget):
    """One number over its caption.

    Replaces a line of prose like ``Session Cost: €0.00``. The number is the
    content; putting it on its own line at a larger size is what makes a column
    of them scannable instead of five sentences to read.
    """

    def __init__(self, caption: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("Transparent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        layout.addWidget(self.value_label)
        self.caption_label = micro(caption)
        layout.addWidget(self.caption_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_caption(self, caption: str) -> None:
        self.caption_label.setText(caption.upper())


class Meter(QWidget):
    """A budget as a bar, with used/cap beside the label.

    "Session remaining: €1 / €1" is two numbers you have to subtract to
    understand. A bar answers the actual question — how much is left — before
    you have read anything.
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Transparent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(XS + 1)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(SM)
        top.addWidget(micro(label))
        top.addStretch()
        self.amount_label = micro("—")
        top.addWidget(self.amount_label)
        layout.addLayout(top)

        self.bar = QProgressBar()
        self.bar.setObjectName("BudgetBar")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

    def set(self, used: float, cap: float) -> None:
        self.amount_label.setText(f"€{used:.2f} / €{cap:.2f}".upper())
        # A zero cap is "no limit", not "fully spent" — showing a full bar there
        # would read as blocked when nothing is.
        percent = 0 if cap <= 0 else min(100, int(round(used / cap * 100)))
        self.bar.setValue(percent)
        self.bar.setProperty("over", percent >= 100)
        self.bar.style().unpolish(self.bar)
        self.bar.style().polish(self.bar)


def rail(object_name: str, width: int) -> QFrame:
    """A fixed-width side column."""
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setFixedWidth(width)
    return frame
