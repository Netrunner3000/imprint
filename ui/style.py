"""The application stylesheet.

A single Qt style sheet built from named tokens, with no application state in
it. Extracted from main.py in refactor phase 1; rewritten as a token system so
that a colour is defined once and every surface that uses it agrees.

## The design system

Dark, low-chroma, one accent. The previous palette ran a neon green
(``#3cff88``) alongside a saturated indigo "Write" button, an orange
"Publish/Market" button and a red "Stop", so four competing hues fought for
attention on one screen and nothing read as more important than anything else.

The rules here:

* **One accent.** ``ACCENT`` marks the current thing — selected tab, focused
  field, active nav item — and nothing else. Emerald rather than neon: it holds
  up against a dark ground without glowing.
* **Semantic colour is reserved for meaning.** ``DANGER`` stops work,
  ``WARNING`` flags an irreversible or paid step, ``INFO`` is neutral emphasis.
  A button is not coloured because it looks nice there.
* **Elevation by surface, not by border.** Three greys (``BG`` → ``SURFACE`` →
  ``ELEVATED``) separate page from card from input. Borders are low-alpha white
  so they read on every surface without being redefined per card.
* **One spacing and radius scale.** 6/8/10/12px radii by element size; padding
  in multiples of 2.

Greys are slightly blue rather than neutral (#0d0f12, not #0f0f0f) because a
pure grey next to the emerald reads faintly magenta.
"""

# ── Tokens ───────────────────────────────────────────────────────────────
# Surfaces, darkest first. Page sits behind cards; inputs sink below cards.
BG        = "#0d0f12"   # window / page
SURFACE   = "#141820"   # cards, panels, group boxes
ELEVATED  = "#1a1f29"   # hover, selected rows, raised chips
SUNKEN    = "#0a0c0f"   # text areas and inputs — below the card, not above

# Text, brightest first.
TEXT      = "#e8ecf1"   # primary copy
TEXT_DIM  = "#9aa5b4"   # labels, secondary copy
TEXT_MUTE = "#6b7684"   # placeholders, disabled, section headers

# Lines. Low-alpha white so one value works on every surface above.
BORDER       = "rgba(255, 255, 255, 0.09)"
BORDER_STRONG = "rgba(255, 255, 255, 0.16)"

# Accent — the current thing, and nothing else.
ACCENT       = "#34d399"
ACCENT_DIM   = "#2bb583"
ACCENT_TEXT  = "#04140d"                      # text *on* an accent fill
ACCENT_WASH  = "rgba(52, 211, 153, 0.12)"     # tinted background
ACCENT_LINE  = "rgba(52, 211, 153, 0.35)"

# Semantic — meaning only.
DANGER      = "#f87171"
DANGER_WASH = "rgba(248, 113, 113, 0.12)"
DANGER_LINE = "rgba(248, 113, 113, 0.35)"
WARNING     = "#fbbf24"
WARNING_WASH = "rgba(251, 191, 36, 0.12)"
WARNING_LINE = "rgba(251, 191, 36, 0.32)"
INFO        = "#60a5fa"
INFO_WASH   = "rgba(96, 165, 250, 0.12)"
INFO_LINE   = "rgba(96, 165, 250, 0.32)"

RADIUS    = "8px"
RADIUS_SM = "6px"
RADIUS_LG = "12px"


GLOBAL_STYLESHEET = f"""
        QWidget {{
            background-color: {BG};
            color: {TEXT_DIM};
            font-size: 13px;
        }}

        /* ── Inputs ────────────────────────────────────────────────── */
        QTextEdit, QTextBrowser, QListWidget {{
            background-color: {SUNKEN};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS};
            padding: 8px 10px;
            selection-background-color: {ACCENT_WASH};
            selection-color: {TEXT};
        }}
        QTextEdit:focus, QListWidget:focus {{
            border: 1px solid {ACCENT_LINE};
        }}

        QSpinBox, QDoubleSpinBox {{
            background-color: {SUNKEN};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 7px 10px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {ACCENT_LINE}; }}

        QLineEdit {{
            background-color: {SUNKEN};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 7px 10px;
            selection-background-color: {ACCENT_WASH};
            selection-color: {TEXT};
        }}
        QLineEdit:focus {{
            border: 1px solid {ACCENT_LINE};
        }}
        QLineEdit:disabled, QTextEdit:disabled {{
            color: {TEXT_MUTE};
            background-color: {BG};
        }}

        QComboBox {{
            background-color: {SUNKEN};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 6px 10px;
            min-height: 20px;
        }}
        QComboBox:hover {{ border: 1px solid {BORDER_STRONG}; }}
        QComboBox:focus {{ border: 1px solid {ACCENT_LINE}; }}
        /* Qt's native arrow is left alone. A CSS border-triangle needs the
           exact right box model on every platform and rendered here as a small
           filled square instead of a chevron, so it is not worth the trade. */
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background-color: {SURFACE};
            color: {TEXT};
            border: 1px solid {BORDER_STRONG};
            border-radius: {RADIUS_SM};
            padding: 4px;
            selection-background-color: {ACCENT_WASH};
            selection-color: {TEXT};
            outline: none;
        }}

        /* ── Buttons ───────────────────────────────────────────────── */
        /* Default is quiet: a card-coloured surface with a hairline. Colour is
           earned by role (PrimaryAction / DangerAction), never by decoration. */
        QPushButton {{
            background-color: {ELEVATED};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 7px 14px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {SURFACE};
            border: 1px solid {BORDER_STRONG};
        }}
        QPushButton:pressed {{ background-color: {SUNKEN}; }}
        QPushButton:disabled {{
            color: {TEXT_MUTE};
            background-color: {BG};
            border: 1px solid {BORDER};
        }}
        QPushButton:checked {{
            background-color: {ACCENT_WASH};
            border: 1px solid {ACCENT_LINE};
            color: {ACCENT};
        }}

        /* The one filled button on a screen: the action that spends or ships. */
        QPushButton#PrimaryAction {{
            background-color: {ACCENT};
            color: {ACCENT_TEXT};
            border: 1px solid {ACCENT};
            font-weight: 600;
        }}
        QPushButton#PrimaryAction:hover {{
            background-color: {ACCENT_DIM};
            border: 1px solid {ACCENT_DIM};
        }}
        QPushButton#PrimaryAction:pressed {{ background-color: {ACCENT_DIM}; }}
        QPushButton#PrimaryAction:disabled {{
            background-color: {ELEVATED};
            color: {TEXT_MUTE};
            border: 1px solid {BORDER};
        }}

        /* Stops or discards. Outlined, not filled — destructive actions should
           not be the brightest thing on the screen. */
        QPushButton#DangerAction {{
            background-color: {DANGER_WASH};
            color: {DANGER};
            border: 1px solid {DANGER_LINE};
            font-weight: 600;
        }}
        QPushButton#DangerAction:hover {{ border: 1px solid {DANGER}; }}
        QPushButton#DangerAction:disabled {{
            background-color: {BG};
            color: {TEXT_MUTE};
            border: 1px solid {BORDER};
        }}

        /* Costs money or leaves the machine. */
        QPushButton#WarnAction {{
            background-color: {WARNING_WASH};
            color: {WARNING};
            border: 1px solid {WARNING_LINE};
            font-weight: 600;
        }}
        QPushButton#WarnAction:hover {{ border: 1px solid {WARNING}; }}
        QPushButton#WarnAction:disabled {{
            background-color: {BG};
            color: {TEXT_MUTE};
            border: 1px solid {BORDER};
        }}

        /* Secondary confirm — continues work already under way. */
        QPushButton#SecondaryAction {{
            background-color: {ACCENT_WASH};
            color: {ACCENT};
            border: 1px solid {ACCENT_LINE};
            font-weight: 600;
        }}
        QPushButton#SecondaryAction:hover {{ border: 1px solid {ACCENT}; }}
        QPushButton#SecondaryAction:disabled {{
            background-color: {BG};
            color: {TEXT_MUTE};
            border: 1px solid {BORDER};
        }}

        /* Small inline utilities that must not compete with the real action. */
        QPushButton#ChipBtn {{
            background-color: transparent;
            color: {TEXT_DIM};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 500;
        }}
        QPushButton#ChipBtn:hover {{
            color: {TEXT};
            background-color: {ELEVATED};
            border: 1px solid {BORDER_STRONG};
        }}

        /* Mode switch inside a panel (Write / Publish · Market). */
        /* The stage switcher inside a workspace (Draft|Publish,
           Audiobooks|Music). A segmented control, not two more buttons: it
           sits directly above the page title, and as accent-filled pills it
           read as the most important thing on the screen when it is only
           navigation. */
        QPushButton#WorkspaceTool {{
            background-color: transparent;
            color: {TEXT_MUTE};
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
            padding: 0 2px;
            margin-right: 20px;
            font-weight: 550;
        }}
        QPushButton#WorkspaceTool:hover {{ color: {TEXT_DIM}; }}
        QPushButton#WorkspaceTool:checked {{
            color: {TEXT};
            border-bottom: 2px solid {ACCENT};
            font-weight: 650;
        }}

        /* Left rail nav rows. */
        QPushButton#AgentBtn {{
            text-align: left;
            padding: 9px 8px 9px 12px;
            background-color: transparent;
            border: none;
            border-left: 2px solid transparent;
            border-radius: 0;
            color: {TEXT_DIM};
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton#AgentBtn:hover {{
            background-color: {SURFACE};
            color: {TEXT};
        }}
        QPushButton#AgentBtn:checked {{
            background-color: {ACCENT_WASH};
            border-left: 2px solid {ACCENT};
            color: {ACCENT};
            font-weight: 600;
        }}

        /* ── Structure ─────────────────────────────────────────────── */
        QGroupBox {{
            background-color: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_LG};
            margin-top: 14px;
            padding: 12px 12px 10px 12px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 6px;
            color: {TEXT_MUTE};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.2px;
        }}

        QWidget#LeftPanel, QWidget#RightPanel {{ background-color: {BG}; }}
        QWidget#RightCardsContainer {{ background-color: transparent; }}
        QWidget#RightCard, QGroupBox#RightCard {{
            background-color: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_LG};
        }}
        QFrame#HeaderDivider {{
            background-color: {BORDER};
            border: none;
        }}
        QFrame#CardDivider {{
            background-color: {BORDER};
            border: none;
            max-height: 1px;
        }}

        QSplitter::handle {{ background-color: transparent; }}
        QSplitter::handle:horizontal {{ width: 10px; }}
        QSplitter::handle:vertical {{ height: 10px; }}
        QSplitter::handle:hover {{ background-color: {ACCENT_WASH}; }}

        /* ── Labels ────────────────────────────────────────────────── */
        QLabel {{ background: transparent; color: {TEXT_DIM}; }}

        QLabel#AgentTitle {{
            color: {TEXT};
            font-size: 21px;
            font-weight: 650;
        }}
        QLabel#AgentSubtitle {{ color: {TEXT_MUTE}; font-size: 12px; }}

        QLabel#StudioBrand {{
            color: {TEXT};
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 1.6px;
        }}
        QLabel#StudioBrandNote {{ color: {TEXT_MUTE}; font-size: 11px; }}

        QLabel#StatusPill {{
            color: {ACCENT};
            font-size: 12px;
            font-weight: 600;
            padding: 0;
        }}
        /* The "next step" hint. Both panels carried their own copy of these
           five declarations inline. */
        QLabel#NextStepBanner {{
            background-color: {ACCENT_WASH};
            border: 1px solid {ACCENT_LINE};
            border-radius: {RADIUS_SM};
            padding: 9px 12px;
            color: {ACCENT};
            font-size: 12px;
        }}
        QLabel#EstimateLine {{ color: {TEXT_MUTE}; font-size: 11px; }}
        QLabel#ResourceLabel {{ color: {TEXT_DIM}; font-size: 12px; }}

        /* Section headers in the rails. */
        QLabel#SectionHeader {{
            color: {TEXT_MUTE};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.4px;
        }}

        /* ── Tabs ──────────────────────────────────────────────────── */
        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: {RADIUS_LG};
            top: -1px;
            background-color: {SURFACE};
        }}
        QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
        QTabBar::tab {{
            background: transparent;
            color: {TEXT_DIM};
            border: none;
            border-bottom: 2px solid transparent;
            padding: 8px 14px;
            margin-right: 2px;
            font-weight: 500;
        }}
        QTabBar::tab:hover {{ color: {TEXT}; }}
        QTabBar::tab:selected {{
            color: {ACCENT};
            border-bottom: 2px solid {ACCENT};
            font-weight: 600;
        }}

        /* The mode switch lives in the header bar, so it reads as navigation:
           text with an accent underline. As pills it looked like five more
           buttons, competing with the one button on the page that spends
           money. */
        QTabBar#WorkspaceTabs {{ background: transparent; }}
        QTabBar#WorkspaceTabs::tab {{
            background: transparent;
            color: {TEXT_MUTE};
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
            padding: 0 4px;
            margin: 0 12px;
            font-weight: 550;
        }}
        QTabBar#WorkspaceTabs::tab:hover {{ color: {TEXT_DIM}; }}
        QTabBar#WorkspaceTabs::tab:selected {{
            color: {TEXT};
            border-bottom: 2px solid {ACCENT};
            font-weight: 650;
        }}

        /* ── Feedback ──────────────────────────────────────────────── */
        QProgressBar {{
            background-color: {SUNKEN};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            height: 6px;
            text-align: center;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background-color: {ACCENT};
            border-radius: {RADIUS_SM};
        }}

        QCheckBox {{ color: {TEXT_DIM}; spacing: 8px; }}
        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 1px solid {BORDER_STRONG};
            border-radius: 4px;
            background-color: {SUNKEN};
        }}
        QCheckBox::indicator:hover {{ border: 1px solid {ACCENT_LINE}; }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT};
            border: 1px solid {ACCENT};
        }}

        QToolTip {{
            background-color: {ELEVATED};
            color: {TEXT};
            border: 1px solid {BORDER_STRONG};
            border-radius: {RADIUS_SM};
            padding: 6px 9px;
        }}

        /* ── Scrollbars ────────────────────────────────────────────── */
        QScrollArea {{ background: transparent; border: none; }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {BORDER_STRONG};
            border-radius: 5px;
            min-height: 28px;
        }}
        QScrollBar::handle:vertical:hover {{ background-color: {TEXT_MUTE}; }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {BORDER_STRONG};
            border-radius: 5px;
            min-width: 28px;
        }}
        QScrollBar::handle:horizontal:hover {{ background-color: {TEXT_MUTE}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

        /* ── Left rail ─────────────────────────────────────────────── */
        /* Scoped rules that used to live as an inline stylesheet on the rail
           widget in main.py, carrying its own copy of the old palette. Moved
           here so the rails follow the tokens like everything else. */
        QWidget#LeftPanel QLineEdit {{
            background-color: {SUNKEN};
            border: 1px solid {BORDER};
            border-radius: {RADIUS};
            padding: 6px 10px;
            color: {TEXT};
        }}
        QWidget#LeftPanel QLineEdit:focus {{ border: 1px solid {ACCENT_LINE}; }}
        QWidget#LeftPanel QListWidget {{
            background-color: {SUNKEN};
            border: 1px solid {BORDER};
            border-radius: {RADIUS};
            font-size: 12px;
            color: {TEXT_DIM};
            padding: 4px;
        }}
        QWidget#LeftPanel QListWidget::item {{ padding: 5px 8px; border-radius: 4px; }}
        QWidget#LeftPanel QListWidget::item:hover {{ background-color: {ELEVATED}; }}
        QWidget#LeftPanel QListWidget::item:selected {{
            background-color: {ACCENT_WASH};
            color: {ACCENT};
        }}
        QWidget#LeftPanel > QPushButton {{
            background-color: {ELEVATED};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 8px 10px;
            color: {TEXT};
            margin-top: 6px;
        }}
        QWidget#LeftPanel > QPushButton:hover {{
            background-color: {SURFACE};
            border: 1px solid {ACCENT_LINE};
            color: {TEXT};
        }}

        /* ── Right rail cards ──────────────────────────────────────── */
        QGroupBox#RightCard QLabel {{ color: {TEXT_DIM}; font-size: 12px; }}
        QGroupBox#RightCard QLineEdit {{
            background-color: {SUNKEN};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 5px 10px;
            color: {TEXT};
        }}
        QGroupBox#RightCard QLineEdit:focus {{ border: 1px solid {ACCENT_LINE}; }}
        QGroupBox#RightCard QPushButton {{
            background-color: {ELEVATED};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM};
            padding: 7px 10px;
            color: {TEXT};
        }}
        QGroupBox#RightCard QPushButton:hover {{
            background-color: {SURFACE};
            border: 1px solid {BORDER_STRONG};
        }}
        QGroupBox#RightCard QPushButton:pressed {{ background-color: {SUNKEN}; }}
        QGroupBox#RightCard QPushButton:disabled {{
            color: {TEXT_MUTE};
            background-color: {BG};
        }}

        /* ── Form primitives (ui/forms.py) ─────────────────────────── */
        /* The type scale lives here rather than on each widget, so a panel
           never carries its own copy of it. */
        QLabel#MicroLabel {{
            color: {TEXT_MUTE};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.1px;
        }}
        QLabel#SectionLabel {{
            color: {TEXT_MUTE};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.4px;
        }}
        QLabel#StatValue {{
            color: {TEXT};
            font-size: 20px;
            font-weight: 600;
        }}
        /* One height for every single-line control, so a row of mixed inputs
           and buttons sits on a line instead of stepping. */
        /* One control height, enforced. Qt stylesheet min/max-height apply to
           the *content* box, so each rule subtracts its own padding and border
           to land on the same 44px total. Left to their natural size hints
           these came out at 48 / 46 / 53 — and a QSpinBox three pixels taller
           than the QLineEdit beside it drops its whole field below the row. */
        QLineEdit, QPushButton {{ min-height: 28px; max-height: 28px; }}
        QComboBox {{ min-height: 30px; max-height: 30px; }}
        QSpinBox, QDoubleSpinBox {{ min-height: 28px; max-height: 28px; }}

        /* ── Shell chrome ──────────────────────────────────────────── */
        /* Header and rails are one surface lifted off the page, separated by a
           hairline rather than a gap. Three floating panes with gutters between
           them read as three apps; one surface with divisions reads as one. */
        QFrame#AppHeader {{
            background-color: {SURFACE};
            border: none;
            border-bottom: 1px solid {BORDER};
        }}
        QFrame#RailLeft {{
            background-color: {SURFACE};
            border: none;
            border-right: 1px solid {BORDER};
        }}
        QFrame#RailRight {{
            background-color: {SURFACE};
            border: none;
            border-left: 1px solid {BORDER};
        }}
        /* Layout containers must not paint. The global QWidget background
           otherwise lands behind every helper container and stamps a page-
           coloured rectangle onto the rail surface. */
        QWidget#Transparent {{ background: transparent; }}

        QLabel#Wordmark {{
            color: {TEXT};
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 2.4px;
        }}
        QLabel#WordmarkDot {{ color: {ACCENT}; font-size: 11px; }}

        /* Navigation, not action: an underline marks the current mode. A pill
           here would compete with the buttons that actually spend money. */
        QPushButton#NavTab {{
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
            color: {TEXT_MUTE};
            font-weight: 550;
            padding: 0 2px;
            margin: 0 10px;
        }}
        QPushButton#NavTab:hover {{ color: {TEXT_DIM}; }}
        QPushButton#NavTab:checked {{
            color: {TEXT};
            border-bottom: 2px solid {ACCENT};
            font-weight: 650;
        }}

        /* Opens a window, changes nothing. Reads as a link. */
        QPushButton#QuietAction {{
            background: transparent;
            border: none;
            border-radius: 0;
            color: {TEXT_DIM};
            font-weight: 500;
            padding: 0 8px;
            text-align: left;
        }}
        QPushButton#QuietAction:hover {{ color: {TEXT}; }}
        QPushButton#QuietAction:disabled {{ color: {TEXT_MUTE}; }}

        QProgressBar#BudgetBar {{
            background-color: rgba(255, 255, 255, 0.07);
            border: none;
            border-radius: 3px;
            min-height: 5px;
            max-height: 5px;
        }}
        QProgressBar#BudgetBar::chunk {{
            background-color: {ACCENT_DIM};
            border-radius: 3px;
        }}
        /* Over the cap is a state, not a decoration — the one place a budget
           bar is allowed to change colour. */
        QProgressBar#BudgetBar[over="true"]::chunk {{ background-color: {DANGER}; }}

        /* The project rail: a list, not a boxed widget inside a boxed panel. */
        QFrame#RailLeft QListWidget {{
            background: transparent;
            border: none;
            font-size: 13px;
            color: {TEXT_DIM};
        }}
        QFrame#RailLeft QListWidget::item {{
            padding: 7px 8px;
            border-radius: {RADIUS_SM};
        }}
        QFrame#RailLeft QListWidget::item:hover {{ background-color: {ELEVATED}; }}
        QFrame#RailLeft QListWidget::item:selected {{
            background-color: {ACCENT_WASH};
            color: {ACCENT};
        }}
"""
