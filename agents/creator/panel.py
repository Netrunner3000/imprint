"""Brand Creator workspace and its guarded drafting/teaser lifecycles.

Phase 4 extraction: the profile form, compose controls and the seven tabs
(Draft, Calendar, Earnings, Voice, Media, Agency, Records) and every
handler moved here from main.py. The host supplies shared budget
authorization, usage records, the chat-worker factory, `_note_failure`
and the Higgsfield permission checkbox; the workers stay host attributes
so the umbrella's shutdown sweep keeps seeing them.

Request tokens live on this panel: "creator" is shared by the text
drafting flow and the Higgsfield teaser (whose token rides in its own
job context), so nothing here resolves a request by agent name.
"""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from agents.creator import ConsentError, PROMO_CHANNELS
from services.creator_csv import ingest_creator_csv
from services.creator_insights import (
    account_summary, agency_overview, asset_outcomes, hook_results,
    price_history, price_points, record_outcome, record_revenue, top_content,
)
from services.creator_platform_policy import get_policy, save_policy
from services.creator_profile import (
    load_persona, load_voice, reference_images, save_persona, save_voice,
)
from services.database import get_connection
from services.higgsfield_client import (
    ContentPolicyError, HiggsfieldClient, check_prompt,
)
from services.runtime_paths import user_data_base
from ui.creator_earnings import CreatorEarningsView
from ui.creator_outcome_dialog import CreatorOutcomeDialog
from ui.creator_policy_dialog import CreatorPolicyDialog
from ui.forms import LG, MD, SM, combo, field, line_edit, primary, quiet, section
from ui.panels.base import AgentPanel
from ui.widgets import scrollable


class CreatorPanel(QWidget):
    """Profiles, consent-aware drafting, and the evidence tabs around them."""

    HOST_CONTROLS = (
        "creator_account_box", "creator_handle_input", "creator_platform_box",
        "creator_type_box", "creator_consent_input", "creator_disclosure_input",
        "creator_consent_field", "creator_disclosure_field",
        "creator_save_account_btn", "creator_delete_account_btn",
        "creator_policy_status", "creator_policy_btn", "creator_kind_box",
        "creator_price_input", "creator_segment_box", "creator_channel_box",
        "creator_campaign_input", "creator_price_field",
        "creator_segment_field", "creator_channel_field",
        "creator_campaign_field", "creator_compose_grid", "creator_kind_field",
        "creator_brief_input", "creator_panel_base", "creator_provider_box",
        "creator_model_box", "creator_generate_btn", "creator_schedule_btn",
        "creator_video_btn", "creator_video_cancel_btn", "creator_stop_btn",
        "creator_status_label", "creator_video_status", "creator_tabs",
        "creator_output", "creator_calendar_table", "creator_earnings_view",
        "creator_revenue_btn", "creator_import_btn", "creator_voice_tab",
        "creator_media_table", "creator_add_media_btn", "creator_agency_table",
        "creator_records_table", "creator_add_performer_btn",
        "creator_voice_samples", "creator_voice_tone", "creator_voice_emoji",
        "creator_voice_length", "creator_voice_banned",
        "creator_persona_group", "creator_persona_appearance",
        "creator_persona_backstory", "creator_persona_personality",
        "creator_persona_boundaries", "creator_persona_seed",
    )

    def __init__(self, host):
        super().__init__()
        self.host = host
        self._draft_token = None
        self._last_generation_cost_eur = 0.0
        self._calendar_ids: list = []
        self._video_context: dict = {}
        self.setObjectName("CreatorPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        # ── Account ─────────────────────────────────────────────────────
        layout.addWidget(section("Content profile"))

        self.creator_account_box = QComboBox()
        self.creator_account_box.currentIndexChanged.connect(self._account_changed)
        self.creator_handle_input = line_edit("@handle")
        self.creator_platform_box = combo([
            "General", "OnlyFans", "Writing / Publishing", "Music",
            "AltMerch", "Instagram", "TikTok", "X / Twitter", "Reddit",
            "YouTube", "Other",
        ], "General")
        self.creator_platform_box.currentTextChanged.connect(
            self._update_policy_status)
        self.creator_type_box = combo(["own", "managed", "persona"])
        self.creator_type_box.currentTextChanged.connect(self._type_changed)
        self.creator_consent_input = line_edit("Who authorised this, and when")
        self.creator_disclosure_input = line_edit(
            "How the account discloses it is a synthetic persona")

        # The whole field hides, not just its input: hiding a control while
        # leaving its label behind is what produced orphaned "Authorised by:"
        # captions above nothing.
        self.creator_consent_field = field("Authorised by", self.creator_consent_input)
        self.creator_disclosure_field = field("Disclosure", self.creator_disclosure_input)

        account = QGridLayout()
        account.setHorizontalSpacing(MD)
        account.setVerticalSpacing(MD)
        account.addWidget(field("Profile", self.creator_account_box), 0, 0, Qt.AlignTop)
        account.addWidget(field("Handle / project", self.creator_handle_input), 0, 1, Qt.AlignTop)
        account.addWidget(field("Platform / venture", self.creator_platform_box), 0, 2, Qt.AlignTop)
        account.addWidget(field("Ownership", self.creator_type_box), 1, 0, Qt.AlignTop)
        account.addWidget(self.creator_consent_field, 1, 1, Qt.AlignTop)
        account.addWidget(self.creator_disclosure_field, 1, 2, Qt.AlignTop)
        for column in range(3):
            account.setColumnStretch(column, 1)
        layout.addLayout(account)

        account_actions = QHBoxLayout()
        account_actions.setSpacing(SM)
        self.creator_save_account_btn = QPushButton("Save Profile")
        self.creator_save_account_btn.clicked.connect(self.save_account)
        account_actions.addWidget(self.creator_save_account_btn)
        self.creator_delete_account_btn = quiet("Remove profile")
        self.creator_delete_account_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.creator_delete_account_btn.clicked.connect(self.delete_account)
        account_actions.addWidget(self.creator_delete_account_btn)
        account_actions.addStretch()
        layout.addLayout(account_actions)

        policy_row = QHBoxLayout()
        self.creator_policy_status = QLabel("")
        self.creator_policy_status.setObjectName("EstimateLine")
        self.creator_policy_status.setWordWrap(True)
        policy_row.addWidget(self.creator_policy_status, 1)
        self.creator_policy_btn = quiet("Review platform policy")
        self.creator_policy_btn.clicked.connect(self.review_policy)
        policy_row.addWidget(self.creator_policy_btn)
        layout.addLayout(policy_row)
        self._update_policy_status(self.creator_platform_box.currentText())

        # ── Compose ─────────────────────────────────────────────────────
        layout.addWidget(section("Compose"))

        self.creator_kind_box = combo(
            ["post", "caption", "campaign", "posting_plan", "promo_assets",
             "hooks", "bio", "ppv", "welcome", "promo"])
        self.creator_kind_box.currentTextChanged.connect(self._kind_changed)
        self.creator_price_input = line_edit("12.00")
        self.creator_segment_box = combo(
            ["(any)", "new", "loyal", "lapsed", "big_spender"])
        self.creator_channel_box = combo(list(PROMO_CHANNELS))
        for _extra_channel in ("OnlyFans", "Website", "Email", "Other"):
            self.creator_channel_box.addItem(_extra_channel)
        self.creator_campaign_input = line_edit("Campaign or test name")

        self.creator_price_field = field("Price (USD)", self.creator_price_input)
        self.creator_segment_field = field("Audience", self.creator_segment_box)
        self.creator_channel_field = field("Channel", self.creator_channel_box)
        self.creator_campaign_field = field("Campaign", self.creator_campaign_input)

        # Three of these four fields only apply to some kinds of post, so the
        # grid is re-packed when the kind changes. Simply hiding a cell leaves
        # a hole in the row — which is the same "nothing lines up" complaint,
        # produced by an empty cell instead of a misplaced one.
        self.creator_compose_grid = QGridLayout()
        self.creator_compose_grid.setHorizontalSpacing(MD)
        self.creator_compose_grid.setVerticalSpacing(MD)
        self.creator_kind_field = field("Kind", self.creator_kind_box)
        for column in range(3):
            self.creator_compose_grid.setColumnStretch(column, 1)
        layout.addLayout(self.creator_compose_grid)

        self.creator_brief_input = QTextEdit()
        self.creator_brief_input.setPlaceholderText(
            "What is this about? The more concrete, the less generic the draft.")
        self.creator_brief_input.setFixedHeight(70)
        layout.addWidget(field("Brief", self.creator_brief_input))

        self.creator_panel_base = AgentPanel(
            host, "creator",
            providers=("anthropic", "openai", "deepseek", "kimi", "gemini", "qwen"),
            default_provider="anthropic")
        self.creator_provider_box = self.creator_panel_base.provider_box
        self.creator_model_box = self.creator_panel_base.model_box

        models = QGridLayout()
        models.setHorizontalSpacing(MD)
        models.setVerticalSpacing(MD)
        models.addWidget(field("Provider", self.creator_provider_box), 0, 0, Qt.AlignTop)
        models.addWidget(field("Model", self.creator_model_box), 0, 1, Qt.AlignTop)
        for column in range(3):
            models.setColumnStretch(column, 1)
        layout.addLayout(models)

        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.creator_generate_btn = primary("Draft")
        self.creator_generate_btn.setMinimumWidth(160)
        self.creator_generate_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.creator_generate_btn.clicked.connect(self.generate)
        actions.addWidget(self.creator_generate_btn)

        self.creator_schedule_btn = QPushButton("Add to Calendar")
        self.creator_schedule_btn.clicked.connect(self.schedule)
        actions.addWidget(self.creator_schedule_btn)

        self.creator_video_btn = QPushButton("Generate Teaser")
        self.creator_video_btn.setToolTip(
            "Render a promo teaser with Higgsfield. Paid, and subject to their "
            "content rules.")
        self.creator_video_btn.clicked.connect(self.generate_video)
        actions.addWidget(self.creator_video_btn)

        self.creator_video_cancel_btn = QPushButton("Cancel Teaser")
        self.creator_video_cancel_btn.setObjectName("DangerAction")
        self.creator_video_cancel_btn.clicked.connect(self.cancel_video)
        self.creator_video_cancel_btn.hide()
        actions.addWidget(self.creator_video_cancel_btn)

        self.creator_stop_btn = QPushButton("Stop")
        self.creator_stop_btn.setObjectName("DangerAction")
        self.creator_stop_btn.clicked.connect(self.stop)
        self.creator_stop_btn.hide()
        actions.addWidget(self.creator_stop_btn)

        actions.addStretch()
        self.creator_status_label = QLabel("")
        self.creator_status_label.setObjectName("EstimateLine")
        actions.addWidget(self.creator_status_label)
        layout.addLayout(actions)

        self.creator_video_status = QLabel("")
        self.creator_video_status.setObjectName("EstimateLine")
        self.creator_video_status.setWordWrap(True)
        layout.addWidget(self.creator_video_status)

        # ── Tabs ────────────────────────────────────────────────────────
        self.creator_tabs = QTabWidget()

        self.creator_output = QTextEdit()
        self.creator_output.setPlaceholderText(
            "Drafts appear here, fully editable. Nothing is sent anywhere — "
            "review it, then post it yourself.")
        self.creator_tabs.addTab(self.creator_output, "Draft")

        self.creator_calendar_table = QTableWidget(0, 5)
        self.creator_calendar_table.setHorizontalHeaderLabels(
            ["When", "Kind", "Title", "$", "Status"])
        self.creator_calendar_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self.creator_tabs.addTab(self.creator_calendar_table, "Calendar")

        self.creator_earnings_view = CreatorEarningsView()
        self.creator_revenue_btn = QPushButton("Record outcome")
        self.creator_revenue_btn.setToolTip(
            "Select an asset in Calendar first, then record its observed results and costs.")
        self.creator_revenue_btn.clicked.connect(self.record_outcome)
        self.creator_import_btn = QPushButton("Import Earnings CSV")
        self.creator_import_btn.clicked.connect(self.import_earnings)
        self.creator_tabs.addTab(
            self._tab_with_actions(
                self.creator_earnings_view,
                [self.creator_import_btn, self.creator_revenue_btn]),
            "Earnings")

        self.creator_voice_tab = self._build_voice_tab()
        self.creator_tabs.addTab(self.creator_voice_tab, "Voice")

        self.creator_media_table = QTableWidget(0, 4)
        self.creator_media_table.setHorizontalHeaderLabels(
            ["File", "Kind", "Source", "Caption"])
        self.creator_media_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.creator_add_media_btn = QPushButton("Add Media")
        self.creator_add_media_btn.clicked.connect(self.add_media)
        self.creator_tabs.addTab(
            self._tab_with_actions(
                self.creator_media_table, [self.creator_add_media_btn]),
            "Media")

        self.creator_agency_table = QTableWidget(0, 6)
        self.creator_agency_table.setHorizontalHeaderLabels(
            ["Account", "Type", "Authorised by", "Net $", "Subs", "Drafts"])
        self.creator_agency_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.creator_tabs.addTab(self.creator_agency_table, "Agency")

        self.creator_records_table = QTableWidget(0, 5)
        self.creator_records_table.setHorizontalHeaderLabels(
            ["Performer", "Verified", "ID on file", "Release", "Records held at"])
        self.creator_records_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.creator_add_performer_btn = QPushButton("Add Performer Record")
        self.creator_add_performer_btn.clicked.connect(self.add_performer)
        self.creator_tabs.addTab(
            self._tab_with_actions(
                self.creator_records_table, [self.creator_add_performer_btn]),
            "Records")

        layout.addWidget(self.creator_tabs, 1)

        # Aliases retired 2026-09-21: shared wiring resolves controls
        # through host._find_control(); HOST_CONTROLS stays as the
        # published contract of what this panel owns.
        host.creator_panel = self
        host.creator_worker = None
        host.creator_video_estimate_worker = None
        host.creator_video_worker = None
        self.hide()
        self._type_changed(self.creator_type_box.currentText())
        self._kind_changed(self.creator_kind_box.currentText())
        self.refresh_accounts()

    @staticmethod
    def _tab_with_actions(body: QWidget, buttons: list) -> QWidget:
        """A tab page: its content, and the buttons that act on that content.

        Putting "Add Media" next to the media table is the difference between
        a button you can find and one of eight in a column labelled nothing.
        """
        page = QWidget()
        page.setObjectName("Transparent")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(MD, MD, MD, MD)
        page_layout.setSpacing(MD)
        page_layout.addWidget(body, 1)
        row = QHBoxLayout()
        row.setSpacing(SM)
        row.addStretch()
        for button in buttons:
            row.addWidget(button)
        page_layout.addLayout(row)
        return page

    def _build_voice_tab(self) -> QWidget:
        """Voice profile, and the persona bible for persona accounts.

        Voice is the single biggest lever on how the drafts read: samples of
        the creator's own writing are what the model imitates, and without them
        every draft starts from nothing.
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(QLabel(
            "Paste a few of this account's own posts. The model imitates these "
            "— it is what stops drafts reading like generic AI copy."))
        self.creator_voice_samples = QTextEdit()
        self.creator_voice_samples.setPlaceholderText(
            "One post per line — five or six is plenty.")
        layout.addWidget(self.creator_voice_samples, 1)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.addWidget(QLabel("Tone:"), 0, 0)
        self.creator_voice_tone = QLineEdit()
        self.creator_voice_tone.setPlaceholderText("dry, warm, a bit deadpan")
        grid.addWidget(self.creator_voice_tone, 0, 1)
        grid.addWidget(QLabel("Emoji:"), 0, 2)
        self.creator_voice_emoji = QLineEdit()
        self.creator_voice_emoji.setPlaceholderText("sparse — one at most")
        grid.addWidget(self.creator_voice_emoji, 0, 3)
        grid.addWidget(QLabel("Length:"), 1, 0)
        self.creator_voice_length = QLineEdit()
        self.creator_voice_length.setPlaceholderText("1–2 short sentences")
        grid.addWidget(self.creator_voice_length, 1, 1)
        grid.addWidget(QLabel("Never say:"), 1, 2)
        self.creator_voice_banned = QLineEdit()
        self.creator_voice_banned.setPlaceholderText("babe, hun, 🔥")
        grid.addWidget(self.creator_voice_banned, 1, 3)
        layout.addLayout(grid)

        # Persona bible — shown only for persona accounts.
        self.creator_persona_group = QGroupBox("Character bible (persona accounts)")
        pg = QGridLayout(self.creator_persona_group)
        pg.setSpacing(6)
        pg.addWidget(QLabel("Appearance:"), 0, 0)
        self.creator_persona_appearance = QLineEdit()
        self.creator_persona_appearance.setPlaceholderText(
            "Locked description — reused in every render so it stays the same character")
        pg.addWidget(self.creator_persona_appearance, 0, 1, 1, 3)
        pg.addWidget(QLabel("Backstory:"), 1, 0)
        self.creator_persona_backstory = QLineEdit()
        pg.addWidget(self.creator_persona_backstory, 1, 1, 1, 3)
        pg.addWidget(QLabel("Personality:"), 2, 0)
        self.creator_persona_personality = QLineEdit()
        pg.addWidget(self.creator_persona_personality, 2, 1, 1, 3)
        pg.addWidget(QLabel("Never does:"), 3, 0)
        self.creator_persona_boundaries = QLineEdit()
        pg.addWidget(self.creator_persona_boundaries, 3, 1, 1, 3)
        pg.addWidget(QLabel("Seed:"), 4, 0)
        self.creator_persona_seed = QLineEdit()
        self.creator_persona_seed.setPlaceholderText("e.g. 4821 — keeps renders on-model")
        self.creator_persona_seed.setMaximumWidth(120)
        pg.addWidget(self.creator_persona_seed, 4, 1)
        layout.addWidget(self.creator_persona_group)

        save_btn = QPushButton("Save Voice && Character")
        save_btn.setObjectName("PrimaryAction")
        save_btn.clicked.connect(self.save_voice)
        layout.addWidget(save_btn)
        return page

    # ── profile form ────────────────────────────────────────────────────
    def load_models(self) -> None:
        self.creator_panel_base.load_models()

    def _type_changed(self, account_type: str):
        """Consent fields matter for managed accounts; disclosure for personas."""
        is_managed = account_type == "managed"
        is_persona = account_type == "persona"
        self.creator_consent_field.setVisible(is_managed)
        self.creator_disclosure_field.setVisible(is_persona)

    def _update_policy_status(self, platform: str):
        if not hasattr(self, "creator_policy_status"):
            return
        policy = get_policy(platform)
        review = policy["reviewed_on"] or "not reviewed"
        self.creator_policy_status.setText(
            f"{platform} policy · {review} · synthetic personas: "
            f"{policy['synthetic_persona']} · publishing: "
            f"{policy['publishing_method'].replace('_', ' ')}")

    def review_policy(self):
        platform = self.creator_platform_box.currentText()
        dialog = CreatorPolicyDialog(platform, get_policy(platform), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            save_policy(platform, **dialog.values())
        except ValueError as exc:
            QMessageBox.warning(self, "Policy not saved", str(exc))
            return
        self._update_policy_status(platform)

    def _kind_changed(self, kind: str):
        # Which fields apply, in the order they should appear. Kind is always
        # shown; the other three depend on it.
        wanted = [
            (self.creator_kind_field, True),
            (self.creator_campaign_field, True),
            (self.creator_channel_field, True),
            (self.creator_price_field, kind == "ppv"),
            # Audience only shapes a message aimed at someone.
            (self.creator_segment_field, kind in ("welcome", "ppv", "post", "caption")),
        ]
        self._reflow_compose(wanted)

    def _reflow_compose(self, wanted: list) -> None:
        """Re-pack the compose grid so only applicable fields take a cell.

        Visibility is passed in rather than read back off the widgets: a widget
        that has never been shown reports isHidden() as True, so asking the
        widgets themselves emptied the grid on the first call.
        """
        grid = self.creator_compose_grid
        index = 0
        for widget, visible in wanted:
            grid.removeWidget(widget)
            widget.setVisible(visible)
            if not visible:
                continue
            grid.addWidget(widget, index // 3, index % 3, Qt.AlignTop)
            index += 1

    # ── accounts ────────────────────────────────────────────────────────
    def refresh_accounts(self):
        self.creator_account_box.blockSignals(True)
        self.creator_account_box.clear()
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, handle, platform, account_type FROM creator_accounts "
                    "ORDER BY handle").fetchall()
            for row in rows:
                self.creator_account_box.addItem(
                    f"{row['handle']}  ({row['platform']} · {row['account_type']})",
                    row["id"])
        except Exception as exc:
            self.host._note_failure("creator: load accounts", exc)
        self.creator_account_box.blockSignals(False)
        if self.creator_account_box.count():
            self._account_changed(self.creator_account_box.currentIndex())

    def _account_changed(self, index: int):
        account = self.current_account()
        if not account:
            return
        self.creator_handle_input.setText(account.get("handle", ""))
        platform = account.get("platform", "General") or "General"
        platform_index = self.creator_platform_box.findText(
            platform, Qt.MatchFixedString)
        if platform_index < 0 and platform.lower() == "onlyfans":
            platform_index = self.creator_platform_box.findText("OnlyFans")
        self.creator_platform_box.setCurrentIndex(max(0, platform_index))
        self.creator_type_box.setCurrentText(account.get("account_type", "own"))
        self.creator_consent_input.setText(account.get("consent_holder", ""))
        self.creator_disclosure_input.setText(account.get("disclosure", ""))
        self.refresh_calendar()
        self.refresh_earnings()
        self.load_voice_tab()
        self.refresh_media()
        self.refresh_records()
        self.refresh_agency()

    def current_account(self) -> dict | None:
        account_id = self.creator_account_box.currentData()
        if account_id is None:
            return None
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM creator_accounts WHERE id = ?",
                    (account_id,)).fetchone()
            return dict(row) if row else None
        except Exception as exc:
            self.host._note_failure("creator: read account", exc)
            return None

    def save_account(self):
        handle = self.creator_handle_input.text().strip()
        if not handle:
            QMessageBox.warning(
                self, "No Profile", "Enter a handle or project name first.")
            return
        account_type = self.creator_type_box.currentText()
        platform = self.creator_platform_box.currentText().strip() or "General"
        stored_platform = "onlyfans" if platform == "OnlyFans" else platform
        consent = self.creator_consent_input.text().strip()
        if account_type == "managed" and not consent:
            QMessageBox.warning(
                self, "Authorisation Required",
                "This account is marked as managed for someone else. Record "
                "who authorised it before saving — the drafting tools refuse "
                "to run for a managed account without it.")
            return
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO creator_accounts
                      (handle, platform, account_type, consent_holder,
                       consent_date, disclosure, created_at)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(handle) DO UPDATE SET
                      platform=excluded.platform,
                      account_type=excluded.account_type,
                      consent_holder=excluded.consent_holder,
                      disclosure=excluded.disclosure
                """, (handle, stored_platform, account_type, consent,
                      datetime.now().isoformat(timespec="seconds") if consent else "",
                      self.creator_disclosure_input.text().strip(),
                      datetime.now().isoformat(timespec="seconds")))
                conn.commit()
        except Exception as exc:
            self.host._note_failure("creator: save account", exc,
                                    self.creator_status_label)
            return
        self.creator_status_label.setText(f"Saved {handle}.")
        self.refresh_accounts()

    def delete_account(self):
        account = self.current_account()
        if not account:
            return
        confirm = QMessageBox.question(
            self, "Remove Profile",
            f"Remove {account['handle']} and its drafts and performance from "
            "Imprint?\n\nThis only affects this app — nothing on the platform "
            "is touched.")
        if confirm != QMessageBox.Yes:
            return
        try:
            with get_connection() as conn:
                conn.execute(
                    "DELETE FROM creator_variants WHERE content_id IN "
                    "(SELECT id FROM creator_content WHERE account_id = ?)",
                    (account["id"],))
                for table in (
                        "creator_video_jobs", "creator_media", "creator_voice",
                        "creator_persona", "creator_performers",
                        "creator_content", "creator_earnings"):
                    conn.execute(f"DELETE FROM {table} WHERE account_id = ?",
                                 (account["id"],))
                conn.execute("DELETE FROM creator_accounts WHERE id = ?",
                             (account["id"],))
                conn.commit()
        except Exception as exc:
            self.host._note_failure("creator: delete account", exc)
            return
        self.refresh_accounts()

    # ── drafting ────────────────────────────────────────────────────────
    def generate(self):
        account = self.current_account()
        if not account:
            QMessageBox.warning(self, "No Profile",
                                "Add a content profile before drafting.")
            return

        agent = self.host.agent_instances["creator"]
        kind = self.creator_kind_box.currentText()
        brief = self.creator_brief_input.toPlainText().strip()
        try:
            price = float(self.creator_price_input.text().strip() or 0)
        except ValueError:
            price = 0.0

        try:
            segment = self.creator_segment_box.currentText()
            messages = agent.build_draft_prompt(
                account, kind, brief, price_usd=price,
                channel=self.creator_channel_box.currentText(),
                segment="" if segment == "(any)" else segment,
                price_history=price_history(account["id"]))
        except ConsentError as exc:
            QMessageBox.warning(self, "Authorisation Required", str(exc))
            return
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot Draft", str(exc))
            return

        provider = self.creator_provider_box.currentText()
        model = self.creator_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Select a model first.")
            return
        # Keep the token: "creator" is shared with the Higgsfield teaser
        # flow, and resolving by name can bill the teaser's flat cost
        # against this text response (and leave the render unbilled).
        token = self.host.authorize_request("creator", provider, model,
                                            messages[-1]["content"], label=kind)
        if not token:
            return
        self._draft_token = token

        self.creator_generate_btn.setEnabled(False)
        self._last_generation_cost_eur = 0.0
        self.creator_stop_btn.setEnabled(True)
        self.creator_stop_btn.show()
        self.creator_status_label.setText(f"Drafting {kind}…")
        self.creator_output.clear()

        worker = self.host._new_chat_worker(provider, model, messages, "")
        self.host.creator_worker = worker
        worker.finished_signal.connect(self._on_finished)
        worker.error_signal.connect(self._on_error)
        worker.start()

    def _on_finished(self, response: str):
        self.creator_output.setPlainText(response)
        token, self._draft_token = self._draft_token, None
        if token:
            self.host.record_request(token, response)
        self._last_generation_cost_eur = float(self.host.last_request_cost or 0)
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText("Draft ready — review before posting.")

    def _on_error(self, error: str):
        token, self._draft_token = self._draft_token, None
        if token:
            self.host.abandon_request(token)
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText(f"[Error] {error}")

    def stop(self):
        # cancel(), never terminate(): killing a QThread that is inside a
        # Python call or holds the GIL is a crash/deadlock, and the worker
        # checks its flag at the next safe point anyway.
        worker = self.host.creator_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
        token, self._draft_token = self._draft_token, None
        if token:
            self.host.abandon_request(token, reason="stopped")
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText("Stopped.")

    # ── calendar ────────────────────────────────────────────────────────
    def schedule(self):
        account = self.current_account()
        body = self.creator_output.toPlainText().strip()
        if not account or not body:
            QMessageBox.warning(self, "Nothing to Schedule",
                                "Draft something first.")
            return
        when, ok = QInputDialog.getText(
            self, "Add to Calendar",
            "When should this go out? (free text — you post it yourself)")
        if not ok:
            return
        try:
            price = float(self.creator_price_input.text().strip() or 0)
        except ValueError:
            price = 0.0
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO creator_content
                      (account_id, created_at, scheduled_for, kind, title,
                       body, price_usd, status, campaign, channel,
                       generation_cost_eur)
                    VALUES (?,?,?,?,?,?,?,'draft',?,?,?)
                """, (account["id"],
                      datetime.now().isoformat(timespec="seconds"),
                      when.strip(),
                      self.creator_kind_box.currentText(),
                      body.splitlines()[0][:80] if body else "",
                      body, price,
                      self.creator_campaign_input.text().strip(),
                      self.creator_channel_box.currentText(),
                      float(self._last_generation_cost_eur)))
                conn.commit()
        except Exception as exc:
            self.host._note_failure("creator: schedule", exc,
                                    self.creator_status_label)
            return
        self.refresh_calendar()
        self.creator_tabs.setCurrentIndex(1)

    def refresh_calendar(self):
        account = self.current_account()
        self.creator_calendar_table.setRowCount(0)
        if not account:
            return
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, scheduled_for, kind, title, price_usd, status, "
                    "revenue_usd FROM creator_content WHERE account_id = ? "
                    "ORDER BY id DESC", (account["id"],)).fetchall()
        except Exception as exc:
            self.host._note_failure("creator: load calendar", exc)
            return
        # Row order maps to content ids so revenue can attach to a selection.
        self._calendar_ids = [row["id"] for row in rows]
        for row in rows:
            r = self.creator_calendar_table.rowCount()
            self.creator_calendar_table.insertRow(r)
            for col, value in enumerate([
                    row["scheduled_for"], row["kind"], row["title"],
                    f"{row['price_usd']:.2f}" if row["price_usd"] else "",
                    f"{row['status']}"
                    + (f"  (${row['revenue_usd']:,.2f})" if row["revenue_usd"] else "")]):
                self.creator_calendar_table.setItem(r, col, QTableWidgetItem(str(value)))

    # ── promo video ─────────────────────────────────────────────────────
    def generate_video(self):
        from ui.workers import HiggsfieldEstimateWorker

        account = self.current_account()
        if not account:
            QMessageBox.warning(self, "No Account", "Add an account first.")
            return
        agent = self.host.agent_instances["creator"]
        try:
            prompt = agent.build_video_prompt(
                account, self.creator_brief_input.toPlainText().strip())
        except ConsentError as exc:
            QMessageBox.warning(self, "Authorisation Required", str(exc))
            return

        client = HiggsfieldClient()
        if not client.configured:
            QMessageBox.information(
                self, "Higgsfield Key Needed",
                "Set both HF_API_KEY_ID and HF_API_KEY_SECRET in Imprint's "
                "private .env file to generate promo video.")
            return
        if not self.host.allow_higgsfield_checkbox.isChecked():
            QMessageBox.warning(
                self, "Higgsfield Not Enabled",
                "Enable Higgsfield in the API permissions row before sending "
                "a prompt or reference image to the service.")
            return
        try:
            check_prompt(prompt)
        except ContentPolicyError as exc:
            QMessageBox.warning(self, "Higgsfield Content Policy", str(exc))
            return

        # Reference media is uploaded during preparation because Higgsfield's
        # estimate endpoint accepts the exact generation payload, including its
        # public image URL. No paid generation starts until the estimate is
        # shown and the normal budget/approval guard accepts it.
        references = reference_images(account["id"])

        output_dir = user_data_base() / "output" / "creator" / str(account["id"])
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = output_dir / f"teaser-{stamp}.mp4"

        row = self.creator_calendar_table.currentRow()
        content_id = None
        if 0 <= row < len(self._calendar_ids):
            content_id = self._calendar_ids[row]

        self._video_context = {
            "account_id": account["id"],
            "content_id": content_id,
            "prompt": prompt,
            "output_path": str(output_path),
            "request_token": None,
            "job_id": "",
            "provider_completed": False,
            "cancel_requested": False,
        }

        self.creator_video_btn.setEnabled(False)
        self.creator_video_cancel_btn.setEnabled(True)
        self.creator_video_cancel_btn.show()
        self.creator_video_status.setText("Preparing Higgsfield estimate…")

        estimate_worker = HiggsfieldEstimateWorker(
            client, prompt, reference_image=references[0] if references else None)
        self.host.creator_video_estimate_worker = estimate_worker
        estimate_worker.status_signal.connect(self.creator_video_status.setText)
        estimate_worker.done_signal.connect(
            lambda request, estimate, c=client:
            self._video_estimated(c, request, estimate))
        estimate_worker.error_signal.connect(self._video_error)
        estimate_worker.start()

    def _video_estimated(self, client, request, estimate):
        """Show the provider's exact price before authorising generation."""
        from services.per_unit_pricing import eur_per_usd
        from ui.workers import HiggsfieldWorker

        context = self._video_context
        if not context:
            return
        if context.get("cancel_requested"):
            self._video_reset("Cancelled.")
            return
        cost_eur = round(estimate.usd * eur_per_usd(), 6)
        context.update({
            "endpoint": request.endpoint,
            "estimated_credits": estimate.credits,
            "estimated_usd": estimate.usd,
            "estimated_eur": cost_eur,
        })
        self.creator_video_status.setText(
            f"Estimated by Higgsfield: ${estimate.usd:.2f} "
            f"({estimate.credits:g} credits). Awaiting approval…")

        token = self.host.authorize_request(
            "creator", "higgsfield", request.endpoint,
            context["prompt"], label="promo teaser", flat_cost_eur=cost_eur)
        if not token:
            self._video_reset("Render not approved.")
            return
        context["request_token"] = token

        render_worker = HiggsfieldWorker(
            client, context["prompt"], context["output_path"],
            prepared_request=request)
        self.host.creator_video_worker = render_worker
        render_worker.status_signal.connect(self.creator_video_status.setText)
        render_worker.job_signal.connect(self._video_job_update)
        render_worker.done_signal.connect(
            lambda path, aid=context["account_id"]:
            self._video_done(aid, path))
        render_worker.error_signal.connect(self._video_error)
        render_worker.start()

    def cancel_video(self):
        """Cancel preparation, or ask Higgsfield to cancel a queued render."""
        if self._video_context:
            self._video_context["cancel_requested"] = True
        estimate_worker = self.host.creator_video_estimate_worker
        render_worker = self.host.creator_video_worker
        if estimate_worker is not None and estimate_worker.isRunning():
            estimate_worker.cancel()
            self.creator_video_status.setText("Cancelling estimate…")
        elif render_worker is not None and render_worker.isRunning():
            render_worker.cancel()
            self.creator_video_status.setText(
                "Cancellation requested. If rendering already began, "
                "Higgsfield will finish and Imprint will save the result.")
        self.creator_video_cancel_btn.setEnabled(False)

    def _video_job_update(self, job):
        """Persist every provider state transition for recovery and support."""
        context = self._video_context
        if not context:
            return
        context["job_id"] = job.job_id
        if job.status == "completed":
            context["provider_completed"] = True
        now = datetime.now().isoformat(timespec="seconds")
        policy_result = ("provider-rejected" if job.status == "nsfw"
                         else "local-approved")
        actual_usd = (context.get("estimated_usd")
                      if job.status == "completed" else None)
        cost_basis = ("provider preflight estimate; render completed"
                      if actual_usd is not None else "")
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO creator_video_jobs
                      (request_id, account_id, content_id, created_at, updated_at,
                       endpoint, prompt, prompt_version, estimated_credits,
                       estimated_usd, actual_usd, cost_basis, status,
                       policy_result, error, correlation_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(request_id) DO UPDATE SET
                      updated_at=excluded.updated_at,
                      actual_usd=COALESCE(excluded.actual_usd,
                                          creator_video_jobs.actual_usd),
                      cost_basis=CASE WHEN excluded.cost_basis != ''
                                      THEN excluded.cost_basis
                                      ELSE creator_video_jobs.cost_basis END,
                      status=excluded.status,
                      policy_result=excluded.policy_result,
                      error=excluded.error,
                      correlation_id=CASE WHEN excluded.correlation_id != ''
                                          THEN excluded.correlation_id
                                          ELSE creator_video_jobs.correlation_id END
                """, (
                    job.job_id, context["account_id"], context.get("content_id"),
                    now, now, job.endpoint or context.get("endpoint", ""),
                    context["prompt"], "creator-video-v1",
                    context.get("estimated_credits", 0.0),
                    context.get("estimated_usd", 0.0), actual_usd, cost_basis,
                    job.status, policy_result, job.error, job.correlation_id,
                ))
                conn.commit()
        except Exception as exc:
            self.host._note_failure("creator: track Higgsfield job", exc,
                                    self.creator_video_status)

    def _video_done(self, account_id: int, path: str):
        """Store the render in the media library rather than leaving it on disk."""
        context = self._video_context
        # Only ever by the token this flow authorized — never by the shared
        # "creator" name, which the drafting flow also uses.
        token = context.get("request_token")
        if token:
            self.host.record_request(token, f"teaser: {Path(path).name}")
        self._store_media(account_id, path, source="higgsfield",
                          job_id=context.get("job_id", ""),
                          caption="Higgsfield teaser")
        attached = False
        if context.get("content_id"):
            try:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE creator_content SET media_path = ? WHERE id = ?",
                        (path, context["content_id"]))
                    conn.execute(
                        "UPDATE creator_video_jobs SET local_path = ? "
                        "WHERE request_id = ?",
                        (path, context.get("job_id", "")))
                    conn.commit()
                attached = True
            except Exception as exc:
                self.host._note_failure("creator: attach teaser", exc,
                                        self.creator_video_status)
        elif context.get("job_id"):
            try:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE creator_video_jobs SET local_path = ? "
                        "WHERE request_id = ?",
                        (path, context["job_id"]))
                    conn.commit()
            except Exception as exc:
                self.host._note_failure("creator: save teaser path", exc,
                                        self.creator_video_status)
        note = f"Saved: {Path(path).name}"
        if attached:
            note += " · attached to the selected calendar item"
        self._video_reset(note)
        self.refresh_media()
        if attached:
            self.refresh_calendar()

    def _video_error(self, error: str):
        context = self._video_context
        token = context.get("request_token") if context else None
        if token:
            if context.get("provider_completed"):
                # A completed render is charged even if the local download
                # later fails; keep spend accounting honest.
                self.host.record_request(
                    token, f"render completed; local error: {error}")
            else:
                self.host.abandon_request(token)
        self._video_reset(f"[Error] {error}")

    def _video_reset(self, status: str):
        self.creator_video_btn.setEnabled(True)
        self.creator_video_cancel_btn.setEnabled(False)
        self.creator_video_cancel_btn.hide()
        self.creator_video_status.setText(status)

    # ── earnings ────────────────────────────────────────────────────────
    def import_earnings(self):
        """Import an earnings CSV exported from the platform.

        The same shape as the KDP importer, and for the same reason: no API, so
        the numbers only exist here once the statement is exported and read in.
        """
        account = self.current_account()
        if not account:
            QMessageBox.warning(self, "No Account", "Add an account first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Earnings CSV", "", "CSV files (*.csv)")
        if not path:
            return
        try:
            summary = ingest_creator_csv(account["id"], Path(path))
        except Exception as exc:
            self.host._note_failure("creator: import earnings", exc,
                                    self.creator_status_label)
            return
        self.creator_status_label.setText(
            f"Imported {summary['rows']} rows from {Path(path).name}.")
        self.refresh_earnings()
        self.creator_tabs.setCurrentIndex(2)

    def refresh_earnings(self):
        account = self.current_account()
        if not account:
            return
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT source_file, period_from, period_to, gross_usd, "
                    "net_usd, subscribers FROM creator_earnings "
                    "WHERE account_id = ? ORDER BY id DESC",
                    (account["id"],)).fetchall()
        except Exception as exc:
            self.host._note_failure("creator: load earnings", exc)
            return
        summary = account_summary(account["id"])
        # A user can record post revenue without importing a statement. Only
        # show the empty state when neither kind of evidence exists.
        if not rows and not summary["posted"]:
            self.creator_earnings_view.show_empty()
            return
        points = price_points(account["id"])
        best = top_content(account["id"])
        self.creator_earnings_view.set_data(
            summary, points, best, [dict(row) for row in rows],
            outcomes=asset_outcomes(account["id"]),
            hooks=hook_results(account["id"]))

    # ── voice and persona ───────────────────────────────────────────────
    def save_voice(self):
        account = self.current_account()
        if not account:
            QMessageBox.warning(self, "No Account", "Select an account first.")
            return
        save_voice(
            account["id"],
            samples=self.creator_voice_samples.toPlainText(),
            tone=self.creator_voice_tone.text(),
            emoji_style=self.creator_voice_emoji.text(),
            banned_words=self.creator_voice_banned.text(),
            typical_length=self.creator_voice_length.text(),
        )
        if account.get("account_type") == "persona":
            try:
                seed = int(self.creator_persona_seed.text().strip() or 0) or None
            except ValueError:
                seed = None
            save_persona(
                account["id"],
                appearance=self.creator_persona_appearance.text(),
                backstory=self.creator_persona_backstory.text(),
                personality=self.creator_persona_personality.text(),
                boundaries=self.creator_persona_boundaries.text(),
                seed=seed,
            )
        self.creator_status_label.setText("Voice saved — drafts will use it.")

    def load_voice_tab(self):
        account = self.current_account()
        if not account:
            return
        voice = load_voice(account["id"])
        self.creator_voice_samples.setPlainText(voice.get("samples", ""))
        self.creator_voice_tone.setText(voice.get("tone", ""))
        self.creator_voice_emoji.setText(voice.get("emoji_style", ""))
        self.creator_voice_banned.setText(voice.get("banned_words", ""))
        self.creator_voice_length.setText(voice.get("typical_length", ""))

        is_persona = account.get("account_type") == "persona"
        self.creator_persona_group.setVisible(is_persona)
        if is_persona:
            persona = load_persona(account["id"])
            self.creator_persona_appearance.setText(persona.get("appearance", ""))
            self.creator_persona_backstory.setText(persona.get("backstory", ""))
            self.creator_persona_personality.setText(persona.get("personality", ""))
            self.creator_persona_boundaries.setText(persona.get("boundaries", ""))
            seed = persona.get("seed")
            self.creator_persona_seed.setText(str(seed) if seed else "")

    # ── media library ───────────────────────────────────────────────────
    def add_media(self):
        account = self.current_account()
        if not account:
            QMessageBox.warning(self, "No Account", "Select an account first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Media", "",
            "Media (*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.m4a *.mp3)")
        if not paths:
            return
        for path in paths:
            self._store_media(account["id"], path, source="upload")
        self.refresh_media()
        self.creator_tabs.setCurrentWidget(self.creator_media_table)

    def _store_media(self, account_id: int, path: str,
                     *, source: str = "upload", job_id: str = "",
                     caption: str = ""):
        suffix = Path(path).suffix.lower()
        kind = ("video" if suffix in (".mp4", ".mov")
                else "audio" if suffix in (".mp3", ".m4a") else "image")
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO creator_media
                      (account_id, path, kind, caption, source, job_id, added_at)
                    VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(account_id, path) DO UPDATE SET
                      caption=excluded.caption, source=excluded.source,
                      job_id=CASE WHEN excluded.job_id != '' THEN excluded.job_id
                                  ELSE creator_media.job_id END
                """, (account_id, path, kind, caption, source, job_id,
                      datetime.now().isoformat(timespec="seconds")))
                conn.commit()
        except Exception as exc:
            self.host._note_failure("creator: store media", exc)

    def refresh_media(self):
        account = self.current_account()
        self.creator_media_table.setRowCount(0)
        if not account:
            return
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT path, kind, source, caption FROM creator_media "
                    "WHERE account_id = ? ORDER BY id DESC",
                    (account["id"],)).fetchall()
        except Exception as exc:
            self.host._note_failure("creator: load media", exc)
            return
        for row in rows:
            r = self.creator_media_table.rowCount()
            self.creator_media_table.insertRow(r)
            for col, value in enumerate([Path(row["path"]).name, row["kind"],
                                         row["source"], row["caption"]]):
                self.creator_media_table.setItem(r, col, QTableWidgetItem(str(value)))

    # ── performer records ───────────────────────────────────────────────
    def add_performer(self):
        """Record that age/identity records exist for someone depicted.

        Deliberately records *that* documents are held and where — not the
        documents. In the US, 18 U.S.C. 2257 puts this obligation on the
        producer; storing scans of passports in an app database would create a
        second problem rather than solve the first.
        """
        account = self.current_account()
        if not account:
            QMessageBox.warning(self, "No Account", "Select an account first.")
            return
        name, ok = QInputDialog.getText(
            self, "Add Performer Record",
            "Performer's legal name (as it appears on their ID):")
        if not ok or not name.strip():
            return
        location, ok = QInputDialog.getText(
            self, "Records Location",
            "Where are the ID and release documents actually held?\n"
            "(This app stores the reference, never the documents.)")
        if not ok:
            return
        try:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO creator_performers
                      (account_id, legal_name, date_verified, id_on_file,
                       release_signed, records_location, created_at)
                    VALUES (?,?,?,1,1,?,?)
                """, (account["id"], name.strip(),
                      datetime.now().strftime("%Y-%m-%d"),
                      location.strip(),
                      datetime.now().isoformat(timespec="seconds")))
                conn.commit()
        except Exception as exc:
            self.host._note_failure("creator: add performer", exc)
            return
        self.refresh_records()
        self.creator_tabs.setCurrentWidget(self.creator_records_table)

    def refresh_records(self):
        account = self.current_account()
        self.creator_records_table.setRowCount(0)
        if not account:
            return
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT legal_name, date_verified, id_on_file, "
                    "release_signed, records_location FROM creator_performers "
                    "WHERE account_id = ? ORDER BY legal_name",
                    (account["id"],)).fetchall()
        except Exception as exc:
            self.host._note_failure("creator: load records", exc)
            return
        for row in rows:
            r = self.creator_records_table.rowCount()
            self.creator_records_table.insertRow(r)
            for col, value in enumerate([
                    row["legal_name"], row["date_verified"],
                    "yes" if row["id_on_file"] else "no",
                    "yes" if row["release_signed"] else "no",
                    row["records_location"]]):
                self.creator_records_table.setItem(r, col, QTableWidgetItem(str(value)))

    # ── revenue attribution ─────────────────────────────────────────────
    def record_outcome(self):
        """Attach a source-labelled observation to the selected calendar item."""
        row = self.creator_calendar_table.currentRow()
        ids = self._calendar_ids
        if row < 0 or row >= len(ids):
            QMessageBox.information(
                self, "Select an item",
                "Select an asset on Calendar first, then return to Earnings.")
            return
        with get_connection() as conn:
            item = conn.execute(
                "SELECT * FROM creator_content WHERE id=?", (ids[row],)).fetchone()
        if item is None:
            QMessageBox.warning(self, "Missing item",
                                "The selected asset no longer exists.")
            return
        dialog = CreatorOutcomeDialog(dict(item), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            record_outcome(ids[row], **dialog.values())
        except ValueError as exc:
            QMessageBox.warning(self, "Outcome not saved", str(exc))
            return
        self.refresh_calendar()
        self.refresh_earnings()
        self.creator_tabs.setCurrentIndex(2)

    def record_revenue(self):
        """Attach what a calendar item earned, closing the loop to the drafter."""
        row = self.creator_calendar_table.currentRow()
        ids = self._calendar_ids
        if row < 0 or row >= len(ids):
            QMessageBox.information(
                self, "Select an Item",
                "Pick a row on the Calendar tab first — revenue attaches to "
                "one piece of content.")
            return
        amount, ok = QInputDialog.getDouble(
            self, "Record Revenue", "What did it earn (USD)?", 0, 0, 1e6, 2)
        if not ok:
            return
        record_revenue(ids[row], amount)
        self.refresh_calendar()
        self.refresh_earnings()

    # ── agency ──────────────────────────────────────────────────────────
    def refresh_agency(self):
        self.creator_agency_table.setRowCount(0)
        try:
            rows = agency_overview()
        except Exception as exc:
            self.host._note_failure("creator: agency overview", exc)
            return
        for row in rows:
            r = self.creator_agency_table.rowCount()
            self.creator_agency_table.insertRow(r)
            for col, value in enumerate([
                    row["handle"], row["account_type"],
                    row["consent_holder"] or "—",
                    f"{row['net']:,.2f}", row["subscribers"], row["drafts"]]):
                self.creator_agency_table.setItem(r, col, QTableWidgetItem(str(value)))
