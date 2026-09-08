"""
Imprint — audiobook library and player
======================================
Type: Unit tests for the library scan, resume bookkeeping and the player.

Two bugs found by actually playing a file rather than reasoning about the code,
both of which silently defeated the resume feature. Each has a test here:

* `stop()` saved the position, then QMediaPlayer reset position to 0 and the
  resulting state change saved *again* — overwriting it. Every listen recorded
  0 and nothing ever resumed.
* the resume seek was applied on `durationChanged`, which arrives before the
  media is seekable. The seek was accepted and then discarded, so playback
  started from the beginning while appearing to work.

Run with:  pytest tests/test_audiobook_player.py -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def library(tmp_path, monkeypatch):
    import services.database as database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    database.init_db()
    import services.audiobook_library as lib
    monkeypatch.setattr(lib, "get_connection", database.get_connection)
    return lib


# ── Scanning ─────────────────────────────────────────────────────────────────
def test_missing_folder_is_not_an_error(library, tmp_path):
    assert library.scan(tmp_path / "nope") == []


def test_only_audio_files_are_listed(library, tmp_path):
    (tmp_path / "book.mp3").write_bytes(b"x")
    (tmp_path / "cover.jpg").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    assert [b.path.name for b in library.scan(tmp_path)] == ["book.mp3"]


def test_scan_is_recursive(library, tmp_path):
    """The converter can be pointed at a per-book subfolder."""
    nested = tmp_path / "Some Book"
    nested.mkdir()
    (nested / "full.m4b").write_bytes(b"x")
    assert len(library.scan(tmp_path)) == 1


def test_underscores_become_spaces_in_the_title(library, tmp_path):
    (tmp_path / "The_Long_Road.mp3").write_bytes(b"x")
    assert library.scan(tmp_path)[0].title == "The Long Road"


# ── Resume bookkeeping ───────────────────────────────────────────────────────
def test_position_round_trips(library, tmp_path):
    path = tmp_path / "b.mp3"
    path.write_bytes(b"x")
    library.save_position(path, 42_000, 600_000, "B")
    assert library.load_position(path) == 42_000


def test_a_finished_book_resumes_from_the_start(library, tmp_path):
    """Otherwise it resumes three seconds from the end and stops immediately."""
    path = tmp_path / "b.mp3"
    path.write_bytes(b"x")
    library.save_position(path, 599_000, 600_000, "B")
    assert library.load_position(path) == 0
    assert library.scan(tmp_path)[0].finished


def test_start_over_clears_the_finished_flag(library, tmp_path):
    path = tmp_path / "b.mp3"
    path.write_bytes(b"x")
    library.save_position(path, 600_000, 600_000, "B")
    library.mark_unfinished(path)
    assert not library.scan(tmp_path)[0].finished


def test_progress_survives_a_rescan(library, tmp_path):
    path = tmp_path / "b.mp3"
    path.write_bytes(b"x")
    library.save_position(path, 30_000, 120_000, "B")
    book = library.scan(tmp_path)[0]
    assert book.position_ms == 30_000
    assert book.progress == pytest.approx(0.25)
    assert book.started


def test_duration_is_not_erased_by_a_later_save(library, tmp_path):
    """The player reports duration 0 until the media loads; a save at that
    moment must not wipe a known length."""
    path = tmp_path / "b.mp3"
    path.write_bytes(b"x")
    library.save_position(path, 1_000, 120_000, "B")
    library.save_position(path, 2_000, 0, "B")
    assert library.scan(tmp_path)[0].duration_ms == 120_000


@pytest.mark.parametrize("ms,expected", [
    (0, "0:00"), (5_000, "0:05"), (65_000, "1:05"),
    (3_600_000, "1:00:00"), (3_725_000, "1:02:05"),
])
def test_time_formatting(library, ms, expected):
    assert library.format_time(ms) == expected


# ── Player ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def audio_file(tmp_path_factory):
    """A real 6-second MP3. Resume cannot be tested against a fake file."""
    if not shutil_which("ffmpeg"):
        pytest.skip("ffmpeg not available")
    path = tmp_path_factory.mktemp("audio") / "test.mp3"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=220:duration=6",
         "-q:a", "9", str(path), "-y"],
        capture_output=True, timeout=60)
    if not path.exists():
        pytest.skip("ffmpeg could not produce a test file")
    return path


def shutil_which(name):
    import shutil
    return shutil.which(name)


def _wait(ms):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_stopping_does_not_overwrite_the_saved_position(app, audio_file,
                                                        library, monkeypatch):
    """The bug that defeated the whole feature: stop() saved the real position,
    then QMediaPlayer reset to 0 and the state change saved over it."""
    import ui.audio_player as player_module
    monkeypatch.setattr(player_module, "save_position", library.save_position)

    player = player_module.AudiobookPlayer()
    player.load(audio_file, title="T", resume_ms=0)
    player.play()
    _wait(2500)
    player.stop()

    assert library.load_position(audio_file) > 500, \
        "position was overwritten with 0 on stop"


def test_a_reopened_player_resumes_where_it_stopped(app, audio_file,
                                                    library, monkeypatch):
    """The second bug: the seek was applied before the media was seekable, so
    it looked applied and played from the beginning anyway."""
    import ui.audio_player as player_module
    monkeypatch.setattr(player_module, "save_position", library.save_position)

    first = player_module.AudiobookPlayer()
    first.load(audio_file, title="T", resume_ms=0)
    first.play()
    _wait(2500)
    first.stop()
    saved = library.load_position(audio_file)
    assert saved > 500

    second = player_module.AudiobookPlayer()
    second.load(audio_file, title="T", resume_ms=saved)
    second.play()
    _wait(1500)
    assert second._player.position() >= saved, "did not resume"
    second.stop()


def test_saving_with_nothing_loaded_is_harmless(app, library, monkeypatch):
    import ui.audio_player as player_module
    monkeypatch.setattr(player_module, "save_position", library.save_position)
    player_module.AudiobookPlayer().save_now()


def test_controls_are_disabled_until_something_is_loaded(app):
    from ui.audio_player import AudiobookPlayer
    assert not AudiobookPlayer().play_btn.isEnabled()
