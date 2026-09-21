"""Social workspace and its guarded write/clip lifecycles.

Phase 4 extraction: the campaign form, compose controls and the
Draft/Schedule/Analytics/Accounts tabs and every handler moved here from
main.py. The host supplies shared budget authorization, usage records,
the chat-worker factory, and the Video panel's library refresh; the
workers stay host attributes so the umbrella's shutdown sweep keeps
seeing them.

Request tokens live on this panel: "social" is shared by the post-writing
and clip-brief flows, and the clip render authorizes under "video" — the
same key as the Video tab — so nothing here resolves a request by agent
name.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QGridLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QMessageBox, QPushButton, QSizePolicy,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)

from agents.social.agent import (
    ANGLES, SUBJECT_KINDS, build_clip_brief_messages, build_post_messages,
    over_limit, split_variants,
)
from ui.forms import LG, MD, SM, combo, field, line_edit, primary, quiet, section
from ui.panels.base import AgentPanel
from ui.style import ACCENT, TEXT_DIM, TEXT_MUTE
from ui.widgets import FlowLayout, scrollable


class SocialPanel(QWidget):
    """Campaigns, per-platform drafting, a schedule, and honest analytics."""

    HOST_CONTROLS = (
        "social_campaign_box", "social_subject_input", "social_kind_box",
        "social_goal_input", "social_audience_input", "social_links_input",
        "social_new_campaign_btn", "social_save_campaign_btn",
        "social_delete_campaign_btn", "social_platform_box", "social_angle_box",
        "social_variants_box", "social_notes_input", "social_panel_base",
        "social_provider_box", "social_model_box", "social_write_btn",
        "social_clip_btn", "social_schedule_btn", "social_stop_btn",
        "social_status_label", "social_tabs", "social_draft_box",
        "social_limit_label", "social_save_draft_btn", "social_schedule_table",
        "social_copy_btn", "social_mark_posted_btn", "social_metrics_btn",
        "social_post_btn", "social_delete_post_btn", "social_analytics_table",
        "social_accounts_box", "social_refresh_accounts_btn",
    )

    def __init__(self, host):
        super().__init__()
        from agents.social import platforms

        self.host = host
        self._write_token = None
        self._brief_token = None
        self._clip_video_token = None
        self._pending_clip = ("tiktok", 30)
        self.setObjectName("SocialPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        # ── Campaign ────────────────────────────────────────────────────
        layout.addWidget(section("Campaign"))

        self.social_campaign_box = QComboBox()
        self.social_campaign_box.currentIndexChanged.connect(
            self._campaign_changed)
        self.social_subject_input = line_edit("The Salt Road")
        self.social_kind_box = combo(list(SUBJECT_KINDS))
        self.social_goal_input = line_edit("launch week sales")
        self.social_audience_input = line_edit("literary fiction readers")
        self.social_links_input = line_edit("https://…")

        campaign = QGridLayout()
        campaign.setHorizontalSpacing(MD)
        campaign.setVerticalSpacing(MD)
        campaign.addWidget(field("Campaign", self.social_campaign_box), 0, 0, Qt.AlignTop)
        campaign.addWidget(field("Subject", self.social_subject_input), 0, 1, Qt.AlignTop)
        campaign.addWidget(field("Subject is a", self.social_kind_box), 0, 2, Qt.AlignTop)
        campaign.addWidget(field("Goal", self.social_goal_input), 1, 0, Qt.AlignTop)
        campaign.addWidget(field("Audience", self.social_audience_input), 1, 1, Qt.AlignTop)
        campaign.addWidget(field("Link", self.social_links_input), 1, 2, Qt.AlignTop)
        for column in range(3):
            campaign.setColumnStretch(column, 1)
        layout.addLayout(campaign)

        campaign_actions = QHBoxLayout()
        campaign_actions.setSpacing(SM)
        self.social_new_campaign_btn = QPushButton("New Campaign")
        self.social_new_campaign_btn.clicked.connect(self.new_campaign)
        campaign_actions.addWidget(self.social_new_campaign_btn)
        self.social_save_campaign_btn = QPushButton("Save Campaign")
        self.social_save_campaign_btn.clicked.connect(self.save_campaign)
        campaign_actions.addWidget(self.social_save_campaign_btn)
        self.social_delete_campaign_btn = quiet("Delete campaign")
        self.social_delete_campaign_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.social_delete_campaign_btn.clicked.connect(self.delete_campaign)
        campaign_actions.addWidget(self.social_delete_campaign_btn)
        campaign_actions.addStretch()
        layout.addLayout(campaign_actions)

        # ── Compose ─────────────────────────────────────────────────────
        layout.addWidget(section("Compose"))

        self.social_platform_box = combo(list(platforms.names()))
        self.social_platform_box.currentTextChanged.connect(self._platform_changed)
        self.social_angle_box = combo(list(ANGLES))
        self.social_variants_box = combo(["1", "2", "3"], "2")
        self.social_notes_input = line_edit("Anything specific to include")

        compose = QGridLayout()
        compose.setHorizontalSpacing(MD)
        compose.setVerticalSpacing(MD)
        compose.addWidget(field("Platform", self.social_platform_box), 0, 0, Qt.AlignTop)
        compose.addWidget(field("Angle", self.social_angle_box), 0, 1, Qt.AlignTop)
        compose.addWidget(field("Variants", self.social_variants_box), 0, 2, Qt.AlignTop)
        compose.addWidget(field("Specifics", self.social_notes_input), 1, 0, 1, 3, Qt.AlignTop)
        for column in range(3):
            compose.setColumnStretch(column, 1)
        layout.addLayout(compose)

        self.social_panel_base = AgentPanel(
            host, "social",
            providers=("anthropic", "openai", "deepseek", "kimi", "gemini",
                       "qwen", "ollama"),
            default_provider="anthropic")
        self.social_provider_box = self.social_panel_base.provider_box
        self.social_model_box = self.social_panel_base.model_box

        models = QGridLayout()
        models.setHorizontalSpacing(MD)
        models.setVerticalSpacing(MD)
        models.addWidget(field("Provider", self.social_provider_box), 0, 0, Qt.AlignTop)
        models.addWidget(field("Model", self.social_model_box), 0, 1, Qt.AlignTop)
        for column in range(3):
            models.setColumnStretch(column, 1)
        layout.addLayout(models)

        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.social_write_btn = primary("Write Posts")
        self.social_write_btn.setMinimumWidth(160)
        self.social_write_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.social_write_btn.clicked.connect(self.write)
        actions.addWidget(self.social_write_btn)

        # The cooperation with Video: Social does not render anything itself,
        # it asks the video pipeline for a clip sized for the platform.
        self.social_clip_btn = QPushButton("Make a Clip")
        self.social_clip_btn.setToolTip(
            "Write a brief and hand it to the Video pipeline as a vertical "
            "clip for this platform.")
        self.social_clip_btn.clicked.connect(self.make_clip)
        actions.addWidget(self.social_clip_btn)

        self.social_schedule_btn = QPushButton("Schedule Drafts")
        self.social_schedule_btn.setToolTip(
            "Spread the campaign's undated drafts across the coming weeks at "
            "each platform's own cadence.")
        self.social_schedule_btn.clicked.connect(self.schedule_drafts)
        actions.addWidget(self.social_schedule_btn)

        self.social_stop_btn = QPushButton("Stop")
        self.social_stop_btn.setObjectName("DangerAction")
        self.social_stop_btn.clicked.connect(self.stop)
        self.social_stop_btn.hide()
        actions.addWidget(self.social_stop_btn)

        actions.addStretch()
        self.social_status_label = QLabel("")
        self.social_status_label.setObjectName("EstimateLine")
        actions.addWidget(self.social_status_label)
        layout.addLayout(actions)

        # ── Tabs ────────────────────────────────────────────────────────
        self.social_tabs = QTabWidget()

        drafts_page = QWidget()
        drafts_page.setObjectName("Transparent")
        drafts = QVBoxLayout(drafts_page)
        drafts.setContentsMargins(MD, MD, MD, MD)
        drafts.setSpacing(MD)
        self.social_draft_box = QTextEdit()
        self.social_draft_box.setPlaceholderText(
            "Drafts appear here, fully editable. Nothing is sent until you "
            "press Post on a row in the Schedule tab.")
        drafts.addWidget(self.social_draft_box, 1)
        draft_actions = QHBoxLayout()
        draft_actions.setSpacing(SM)
        self.social_limit_label = QLabel("")
        self.social_limit_label.setObjectName("EstimateLine")
        draft_actions.addWidget(self.social_limit_label)
        draft_actions.addStretch()
        self.social_save_draft_btn = QPushButton("Save to Schedule")
        self.social_save_draft_btn.clicked.connect(self.save_draft)
        draft_actions.addWidget(self.social_save_draft_btn)
        drafts.addLayout(draft_actions)
        self.social_draft_box.textChanged.connect(self._update_limit)
        self.social_tabs.addTab(drafts_page, "Draft")

        schedule_page = QWidget()
        schedule_page.setObjectName("Transparent")
        schedule = QVBoxLayout(schedule_page)
        schedule.setContentsMargins(MD, MD, MD, MD)
        schedule.setSpacing(MD)
        self.social_schedule_table = QTableWidget(0, 6)
        self.social_schedule_table.setHorizontalHeaderLabels(
            ["When", "Platform", "Format", "Post", "Status", "Link"])
        header = self.social_schedule_table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for column in (0, 1, 2, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.social_schedule_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.social_schedule_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.social_schedule_table.verticalHeader().setVisible(False)
        schedule.addWidget(self.social_schedule_table, 1)

        schedule_actions_container = QWidget()
        schedule_actions_container.setObjectName("Transparent")
        schedule_actions = FlowLayout(schedule_actions_container, spacing=SM)
        self.social_copy_btn = QPushButton("Copy Text")
        self.social_copy_btn.clicked.connect(self.copy_selected)
        schedule_actions.addWidget(self.social_copy_btn)
        self.social_mark_posted_btn = QPushButton("Mark Posted")
        self.social_mark_posted_btn.setToolTip(
            "For the platforms you post by hand.")
        self.social_mark_posted_btn.clicked.connect(self.mark_posted)
        schedule_actions.addWidget(self.social_mark_posted_btn)
        self.social_metrics_btn = QPushButton("Record metrics")
        self.social_metrics_btn.setToolTip(
            "Enter observed reach and clicks for the selected posted item, "
            "with source and date window.")
        self.social_metrics_btn.clicked.connect(self.record_metrics)
        schedule_actions.addWidget(self.social_metrics_btn)
        self.social_post_btn = QPushButton("Post Now")
        self.social_post_btn.setObjectName("WarnAction")
        self.social_post_btn.setToolTip(
            "Publishes this one post through the platform's API. Only enabled "
            "where that is configured.")
        self.social_post_btn.clicked.connect(self.post_selected)
        schedule_actions.addWidget(self.social_post_btn)
        self.social_delete_post_btn = quiet("Delete")
        self.social_delete_post_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.social_delete_post_btn.clicked.connect(self.delete_post)
        schedule_actions.addWidget(self.social_delete_post_btn)
        schedule.addWidget(schedule_actions_container)
        self.social_tabs.addTab(schedule_page, "Schedule")

        analytics_page = QWidget()
        analytics_page.setObjectName("Transparent")
        analytics_layout = QVBoxLayout(analytics_page)
        analytics_layout.setContentsMargins(MD, MD, MD, MD)
        analytics_layout.setSpacing(MD)
        analytics_note = QLabel(
            "Observed post metrics only. Click-through rate is clicks ÷ reach "
            "for the same post and window; it does not prove sales or compare "
            "different audiences fairly.")
        analytics_note.setWordWrap(True)
        analytics_note.setObjectName("EstimateLine")
        analytics_layout.addWidget(analytics_note)
        self.social_analytics_table = QTableWidget(0, 6)
        self.social_analytics_table.setHorizontalHeaderLabels(
            ["Platform", "Angle", "Reach", "Clicks", "Click rate", "Source / window"])
        self.social_analytics_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.social_analytics_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.social_analytics_table.verticalHeader().setVisible(False)
        analytics_layout.addWidget(self.social_analytics_table, 1)
        self.social_tabs.addTab(analytics_page, "Analytics")

        accounts_page = QWidget()
        accounts_page.setObjectName("Transparent")
        accounts = QVBoxLayout(accounts_page)
        accounts.setContentsMargins(MD, MD, MD, MD)
        accounts.setSpacing(MD)
        self.social_accounts_box = QTextBrowser()
        accounts.addWidget(self.social_accounts_box, 1)
        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        self.social_refresh_accounts_btn = quiet("Re-check")
        self.social_refresh_accounts_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.social_refresh_accounts_btn.clicked.connect(self.refresh_accounts)
        refresh_row.addWidget(self.social_refresh_accounts_btn)
        accounts.addLayout(refresh_row)
        self.social_tabs.addTab(accounts_page, "Accounts")

        layout.addWidget(self.social_tabs, 1)

        # Aliases retired 2026-09-21: shared wiring resolves controls
        # through host._find_control(); HOST_CONTROLS stays as the
        # published contract of what this panel owns.
        host.social_panel = self
        host.social_worker = None
        self.social_panel_base.load_models()
        self.refresh_campaigns()
        self.refresh_accounts()
        self._platform_changed(self.social_platform_box.currentText())
        self.hide()

    # ── campaigns ───────────────────────────────────────────────────────
    def load_models(self) -> None:
        self.social_panel_base.load_models()

    def refresh_campaigns(self):
        from agents.social import store
        self.social_campaign_box.blockSignals(True)
        self.social_campaign_box.clear()
        for campaign in store.list_campaigns():
            self.social_campaign_box.addItem(
                campaign["name"] or campaign["subject"] or "Untitled",
                campaign["id"])
        self.social_campaign_box.blockSignals(False)
        self._campaign_changed(self.social_campaign_box.currentIndex())

    def current_campaign(self) -> dict | None:
        from agents.social import store
        campaign_id = self.social_campaign_box.currentData()
        return store.get_campaign(campaign_id) if campaign_id else None

    def _campaign_changed(self, _index):
        campaign = self.current_campaign()
        if not campaign:
            for widget in (self.social_subject_input, self.social_goal_input,
                           self.social_audience_input, self.social_links_input):
                widget.clear()
            self.refresh_schedule()
            return
        self.social_subject_input.setText(campaign.get("subject", ""))
        self.social_kind_box.setCurrentText(campaign.get("subject_kind", "other"))
        self.social_goal_input.setText(campaign.get("goal", ""))
        self.social_audience_input.setText(campaign.get("audience", ""))
        self.social_links_input.setText(campaign.get("links", ""))
        self.refresh_schedule()

    def new_campaign(self):
        from agents.social import store
        subject = self.social_subject_input.text().strip() or "Untitled"
        campaign_id = store.create_campaign(
            name=subject, subject=subject,
            subject_kind=self.social_kind_box.currentText(),
            goal=self.social_goal_input.text().strip(),
            audience=self.social_audience_input.text().strip(),
            links=self.social_links_input.text().strip())
        self.refresh_campaigns()
        index = self.social_campaign_box.findData(campaign_id)
        if index >= 0:
            self.social_campaign_box.setCurrentIndex(index)
        self.social_status_label.setText(f"Created “{subject}”")

    def save_campaign(self):
        from agents.social import store
        campaign = self.current_campaign()
        if not campaign:
            self.new_campaign()
            return
        subject = self.social_subject_input.text().strip()
        store.update_campaign(
            campaign["id"], name=subject or campaign["name"], subject=subject,
            subject_kind=self.social_kind_box.currentText(),
            goal=self.social_goal_input.text().strip(),
            audience=self.social_audience_input.text().strip(),
            links=self.social_links_input.text().strip())
        self.refresh_campaigns()
        self.social_status_label.setText("Saved")

    def delete_campaign(self):
        from agents.social import store
        campaign = self.current_campaign()
        if not campaign:
            return
        confirm = QMessageBox.question(
            self, "Delete campaign",
            f"Delete “{campaign['name']}” and all of its posts?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        store.delete_campaign(campaign["id"])
        self.refresh_campaigns()

    # ── platform and limit ──────────────────────────────────────────────
    def _platform(self):
        from agents.social import platforms
        return platforms.get(
            platforms.key_for_name(self.social_platform_box.currentText()))

    def _platform_changed(self, _name=""):
        self._update_limit()

    def _update_limit(self):
        """Character count against the platform ceiling, live.

        The limit is in the prompt and models overshoot it anyway; posting an
        over-length draft is a rejected API call at the worst moment, so the
        count is visible while editing rather than checked at submit.
        """
        platform = self._platform()
        if platform is None:
            self.social_limit_label.setText("")
            return
        text = self.social_draft_box.toPlainText().strip()
        if not platform.limit:
            self.social_limit_label.setText(f"{len(text)} characters")
            return
        over = over_limit(text, platform)
        suffix = f" · {over} over" if over else ""
        self.social_limit_label.setText(
            f"{len(text)} / {platform.limit} characters{suffix}")

    # ── writing ─────────────────────────────────────────────────────────
    def write(self):
        campaign = self.current_campaign()
        if not campaign:
            QMessageBox.warning(self, "No Campaign",
                                "Create a campaign first.")
            return
        platform = self._platform()
        provider = self.social_provider_box.currentText()
        model = self.social_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Pick a model first.")
            return

        variants = int(self.social_variants_box.currentText() or 1)
        messages = build_post_messages(
            campaign, platform, self.social_angle_box.currentText(),
            notes=self.social_notes_input.text().strip(), variants=variants)

        # Keep the token: "social" is shared with the clip-brief flow, and
        # resolving by name pops whichever request happens to be oldest.
        token = self.host.authorize_request("social", provider, model,
                                            messages[-1]["content"],
                                            label=f"{platform.key} post")
        if not token:
            return
        self._write_token = token

        self.social_write_btn.setEnabled(False)
        self.social_stop_btn.show()
        self.social_stop_btn.setEnabled(True)
        self.social_status_label.setText(f"Writing for {platform.name}…")

        worker = self.host._new_chat_worker(provider, model, messages, "")
        self.host.social_worker = worker
        worker.finished_signal.connect(self._on_written)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_write_error)
        worker.start()

    def _on_written(self, response: str):
        token, self._write_token = self._write_token, None
        if token:
            self.host.record_request(token, response)
        variants = split_variants(response)
        separator = "\n\n" + "—" * 30 + "\n\n"
        self.social_draft_box.setPlainText(separator.join(variants))
        self.social_status_label.setText(
            f"{len(variants)} variant(s) — edit, then Save to Schedule")
        self._reset_buttons()
        self.social_tabs.setCurrentIndex(0)

    def _on_write_error(self, error: str):
        token, self._write_token = self._write_token, None
        if token:
            self.host.abandon_request(token)
        self.social_status_label.setText(f"[Error] {error}")
        self._reset_buttons()

    def _reset_buttons(self):
        self.social_write_btn.setEnabled(True)
        self.social_stop_btn.setEnabled(False)
        self.social_stop_btn.hide()

    def stop(self):
        # ChatWorker has cancel(), not stop().
        if self.host.social_worker is not None:
            self.host.social_worker.cancel()
        token, self._write_token = self._write_token, None
        if token:
            self.host.abandon_request(token, reason="stopped")
        self._reset_buttons()

    # ── clips, via the Video pipeline ───────────────────────────────────
    def make_clip(self):
        """Ask the Video mode for a clip sized for this platform.

        Social owns no rendering of its own. It writes a topic brief and hands
        it to the same `produce()` the Video tab uses, with the platform's
        aspect and a short length — which is why adding video to social cost a
        brief-writing prompt rather than a second video pipeline.
        """
        from agents.video import video_studio

        campaign = self.current_campaign()
        if not campaign:
            QMessageBox.warning(self, "No Campaign", "Create a campaign first.")
            return
        if not video_studio.available():
            QMessageBox.warning(self, "Video Unavailable",
                                video_studio.unavailable_reason())
            return
        platform = self._platform()
        if "clip" not in platform.formats:
            QMessageBox.information(
                self, "Not a video platform",
                f"{platform.name} does not take video posts.")
            return

        provider = self.social_provider_box.currentText()
        model = self.social_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Pick a model first.")
            return

        seconds = 30
        messages = build_clip_brief_messages(campaign, platform, seconds,
                                             self.social_notes_input.text().strip())
        token = self.host.authorize_request("social", provider, model,
                                            messages[-1]["content"],
                                            label="clip brief")
        if not token:
            return
        self._brief_token = token

        self.social_write_btn.setEnabled(False)
        self.social_clip_btn.setEnabled(False)
        self.social_status_label.setText("Writing the clip brief…")
        self._pending_clip = (platform.key, seconds)

        worker = self.host._new_chat_worker(provider, model, messages, "")
        self.host.social_worker = worker
        worker.finished_signal.connect(self._on_clip_brief)
        worker.usage_signal.connect(
            lambda u, t=token: self.host.note_request_usage(t, u))
        worker.error_signal.connect(self._on_clip_error)
        worker.start()

    def _on_clip_brief(self, brief: str):
        from agents.video import video_studio
        from services.per_unit_pricing import eur_per_usd
        from ui.workers import VideoWorker

        token, self._brief_token = self._brief_token, None
        if token:
            self.host.record_request(token, brief)
        platform_key, seconds = self._pending_clip
        topic = brief.strip().split("\n")[0][:300]

        aspect = ("Square 1:1" if platform_key == "pinterest"
                  else "Vertical 9:16")
        overrides = video_studio.clip_overrides(aspect, seconds)
        estimate = video_studio.pre_estimate(video_studio.load_config(overrides))
        cost_eur = round(estimate["total"] * eur_per_usd(), 4)

        confirm = QMessageBox.question(
            self, "Render this clip?",
            f"Topic:\n{topic}\n\n{aspect}, {seconds}s, "
            f"{estimate['scenes']} scenes — about €{cost_eur:.2f}.\n\nRender it?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if confirm != QMessageBox.Yes:
            self.social_status_label.setText("Clip cancelled")
            self._clip_done()
            return

        # A "video"-keyed request from Social: keeping the token is what
        # stops a concurrent Video-tab failure from popping this render's
        # pending context (and vice versa).
        video_token = self.host.authorize_request(
            "video", "openai", "vidforge-pipeline", topic,
            label=f"{platform_key} clip", flat_cost_eur=cost_eur)
        if not video_token:
            self._clip_done()
            return
        self._clip_video_token = video_token

        self.social_status_label.setText("Rendering clip — see the Video tab")
        self.host.social_worker = None
        clip_worker = VideoWorker(topic=topic, overrides=overrides)
        self.host._social_clip_worker = clip_worker
        clip_worker.progress_signal.connect(
            lambda pct, detail: self.social_status_label.setText(
                f"Rendering clip… {pct}%"))
        clip_worker.done_signal.connect(self._on_clip_rendered)
        clip_worker.error_signal.connect(self._on_clip_error)
        clip_worker.start()

    def _on_clip_rendered(self, slug: str, path: str):
        from agents.social import store
        token, self._clip_video_token = self._clip_video_token, None
        if token:
            self.host.record_request(token, f"social clip {slug}")
        campaign = self.current_campaign()
        platform_key, _seconds = self._pending_clip
        if campaign:
            store.add_post(
                campaign["id"], platform_key,
                self.social_draft_box.toPlainText().strip(),
                fmt="clip", media_path=path,
                angle=self.social_angle_box.currentText())
            self.refresh_schedule()
        self.social_status_label.setText(f"Clip ready — {Path(path).name}")
        self._clip_done()
        self.host.refresh_video_library()

    def _on_clip_error(self, error: str):
        # The error can arrive from either stage: brief (its token pending)
        # or render (the video token pending). Abandon exactly what this
        # flow authorized, never by agent name.
        for attr in ("_brief_token", "_clip_video_token"):
            token = getattr(self, attr)
            setattr(self, attr, None)
            if token:
                self.host.abandon_request(token)
        self.social_status_label.setText(f"[Error] {error}")
        self._clip_done()

    def _clip_done(self):
        self.social_write_btn.setEnabled(True)
        self.social_clip_btn.setEnabled(True)

    # ── drafts and schedule ─────────────────────────────────────────────
    def save_draft(self):
        """Split the editor on its variant separators and store each as a post."""
        from agents.social import store
        campaign = self.current_campaign()
        if not campaign:
            QMessageBox.warning(self, "No Campaign", "Create a campaign first.")
            return
        text = self.social_draft_box.toPlainText().strip()
        if not text:
            return
        platform = self._platform()
        pieces = [p.strip() for p in text.split("—" * 30)]
        pieces = [p for p in pieces if p]
        for piece in pieces:
            store.add_post(campaign["id"], platform.key, piece,
                                  fmt="text", angle=self.social_angle_box.currentText())
        self.refresh_schedule()
        self.social_tabs.setCurrentIndex(1)
        self.social_status_label.setText(
            f"{len(pieces)} post(s) saved to the schedule")

    def schedule_drafts(self):
        """Give every undated draft a date at its platform's own cadence."""
        from datetime import date

        from agents.social import store
        campaign = self.current_campaign()
        if not campaign:
            return
        undated = [p for p in store.list_posts(campaign["id"])
                   if not p.get("scheduled_for")]
        if not undated:
            self.social_status_label.setText("Nothing undated to schedule")
            return

        platforms = sorted({p["platform"] for p in undated})
        slots = store.build_schedule(platforms, weeks=4,
                                            start=date.today())
        by_platform: dict[str, list] = {}
        for day, platform_key in slots:
            by_platform.setdefault(platform_key, []).append(day)

        scheduled = 0
        for post in undated:
            days = by_platform.get(post["platform"], [])
            if not days:
                continue
            store.update_post(post["id"],
                                     scheduled_for=days.pop(0).isoformat(),
                                     status="scheduled")
            scheduled += 1
        self.refresh_schedule()
        self.social_status_label.setText(f"{scheduled} post(s) scheduled")

    def refresh_schedule(self):
        from agents.social import platforms, store
        campaign = self.current_campaign()
        posts = store.list_posts(campaign["id"]) if campaign else []
        self.social_schedule_table.setRowCount(0)
        for post in posts:
            row = self.social_schedule_table.rowCount()
            self.social_schedule_table.insertRow(row)
            platform = platforms.get(post["platform"])
            body = " ".join(post["body"].split())
            values = [
                post.get("scheduled_for") or "—",
                platform.name if platform else post["platform"],
                post.get("format", "text"),
                body[:120] + ("…" if len(body) > 120 else ""),
                post.get("status", "draft"),
                post.get("permalink") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, post["id"])
                self.social_schedule_table.setItem(row, column, item)
        self.refresh_analytics(posts)

    def refresh_analytics(self, posts: list[dict] | None = None):
        from agents.social import store
        if posts is None:
            campaign = self.current_campaign()
            posts = store.list_posts(campaign["id"]) if campaign else []
        self.social_analytics_table.setRowCount(0)
        for post in posts:
            if post["status"] != "posted" or not post.get("metric_source"):
                continue
            reach, clicks = int(post["reach"]), int(post["clicks"])
            rate = f"{clicks / reach:.1%}" if reach else "—"
            values = (post["platform"], post.get("angle") or "—",
                      f"{reach:,}", f"{clicks:,}", rate,
                      f"{post['metric_source']} · {post['metric_window']}")
            row = self.social_analytics_table.rowCount()
            self.social_analytics_table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.social_analytics_table.setItem(row, column, item)

    def record_metrics(self):
        from agents.social import store
        post = self._selected_post()
        if not post:
            QMessageBox.information(self, "Select a post",
                                    "Select a posted row in Schedule first.")
            return
        if post["status"] != "posted":
            QMessageBox.information(self, "Not posted",
                                    "Only posted items have observed metrics.")
            return
        reach, ok = QInputDialog.getInt(
            self, "Record reach", "Unique accounts reached:",
            int(post["reach"]), 0, 1_000_000_000)
        if not ok:
            return
        clicks, ok = QInputDialog.getInt(
            self, "Record clicks", "Link clicks:",
            int(post["clicks"]), 0, 1_000_000_000)
        if not ok:
            return
        source, ok = QInputDialog.getText(
            self, "Metric source", "Platform report or export:",
            text=post["metric_source"])
        if not ok:
            return
        window, ok = QInputDialog.getText(
            self, "Measurement window", "For example 2026-09-01 to 2026-09-07:",
            text=post["metric_window"])
        if not ok:
            return
        try:
            store.record_metrics(post["id"], reach=reach, clicks=clicks,
                                        source=source, window=window)
        except ValueError as exc:
            QMessageBox.warning(self, "Metrics not saved", str(exc))
            return
        self.refresh_schedule()
        self.social_tabs.setCurrentIndex(2)

    def _selected_post(self) -> dict | None:
        from agents.social import store
        row = self.social_schedule_table.currentRow()
        if row < 0:
            return None
        item = self.social_schedule_table.item(row, 0)
        post_id = item.data(Qt.UserRole) if item else None
        return store.get_post(post_id) if post_id else None

    def copy_selected(self):
        post = self._selected_post()
        if not post:
            return
        QApplication.clipboard().setText(post["body"])
        self.social_status_label.setText("Copied")

    def mark_posted(self):
        from agents.social import store
        post = self._selected_post()
        if not post:
            return
        store.mark_posted(post["id"])
        self.refresh_schedule()

    def delete_post(self):
        from agents.social import store
        post = self._selected_post()
        if not post:
            return
        store.delete_post(post["id"])
        self.refresh_schedule()

    def post_selected(self):
        """Publish one post. Never more than one, never unattended."""
        from agents.social import platforms, publishing, store

        post = self._selected_post()
        if not post:
            return
        platform = platforms.get(post["platform"])
        publisher = publishing.publisher_for(post["platform"])
        if publisher is None or not publisher.configured:
            QMessageBox.information(
                self, f"{platform.name if platform else post['platform']} cannot post",
                (publisher.why_not() if publisher else platform.posting_note))
            return

        extra: dict = {}
        if post["platform"] == "reddit":
            subreddit, ok = QInputDialog.getText(
                self, "Subreddit", "Post to which subreddit? (without r/)")
            if not ok or not subreddit.strip():
                return
            title, ok = QInputDialog.getText(self, "Title", "Post title:")
            if not ok or not title.strip():
                return
            extra = {"subreddit": subreddit.strip(), "title": title.strip()}
        elif post["platform"] == "pinterest":
            board_id, ok = QInputDialog.getText(self, "Board", "Pinterest board id:")
            if not ok or not board_id.strip():
                return
            extra = {"board_id": board_id.strip(),
                     "link": (self.social_links_input.text().strip() or "")}
        elif post["platform"] == "youtube":
            title, ok = QInputDialog.getText(self, "Title", "Video title:")
            if not ok or not title.strip():
                return
            extra = {"title": title.strip(), "privacy": "private"}

        confirm = QMessageBox.question(
            self, "Post now?",
            f"This publishes to {platform.name if platform else post['platform']} "
            f"from your own account, immediately.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        self.social_status_label.setText("Posting…")
        try:
            result = publisher.publish(post["body"], post.get("media_path", ""),
                                       **extra)
        except Exception as exc:
            store.mark_failed(post["id"], str(exc))
            self.refresh_schedule()
            QMessageBox.warning(self, "Post failed", str(exc))
            self.social_status_label.setText("[Error] post failed")
            return
        store.mark_posted(post["id"], result.permalink)
        self.refresh_schedule()
        self.social_status_label.setText(f"Posted — {result.permalink or 'done'}")

    def refresh_accounts(self):
        """What can post today, and what stands in the way of the rest."""
        from agents.social import publishing

        rows = []
        for name, ready, note in publishing.status_lines():
            colour = ACCENT if ready else TEXT_MUTE
            label = "ready" if ready else "drafting only"
            rows.append(
                f"<p style='margin:0 0 10px 0'>"
                f"<b style='color:{colour}'>{name}</b> "
                f"<span style='color:{TEXT_MUTE}'>— {label}</span><br>"
                f"<span style='color:{TEXT_DIM}'>{note}</span></p>")
        self.social_accounts_box.setHtml(
            f"<div style='color:{TEXT_DIM}; font-size:12px'>"
            "<p style='margin:0 0 14px 0'>Writing works for every platform "
            "below. Posting works for the ones marked ready — the rest need an "
            "app review, a business account or a paid tier that this app "
            "cannot obtain on your behalf.</p>"
            + "".join(rows) + "</div>")
