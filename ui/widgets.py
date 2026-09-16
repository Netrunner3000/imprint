"""Reusable layout widgets.

Moved verbatim out of main.py (see docs/refactor_plan.md, phase 1).

`FlowLayout` exists because a QHBoxLayout reports the sum of its children as its
minimum width, which pins an impossible minimum on a pane and makes Qt compress
controls past their own minimums until the labels are chopped.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QRect, QPoint, QSize
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QLayout, QProxyStyle,
    QPushButton, QScrollArea, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ui.style import ACCENT, ELEVATED, TEXT, TEXT_MUTE


# Semantic item roles used by the recommendation system.  A recommendation is
# data, not a colour: using ForegroundRole made the renderer confuse grey
# oversized local models with BEST FIT entries and lost the badge on restyle.
RECOMMENDED_ROLE = int(Qt.ItemDataRole.UserRole) + 101
RECOMMENDATION_REASON_ROLE = int(Qt.ItemDataRole.UserRole) + 102
RECOMMENDATION_SCORE_ROLE = int(Qt.ItemDataRole.UserRole) + 103
RECOMMENDATION_CONFIDENCE_ROLE = int(Qt.ItemDataRole.UserRole) + 104
RECOMMENDATION_BADGE_ROLE = int(Qt.ItemDataRole.UserRole) + 105


class DropdownProxyStyle(QProxyStyle):
    """Force Qt's styleable list popup instead of macOS's native menu.

    Cocoa reports ``SH_ComboBox_Popup`` as true. That route paints the popup
    as a platform menu with a checkmark and mostly ignores the QAbstractItemView
    rules in our stylesheet — exactly why the previous visual refresh was not
    visible in the running app. Fusion supplies predictable control metrics;
    Imprint's stylesheet still owns the colours, border and chevron.
    """

    def __init__(self):
        super().__init__("Fusion")

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_ComboBox_Popup:
            return 0
        return super().styleHint(hint, option, widget, returnData)


class DropdownItemDelegate(QStyledItemDelegate):
    """Paint a compact menu card with an unmistakable selected state."""

    ROW_HEIGHT = 42
    HORIZONTAL_PADDING = 14
    CHECK_SPACE = 34
    BADGE_SPACE = 72

    def sizeHint(self, option, index):  # noqa: N802 - Qt API
        base = super().sizeHint(option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        width = option.fontMetrics.horizontalAdvance(text)
        badge_space = self.BADGE_SPACE \
            if index.data(RECOMMENDED_ROLE) else 0
        # QStyledItemDelegate's width can be the popup viewport's current width
        # (640px before layout on macOS). Only the content should influence the
        # horizontal hint; retain the base hint solely for row height.
        return QSize(
            width + self.HORIZONTAL_PADDING * 2 + self.CHECK_SPACE + badge_space,
            max(base.height(), self.ROW_HEIGHT),
        )

    @staticmethod
    def _wash(color: str, alpha: int) -> QColor:
        result = QColor(color)
        result.setAlpha(alpha)
        return result

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        row = option.rect.adjusted(5, 2, -5, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        recommendation_color = QColor(ACCENT)
        recommended = bool(index.data(RECOMMENDED_ROLE))

        painter.setPen(Qt.PenStyle.NoPen)
        if selected:
            painter.setBrush(self._wash(ACCENT, 30))
            painter.drawRoundedRect(row, 7, 7)
            rail = QRect(row.left(), row.top() + 8, 3, max(8, row.height() - 16))
            painter.setBrush(QColor(ACCENT))
            painter.drawRoundedRect(rail, 2, 2)
        elif hovered:
            painter.setBrush(QColor(ELEVATED))
            painter.drawRoundedRect(row, 7, 7)

        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text_left = row.left() + self.HORIZONTAL_PADDING
        if isinstance(icon, QIcon) and not icon.isNull():
            icon_size = 18
            icon.paint(painter, text_left, row.center().y() - icon_size // 2,
                       icon_size, icon_size)
            text_left += icon_size + 9

        item_font = index.data(Qt.ItemDataRole.FontRole)
        font = QFont(item_font) if isinstance(item_font, QFont) else QFont(option.font)
        if selected:
            font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        if isinstance(foreground, QBrush):
            foreground = foreground.color()
        text_color = (recommendation_color if recommended else
                      foreground if isinstance(foreground, QColor) else QColor(TEXT))
        painter.setPen(text_color if enabled else QColor(TEXT_MUTE))
        badge_space = self.BADGE_SPACE if recommended else 0
        text_rect = QRect(
            text_left,
            row.top(),
            max(0, row.right() - text_left - self.CHECK_SPACE - badge_space),
            row.height(),
        )
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.fontMetrics.elidedText(
                text, Qt.TextElideMode.ElideRight, text_rect.width()),
        )

        if recommended:
            badge = QRect(row.right() - self.CHECK_SPACE - 66,
                          row.center().y() - 9, 60, 18)
            painter.setPen(QPen(self._wash(ACCENT, 90), 1))
            painter.setBrush(self._wash(ACCENT, 22))
            painter.drawRoundedRect(badge, 8, 8)
            badge_font = QFont(option.font)
            badge_font.setPointSizeF(max(8.0, badge_font.pointSizeF() - 2.0))
            badge_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(badge_font)
            painter.setPen(QColor(ACCENT))
            badge_text = str(index.data(RECOMMENDATION_BADGE_ROLE) or "BEST FIT")
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, badge_text)

        if selected:
            centre = QPoint(row.right() - 17, row.center().y())
            painter.setBrush(self._wash(ACCENT, 36))
            painter.setPen(QPen(self._wash(ACCENT, 105), 1))
            painter.drawEllipse(centre, 10, 10)
            check_pen = QPen(QColor(ACCENT), 2)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.drawLine(centre + QPoint(-4, 0), centre + QPoint(-1, 4))
            painter.drawLine(centre + QPoint(-1, 4), centre + QPoint(5, -4))

        painter.restore()


_DROPDOWN_STYLE: DropdownProxyStyle | None = None
_DROPDOWN_POLISHER: QObject | None = None
POPUP_MIN_WIDTH = 180
POPUP_MAX_WIDTH = 480
POPUP_FRAME_WIDTH = 12


def _dropdown_style() -> DropdownProxyStyle:
    global _DROPDOWN_STYLE
    if _DROPDOWN_STYLE is None:
        _DROPDOWN_STYLE = DropdownProxyStyle()
    return _DROPDOWN_STYLE


def polish_combo(combo: QComboBox, visible_chars: int = 8) -> None:
    """Apply the complete Imprint dropdown behavior to one combo box."""
    natural = combo.sizeHint().width()
    if not combo.property("imprintModernDropdown"):
        # Mark first: setStyle() emits another Polish event on some platforms.
        combo.setProperty("imprintModernDropdown", True)
        combo.setStyle(_dropdown_style())

    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(visible_chars)
    combo.setMaxVisibleItems(9)
    view = combo.view()
    view.setObjectName("ImprintComboPopup")
    if not isinstance(combo.itemDelegate(), DropdownItemDelegate):
        combo.setItemDelegate(DropdownItemDelegate(combo))
    view.setMouseTracking(True)
    view.setUniformItemSizes(True)
    content_width = max(
        (view.sizeHintForColumn(column) for column in range(view.model().columnCount())),
        default=0,
    ) + POPUP_FRAME_WIDTH
    # A QWidget starts life at 640px wide on macOS. Trust combo.width() only
    # once the control is visible; otherwise that placeholder becomes the
    # permanent popup minimum and a two-item menu spans most of the canvas.
    field_width = combo.width() if combo.isVisible() else natural
    minimum = 120 if combo.objectName() == "CompactCombo" else POPUP_MIN_WIDTH
    popup_width = min(
        POPUP_MAX_WIDTH,
        max(minimum, field_width, content_width),
    )
    view.setFixedWidth(popup_width)
    view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


class _DropdownPolisher(QObject):
    """Catch combo boxes created later by dialogs and auxiliary windows."""

    def eventFilter(self, watched, event):  # noqa: N802 - Qt API
        if isinstance(watched, QComboBox) and event.type() in (
            QEvent.Type.Polish,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.KeyPress,
        ):
            polish_combo(watched)
        return False


def install_dropdown_system(app: QApplication | None) -> None:
    """Install the design-system dropdown once for the whole application."""
    if app is None:
        return
    global _DROPDOWN_POLISHER
    if _DROPDOWN_POLISHER is None:
        _DROPDOWN_POLISHER = _DropdownPolisher(app)
        app.installEventFilter(_DROPDOWN_POLISHER)
    for widget in app.allWidgets():
        if isinstance(widget, QComboBox):
            polish_combo(widget)


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
    """Quiet accordion with a readable label and a contained content region.

    Section headings used to reuse the tiny, tracked field-label style.  In a
    narrow rail that made the hierarchy disappear and left the expanded body
    looking detached from its title.  This is navigation, so it uses sentence
    case, a full-width target, and an explicit open/closed state.
    """

    HEADER_STYLE = """
        QPushButton#CollapsibleHeader {
            text-align: left;
            padding: 9px 10px;
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 7px;
            color: #9aa5b4;
            font-weight: 600;
            font-size: 12px;
        }
        QPushButton#CollapsibleHeader:hover {
            color: #e8ecf1;
            background-color: #1a1f29;
            border-color: rgba(255, 255, 255, 0.09);
        }
        QPushButton#CollapsibleHeader:checked {
            color: #e8ecf1;
            background-color: rgba(255, 255, 255, 0.035);
        }
    """

    def __init__(self, title: str, expanded: bool = True):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._expanded = expanded
        self._title = title

        self.header_btn = QPushButton()
        self.header_btn.setObjectName("CollapsibleHeader")
        self.header_btn.setCheckable(True)
        self.header_btn.setChecked(expanded)
        self.header_btn.setStyleSheet(self.HEADER_STYLE)
        self.header_btn.setAccessibleName(title)
        self.header_btn.setAccessibleDescription(
            f"Show or hide the {title} section")
        self.header_btn.clicked.connect(self._toggle)
        layout.addWidget(self.header_btn)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 10)
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
        arrow = "⌄" if self._expanded else "›"
        # QPushButton reads "&" as a mnemonic marker, which silently turned
        # "Finance & Business" into "FINANCE _BUSINESS". Double it to render a
        # literal ampersand.
        title = self._title.replace("&", "&&")
        self.header_btn.setText(f"{arrow}   {title}")
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


def let_combos_shrink(root: QWidget, visible_chars: int = 8) -> int:
    """Stop combo boxes from pinning a control column wider than its pane.

    A QComboBox sizes itself to its longest *item*, so one entry like
    "claude-opus-4-6" asks for 230px in a 200px column. The column cannot meet
    that, so the content is clipped and a horizontal scrollbar appears — the
    fields cut off down the right-hand edge.

    Sizing to a fixed character count instead lets the box shrink with its
    column. The popup keeps the full natural width, so the long names are still
    readable when choosing; only the collapsed box gets shorter, and the
    current value elides.

    Returns how many boxes were adjusted, so a caller can assert it ran.
    """
    count = 0
    for combo in root.findChildren(QComboBox):
        polish_combo(combo, visible_chars)
        count += 1
    return count
