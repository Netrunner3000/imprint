"""User-assisted Suno handoff; no private API or browser automation."""
import json
import shutil
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QPushButton, QSpinBox, QComboBox, QListWidget,
    QFileDialog, QMessageBox, QApplication)

from services.runtime_paths import user_data_base
from ui.workers import ChatWorker


class SunoPanel(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.root = user_data_base() / "data" / "music_library"
        self.current = None
        self.worker = None
        layout = QVBoxLayout(self)
        note = QLabel("Prepare lyrics and song prompts here, create audio in Suno, then import your downloads. "
                      "Suno generation and billing happen in your Suno account.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.albums = QComboBox()
        layout.addWidget(self.albums)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Song or album title")
        layout.addWidget(self.title)
        self.count = QSpinBox()
        self.count.setRange(1, 20)
        self.count.setPrefix("Tracks: ")
        layout.addWidget(self.count)
        self.brief = QTextEdit()
        self.brief.setPlaceholderText("Album concept, mood, instruments, language, vocals or instrumental, and lyrical direction")
        self.brief.setMaximumHeight(100)
        layout.addWidget(self.brief)
        self.output = QTextEdit()
        self.output.setPlaceholderText("Editable lyrics, style prompts, and track sequence")
        layout.addWidget(self.output)
        self.generate = QPushButton("Draft songs & Suno prompts")
        self.generate.clicked.connect(self.draft)
        layout.addWidget(self.generate)
        row = QHBoxLayout()
        for label, action in [("New", self.new), ("Save", self.save),
                              ("Copy selected / all", self.copy), ("Open Suno", self.open_suno)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        self.tracks = QListWidget()
        self.tracks.setMaximumHeight(130)
        self.tracks.itemDoubleClicked.connect(self.play)
        layout.addWidget(self.tracks)
        row = QHBoxLayout()
        for label, action in [("Import audio", self.import_audio), ("Move up", lambda: self.move(-1)),
                              ("Move down", lambda: self.move(1)), ("Open album folder", self.open_folder)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        self.status = QLabel("Double-click an imported track to listen in your audio player.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.albums.activated.connect(self.load)
        self.refresh()

    def refresh(self):
        self.albums.clear()
        self.albums.addItem("Choose a saved song / album", None)
        if self.root.exists():
            for path in sorted(self.root.glob("*/album.json")):
                try:
                    data = json.loads(path.read_text())
                    self.albums.addItem(data["title"], str(path.parent))
                except (OSError, ValueError, KeyError):
                    continue

    def new(self):
        if self.title.text().strip() and not self.save():
            return
        self.current = None
        self.title.clear()
        self.brief.clear()
        self.output.clear()
        self.tracks.clear()
        self.count.setValue(1)
        self.albums.setCurrentIndex(0)

    def save(self):
        if not self.title.text().strip():
            self.status.setText("Enter a song or album title first.")
            return False
        try:
            if self.current is None:
                self.current = self.root / uuid4().hex
            self.current.mkdir(parents=True, exist_ok=True)
            data = dict(title=self.title.text().strip(), brief=self.brief.toPlainText(),
                        count=self.count.value(), prompts=self.output.toPlainText(),
                        tracks=[self.tracks.item(i).text() for i in range(self.tracks.count())])
            temporary = self.current / "album.json.tmp"
            temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temporary.replace(self.current / "album.json")
            self.refresh()
            self.albums.setCurrentIndex(self.albums.findData(str(self.current)))
            self.status.setText("Saved locally.")
            return True
        except OSError as error:
            self.status.setText(f"Could not save: {error}")
            return False

    def load(self):
        path = self.albums.currentData()
        if not path:
            return
        if self.title.text().strip() and not self.save():
            return
        try:
            data = json.loads((Path(path) / "album.json").read_text())
            self.current = Path(path)
            self.title.setText(data["title"])
            self.brief.setPlainText(data["brief"])
            self.output.setPlainText(data["prompts"])
            self.count.setValue(data["count"])
            self.tracks.clear()
            self.tracks.addItems(data["tracks"])
            self.albums.setCurrentIndex(self.albums.findData(path))
        except (OSError, ValueError, KeyError) as error:
            self.status.setText(f"Could not open album: {error}")

    def copy(self):
        QApplication.clipboard().setText(self.output.textCursor().selectedText().replace("\u2029", "\n")
                                        or self.output.toPlainText())

    def open_suno(self):
        QDesktopServices.openUrl(QUrl("https://suno.com/create"))

    def open_folder(self):
        if self.save():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current)))

    def import_audio(self):
        if not self.save():
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Import downloaded songs", "",
                                               "Audio (*.mp3 *.wav *.m4a *.flac *.ogg *.aac)")
        for filename in files:
            source = Path(filename)
            target = self.current / source.name
            if target.exists():
                target = self.current / f"{source.stem}-{uuid4().hex[:8]}{source.suffix}"
            try:
                shutil.copy2(source, target)
                self.tracks.addItem(target.name)
            except OSError as error:
                QMessageBox.warning(self, "Import failed", str(error))
        self.save()

    def play(self, item):
        if self.current and Path(item.text()).name == item.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current / item.text())))

    def move(self, delta):
        index = self.tracks.currentRow()
        destination = index + delta
        if index >= 0 and 0 <= destination < self.tracks.count():
            self.tracks.insertItem(destination, self.tracks.takeItem(index))
            self.tracks.setCurrentRow(destination)
            self.save()

    def draft(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.brief.toPlainText().strip() or not self.save():
            self.status.setText("Enter a title and a creative brief first.")
            return
        host = self.host
        if host.music_worker and host.music_worker.isRunning():
            self.status.setText("Wait for the current music plan to finish.")
            return
        provider = host.music_provider_box.currentText()
        model = host.music_model_box.currentText()
        prompt = (f"Create {self.count.value()} original songs for {self.title.text()}. "
                  f"Artist: {host.music_artist_input.text()}. Genre: {host.music_genre_box.currentText()}. "
                  f"Brief: {self.brief.toPlainText()}")
        if not model or not host.authorize_request("music", provider, model, prompt):
            return
        system = ("Draft a coherent song or album package for manual creation in Suno. "
                  "For each numbered track give a title, a short distinct style prompt, and complete original "
                  "lyrics with verse/chorus/bridge labels, or an instrumental arrangement if requested. "
                  "Include track order and a consistent album direction. Do not claim audio was generated. "
                  "Finish with simple instructions to paste each track into Suno, review variants, download "
                  "per the user's account permissions, and import audio into Imprint. Do not invent API access.")
        self.output.clear()
        self.generate.setEnabled(False)
        self.setEnabled(False)
        host.music_analyse_btn.setEnabled(False)
        self.worker = ChatWorker(host.run_backend, provider, model,
                                 [{"role": "system", "content": system},
                                  {"role": "user", "content": prompt}], prompt)
        host.music_worker = self.worker
        self.worker.usage_signal.connect(lambda usage: host.note_request_usage("music", usage))
        self.worker.finished_signal.connect(self.complete)
        self.worker.error_signal.connect(self.failed)
        self.status.setText("Drafting lyrics and prompts…")
        self.worker.start()

    def complete(self, text):
        self.setEnabled(True)
        self.host.record_request("music", text)
        self.output.setPlainText(text)
        self.save()
        self.generate.setEnabled(True)
        self.host.music_analyse_btn.setEnabled(True)

    def failed(self, error):
        self.setEnabled(True)
        self.host.abandon_request("music")
        self.status.setText(error)
        self.generate.setEnabled(True)
        self.host.music_analyse_btn.setEnabled(True)
