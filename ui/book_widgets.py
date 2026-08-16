"""
Shared widget factories for the book pipeline panels.

The Quote Graphics, Shorts, Quote Finder and Calendar tabs all offer the same
theme / voice / attribution controls. These factories keep those options defined
once, so adding a theme or a voice source doesn't mean editing four places.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLineEdit

from providers.voice.registry import VOICE_SOURCES, list_voices_for_source
from services.quote_graphics import THEMES

# Display order for the theme dropdown; values map to services.quote_graphics.THEMES keys.
THEME_LABELS = [name.capitalize() for name in THEMES]

SIZE_SQUARE = "Square (1080×1080)"
SIZE_VERTICAL = "Story / Reel / Pin (1080×1920)"
SIZE_LABELS = [SIZE_SQUARE, SIZE_VERTICAL]


def make_theme_box() -> QComboBox:
    """Dropdown of quote-graphic themes."""
    box = QComboBox()
    box.addItems(THEME_LABELS)
    return box


def theme_key(box: QComboBox) -> str:
    """The services.quote_graphics theme key for the current selection."""
    return box.currentText().lower()


def make_size_box() -> QComboBox:
    """Dropdown of quote-graphic output sizes."""
    box = QComboBox()
    box.addItems(SIZE_LABELS)
    return box


def size_key(box: QComboBox) -> str:
    """'square' or 'vertical' for the current selection."""
    return "square" if box.currentText() == SIZE_SQUARE else "vertical"


def make_voice_source_box() -> QComboBox:
    """Dropdown choosing between free system TTS and ElevenLabs."""
    box = QComboBox()
    box.addItems(VOICE_SOURCES)
    return box


def make_attribution_input(placeholder: str = "Your book title") -> QLineEdit:
    """Optional attribution line rendered under a quote."""
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    return field


def populate_voice_box(voice_box: QComboBox, source: str) -> None:
    """Refill `voice_box` with the voices available for `source`.

    Stores the voice id as item data, so callers read it with `currentData()`.
    """
    voice_box.clear()
    for name, voice_id in list_voices_for_source(source):
        voice_box.addItem(name, voice_id)


def unique_output_path(directory, stem: str, suffix: str):
    """A timestamped path under `directory` that does not already exist.

    Millisecond timestamps alone still collide when several assets are generated
    in a tight loop (e.g. clicking through Calendar rows), which silently
    overwrote earlier files — so append a counter until the name is free.
    """
    import time
    from pathlib import Path

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    candidate = directory / f"{stem}_{ts}{suffix}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{ts}_{n}{suffix}"
        n += 1
    return candidate
