"""Reusable layout widgets.

Moved verbatim out of main.py (see docs/refactor_plan.md, phase 1).

`FlowLayout` exists because a QHBoxLayout reports the sum of its children as its
minimum width, which pins an impossible minimum on a pane and makes Qt compress
controls past their own minimums until the labels are chopped.
"""
from PySide6.QtCore import Qt, QRect, QPoint, QSize
from PySide6.QtWidgets import (
    QLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)


class FlowLayout(QLayout):
    """Left-to-right layout that wraps onto a new line when it runs out of width.

    A QHBoxLayout of buttons reports the sum of their widths as its minimum, so a
    long control row pins a hard minimum width on the whole pane. Below that the
    splitter compresses the buttons past their own minimums and the labels get
    chopped ("Auto Rout", "ecomme"). Wrapping instead keeps every control at its
    natural size and lets the pane shrink to the width of the widest single item.
    """

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    # ── QLayout plumbing ────────────────────────────────────────────────
    def addWidget(self, widget, stretch=0, alignment=None):
        """Drop-in for QBoxLayout.addWidget, which takes a stretch factor.

        Stretch and alignment have no meaning once items wrap, but accepting
        them means a QHBoxLayout can be swapped for this without touching the
        call sites.
        """
        super().addWidget(widget)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(),
                            margins.top() + margins.bottom())

    # ── placement ───────────────────────────────────────────────────────
    def _arrange(self, rect, apply):
        margins = self.contentsMargins()
        left = rect.x() + margins.left()
        right = rect.right() - margins.right()
        x, y = left, rect.y() + margins.top()
        line_height = 0
        space = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > right and line_height > 0:   # wrap
                x = left
                y += line_height + space
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + space
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


class CollapsibleSection(QWidget):
    """Modern accordion-style section with header button and toggleable content."""

    HEADER_STYLE = """
        QPushButton#CollapsibleHeader {
            text-align: left;
            padding: 4px 10px;
            background-color: transparent;
            border: none;
            color: #707070;
            font-weight: bold;
            font-size: 10px;
            letter-spacing: 1.5px;
        }
        QPushButton#CollapsibleHeader:hover {
            color: #ffffff;
        }
        QPushButton#CollapsibleHeader:checked {
            color: #999999;
        }
    """

    def __init__(self, title: str, expanded: bool = True):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._expanded = expanded
        self._title = title

        self.header_btn = QPushButton()
        self.header_btn.setObjectName("CollapsibleHeader")
        self.header_btn.setCheckable(True)
        self.header_btn.setChecked(expanded)
        self.header_btn.setStyleSheet(self.HEADER_STYLE)
        self.header_btn.clicked.connect(self._toggle)
        layout.addWidget(self.header_btn)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 4, 0, 10)
        self.content_layout.setSpacing(3)
        layout.addWidget(self.content)

        self._update_header()
        self.content.setVisible(expanded)

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)

    def _toggle(self):
        self._expanded = not self._expanded
        self.content.setVisible(self._expanded)
        self._update_header()

    def _update_header(self):
        arrow = "▾" if self._expanded else "▸"
        # QPushButton reads "&" as a mnemonic marker, which silently turned
        # "Finance & Business" into "FINANCE _BUSINESS". Double it to render a
        # literal ampersand.
        title = self._title.upper().replace("&", "&&")
        self.header_btn.setText(f"  {arrow}   {title}")
        self.header_btn.setChecked(self._expanded)


def scrollable(widget: QWidget, *, min_width: int | None = None,
               max_width: int | None = None) -> QScrollArea:
    """Wrap a control column so it scrolls instead of overlapping itself.

    The same failure FlowLayout fixes horizontally, on the vertical axis. A
    QVBoxLayout reports the sum of its children as its minimum height; drop a
    splitter pane below that and Qt compresses the children past their own
    minimums, and they are drawn on top of each other — the direction box
    landing over the Task and Provider rows beneath it.

    A splitter will happily do that, because it honours the sizes the user drags
    to over a child's minimumSizeHint. Wrapping the column in a scroll area
    gives the content its full natural height and scrolls the overflow.

    Width is carried across because the wrapper, not the inner widget, is what
    the splitter now sizes.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    # AsNeeded, not AlwaysOff: widgetResizable shrinks the column to the
    # viewport, but it can only shrink to the widest control's own minimum.
    # Past that, AlwaysOff clips the control out of reach; a scrollbar is
    # less pretty and still usable.
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

    # Move the width constraints up to the wrapper, or the splitter sizes the
    # scroll area freely and the inner column keeps its old limits.
    if min_width is None and widget.minimumWidth():
        min_width = widget.minimumWidth()
    if max_width is None and widget.maximumWidth() < 16777215:
        max_width = widget.maximumWidth()
    widget.setMinimumWidth(0)
    widget.setMaximumWidth(16777215)
    if min_width:
        area.setMinimumWidth(min_width)
    if max_width:
        area.setMaximumWidth(max_width)

    area.setWidget(widget)
    return area
