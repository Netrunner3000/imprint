"""Video workspace and its guarded render lifecycles.

Phase 4 extraction: the Render and Library tabs and every handler moved
here from main.py. The pipeline itself stays where it was — vidforge,
reached through ``agents.video.studio`` — and the host still supplies the
shared budget guard, the provider clients and the worker attributes its
global shutdown sweep watches. Request tokens live on this panel: "video"
is also authorized by the Social clip flow, so nothing here resolves a
request by agent name.

A checkout of imprint alone has no vidforge; the panel then builds a
notice instead of a form, aliases nothing onto the host, and every public
method is a no-op.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QProgressBar, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from services.higgsfield_client import HiggsfieldClient
from ui.forms import LG, MD, SM, combo, field, line_edit, primary, quiet, section
from ui.widgets import scrollable


class VideoPanel(QWidget):
    """Topic in, finished video out — vidforge driven in-process."""

    HOST_CONTROLS = (
        "video_tabs", "video_topic_input", "video_format_box",
        "video_aspect_box", "video_length_box", "video_visual_provider_box",
        "video_visual_model_box", "video_aspect_field", "video_length_field",
        "video_visual_note", "video_render_btn", "video_folder_btn",
        "video_stop_btn", "video_cost_label", "video_progress",
        "video_status_label", "video_log", "video_library_table",
        "video_play_btn", "video_reveal_btn", "video_refresh_btn",
    )

    def __init__(self, host):
        super().__init__()
        from agents.video import video_studio
        from services.media_catalog import MEDIA_PROVIDERS

        self.host = host
        self._request_token = None
        self._external_context: dict = {}
        self._active_kind = ""
        self._available = video_studio.available()
        self.setObjectName("VideoPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # A checkout of imprint alone has no vidforge. Explain that in place
        # of a form that cannot work, rather than failing on the first click.
        if not self._available:
            notice = QLabel(video_studio.unavailable_reason())
            notice.setObjectName("EstimateLine")
            notice.setWordWrap(True)
            notice.setAlignment(Qt.AlignTop)
            outer.addWidget(notice)
            outer.addStretch()
            host.video_panel = self
            self.hide()
            return

        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        self.video_tabs = QTabWidget()

        # ── Render tab ──────────────────────────────────────────────────
        render_page = QWidget()
        render_page.setObjectName("Transparent")
        render = QVBoxLayout(render_page)
        render.setContentsMargins(MD, MD, MD, MD)
        render.setSpacing(LG)

        render.addWidget(section("Brief"))

        self.video_topic_input = line_edit(
            "Leave empty to take the next topic from topics.txt")
        self.video_format_box = combo(["Long-form", "Social clip"])
        self.video_format_box.currentTextChanged.connect(self._format_changed)
        self.video_aspect_box = combo(list(video_studio.ASPECTS),
                                      video_studio.DEFAULT_ASPECT)
        self.video_aspect_box.currentTextChanged.connect(self.update_estimate)
        self.video_length_box = combo([f"{n}s" for n in video_studio.CLIP_SECONDS],
                                      "30s")
        self.video_length_box.currentTextChanged.connect(self.update_estimate)

        self.video_visual_provider_box = combo(list(MEDIA_PROVIDERS), "OpenAI")
        self.video_visual_model_box = QComboBox()
        self.video_visual_provider_box.currentTextChanged.connect(
            self._visual_provider_changed)
        self.video_visual_model_box.currentIndexChanged.connect(
            self._visual_model_changed)

        self.video_aspect_field = field("Aspect", self.video_aspect_box)
        self.video_length_field = field("Clip length", self.video_length_box)

        brief = QGridLayout()
        brief.setHorizontalSpacing(MD)
        brief.setVerticalSpacing(MD)
        brief.addWidget(field("Topic", self.video_topic_input), 0, 0, 1, 2, Qt.AlignTop)
        brief.addWidget(field("Format", self.video_format_box), 0, 2, Qt.AlignTop)
        brief.addWidget(field("Visual provider", self.video_visual_provider_box),
                        1, 0, Qt.AlignTop)
        brief.addWidget(field("Visual model", self.video_visual_model_box),
                        1, 1, 1, 2, Qt.AlignTop)
        brief.addWidget(self.video_aspect_field, 2, 0, Qt.AlignTop)
        brief.addWidget(self.video_length_field, 2, 1, Qt.AlignTop)
        for column in range(3):
            brief.setColumnStretch(column, 1)
        render.addLayout(brief)

        self.video_visual_note = QLabel("")
        self.video_visual_note.setObjectName("EstimateLine")
        self.video_visual_note.setWordWrap(True)
        render.addWidget(self.video_visual_note)

        # ── Actions ─────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.video_render_btn = primary("Render Video")
        self.video_render_btn.setMinimumWidth(160)
        self.video_render_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.video_render_btn.clicked.connect(self.render)
        actions.addWidget(self.video_render_btn)

        self.video_folder_btn = QPushButton("Open Output Folder")
        self.video_folder_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(video_studio.output_root()))))
        actions.addWidget(self.video_folder_btn)

        self.video_stop_btn = QPushButton("Stop")
        self.video_stop_btn.setObjectName("DangerAction")
        self.video_stop_btn.clicked.connect(self.stop)
        self.video_stop_btn.hide()
        actions.addWidget(self.video_stop_btn)

        actions.addStretch()
        self.video_cost_label = QLabel("")
        self.video_cost_label.setObjectName("EstimateLine")
        actions.addWidget(self.video_cost_label)
        render.addLayout(actions)

        # ── Progress ────────────────────────────────────────────────────
        self.video_progress = QProgressBar()
        self.video_progress.setRange(0, 100)
        self.video_progress.setValue(0)
        self.video_progress.setTextVisible(True)
        render.addWidget(self.video_progress)

        self.video_status_label = QLabel("Idle")
        self.video_status_label.setObjectName("EstimateLine")
        self.video_status_label.setWordWrap(True)
        render.addWidget(self.video_status_label)

        self.video_log = QTextEdit()
        self.video_log.setReadOnly(True)
        self.video_log.setPlaceholderText(
            "The pipeline reports each stage here: script, narration, "
            "captions, visuals, clips, audio, assembly, thumbnail.")
        render.addWidget(self.video_log, 1)
        self.video_tabs.addTab(render_page, "Render")

        # ── Library tab ─────────────────────────────────────────────────
        # Reads vidforge's own history, so a render started in the standalone
        # app appears here and vice versa. One library, not two.
        library_page = QWidget()
        library_page.setObjectName("Transparent")
        lib = QVBoxLayout(library_page)
        lib.setContentsMargins(MD, MD, MD, MD)
        lib.setSpacing(MD)

        self.video_library_table = QTableWidget(0, 4)
        self.video_library_table.setHorizontalHeaderLabels(
            ["Title", "Created", "Length", "Status"])
        header = self.video_library_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.video_library_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.video_library_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.video_library_table.verticalHeader().setVisible(False)
        lib.addWidget(self.video_library_table, 1)

        lib_actions = QHBoxLayout()
        lib_actions.setSpacing(SM)
        lib_actions.addStretch()
        self.video_play_btn = QPushButton("Play")
        self.video_play_btn.clicked.connect(self.play_selected)
        lib_actions.addWidget(self.video_play_btn)
        self.video_reveal_btn = QPushButton("Show in Finder")
        self.video_reveal_btn.clicked.connect(self.reveal_selected)
        lib_actions.addWidget(self.video_reveal_btn)
        self.video_refresh_btn = quiet("Rescan")
        self.video_refresh_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.video_refresh_btn.clicked.connect(self.refresh_library)
        lib_actions.addWidget(self.video_refresh_btn)
        lib.addLayout(lib_actions)
        self.video_tabs.addTab(library_page, "Library")

        layout.addWidget(self.video_tabs, 1)

        # Shared recommendation and tooltip wiring still resolves these on
        # the host; ownership and lifecycle are local to this panel. The
        # workers stay host attributes so the global shutdown sweep sees them.
        for name in self.HOST_CONTROLS:
            setattr(host, name, getattr(self, name))
        host.video_panel = self
        host.video_worker = None
        host.video_estimate_worker = None
        self._visual_provider_changed(
            self.video_visual_provider_box.currentText())
        self._format_changed(self.video_format_box.currentText())
        self.hide()

    # ── selection and constraints ───────────────────────────────────────
    def _visual_provider_changed(self, provider: str):
        """List only media models that have a real execution path."""
        from services.media_catalog import MODELS

        self.video_visual_model_box.blockSignals(True)
        self.video_visual_model_box.clear()
        for option in MODELS:
            if option.provider == provider:
                self.video_visual_model_box.addItem(option.label, option)
        self.video_visual_model_box.blockSignals(False)
        self._visual_model_changed()

    def _media_selection(self):
        return self.video_visual_model_box.currentData()

    def _set_lengths(self, values: tuple[int, ...], preferred: int) -> None:
        current = self.video_length_box.currentText()
        wanted = current if current in {f"{n}s" for n in values} else f"{preferred}s"
        self.video_length_box.blockSignals(True)
        self.video_length_box.clear()
        self.video_length_box.addItems([f"{n}s" for n in values])
        self.video_length_box.setCurrentText(wanted)
        self.video_length_box.blockSignals(False)

    def _visual_model_changed(self, *_args):
        from agents.video import video_studio

        selection = self._media_selection()
        if selection is None:
            return
        direct = selection.kind == "direct_video"
        if direct:
            self.video_format_box.setCurrentText("Social clip")
            self.video_format_box.setEnabled(False)
            durations = selection.durations or (4, 8, 12)
            preferred = 8 if 8 in durations else durations[0]
            self._set_lengths(durations, preferred)
            if self.video_aspect_box.currentText() not in selection.aspects:
                wanted = ("Vertical 9:16" if "Vertical 9:16" in selection.aspects
                          else selection.aspects[0])
                self.video_aspect_box.setCurrentText(wanted)
        else:
            self.video_format_box.setEnabled(True)
            self._set_lengths(video_studio.CLIP_SECONDS, 30)

        if selection.provider == "OpenAI" and selection.kind == "scene_images":
            note = (
                f"{selection.note} One image is generated for each scene. "
                "DALL·E 2 and 3 are not listed because OpenAI retired and "
                "removed both APIs. Sora is no longer offered — its Videos "
                "API shuts down on 24 September 2026 with no successor; "
                "choose Gemini, Qwen or Higgsfield for direct video.")
        else:
            note = selection.note
        self.video_visual_note.setText(note)
        self._format_changed(self.video_format_box.currentText())

    def _format_changed(self, fmt: str):
        """Clip controls only apply to a clip."""
        is_clip = fmt == "Social clip"
        self.video_aspect_field.setVisible(is_clip)
        self.video_length_field.setVisible(is_clip)
        if is_clip and self.video_aspect_box.currentText() == "Landscape 16:9":
            self.video_aspect_box.setCurrentText("Vertical 9:16")
        self.update_estimate()

    # ── estimates ───────────────────────────────────────────────────────
    def _overrides(self) -> dict:
        from agents.video import video_studio
        selection = self._media_selection()
        overrides = {}
        if self.video_format_box.currentText() == "Social clip":
            seconds = int(self.video_length_box.currentText().rstrip("s") or 30)
            overrides.update(video_studio.clip_overrides(
                self.video_aspect_box.currentText(), seconds))
        if selection is not None:
            if selection.kind == "scene_images":
                overrides.update({
                    "visuals.source": "ai",
                    "visuals.image_model": selection.model_id,
                })
            elif selection.kind == "stock":
                overrides["visuals.source"] = "pexels"
            elif selection.kind == "local":
                overrides["visuals.source"] = "gradient"
        return overrides

    def _estimate(self) -> dict:
        from agents.video import video_studio
        from services.media_catalog import direct_video_cost_usd

        selection = self._media_selection()
        if (selection is not None and selection.kind == "direct_video"
                and selection.provider in {"OpenAI", "Gemini", "Qwen"}):
            seconds = int(self.video_length_box.currentText().rstrip("s") or 4)
            return {
                "scenes": 1, "words": 0,
                "total": direct_video_cost_usd(selection.model_id, seconds),
                "direct": True,
                "reserve": selection.model_id == "gemini-omni-1.1-flash",
            }
        if (selection is not None and selection.provider == "Higgsfield"
                and selection.kind == "direct_video"):
            return {"provider_estimate": True, "direct": True}
        try:
            cfg = video_studio.load_config(self._overrides())
        except Exception:
            return {}
        return video_studio.pre_estimate(cfg)

    def update_estimate(self, *_args):
        """What the run will cost, beside the button that starts it.

        A render is billed per image, per character of narration and per audio
        minute — none of which the token cost model can express. The number
        comes from vidforge's own per-stage arithmetic and is handed to the
        budget guard as a flat cost, so it counts against the caps rather than
        landing as €0.00.
        """
        from services.per_unit_pricing import eur_per_usd
        estimate = self._estimate()
        if not estimate:
            self.video_cost_label.setText("")
            return
        if estimate.get("provider_estimate"):
            self.video_cost_label.setText("Exact provider quote before approval")
            return
        eur = estimate["total"] * eur_per_usd()
        if estimate.get("direct"):
            prefix = "Budget reserve" if estimate.get("reserve") else "Direct clip"
            self.video_cost_label.setText(
                f"{prefix} · ${estimate['total']:.2f} · ≈ €{eur:.2f}")
        else:
            self.video_cost_label.setText(
                f"{estimate['scenes']} scenes · ~{estimate['words']} words · "
                f"budget reserve ≈ €{eur:.2f}")

    # ── rendering ───────────────────────────────────────────────────────
    def render(self):
        from agents.video import video_studio
        from services.per_unit_pricing import eur_per_usd
        from ui.workers import VideoWorker

        if self.host.video_worker is not None and self.host.video_worker.isRunning():
            return
        selection = self._media_selection()
        if selection is not None and selection.kind == "direct_video":
            self.render_direct(selection)
            return
        estimate = self._estimate()
        if not estimate:
            QMessageBox.warning(self, "Video Unavailable",
                                video_studio.unavailable_reason())
            return

        topic = self.video_topic_input.text().strip()
        cost_eur = round(estimate["total"] * eur_per_usd(), 4)
        # Keep the token: the Social clip flow also authorizes under
        # "video", and resolving by name pops whichever request is oldest.
        token = self.host.authorize_request(
            "video", "openai", "vidforge-pipeline",
            topic or "next topic from topics.txt",
            label=self.video_format_box.currentText().lower(),
            flat_cost_eur=cost_eur)
        if not token:
            return
        self._request_token = token

        self._begin("pipeline", can_cancel=True)

        worker = VideoWorker(topic=topic, overrides=self._overrides())
        self.host.video_worker = worker
        worker.stage_signal.connect(
            lambda _key, label: self.video_status_label.setText(f"{label}…"))
        worker.progress_signal.connect(self._on_progress)
        worker.log_signal.connect(self.video_log.append)
        worker.done_signal.connect(self._on_done)
        worker.error_signal.connect(self._on_error)
        worker.start()

    def _begin(self, kind: str, *, can_cancel: bool) -> None:
        self._active_kind = kind
        self.video_log.clear()
        self.video_progress.setValue(0)
        self.video_status_label.setText("Starting…")
        self.video_render_btn.setEnabled(False)
        self.video_stop_btn.setText(
            "Stop" if kind == "pipeline"
            else "Cancel" if can_cancel else "Cannot Cancel")
        self.video_stop_btn.setEnabled(can_cancel)
        self.video_stop_btn.show()

    def _direct_parameters(self) -> tuple[int, str]:
        seconds = int(self.video_length_box.currentText().rstrip("s") or 4)
        aspect = self.video_aspect_box.currentText()
        provider_aspect = {
            "Landscape 16:9": "16:9",
            "Vertical 9:16": "9:16",
            "Square 1:1": "1:1",
        }.get(aspect, "16:9")
        return seconds, provider_aspect

    def render_direct(self, selection) -> None:
        from agents.video import video_studio
        from ui.workers import HiggsfieldEstimateWorker, VideoGenerationWorker

        if selection.provider == "OpenAI":
            # Defensive: no OpenAI direct_video row exists in the catalog any
            # more, but a stale selection must still refuse cleanly.
            QMessageBox.warning(
                self, "Sora is being discontinued",
                "OpenAI is shutting the Sora Videos API down on 24 September "
                "2026 with no successor — Imprint no longer starts Sora jobs. "
                "Choose Gemini, Qwen or Higgsfield for direct video, or "
                "OpenAI GPT Image for a narrated scene-based video.")
            return

        topic = self.video_topic_input.text().strip()
        if not topic:
            QMessageBox.warning(
                self, "Topic Needed",
                "Direct video models need a prompt in the Topic field.")
            return
        seconds, provider_aspect = self._direct_parameters()
        self._external_context = {
            "slug": "", "path": "", "topic": topic,
            "provider": selection.provider.lower(), "model": selection.model_id,
            "seconds": seconds, "job_id": "", "provider_completed": False,
            "cancel_requested": False,
        }

        if selection.provider in {"Gemini", "Qwen"}:
            from services.media_catalog import direct_video_cost_usd
            from services.per_unit_pricing import eur_per_usd

            provider_key = selection.provider.lower()
            client = (self.host.gemini if selection.provider == "Gemini"
                      else self.host.qwen)
            checkbox = (self.host.allow_gemini_checkbox
                        if selection.provider == "Gemini"
                        else self.host.allow_qwen_checkbox)
            env_name = ("GOOGLE_API_KEY (or GEMINI_API_KEY)"
                        if selection.provider == "Gemini" else "DASHSCOPE_API_KEY")
            if not client.key_available():
                QMessageBox.information(
                    self, f"{selection.provider} Key Needed",
                    f"Set {env_name} in Imprint's private .env file.")
                return
            if not checkbox.isChecked():
                QMessageBox.warning(
                    self, f"{selection.provider} Not Enabled",
                    f"Enable {selection.provider} in the API permissions row first.")
                return
            cost_usd = direct_video_cost_usd(selection.model_id, seconds)
            token = self.host.authorize_request(
                "video", provider_key, selection.model_id, topic,
                label="direct video", flat_cost_eur=round(
                    cost_usd * eur_per_usd(), 6))
            if not token:
                return
            self._request_token = token
            try:
                slug, output_path = video_studio.external_output_path(
                    topic, selection.model_id)
            except Exception as exc:
                self._on_error(str(exc))
                return
            self._external_context.update({
                "slug": slug, "path": str(output_path),
            })
            active_kind = f"{provider_key}-video"
            self._begin(active_kind, can_cancel=False)
            self.video_status_label.setText(
                f"Submitting to {selection.provider}… The provider has no safe "
                "cancel operation after submission, so Imprint will preserve "
                "the result locally.")
            worker = VideoGenerationWorker(
                client, topic, output_path, provider=selection.provider,
                model=selection.model_id, seconds=seconds,
                aspect_ratio=provider_aspect)
            self.host.video_worker = worker
            worker.status_signal.connect(self.video_status_label.setText)
            worker.progress_signal.connect(self._on_progress)
            worker.job_signal.connect(self._external_job)
            worker.done_signal.connect(self._external_done)
            worker.error_signal.connect(self._on_error)
            worker.start()
            return

        if selection.provider == "Higgsfield":
            client = HiggsfieldClient()
            if not client.configured:
                QMessageBox.information(
                    self, "Higgsfield Key Needed",
                    "Set HF_API_KEY_ID and HF_API_KEY_SECRET in Imprint's "
                    "private .env file.")
                return
            if not self.host.allow_higgsfield_checkbox.isChecked():
                QMessageBox.warning(
                    self, "Higgsfield Not Enabled",
                    "Enable Higgsfield in the API permissions row first.")
                return
            self._begin("higgsfield-estimate", can_cancel=True)
            self.video_status_label.setText("Preparing Higgsfield estimate…")
            estimate_worker = HiggsfieldEstimateWorker(
                client, topic, duration=seconds,
                aspect_ratio=provider_aspect, resolution="720",
                model=selection.model_id)
            self.host.video_estimate_worker = estimate_worker
            self.host.video_worker = estimate_worker
            estimate_worker.status_signal.connect(
                self.video_status_label.setText)
            estimate_worker.done_signal.connect(
                lambda request, estimate, c=client:
                self._higgsfield_estimated(c, request, estimate))
            estimate_worker.error_signal.connect(self._on_error)
            estimate_worker.start()

    def _higgsfield_estimated(self, client, request, estimate) -> None:
        from agents.video import video_studio
        from services.per_unit_pricing import eur_per_usd
        from ui.workers import HiggsfieldWorker

        context = self._external_context
        if context.get("cancel_requested"):
            self._reset("Estimate cancelled.")
            return
        token = self.host.authorize_request(
            "video", "higgsfield", request.endpoint, context["topic"],
            label="direct video", flat_cost_eur=round(
                estimate.usd * eur_per_usd(), 6))
        if not token:
            self._reset("Render not approved.")
            return
        self._request_token = token
        try:
            slug, output_path = video_studio.external_output_path(
                context["topic"], context["model"])
        except Exception as exc:
            self._on_error(str(exc))
            return
        context.update({
            "slug": slug, "path": str(output_path),
            "model": request.endpoint,
        })
        self._begin("higgsfield", can_cancel=True)
        worker = HiggsfieldWorker(
            client, context["topic"], context["path"],
            prepared_request=request)
        self.host.video_worker = worker
        worker.status_signal.connect(self.video_status_label.setText)
        worker.job_signal.connect(self._external_job)
        worker.done_signal.connect(self._external_done)
        worker.error_signal.connect(self._on_error)
        worker.start()

    # ── external-provider completion ────────────────────────────────────
    def _external_job(self, job) -> None:
        self._external_context["job_id"] = getattr(job, "job_id", "")
        if getattr(job, "status", "") == "completed":
            # The provider has already produced the billable asset. Preserve
            # that fact even if saving it to disk or indexing it later fails.
            self._external_context["provider_completed"] = True

    def _external_done(self, path: str) -> None:
        from agents.video import video_studio

        context = self._external_context
        try:
            video_studio.record_external(
                slug=context["slug"], path=Path(path), topic=context["topic"],
                provider=context["provider"], model=context["model"],
                seconds=context["seconds"], job_id=context.get("job_id", ""))
        except Exception as exc:
            self._on_error(
                f"The provider completed the clip, but Imprint could not add "
                f"it to the library: {exc}")
            return
        self._on_done(context["slug"], path)

    # ── progress and completion ─────────────────────────────────────────
    def _on_progress(self, percent: int, detail: str):
        self.video_progress.setValue(percent)
        if detail:
            self.video_status_label.setText(detail)

    def _on_done(self, slug: str, path: str):
        # Never fall back to the agent name: with the Social clip flow also
        # authorizing under "video", a name lookup can pop the other flow's
        # pending context.
        token, self._request_token = self._request_token, None
        if token:
            self.host.record_request(token, f"rendered {slug}")
        self._reset(f"Done — {Path(path).name}")
        self.refresh_library()

    def _on_error(self, error: str):
        provider_completed = (
            self._active_kind in {
                "higgsfield", "gemini-video", "qwen-video"}
            and self._external_context.get("provider_completed", False)
        )
        token, self._request_token = self._request_token, None
        if token and provider_completed:
            self.host.record_request(
                token, "provider completed render; local save/index failed")
        elif token:
            # A failed or cancelled render releases the whole-video reserve.
            self.host.abandon_request(token)
        self.video_log.append(error)
        self._reset(f"[Error] {error}")

    def _reset(self, status: str) -> None:
        self.video_status_label.setText(status)
        self.video_render_btn.setEnabled(True)
        self.video_stop_btn.setEnabled(False)
        self.video_stop_btn.hide()
        self._active_kind = ""
        self._visual_model_changed()

    def stop(self):
        if self._active_kind in {"gemini-video", "qwen-video"}:
            provider = {
                "gemini-video": "Gemini", "qwen-video": "Wan",
            }[self._active_kind]
            self.video_status_label.setText(
                f"{provider} has no safe cancel operation here. Imprint will "
                "keep watching and "
                "save the paid result.")
            return
        if self.host.video_worker is not None:
            if self._active_kind == "higgsfield-estimate":
                self._external_context["cancel_requested"] = True
            self.host.video_worker.cancel()
            if self._active_kind.startswith("higgsfield"):
                self.video_status_label.setText("Requesting cancellation…")
            else:
                self.video_status_label.setText("Cancelling after this stage…")

    # ── library ─────────────────────────────────────────────────────────
    def refresh_library(self):
        from agents.video import video_studio
        if not self._available:
            return
        entries = video_studio.library()
        self.video_library_table.setRowCount(0)
        for entry in entries:
            row = self.video_library_table.rowCount()
            self.video_library_table.insertRow(row)
            seconds = float(entry.get("duration_seconds") or 0)
            length = f"{int(seconds // 60)}:{int(seconds % 60):02d}" if seconds else "—"
            if not entry.get("complete"):
                status = "Incomplete"
            elif entry.get("published"):
                status = "Published"
            else:
                status = "Ready"
            values = [entry.get("title", entry.get("slug", "")),
                      (entry.get("created") or "")[:16].replace("T", " "),
                      length, status]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, entry.get("path", ""))
                self.video_library_table.setItem(row, column, item)

    def _selected_path(self) -> Path | None:
        row = self.video_library_table.currentRow()
        if row < 0:
            return None
        item = self.video_library_table.item(row, 0)
        raw = item.data(Qt.UserRole) if item else ""
        return Path(raw) if raw else None

    def play_selected(self):
        path = self._selected_path()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                self, "Not on disk",
                "That render is in the library but its file is missing — it "
                "was probably cancelled before the assembly stage.")

    def reveal_selected(self):
        path = self._selected_path()
        target = path.parent if path else None
        if target and target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
