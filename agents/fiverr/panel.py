"""Client Gigs workspace and its guarded text/image lifecycles.

Phase 4 extraction: the brief, models, actions, preview/delivery/gig/orders
tabs and every handler moved here from main.py. The host supplies shared
budget authorization, usage records, the chat-worker factory and the OpenAI
client; the workers themselves stay on the host so the umbrella's global
Stop and shutdown sweeps keep seeing them. Request tokens live on this
panel — "fiverr" is shared by four flows (prompt, images, delivery, gig),
so nothing here resolves a request by agent name.
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from services.openai_client import (
    DEFAULT_IMAGE_MODEL, IMAGE_MODELS, OpenAIClientWrapper,
)
from services.runtime_paths import user_data_base
from ui.forms import LG, MD, SM, combo, field, line_edit, primary, quiet, section
from ui.panels.base import AgentPanel
from ui.widgets import scrollable


class FiverrPanel(QWidget):
    """A client brief, text and image model choices, and four result tabs."""

    HOST_CONTROLS = (
        "fiverr_name_input", "fiverr_industry_input", "fiverr_colors_input",
        "fiverr_style_box", "fiverr_count_spin", "fiverr_notes_input",
        "fiverr_panel_base", "fiverr_provider_box", "fiverr_model_box",
        "fiverr_image_model_box", "fiverr_generate_btn", "fiverr_delivery_btn",
        "fiverr_gig_btn", "fiverr_stop_btn", "fiverr_cost_label",
        "fiverr_status_label", "fiverr_tabs", "fiverr_preview_status",
        "fiverr_save_images_btn", "fiverr_logo_grid", "fiverr_logo_grid_layout",
        "fiverr_delivery_box", "fiverr_gig_box", "fiverr_order_table",
        "fiverr_clear_btn",
    )

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._prompt_token = None
        self._image_token = None
        self._pending_count = 0
        self._pending_brief: dict = {}
        self._image_paths: list = []
        self._order_row: int | None = None
        self.setObjectName("FiverrPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        # ── Brief ───────────────────────────────────────────────────────
        layout.addWidget(section("Client brief"))

        self.fiverr_name_input = line_edit("Apex Fitness Studio")
        self.fiverr_industry_input = line_edit("fitness, law firm, bakery")
        self.fiverr_colors_input = line_edit("navy blue and gold")
        self.fiverr_style_box = combo(
            ["Minimalist", "Bold", "Vintage", "Playful", "Corporate",
             "Luxury", "Futuristic"])
        self.fiverr_count_spin = QSpinBox()
        self.fiverr_count_spin.setRange(1, 4)
        self.fiverr_count_spin.setValue(2)
        self.fiverr_count_spin.valueChanged.connect(self.update_estimate)

        # Equal column stretch is what makes the second row's labels sit under
        # the first row's, instead of each row packing to its own width.
        brief = QGridLayout()
        brief.setHorizontalSpacing(MD)
        brief.setVerticalSpacing(MD)
        brief.addWidget(field("Business name", self.fiverr_name_input), 0, 0, 1, 2,
                        Qt.AlignTop)
        brief.addWidget(field("Style", self.fiverr_style_box), 0, 2, Qt.AlignTop)
        brief.addWidget(field("Industry / niche", self.fiverr_industry_input), 1, 0,
                        Qt.AlignTop)
        brief.addWidget(field("Primary colours", self.fiverr_colors_input), 1, 1,
                        Qt.AlignTop)
        brief.addWidget(field("Concepts", self.fiverr_count_spin), 1, 2, Qt.AlignTop)
        for column in range(3):
            brief.setColumnStretch(column, 1)
        layout.addLayout(brief)

        self.fiverr_notes_input = QTextEdit()
        self.fiverr_notes_input.setPlaceholderText(
            "Tagline, mood, target audience, competitors to avoid…")
        self.fiverr_notes_input.setFixedHeight(70)
        layout.addWidget(field("Notes", self.fiverr_notes_input))

        # ── Models ──────────────────────────────────────────────────────
        layout.addWidget(section("Models"))

        self.fiverr_panel_base = AgentPanel(
            host, "fiverr",
            providers=("anthropic", "openai", "deepseek", "kimi", "gemini",
                       "qwen", "ollama"),
            default_provider="anthropic")
        self.fiverr_provider_box = self.fiverr_panel_base.provider_box
        self.fiverr_model_box = self.fiverr_panel_base.model_box

        self.fiverr_image_model_box = combo(list(IMAGE_MODELS),
                                            DEFAULT_IMAGE_MODEL)
        self.fiverr_image_model_box.currentTextChanged.connect(
            self.update_estimate)

        models = QGridLayout()
        models.setHorizontalSpacing(MD)
        models.setVerticalSpacing(MD)
        models.addWidget(field("Text provider", self.fiverr_provider_box), 0, 0,
                         Qt.AlignTop)
        models.addWidget(field("Text model", self.fiverr_model_box), 0, 1, Qt.AlignTop)
        models.addWidget(field("Image model", self.fiverr_image_model_box), 0, 2,
                         Qt.AlignTop)
        for column in range(3):
            models.setColumnStretch(column, 1)
        layout.addLayout(models)

        # ── Actions ─────────────────────────────────────────────────────
        # One filled button. The other two are real actions but not the answer
        # to this screen, and the cost sits beside the control that spends it.
        actions = QHBoxLayout()
        actions.setSpacing(SM)

        self.fiverr_generate_btn = primary("Generate Logos")
        self.fiverr_generate_btn.setMinimumWidth(160)
        self.fiverr_generate_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.fiverr_generate_btn.clicked.connect(self.generate_logos)
        actions.addWidget(self.fiverr_generate_btn)

        self.fiverr_delivery_btn = QPushButton("Delivery Message")
        self.fiverr_delivery_btn.clicked.connect(self.write_delivery)
        actions.addWidget(self.fiverr_delivery_btn)

        self.fiverr_gig_btn = QPushButton("Gig Description")
        self.fiverr_gig_btn.clicked.connect(self.write_gig)
        actions.addWidget(self.fiverr_gig_btn)

        # Hidden rather than disabled: a permanently greyed button is chrome.
        self.fiverr_stop_btn = QPushButton("Stop")
        self.fiverr_stop_btn.setObjectName("DangerAction")
        self.fiverr_stop_btn.clicked.connect(self.stop)
        self.fiverr_stop_btn.hide()
        actions.addWidget(self.fiverr_stop_btn)

        actions.addStretch()
        self.fiverr_cost_label = QLabel()
        self.fiverr_cost_label.setObjectName("EstimateLine")
        actions.addWidget(self.fiverr_cost_label)
        layout.addLayout(actions)

        self.fiverr_status_label = QLabel("Idle")
        self.fiverr_status_label.setObjectName("EstimateLine")
        self.fiverr_status_label.setWordWrap(True)
        layout.addWidget(self.fiverr_status_label)

        # ── Results ─────────────────────────────────────────────────────
        self.fiverr_tabs = QTabWidget()

        preview_widget = QWidget()
        preview_widget.setObjectName("Transparent")
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(MD, MD, MD, MD)
        preview_layout.setSpacing(MD)

        preview_top = QHBoxLayout()
        preview_top.setSpacing(SM)
        self.fiverr_preview_status = QLabel(
            "No logos yet — fill in the brief and generate.")
        self.fiverr_preview_status.setObjectName("EstimateLine")
        preview_top.addWidget(self.fiverr_preview_status)
        preview_top.addStretch()
        self.fiverr_save_images_btn = quiet("Save All Images")
        self.fiverr_save_images_btn.setEnabled(False)
        self.fiverr_save_images_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.fiverr_save_images_btn.clicked.connect(self.save_images)
        preview_top.addWidget(self.fiverr_save_images_btn)
        preview_layout.addLayout(preview_top)

        self.fiverr_logo_grid = QWidget()
        self.fiverr_logo_grid.setObjectName("Transparent")
        self.fiverr_logo_grid_layout = QHBoxLayout(self.fiverr_logo_grid)
        self.fiverr_logo_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.fiverr_logo_grid_layout.setSpacing(MD)
        preview_layout.addWidget(self.fiverr_logo_grid)
        preview_layout.addStretch()
        self.fiverr_tabs.addTab(preview_widget, "Logo Preview")

        self.fiverr_delivery_box = QTextEdit()
        self.fiverr_delivery_box.setPlaceholderText(
            "Generate a client delivery message with the button above.")
        self.fiverr_tabs.addTab(self.fiverr_delivery_box, "Delivery Message")

        self.fiverr_gig_box = QTextEdit()
        self.fiverr_gig_box.setPlaceholderText(
            "Generate a Fiverr gig listing with the button above.")
        self.fiverr_tabs.addTab(self.fiverr_gig_box, "Gig Description")

        # The order log was a 190px sidebar column holding a three-column
        # table; every column was truncated. As a tab it gets the full width.
        orders_widget = QWidget()
        orders_widget.setObjectName("Transparent")
        orders_layout = QVBoxLayout(orders_widget)
        orders_layout.setContentsMargins(MD, MD, MD, MD)
        orders_layout.setSpacing(MD)
        self.fiverr_order_table = QTableWidget(0, 3)
        self.fiverr_order_table.setHorizontalHeaderLabels(
            ["Business", "Concepts", "Status"])
        header = self.fiverr_order_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.fiverr_order_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.fiverr_order_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.fiverr_order_table.verticalHeader().setVisible(False)
        orders_layout.addWidget(self.fiverr_order_table)

        clear_row = QHBoxLayout()
        clear_row.addStretch()
        self.fiverr_clear_btn = quiet("Clear log")
        self.fiverr_clear_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.fiverr_clear_btn.clicked.connect(self.clear)
        clear_row.addWidget(self.fiverr_clear_btn)
        orders_layout.addLayout(clear_row)
        self.fiverr_tabs.addTab(orders_widget, "Orders")

        layout.addWidget(self.fiverr_tabs, 1)

        # Shared recommendation and tooltip wiring still resolves these on
        # the host; ownership and lifecycle are local to this panel.
        for name in self.HOST_CONTROLS:
            setattr(host, name, getattr(self, name))
        host.fiverr_panel = self
        self.update_estimate()
        self.hide()
        self.fiverr_panel_base.load_models()

    # ── shared helpers ──────────────────────────────────────────────────
    def load_models(self) -> None:
        self.fiverr_panel_base.load_models()

    def update_estimate(self, *_args) -> None:
        """Keep the per-image estimate next to the button that spends it.

        Priced from `config/pricing.json`, the same table the budget guard
        reads, so what the label promises and what gets billed are one number.
        """
        from services.per_unit_pricing import describe, image_cost_eur
        model = self.fiverr_image_model_box.currentText()
        count = self.fiverr_count_spin.value()
        unit = f"{count} image{'s' if count != 1 else ''}"
        self.fiverr_cost_label.setText(
            describe(image_cost_eur(model, count), unit))

    def _get_brief(self) -> dict:
        return {
            "business_name": self.fiverr_name_input.text().strip(),
            "industry": self.fiverr_industry_input.text().strip(),
            "style": self.fiverr_style_box.currentText(),
            "colors": self.fiverr_colors_input.text().strip(),
            "notes": self.fiverr_notes_input.toPlainText().strip(),
        }

    def _reset_buttons(self) -> None:
        """Back to idle. Every exit path from a run goes through here."""
        self.fiverr_generate_btn.setEnabled(True)
        self.fiverr_delivery_btn.setEnabled(True)
        self.fiverr_gig_btn.setEnabled(True)
        self.fiverr_stop_btn.setEnabled(False)
        self.fiverr_stop_btn.hide()

    def _set_busy(self, status: str) -> None:
        self.fiverr_status_label.setText(status)
        self.fiverr_generate_btn.setEnabled(False)
        self.fiverr_delivery_btn.setEnabled(False)
        self.fiverr_gig_btn.setEnabled(False)
        self.fiverr_stop_btn.setEnabled(True)
        self.fiverr_stop_btn.show()

    # ── logo generation (text prompt, then paid images) ─────────────────
    def generate_logos(self) -> None:
        brief = self._get_brief()
        if not brief["business_name"]:
            QMessageBox.warning(self, "Missing Input", "Please enter a business name.")
            return
        if not OpenAIClientWrapper.key_available():
            QMessageBox.warning(
                self, "No API Key",
                "OPENAI_API_KEY is required to generate logo images.")
            return

        count = self.fiverr_count_spin.value()
        provider = self.fiverr_provider_box.currentText()
        model = self.fiverr_model_box.currentText()

        agent = self.host.agent_instances["fiverr"]
        messages = agent.build_image_prompt_request(brief)

        self._set_busy("Building image prompt...")
        self._clear_logo_grid()

        # Keep the token: "fiverr" is shared by the prompt request and the
        # image request that follows it, plus the delivery/gig text flows.
        token = self.host.authorize_request(
            "fiverr", provider, model,
            messages[-1]["content"] if messages else "")
        if not token:
            # Refused — re-enable the buttons disabled above, or the panel
            # stays stuck until restart.
            self._reset_buttons()
            return
        self._prompt_token = token
        worker = self.host._new_chat_worker(provider, model, messages, "")
        self.host.fiverr_text_worker = worker
        worker.finished_signal.connect(self._on_prompt_ready)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_text_error)
        worker.start()
        self._pending_count = count
        self._pending_brief = brief

    def _on_prompt_ready(self, image_prompt: str) -> None:
        from services.per_unit_pricing import image_cost_eur
        from ui.workers import FiverrImageWorker

        token, self._prompt_token = self._prompt_token, None
        if token:
            self.host.record_request(token, image_prompt)
        image_prompt = image_prompt.strip()
        count = self._pending_count
        brief = self._pending_brief
        save_dir = (user_data_base() / "data" / "fiverr_output"
                    / datetime.now().strftime("%Y%m%d_%H%M%S"))
        self.fiverr_status_label.setText(f"Generating {count} concept(s)...")

        # The images are a second paid request, billed per image rather than
        # per token.
        image_model = self.fiverr_image_model_box.currentText()
        image_cost = image_cost_eur(image_model, count)
        if image_cost is None:
            # A rate of 0 means unknown, not free. Refuse rather than bill
            # €0.00 (and never pass None through — authorize_request would
            # fall back to pricing the prompt as a chat request).
            QMessageBox.warning(
                self, "No Price Configured",
                f"{image_model} has no per-image rate in config/pricing.json, "
                "so the logo images cannot be billed against the budget caps. "
                "Add a rate (0 means unknown) before generating.")
            self._reset_buttons()
            return
        image_token = self.host.authorize_request(
            "fiverr", "openai", image_model,
            f"{count} logo concepts: {image_prompt[:200]}",
            label="logo images",
            flat_cost_eur=image_cost)
        if not image_token:
            self._reset_buttons()
            return
        self._image_token = image_token

        worker = FiverrImageWorker(
            self.host.openai, image_prompt, count, save_dir,
            image_model=image_model)
        self.host.fiverr_image_worker = worker
        worker.image_ready_signal.connect(self._on_image_ready)
        worker.all_done_signal.connect(self._on_all_done)
        worker.error_signal.connect(self._on_image_error)
        worker.status_signal.connect(self.fiverr_status_label.setText)
        worker.start()

        row = self.fiverr_order_table.rowCount()
        self.fiverr_order_table.insertRow(row)
        self.fiverr_order_table.setItem(
            row, 0, QTableWidgetItem(brief.get("business_name", "")))
        self.fiverr_order_table.setItem(row, 1, QTableWidgetItem(str(count)))
        self.fiverr_order_table.setItem(row, 2, QTableWidgetItem("Generating"))
        self._order_row = row

    def _on_image_ready(self, path: str, index: int) -> None:
        lbl = QLabel()
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(280, 280, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
            lbl.setPixmap(pixmap)
        else:
            lbl.setText(f"[Concept {index + 1}]")
        lbl.setToolTip(path)
        lbl.setAlignment(Qt.AlignCenter)
        self.fiverr_logo_grid_layout.addWidget(lbl)
        self._image_paths.append(path)
        self.fiverr_preview_status.setText(
            f"Concept {index + 1} ready — {Path(path).name}")
        self.fiverr_tabs.setCurrentIndex(0)

    def _on_all_done(self, paths: list) -> None:
        self._image_paths = paths
        self.fiverr_status_label.setText(f"Done — {len(paths)} logo(s) generated.")
        # Closes out the image request authorised in _on_prompt_ready,
        # billing the per-image cost it was authorised against.
        token, self._image_token = self._image_token, None
        if token:
            self.host.record_request(token, f"{len(paths)} logo images")
        self._reset_buttons()
        self.fiverr_save_images_btn.setEnabled(True)
        if self._order_row is not None:
            self.fiverr_order_table.setItem(
                self._order_row, 2, QTableWidgetItem("Done"))

    def _on_image_error(self, error: str) -> None:
        # A failed render still consumed whatever it managed before failing,
        # but the authorised amount was for the full set — release it rather
        # than bill for images that were never produced.
        token, self._image_token = self._image_token, None
        if token:
            self.host.abandon_request(token)
        self.fiverr_status_label.setText(f"Error: {error}")
        self.fiverr_preview_status.setText(f"[Error] {error}")
        self._reset_buttons()
        if self._order_row is not None:
            self.fiverr_order_table.setItem(
                self._order_row, 2, QTableWidgetItem("Error"))

    def _on_text_error(self, error: str) -> None:
        # Shared by all three text flows (prompt, delivery, gig) — they are
        # single-flight via the disabled buttons, so one token attribute
        # covers them.
        token, self._prompt_token = self._prompt_token, None
        if token:
            self.host.abandon_request(token)
        self.fiverr_status_label.setText(f"Error: {error}")
        self._reset_buttons()

    # ── delivery message ────────────────────────────────────────────────
    def write_delivery(self) -> None:
        brief = self._get_brief()
        provider = self.fiverr_provider_box.currentText()
        model = self.fiverr_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        agent = self.host.agent_instances["fiverr"]
        messages = agent.build_messages(
            "Write a professional delivery message for this logo order.", brief)
        self.fiverr_delivery_box.clear()
        self._set_busy("Writing delivery message...")
        self.fiverr_tabs.setCurrentIndex(1)
        token = self.host.authorize_request(
            "fiverr", provider, model,
            messages[-1]["content"] if messages else "")
        if not token:
            self._reset_buttons()
            return
        self._prompt_token = token
        worker = self.host._new_chat_worker(provider, model, messages, "")
        self.host.fiverr_text_worker = worker
        worker.token_signal.connect(self._on_delivery_token)
        worker.finished_signal.connect(self._on_delivery_done)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_text_error)
        worker.start()

    def _on_delivery_token(self, token: str) -> None:
        self.fiverr_delivery_box.moveCursor(QTextCursor.End)
        self.fiverr_delivery_box.insertPlainText(token)

    def _on_delivery_done(self, _full: str) -> None:
        token, self._prompt_token = self._prompt_token, None
        if token:
            self.host.record_request(token, _full)
        self.fiverr_status_label.setText("Delivery message ready.")
        self._reset_buttons()

    # ── gig description ─────────────────────────────────────────────────
    def write_gig(self) -> None:
        brief = self._get_brief()
        provider = self.fiverr_provider_box.currentText()
        model = self.fiverr_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        agent = self.host.agent_instances["fiverr"]
        messages = agent.build_messages(
            "Write a complete Fiverr gig description for logo design services.",
            brief)
        self.fiverr_gig_box.clear()
        self._set_busy("Writing gig description...")
        self.fiverr_tabs.setCurrentIndex(2)
        token = self.host.authorize_request(
            "fiverr", provider, model,
            messages[-1]["content"] if messages else "")
        if not token:
            self._reset_buttons()
            return
        self._prompt_token = token
        worker = self.host._new_chat_worker(provider, model, messages, "")
        self.host.fiverr_text_worker = worker
        worker.token_signal.connect(self._on_gig_token)
        worker.finished_signal.connect(self._on_gig_done)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_text_error)
        worker.start()

    def _on_gig_token(self, token: str) -> None:
        self.fiverr_gig_box.moveCursor(QTextCursor.End)
        self.fiverr_gig_box.insertPlainText(token)

    def _on_gig_done(self, _full: str) -> None:
        token, self._prompt_token = self._prompt_token, None
        if token:
            self.host.record_request(token, _full)
        self.fiverr_status_label.setText("Gig description ready.")
        self._reset_buttons()

    # ── stop / save / clear ─────────────────────────────────────────────
    def stop(self) -> None:
        image_worker = self.host.fiverr_image_worker
        if image_worker is not None and image_worker.isRunning():
            image_worker.cancel()
        text_worker = self.host.fiverr_text_worker
        if text_worker is not None and text_worker.isRunning():
            text_worker.cancel()
        # Release whatever this panel has pending — a stopped run must not
        # leave an authorized request dangling for the next flow to clobber.
        for attr in ("_prompt_token", "_image_token"):
            token = getattr(self, attr)
            setattr(self, attr, None)
            if token:
                self.host.abandon_request(token, reason="stopped")
        self.fiverr_status_label.setText("Stopped.")
        self._reset_buttons()

    def save_images(self) -> None:
        if not self._image_paths:
            return
        dest_dir = QFileDialog.getExistingDirectory(
            self, "Choose folder to save logos")
        if not dest_dir:
            return
        import shutil
        for src in self._image_paths:
            shutil.copy(src, dest_dir)
        self.fiverr_status_label.setText(
            f"Saved {len(self._image_paths)} image(s).")

    def clear(self) -> None:
        self._clear_logo_grid()
        self.fiverr_delivery_box.clear()
        self.fiverr_gig_box.clear()
        self.fiverr_status_label.setText("Idle")
        self.update_estimate()
        self.fiverr_preview_status.setText("No logos generated yet.")
        self.fiverr_save_images_btn.setEnabled(False)
        self._image_paths = []

    def _clear_logo_grid(self) -> None:
        while self.fiverr_logo_grid_layout.count():
            item = self.fiverr_logo_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
