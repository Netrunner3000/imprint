"""Test-wide setup that has to happen before anything imports Qt.

## Why this file exists

Seven test modules each called `os.environ.setdefault("QT_QPA_PLATFORM",
"offscreen")` — but inside a fixture, which runs long after pytest has imported
every test module. If any of those imports reached Qt first (importing `main`
does), Qt had already chosen its platform plugin, and `setdefault` then did
nothing at all.

Whether that mattered came down to import order, which is why it worked almost
every time. When it did not, the suite ran on the native **cocoa** platform: it
tried to build real windows on the display, and wedged. One run sat there for
57 minutes inside `QComboBox::addItems` -> `endInsertRows` -> `setCurrentIndex`,
having produced no output and burned 8 seconds of CPU — blocked on a lock, not
looping, so nothing looked wrong except that it never finished.

A conftest is imported before any test module, so setting it here makes the
offscreen platform unconditional rather than a race. The per-file calls can
stay; they are harmless no-ops now, and they document the requirement where a
reader of that file will see it.

## The other thing this guards

`QT_QPA_PLATFORM` is only honoured if it is set *before* the first Qt import.
Nothing here may import PySide6 at module level, and nothing may import `main`.
Keep this file Qt-free.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Every test module repeats this; doing it here means a new one does not have to
# remember, and an import of `main` resolves the same way from any directory.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# setdefault, not assignment: a caller who deliberately asked for another
# platform (debugging a layout on a real screen, say) keeps it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Qt otherwise writes a "Populating font family aliases took N ms" warning on
# every run because the offscreen platform has no Sans Serif. Harmless, but it
# buries real output.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")
