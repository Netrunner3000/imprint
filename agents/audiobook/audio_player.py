"""An audiobook player that remembers where you stopped.

A self-contained widget over `QMediaPlayer`. The app could convert a book and
then had no way to play it; this closes that.

Three details do most of the work:

* **Resume is applied after the media loads, not when it is set.** Seeking a
  player that has not finished loading is silently ignored, so the position is
  applied once `duration` first becomes non-zero — which is the earliest moment
  a seek will actually take.
* **Position is saved on a timer, not only on stop.** People close laptops and
  quit apps; a resume that only survives a clean exit is not a resume.
* **A book played to the end is marked finished** rather than parked at the last
  second, so the next play starts from the beginning instead of resuming and
  immediately stopping.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLabel, QMenu, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from agents.audiobook.audiobook_library import (
    delete_mark, embedded_chapters, format_time, save_mark, saved_marks,
    save_position,
)
from ui.widgets import FlowLayout

# How often the playhead is persisted. Frequent enough that a crash costs
# seconds, rare enough that it is not writing to sqlite constantly.
SAVE_INTERVAL_MS = 5000

SKIP_MS = 30_000
SPEEDS = ("0.75×", "1.0×", "1.25×", "1.5×", "1.75×", "2.0×")


class AudiobookPlayer(QWidget):
    """Transport, scrubber and speed for one audio file."""

    position_saved = Signal(int)          # ms, for the library to refresh

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: Path | None = None
        self._title = ""
        self._resume_ms = 0
        self._resume_applied = True

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(0.9)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.now_playing = QLabel("Nothing loaded")
        self.now_playing.setObjectName("NowPlaying")
        self.now_playing.setWordWrap(True)
        layout.addWidget(self.now_playing)

        scrub_row = QHBoxLayout()
        self.elapsed_label = QLabel("0:00")
        scrub_row.addWidget(self.elapsed_label)
        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 0)
        self.scrubber.sliderMoved.connect(self._on_scrub)
        scrub_row.addWidget(self.scrubber, 1)
        self.total_label = QLabel("0:00")
        scrub_row.addWidget(self.total_label)
        layout.addLayout(scrub_row)

        controls = QHBoxLayout()
        self.back_btn = QPushButton("−30s")
        self.back_btn.clicked.connect(lambda: self.skip(-SKIP_MS))
        controls.addWidget(self.back_btn)

        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setObjectName("PrimaryAction")
        self.play_btn.clicked.connect(self.toggle)
        controls.addWidget(self.play_btn)

        self.forward_btn = QPushButton("+30s")
        self.forward_btn.clicked.connect(lambda: self.skip(SKIP_MS))
        controls.addWidget(self.forward_btn)
        controls.addStretch()
        layout.addLayout(controls)

        options = QWidget()
        options.setObjectName("Transparent")
        option_row = FlowLayout(options, spacing=8)

        self.chapters_btn = QPushButton("Chapters & marks")
        self.chapters_btn.setToolTip(
            "Jump to embedded chapters or to a mark you saved while listening.")
        self.chapters_btn.clicked.connect(self.show_chapters)
        option_row.addWidget(self.chapters_btn)

        self.mark_btn = QPushButton("Add mark")
        self.mark_btn.clicked.connect(self.add_mark)
        option_row.addWidget(self.mark_btn)

        option_row.addWidget(QLabel("Speed:"))
        self.speed_box = QComboBox()
        self.speed_box.addItems(SPEEDS)
        self.speed_box.setCurrentText("1.0×")
        self.speed_box.currentTextChanged.connect(self._on_speed)
        option_row.addWidget(self.speed_box)
        option_row.addWidget(QLabel("Sleep:"))
        self.sleep_box = QComboBox()
        for label, minutes in (("Off", 0), ("15 min", 15), ("30 min", 30),
                               ("45 min", 45), ("60 min", 60)):
            self.sleep_box.addItem(label, minutes)
        self.sleep_box.setToolTip("Pause playback after this many minutes.")
        self.sleep_box.currentIndexChanged.connect(self._on_sleep_changed)
        option_row.addWidget(self.sleep_box)
        layout.addWidget(options)

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        # The seek has to wait for the media to be loaded. durationChanged
        # arrives first but the player is not seekable yet, so a setPosition
        # there is accepted and then quietly discarded when playback starts.
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # Saving only on stop would lose the position whenever the app is
        # closed the way people actually close apps.
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(SAVE_INTERVAL_MS)
        self._save_timer.timeout.connect(self.save_now)

        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._on_sleep_expired)

        for key, callback in ((Qt.Key.Key_Space, self.toggle),
                              (Qt.Key.Key_Left, lambda: self.skip(-SKIP_MS)),
                              (Qt.Key.Key_Right, lambda: self.skip(SKIP_MS))):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)

        self.set_enabled(False)

    # ── public API ──────────────────────────────────────────────────────
    def set_enabled(self, enabled: bool) -> None:
        for widget in (self.play_btn, self.back_btn, self.forward_btn,
                       self.scrubber, self.speed_box, self.chapters_btn,
                       self.mark_btn, self.sleep_box):
            widget.setEnabled(enabled)

    def load(self, path: Path, title: str = "", resume_ms: int = 0) -> None:
        """Load a file and arm its resume position."""
        self.save_now()
        self._sleep_timer.stop()
        self.sleep_box.setCurrentIndex(0)
        self._path = Path(path)
        self._title = title or self._path.stem
        self._resume_ms = max(0, int(resume_ms))
        # Applied on the first duration change: seeking before the media has
        # loaded is silently dropped.
        self._resume_applied = self._resume_ms == 0

        self._player.setSource(QUrl.fromLocalFile(str(self._path)))
        self.now_playing.setText(self._title)
        self.set_enabled(True)
        self.elapsed_label.setText(format_time(self._resume_ms))

    def play(self) -> None:
        if self._path:
            self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self.save_now()
        self._sleep_timer.stop()
        self.sleep_box.setCurrentIndex(0)
        self._player.stop()

    def add_mark(self) -> None:
        if not self._path:
            return
        position = self._player.position()
        title, accepted = QInputDialog.getText(
            self, "Save listening mark", "Mark name:",
            text=f"Mark at {format_time(position)}")
        if accepted and title.strip():
            save_mark(self._path, position, title)

    def show_chapters(self) -> None:
        if not self._path:
            return
        menu = QMenu(self)
        embedded = embedded_chapters(self._path)
        marks = saved_marks(self._path)
        if embedded:
            menu.addSection("Embedded chapters")
            for chapter in embedded:
                action = menu.addAction(
                    f"{format_time(chapter.position_ms)}  {chapter.title}")
                action.triggered.connect(
                    lambda _checked=False, position=chapter.position_ms:
                    self._player.setPosition(position))
        if marks:
            menu.addSection("Your marks")
            for mark in marks:
                action = menu.addAction(
                    f"{format_time(mark.position_ms)}  {mark.title}")
                action.triggered.connect(
                    lambda _checked=False, position=mark.position_ms:
                    self._player.setPosition(position))
            remove_menu = menu.addMenu("Remove a mark")
            for mark in marks:
                action = remove_menu.addAction(mark.title)
                action.triggered.connect(
                    lambda _checked=False, position=mark.position_ms:
                    delete_mark(self._path, position))
        if not embedded and not marks:
            action = menu.addAction("No chapters in this file yet — use Add mark")
            action.setEnabled(False)
        menu.exec(self.chapters_btn.mapToGlobal(self.chapters_btn.rect().bottomLeft()))

    def _on_sleep_changed(self, _index: int) -> None:
        self._sleep_timer.stop()
        if not self._path:
            return
        minutes = int(self.sleep_box.currentData() or 0)
        if minutes:
            self._sleep_timer.start(minutes * 60_000)

    def _on_sleep_expired(self) -> None:
        self.pause()
        self.save_now()
        self.sleep_box.setCurrentIndex(0)

    def skip(self, delta_ms: int) -> None:
        if not self._path:
            return
        target = max(0, self._player.position() + delta_ms)
        duration = self._player.duration()
        if duration:
            target = min(target, duration)
        self._player.setPosition(target)

    def save_now(self) -> None:
        """Persist the playhead. Safe to call when nothing is loaded."""
        if not self._path:
            return
        position = self._player.position()
        duration = self._player.duration()
        # Never persist a zero. Two different things report position 0 and
        # neither means "the listener is at the start":
        #
        #   * a player that has not finished loading yet, and
        #   * a player that has just been stopped — QMediaPlayer resets the
        #     position to 0 on stop, and the resulting state change calls back
        #     in here, which would overwrite the position stop() just saved.
        #
        # The second one silently defeated the whole feature: every listen
        # saved 0 and nothing ever resumed. Starting over is an explicit
        # action (mark_unfinished), so refusing to write 0 costs nothing.
        if position <= 0:
            return
        save_position(self._path, position, duration, self._title)
        self.position_saved.emit(position)

    # ── signals ─────────────────────────────────────────────────────────
    def _on_duration(self, duration_ms: int) -> None:
        self.scrubber.setRange(0, duration_ms)
        self.total_label.setText(format_time(duration_ms))
        self._apply_resume()

    def _on_media_status(self, status) -> None:
        """Seek once the media is genuinely ready.

        LoadedMedia is the first status at which a seek sticks; trying earlier
        looks like it worked and then plays from the beginning anyway.
        """
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self._apply_resume()

    def _apply_resume(self) -> None:
        if self._resume_applied or not self._resume_ms:
            return
        if not self._player.isSeekable():
            return
        duration = self._player.duration()
        target = min(self._resume_ms, duration) if duration else self._resume_ms
        self._player.setPosition(target)
        self._resume_applied = True

    def _on_position(self, position_ms: int) -> None:
        if not self.scrubber.isSliderDown():
            self.scrubber.setValue(position_ms)
        self.elapsed_label.setText(format_time(position_ms))

    def _on_scrub(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)

    def _on_speed(self, label: str) -> None:
        try:
            self._player.setPlaybackRate(float(label.rstrip("×")))
        except ValueError:
            pass

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.play_btn.setText("⏸  Pause" if playing else "▶  Play")
        if playing:
            self._save_timer.start()
        else:
            self._save_timer.stop()
            self.save_now()
