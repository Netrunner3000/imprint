"""Regenerate the Learning Centre screenshots.

    .venv/bin/python scripts/make_learning_shots.py

Runs the real window offscreen and grabs each panel, so the images in
`docs/learn/img/` are produced by the current code rather than pasted in and
left to rot. Re-run it after any UI change and commit whatever moves.

Offscreen on purpose: no display needed, so it works over SSH and in CI, and
the output is deterministic rather than depending on the machine's window
manager. `QMessageBox` is stubbed for the same reason a test stubs it — the
Audiobooks panel opens a modal when its input folder holds no ebooks, and a
modal with nobody to click it blocks forever.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

OUT_DIR = PROJECT_ROOT / "docs" / "learn" / "img"

# Wide enough that nothing is scrolled out of frame, which is what a reader
# needs from a reference screenshot.
WINDOW = (1760, 1080)

# (filename, agent key, optional setup callable)
SHOTS: list[tuple[str, str, object]] = [
    ("workspace-draft.png", "author", None),
    ("workspace-publish.png", "author",
     lambda w: (w._author_set_mode("pubmkt"), w._author_set_sub_mode("publish"))),
    ("workspace-market.png", "author",
     lambda w: (w._author_set_mode("pubmkt"), w._author_set_sub_mode("market"))),
    ("agent-manuscript.png", "manuscript", None),
    ("agent-music.png", "music", None),
    ("agent-webdesign.png", "webdesign", None),
    ("agent-fiverr.png", "fiverr", None),
]


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    import main as app_main

    saved = (QMessageBox.warning, QMessageBox.question, QMessageBox.information)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)

    try:
        app = QApplication.instance() or QApplication([])
        window = app_main.GodAI()
        window.show()
        _settle(app)
        window.resize(*WINDOW)
        _settle(app)

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for filename, agent, setup in SHOTS:
            window.select_agent(agent)
            _settle(app)
            if setup is not None:
                setup(window)
                _settle(app)
            path = OUT_DIR / filename
            window.grab().save(str(path))
            print(f"  wrote {path.relative_to(PROJECT_ROOT)}")
    finally:
        QMessageBox.warning, QMessageBox.question, QMessageBox.information = saved

    print(f"\n{len(SHOTS)} screenshots written to {OUT_DIR.relative_to(PROJECT_ROOT)}")
    return 0


def _settle(app, rounds: int = 8) -> None:
    """Let Qt finish laying out before grabbing — a grab taken too early
    catches widgets at their pre-layout geometry."""
    for _ in range(rounds):
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
