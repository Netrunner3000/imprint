import json
import os
import uuid
import re
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Frozen-app narrator worker dispatch ──────────────────────────────────────
# The packaged app can't run `python -m services.narrator.converter`, so it
# re-invokes its own executable with this sentinel. Handle it before importing
# the GUI stack so the audiobook worker process stays lightweight.
if "--narrator-worker" in sys.argv:
    sys.argv.remove("--narrator-worker")
    from services.narrator.converter import main as _narrator_main
    _narrator_main()
    sys.exit(0)

from services.runtime_paths import resource_base, user_data_base, ensure_seeded, is_frozen
ensure_seeded()

# Anchor the working directory to the writable base so the handful of services
# that still use relative paths ("data/chats", "config/settings.json", ...) resolve
# correctly no matter how the app was launched (Finder launches with cwd="/").
os.chdir(str(user_data_base()))

from dotenv import load_dotenv
# API keys: user-data .env when frozen, project .env in dev. Real env vars still win.
load_dotenv(user_data_base() / ".env")

import markdown

from PySide6.QtCore import Qt, QTimer, QProcess, QUrl, QThread, Signal, QEvent, QRect, QPoint, QSize
from PySide6.QtGui import QTextCursor, QDesktopServices, QColor, QKeySequence, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QSizePolicy, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QTextEdit, QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QCheckBox, QTextBrowser, QSplitter, QLineEdit, QFileDialog,
    QProgressBar, QDialog, QTabWidget, QTabBar, QFrame, QScrollArea, QStackedWidget, QLayout,
    QInputDialog, QMenu, QTableWidget, QTableWidgetItem, QHeaderView,
)

from ui.style import (
    GLOBAL_STYLESHEET, ACCENT, ACCENT_LINE, ACCENT_WASH, INFO, WARNING,
    TEXT, TEXT_DIM, TEXT_MUTE,
)
from services.ollama_client import OllamaClient, MUSE_GLIMMER_VARIANTS, muse_glimmer_default
from services.openai_client import OpenAIClientWrapper
from services.deepseek_client import DeepSeekClientWrapper
from services.kimi_client import KimiClientWrapper
from services.gemini_client import GeminiClientWrapper
from services.anthropic_client import AnthropicClientWrapper
from services.qwen_client import QwenClientWrapper
from services.resource_monitor import ResourceMonitor
from services.history_store import HistoryStore
from services.chat_projects import (
    continue_chat_messages, conversation_turns, with_project_instructions,
)
from services.report_exporter import ReportExporter
from services.usage_tracker import UsageTracker
from services.tool_runner import ToolRunner
from services.database import init_db, get_setting, save_setting, get_connection
from services.registry import Registry
from services.validator import Validator
from services.run_logger import RunLogger

from agents.audiobook import AudiobookConnector, AudiobookPanel
from agents.chat import ChatAgent
from agents.author import AuthorAgent
from agents.manuscript import ManuscriptAgent
from agents.webdesign import WebdesignAgent, WebdesignPanel
from agents.music import MusicAgent, MusicPanel
from agents.fiverr import FiverrAgent
from agents.creator import (
    CreatorAgent, ConsentError, PROMO_CHANNELS,
)
from agents.catalog import AGENT_SPECS, workspace_map
from agents.recommendation_profiles import profile_for
from services.recommendations import RecommendationContext, RecommendationEngine
from services.recommendations.catalog import (
    media_candidate, text_candidates,
)
from services.higgsfield_client import (
    HiggsfieldClient, ContentPolicyError, check_prompt,
)
from services.creator_csv import ingest_creator_csv
from services.creator_profile import (
    SEGMENTS, load_persona, load_voice, reference_images,
    save_persona, save_voice,
)
from services.creator_insights import (
    account_summary, agency_overview, asset_outcomes, commission,
    hook_results, price_history, price_points, record_outcome,
    record_revenue, top_content,
)
from ui.book_widgets import (
    make_theme_box, make_size_box, make_voice_source_box,
    theme_key, size_key, unique_output_path,
)
from ui.creator_earnings import CreatorEarningsView
from ui.creator_outcome_dialog import CreatorOutcomeDialog
from ui.creator_policy_dialog import CreatorPolicyDialog
from services.creator_platform_policy import get_policy, save_policy


# Writable base = project root in dev, ~/Library/Application Support/Imprint when frozen.
BASE_DIR = user_data_base()
# Read-only bundled resources (README, config defaults) = project root in dev, bundle when frozen.
RESOURCE_DIR = resource_base()
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
CHATS_DIR = DATA_DIR / "chats"

# Sentinel value for the Saved Chats agent filter — not a real agent name.
ALL_AGENTS_FILTER = "All agents"
ALL_PROJECTS_FILTER = "__all_projects__"
UNFILED_PROJECTS_FILTER = "__unfiled_projects__"

# The app is organised around creative outcomes, not implementation-level agent
# names. Each workspace remembers its last selected tool during the session.
WORKSPACES = workspace_map()

# Agents that own a dedicated `<name>_panel` rather than sharing `normal_panel`.
# update_agent_ui walks this instead of a chain of `is_x` booleans.
CUSTOM_PANELS = tuple(spec.key for spec in AGENT_SPECS if spec.panel)
WORKSPACE_LABELS = {
    spec.key: spec.label for spec in AGENT_SPECS if spec.workspace is not None
}

SETTINGS_FILE = CONFIG_DIR / "settings.json"
AGENTS_FILE = CONFIG_DIR / "agents.json"
COMMANDS_FILE = CONFIG_DIR / "commands.json"
TOOL_PROMPTS_FILE = CONFIG_DIR / "tool_prompts.json"
REGISTRY_FILE = CONFIG_DIR / "registry.json"
README_FILE = RESOURCE_DIR / "README.md"

# agent key -> (provider box attribute, model box attribute)
AGENT_SETUP_WIDGETS = {
    "chat":        ("provider_box",             "model_box"),
    "fiverr":      ("fiverr_provider_box",      "fiverr_model_box"),
    "creator":     ("creator_provider_box",     "creator_model_box"),
    "author":      ("author_provider_box",      "author_model_box"),
    "manuscript":  ("manuscript_provider_box",  "manuscript_model_box"),
    "music":       ("music_provider_box",       "music_model_box"),
    "social":      ("social_provider_box",      "social_model_box"),
    "webdesign":   ("webdesign_provider_box",   "webdesign_model_box"),
}

AGENT_CONTEXT_WIDGETS = {
    "author": ("author_content_type_box", "author_task_box"),
    "creator": ("creator_kind_box", "creator_platform_box"),
    "fiverr": ("fiverr_style_box",),
    "music": ("music_genre_box", "music_release_type_box"),
    "social": ("social_kind_box", "social_platform_box", "social_angle_box"),
    "webdesign": ("webdesign_type_box", "webdesign_framework_box"),
}

AGENT_PRETTY_NAMES = {spec.key: spec.label for spec in AGENT_SPECS}


from ui.panels.base import AgentPanel
from ui.workers import (
    VideoWorker,
    ChatWorker, ModelPullWorker, FiverrImageWorker, ShortsWorker,
    HiggsfieldEstimateWorker, HiggsfieldWorker,
    VideoGenerationWorker,
)
from ui.forms import (
    CONTENT_MAX_WIDTH, CONTROL_HEIGHT, HEADER_HEIGHT, LG, MD, RAIL_LEFT_WIDTH,
    RAIL_RIGHT_WIDTH, SM, XS, Meter, StatBlock, combo, field, form_grid,
    line_edit, micro, nav_tab, primary, quiet, rail, rule, section, stat,
)
from ui.widgets import (
    FlowLayout, CollapsibleSection, install_dropdown_system, scrollable,
    let_combos_shrink, RECOMMENDED_ROLE, RECOMMENDATION_REASON_ROLE,
    RECOMMENDATION_SCORE_ROLE, RECOMMENDATION_CONFIDENCE_ROLE,
    RECOMMENDATION_BADGE_ROLE,
)
from ui.status_cards import (
    ApiKeysStatusCard, ResourceStatusCard, RoutingStatusCard,
    STATUS_CARD_STYLES,
)
from agents.onlyfans import OnlyFansDashboard, format_creator_brief
from agents.social import (
    ANGLES, SUBJECT_KINDS, build_clip_brief_messages,
    build_post_messages, over_limit, split_variants,
)
from ui.tooltips import seed_tooltips

class GodAI(QWidget):
    def __init__(self):
        super().__init__()
        install_dropdown_system(QApplication.instance())
        self._is_initializing = True

        self.setWindowTitle("Imprint")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 600)
        self.showMaximized()

        CONFIG_DIR.mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)
        CHATS_DIR.mkdir(parents=True, exist_ok=True)

        init_db()

        self.commands = self.load_json(COMMANDS_FILE, {"General Chat": ""})
        self.tool_prompts = self.load_json(TOOL_PROMPTS_FILE, {
            "General Chat": {"system": "You are a helpful general assistant."}
        })
        self.agents_config = self.load_json(
            AGENTS_FILE,
            {"agents": ["author", "manuscript", "audiobook", "music", "webdesign", "fiverr"]},
        )
        self.settings = self.load_json(SETTINGS_FILE, {})

        self.ollama = OllamaClient()
        self.openai = OpenAIClientWrapper()
        self.deepseek = DeepSeekClientWrapper()
        self.kimi = KimiClientWrapper()
        self.gemini = GeminiClientWrapper()
        self.anthropic = AnthropicClientWrapper()
        self.qwen = QwenClientWrapper()
        self.recommendation_engine = RecommendationEngine()
        self.monitor = ResourceMonitor()
        self.history = HistoryStore()
        self.report_exporter = ReportExporter()
        self.usage_tracker = UsageTracker()
        self.tool_runner = ToolRunner()
        self.audiobook_connector = AudiobookConnector()

        self.registry = Registry()
        self.validator = Validator(self.registry)
        self.run_logger = RunLogger()
        # request token -> context for an in-flight request (see authorize_request).
        # Keyed by token, not agent name: two concurrent runs of one agent used to
        # overwrite each other here, losing the first run's run_id so its entry in
        # the run log never closed. _pending_by_agent keeps the per-agent FIFO the
        # agent-name API resolves through.
        self._pending_requests: dict[str, dict] = {}
        self._pending_by_agent: dict[str, list[str]] = {}

        self.author_worker: Optional[ChatWorker] = None
        self._last_author_response: str = ""
        self._author_is_continuing: bool = False
        self._author_export_done: bool = False
        self.author_pub_worker: Optional[ChatWorker] = None
        self.author_mkt_worker: Optional[ChatWorker] = None
        self.manuscript_worker: Optional[ChatWorker] = None
        self._manuscript_last_data: str = ""
        self.shorts_worker: Optional[ShortsWorker] = None
        self._last_short_path: str = ""
        self.quote_finder_worker: Optional[ChatWorker] = None
        self.calendar_worker: Optional[ChatWorker] = None
        self._calendar_slots: list = []
        self.music_worker: Optional[ChatWorker] = None
        self.webdesign_worker: Optional[ChatWorker] = None
        self.fiverr_image_worker: Optional[FiverrImageWorker] = None
        self.fiverr_text_worker: Optional[ChatWorker] = None
        self._fiverr_image_paths: list = []
        self._fiverr_current_tab: int = 0

        self.agent_instances = {
            "chat": ChatAgent(),
            "author": AuthorAgent(),
            "webdesign": WebdesignAgent(),
            "music": MusicAgent(),
            "fiverr": FiverrAgent(),
            "creator": CreatorAgent(),
            "manuscript": ManuscriptAgent(),
        }

        self.current_messages = []
        self.current_chat_agent = ""
        self.current_chat_tool = ""
        self.current_chat_project = None

        self.session_cost_total = 0.0
        self.session_request_count = 0
        self.last_request_cost = 0.0
        
        self.session_budget_eur = float(self.settings.get("session_budget_eur", 1.00))
        self.daily_budget_eur = float(self.settings.get("daily_budget_eur", 5.00))

        self.chat_worker: Optional[ChatWorker] = None
        self.active_run_id: Optional[str] = None
        self.chat_started_at: Optional[float] = None
        self.chat_elapsed_seconds = 0
        self.chat_estimated_seconds = 30

        self.audiobook_process: Optional[QProcess] = None

        self.pending_agent = ""
        self.pending_backend = ""
        self.pending_model = ""
        self.pending_command = ""
        self.pending_prompt = ""
        self.pending_messages = []

        # Tooltip state — toggled via the chip in the centre header bar
        self.tooltips_enabled = True

        self.build_ui()
        from ui.learning_center import install_learning_targets
        install_learning_targets(self, RESOURCE_DIR)
        self.learning_shortcut = QShortcut(QKeySequence("F1"), self)
        self.learning_shortcut.setContext(Qt.ApplicationShortcut)
        self.learning_shortcut.activated.connect(self.show_learning_center)
        self._polish_tab_widgets()
        self._seed_tooltips()
        # Install global event filter so we can suppress ToolTip events when disabled
        from PySide6.QtWidgets import QApplication as _QApp
        _QApp.instance().installEventFilter(self)
        self.load_models()
        # Pre-select each agent's recommended provider/model and paint those
        # entries red in their dropdowns. Runs after every panel is built.
        self.install_agent_recommendations()
        self.muse_pull_worker: Optional[ModelPullWorker] = None
        self.refresh_muse_button()
        self.load_history_list()
        self.update_resource_label()
        self.update_usage_labels()
        self.start_resource_timer()
        self._is_initializing = False
        self.select_agent("author")

    def _polish_tab_widgets(self):
        """Disable text elision and enable scroll buttons on every QTabWidget
        in the app so long tab titles never get cut off with ellipses."""
        for tabs in self.findChildren(QTabWidget):
            tabs.setElideMode(Qt.ElideNone)
            tabs.setUsesScrollButtons(True)
            tabs.setDocumentMode(False)
            # Let the tab bar expand and request its preferred (full) text size
            tab_bar = tabs.tabBar()
            if tab_bar is not None:
                tab_bar.setExpanding(False)
                tab_bar.setUsesScrollButtons(True)

    # ── Tooltips ────────────────────────────────────────────────────────────
    def _toggle_tooltips(self):
        """Enable or disable hover tooltips application-wide."""
        self.tooltips_enabled = self.tooltips_toggle_btn.isChecked()
        self.tooltips_toggle_btn.setText(
            "Tooltips: On" if self.tooltips_enabled else "Tooltips: Off"
        )

    def eventFilter(self, obj, event):
        """Handle global tooltip policy and the responsive writing footer."""
        if (event.type() == QEvent.Resize
                and obj is getattr(self, "author_panel", None)):
            # Defer until Qt has finished the resize pass.  Changing visibility
            # while a layout is calculating its geometry can otherwise leave
            # controls at their previous positions for one frame.
            width = event.size().width()
            QTimer.singleShot(0, lambda w=width: self._adapt_author_layout(w))
        if event.type() == QEvent.ToolTip and not self.tooltips_enabled:
            return True
        return super().eventFilter(obj, event)

    def _adapt_author_layout(self, width: int):
        """Keep the document actions usable when the centre pane is narrow."""
        if not hasattr(self, "author_document_bar"):
            return

        compact = width < 660
        compose_stacked = width < 1000
        layout_state = (compact, compose_stacked)
        if layout_state == getattr(self, "_author_layout_state", None):
            return
        self._author_layout_state = layout_state

        # At desktop width Compose is one clean command strip.  On narrower
        # windows the buttons move below the fields instead of crushing model
        # names or leaving the direction box only a few pixels tall.
        if compose_stacked:
            self.author_compose_grid.addWidget(
                self.author_compose_actions, 1, 0, 1, 5, Qt.AlignLeft)
        else:
            self.author_compose_grid.addWidget(
                self.author_compose_actions, 0, 4, Qt.AlignBottom)

        # Counts and metadata are useful context at normal desktop sizes, but
        # the primary Save / format / Export path must win when rails leave the
        # workbench only a few hundred pixels wide.
        for widget in (
            self.author_word_metric,
            self.author_scene_metric,
            self.author_export_label,
            self.author_export_author_input,
            self.author_clear_btn,
        ):
            widget.setVisible(not compact)

        layout = self.author_document_bar.layout()
        if compact:
            layout.setContentsMargins(XS, SM, XS, SM)
            layout.setSpacing(XS)
            self.author_save_btn.setText("Save")
            self.author_save_btn.setFixedWidth(58)
            self.author_export_btn.setText("Export")
            self.author_export_btn.setFixedWidth(68)
            self.author_export_format_box.setFixedWidth(86)
        else:
            layout.setContentsMargins(MD, SM, MD, SM)
            layout.setSpacing(SM)
            self.author_save_btn.setText("Save Draft")
            self.author_save_btn.setMinimumWidth(0)
            self.author_save_btn.setMaximumWidth(16777215)
            self.author_export_btn.setText("Export Book")
            self.author_export_btn.setMinimumWidth(0)
            self.author_export_btn.setMaximumWidth(16777215)
            self.author_export_format_box.setFixedWidth(100)

    def _set_tooltips(self, mapping: dict):
        """Helper: apply a {widget_attr_name: text} mapping in one call.
        Silently skips attributes that don't exist yet (panel not built)."""
        for attr, text in mapping.items():
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setToolTip(text)

    def _seed_tooltips(self):
        seed_tooltips(self)

    def load_json(self, path: Path, default):
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def safe_key_status(self, cls):
        try:
            return "available" if cls.key_available() else "not set"
        except Exception:
            return "unknown"

    def estimate_chat_seconds(self, backend: str, model: str, prompt: str) -> int:
        words = max(1, len(prompt.split()))
        base = 10
        if backend == "ollama":
            if "8b" in model.lower():
                base = 35
            elif "1.5b" in model.lower():
                base = 12
            else:
                base = 25
        elif backend in {"openai", "deepseek", "kimi", "gemini"}:
            base = 15
        return min(180, max(10, base + words // 20))

    def estimate_chat_cost(self, backend, model, prompt):
        """Pre-flight cost estimate in EUR, plus the approximate token count.

        Prices come from the pricing table via UsageTracker — the same source
        that bills the request afterwards. This used to be a second hardcoded
        per-backend dict which had no entry for anthropic or qwen, so both were
        estimated at zero and sailed straight past the budget gate in
        Validator.validate() no matter how expensive the model was.
        """
        project = self._active_project() if hasattr(self, "_active_project") else None
        instructions = (project or {}).get("instructions", "")
        approx_input_tokens = max(1, int((len(prompt) + len(instructions)) / 4))
        approx_output_tokens = max(250, int(approx_input_tokens * 1.2))
        approx_total_tokens = approx_input_tokens + approx_output_tokens

        if backend == "ollama":
            return 0.0, approx_total_tokens

        estimated_cost = self.usage_tracker.calculate_cost_eur(
            backend, model, approx_input_tokens, approx_output_tokens
        )

        return round(estimated_cost, 5), approx_total_tokens

    def _conversation_context_text(self, agent: str, tool: str) -> str:
        """Bill and preview only the conversation that this request will send."""
        project = self._active_project()
        project_id = project["id"] if project else None
        if (self.current_chat_agent != agent or self.current_chat_tool != tool
                or self.current_chat_project != project_id):
            return ""
        return "\n".join(str(turn.get("content") or "")
                         for turn in conversation_turns(self.current_messages))

    def get_current_cost_estimate(self):
        raw_text = self.input_box.toPlainText().strip()

        if not raw_text:
            return 0.0, 0, None, None

        _, full_prompt = self.build_user_prompt(raw_text)
        backend, model = self.resolve_backend_model()
        agent = self.agent_box.currentText()
        tool = self.tool_box.currentText() if hasattr(self, "tool_box") else "General Chat"
        previous = self._conversation_context_text(agent, tool)
        billable_prompt = f"{previous}\n{full_prompt}" if previous else full_prompt

        estimated_cost, approx_tokens = self.estimate_chat_cost(
            backend,
            model,
            billable_prompt
        )

        return estimated_cost, approx_tokens, backend, model
    
    def show_cost_history(self):
        from ui.dialogs import show_cost_history as _show_cost_history
        return _show_cost_history(self)
    def show_run_log(self):
        from ui.dialogs import show_run_log as _show_run_log
        return _show_run_log(self)
    def show_settings(self):
        from ui.dialogs import show_settings as _show_settings
        return _show_settings(self)
    def update_live_cost_estimate(self):
        if not hasattr(self, "live_estimate_label"):
            return

        if self.agent_box.currentText() == "audiobook":
            return

        estimated_cost, approx_tokens, backend, model = self.get_current_cost_estimate()
        if not backend or not model:
            self.live_estimate_label.setText("Next request: nothing selected yet")
            return

        # One line, beside the bars it will move. The cost comes first because
        # it is the only part that decides anything.
        if backend == "ollama":
            self.live_estimate_label.setText(
                f"Next request: free · {model} · ~{approx_tokens} tokens")
        elif backend in {"openai", "deepseek", "kimi", "gemini", "anthropic"}:
            self.live_estimate_label.setText(
                f"Next request: ~€{estimated_cost:.2f} · paid · "
                f"{backend} {model} · ~{approx_tokens} tokens")
        else:
            self.live_estimate_label.setText(
                f"Next request: ~€{estimated_cost:.2f} · "
                f"{backend} {model} · ~{approx_tokens} tokens")

    def show_cost_estimate_popup(self):
        estimated_cost, approx_tokens, backend, model = self.get_current_cost_estimate()

        if backend == "ollama":
            msg = (
                f"Agent: {self.agent_box.currentText()}\n"
                f"Backend: {backend}\n"
                f"Model: {model}\n"
                f"Approx tokens: {approx_tokens}\n\n"
                f"Estimated cost: €0.0000\n"
                f"This is local execution."
            )
        else:
            msg = (
                f"Agent: {self.agent_box.currentText()}\n"
                f"Backend: {backend}\n"
                f"Model: {model}\n"
                f"Approx tokens: {approx_tokens}\n\n"
                f"Estimated cost: ~€{estimated_cost:.2f}\n"
                f"⚠ This may use a paid API."
            )

        QMessageBox.information(self, "Cost Estimate", msg)

    def format_seconds(self, total: int) -> str:
        total = max(0, int(total))
        return f"{total // 60:02d}:{total % 60:02d}"

    # ── Local-model memory guard ─────────────────────────────────────────────
    # Cloud models cost money and are gated by budget. Local models are free, so
    # they bypassed every check — yet they are the only ones that can wedge the
    # machine. This sizes the model against real memory before it is loaded.

    # A loaded model needs roughly its file size resident, plus KV cache and
    # runtime overhead. 1.15 is a deliberately mild allowance: the aim is to
    # catch "this will thrash", not to model llama.cpp allocation exactly.
    MEMORY_OVERHEAD_FACTOR = 1.15
    # Leave room for the OS and the app itself rather than letting a model take
    # every last byte of physical RAM.
    MEMORY_HEADROOM_GB = 3.0

    def assess_local_model(self, model: str) -> dict | None:
        """Weigh a local model against this machine's memory.

        Returns None when the check does not apply (not a known local model, or
        the daemon is unreachable and the size is unknowable). Otherwise a dict
        with level "ok" | "tight" | "too_big", the numbers behind it, and a
        human-readable message.
        """
        import psutil

        size_bytes = self.ollama.model_size_bytes(model)
        if size_bytes is None:
            # Not pulled yet — fall back to the published download size for the
            # builds we ship a figure for, so the dropdown can grey them out.
            published_gb = MUSE_GLIMMER_VARIANTS.get(model)
            if published_gb is None:
                return None
            size_gb = float(published_gb)
        else:
            size_gb = size_bytes / 1e9

        needed_gb = size_gb * self.MEMORY_OVERHEAD_FACTOR
        vm = psutil.virtual_memory()
        total_gb = vm.total / 1e9
        available_gb = vm.available / 1e9

        if needed_gb > total_gb - self.MEMORY_HEADROOM_GB:
            level = "too_big"
            message = (
                f"{model} needs about {needed_gb:.1f} GB of memory, but this machine "
                f"only has {total_gb:.0f} GB in total. It cannot run here without "
                "swapping so hard the system becomes unresponsive."
            )
        elif needed_gb > available_gb:
            level = "tight"
            message = (
                f"{model} needs about {needed_gb:.1f} GB, but only {available_gb:.1f} GB "
                f"is free right now (of {total_gb:.0f} GB). It will fit, but expect "
                "heavy swapping and slow replies — closing other apps will help."
            )
        else:
            level = "ok"
            message = f"{model} needs ~{needed_gb:.1f} GB; {available_gb:.1f} GB free."

        return {
            "level": level,
            "model": model,
            "needed_gb": needed_gb,
            "available_gb": available_gb,
            "total_gb": total_gb,
            "message": message,
        }

    def check_memory_before_request(self, backend: str, model: str) -> bool:
        """Interactive pre-flight for local models. False means "do not run".

        Must be called from the GUI thread, before the worker is constructed.
        """
        if backend != "ollama":
            return True

        verdict = self.assess_local_model(model)
        if verdict is None or verdict["level"] == "ok":
            return True

        if verdict["level"] == "too_big":
            QMessageBox.critical(self, "Model Too Large For This Machine", verdict["message"])
            return False

        choice = QMessageBox.warning(
            self,
            "Low Memory",
            verdict["message"] + "\n\nRun it anyway?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return choice == QMessageBox.Yes

    # check_budget_before_request() was deleted here: no callers, float
    # arithmetic, and it duplicated (worse) what the Decimal validator does
    # inside authorize_request().

    def save_budget_limits(self):
        try:
            self.session_budget_eur = float(self.session_budget_input.text().strip())
            self.daily_budget_eur = float(self.daily_budget_input.text().strip())

            save_setting("session_budget_eur", str(self.session_budget_eur))
            save_setting("daily_budget_eur", str(self.daily_budget_eur))

            self.update_usage_labels()
            self.refresh_all_recommendations()
            QMessageBox.information(self, "Budget Saved", "Budget limits saved.")

        except ValueError:
            QMessageBox.warning(self, "Invalid Budget", "Please enter valid numbers.")

    def reset_session_spend(self):
        self.session_cost_total = 0.0
        self.session_request_count = 0
        self.update_usage_labels()
        self.refresh_all_recommendations()
        QMessageBox.information(self, "Session Reset", "Session spend has been reset.")

    def get_recommended_setup(self):
        provider_result, _model_result = self._text_recommendations("chat")
        if provider_result is None:
            return {
                "mode": self.execution_mode_box.currentText(),
                "provider": self.provider_box.currentText(),
                "model": self.model_box.currentText(),
                "reason": "No eligible model is currently listed.",
                "score": None,
                "confidence": "",
                "setup_needed": True,
            }
        winner = provider_result.candidate
        return {
            "mode": "Local only" if winner.provider == "ollama" else "Hybrid allowed",
            "provider": winner.provider,
            "model": winner.model_id,
            "reason": provider_result.reason,
            "score": round(provider_result.score * 100),
            "confidence": provider_result.confidence,
            "setup_needed": provider_result.fallback,
        }

    def _show_recommended_setup(self, rec: dict) -> None:
        """Render the recommendation as structured evidence in the rail."""
        if hasattr(self, "routing_status_card"):
            self.routing_status_card.set_recommendation(
                rec["provider"], rec["model"], rec["reason"],
                rec.get("score"), rec.get("confidence", ""),
                rec.get("setup_needed", False),
            )
        elif hasattr(self, "recommendation_label"):
            self.recommendation_label.setText(
                f"{rec['provider']} · {rec['model']}\n{rec['reason']}")

    def apply_recommended_setup(self):
        rec = self.get_recommended_setup()

        if hasattr(self, "execution_mode_box"):
            index = self.execution_mode_box.findText(rec["mode"])
            if index >= 0:
                self.execution_mode_box.setCurrentIndex(index)

        if hasattr(self, "provider_box"):
            index = self.provider_box.findText(rec["provider"])
            if index >= 0:
                self.provider_box.setCurrentIndex(index)

        self.load_provider_models()

        if hasattr(self, "model_box") and rec["model"] != "tts":
            index = self.model_box.findText(rec["model"])
            if index >= 0:
                self.model_box.setCurrentIndex(index)

        self._show_recommended_setup(rec)

        self.update_live_cost_estimate()

    def update_recommendation_label(self):
        if not hasattr(self, "recommendation_label"):
            return

        rec = self.get_recommended_setup()

        self._show_recommended_setup(rec)
        # Chat's recommendation moves with the tool/command/prompt, so repaint
        # the red dropdown markings whenever the label is refreshed.
        self.refresh_recommendation_marks("chat")

    def maybe_auto_apply_recommendation(self):
        if not hasattr(self, "auto_recommend_checkbox"):
            return

        if not self.auto_recommend_checkbox.isChecked():
            return

        self.apply_recommended_setup()

    # ── Muse Glimmer (local, via Ollama) ─────────────────────────────────────

    def _set_chat_status(self, text: str) -> None:
        """Write to the chat status line, revealing it if it is still hidden."""
        label = getattr(self, "chat_status_label", None)
        if label is None:
            return
        label.setText(text)
        label.setVisible(bool(text))

    @staticmethod
    def _total_ram_gb() -> int:
        import psutil
        return round(psutil.virtual_memory().total / 1e9)

    def _muse_choice(self) -> tuple[str, int]:
        """The Muse Glimmer build best suited to this machine: (tag, size_gb)."""
        return muse_glimmer_default(self._total_ram_gb())

    def mark_oversized_models(self, combo) -> None:
        """Grey out local models this machine cannot physically run.

        Advisory only — the entry stays selectable, and run_backend() is the
        real gate. Colouring here just makes the limit visible before clicking.
        """
        if combo is None:
            return

        for i in range(combo.count()):
            # Never overwrite the red recommendation marking.
            if combo.itemData(i, Qt.ForegroundRole) is not None:
                continue
            verdict = self.assess_local_model(combo.itemText(i))
            if verdict is None:
                continue
            if verdict["level"] == "too_big":
                combo.setItemData(i, QColor("#666666"), Qt.ForegroundRole)
                combo.setItemData(i, f"⚠ {verdict['message']}", Qt.ToolTipRole)
            elif verdict["level"] == "tight":
                combo.setItemData(i, f"⚠ {verdict['message']}", Qt.ToolTipRole)

    def refresh_muse_button(self) -> None:
        """Show the pull button only while Muse Glimmer is not installed."""
        btn = getattr(self, "get_muse_btn", None)
        if btn is None:
            return

        # Installed at all? Any of the published builds counts.
        installed = any(
            self.ollama.is_model_installed(tag) for tag in MUSE_GLIMMER_VARIANTS
        )
        tag, size_gb = self._muse_choice()

        btn.setVisible(not installed)
        btn.setToolTip(
            f"Download Meta's Muse Glimmer ({tag}) into Ollama — ~{size_gb} GB. "
            "A 30B open-weights agentic model tuned for tool use, long tasks and "
            "failure recovery. Runs locally, so it is free and nothing leaves "
            "this machine."
        )

    def pull_muse_glimmer(self) -> None:
        if getattr(self, "muse_pull_worker", None) is not None and self.muse_pull_worker.isRunning():
            QMessageBox.information(self, "Already Downloading", "Muse Glimmer is already downloading.")
            return

        tag, size_gb = self._muse_choice()
        total_ram_gb = self._total_ram_gb()

        ram_note = ""
        if total_ram_gb and total_ram_gb < size_gb + 8:
            ram_note = (
                f"\n\n⚠ This machine has {total_ram_gb} GB of memory and the model needs "
                f"about {size_gb} GB resident. Expect heavy swapping and slow responses — "
                "Meta targets a 24–32 GB envelope. Close other apps before running it."
            )

        confirm = QMessageBox.question(
            self,
            "Download Muse Glimmer?",
            f"This downloads {tag} (~{size_gb} GB) into Ollama.\n\n"
            "Meta's 30B open-weights agentic model (Apache 2.0), tuned for tool use, "
            "long-running tasks and failure recovery. It runs locally — free, and no "
            f"data leaves this machine.{ram_note}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.get_muse_btn.setEnabled(False)
        self.muse_pull_worker = ModelPullWorker(self.ollama, tag)
        self.muse_pull_worker.progress_signal.connect(self._on_muse_pull_progress)
        self.muse_pull_worker.finished_signal.connect(self._on_muse_pull_finished)
        self.muse_pull_worker.error_signal.connect(self._on_muse_pull_error)
        self.muse_pull_worker.start()

    def _on_muse_pull_progress(self, status: str, done: int, total: int) -> None:
        if total > 0:
            pct = int(done / total * 100)
            self._set_chat_status(
                f"Muse Glimmer: {status} — {done / 1e9:.1f} / {total / 1e9:.1f} GB ({pct}%)"
            )
            self.tool_progress.setValue(pct)
        else:
            self._set_chat_status(f"Muse Glimmer: {status}")

    def _on_muse_pull_finished(self, model: str) -> None:
        self.tool_progress.setValue(100)
        self._set_chat_status(f"Muse Glimmer installed ({model}).")
        self.get_muse_btn.setEnabled(True)
        self.refresh_muse_button()
        # Bring it into the dropdown straight away if Ollama is the live provider.
        if self.provider_box.currentText() == "ollama":
            self.load_provider_models()
        QMessageBox.information(
            self,
            "Muse Glimmer Ready",
            f"{model} is installed.\n\nSelect provider 'ollama' and pick it from the "
            "Model list. It runs locally at no cost.",
        )

    def _on_muse_pull_error(self, message: str) -> None:
        self.tool_progress.setValue(0)
        self._set_chat_status("Muse Glimmer download failed.")
        self.get_muse_btn.setEnabled(True)
        QMessageBox.warning(self, "Download Failed", message)

    def models_for_provider(self, provider: str) -> list[str]:
        """Model ids offered by one provider, or [] for an unknown provider.

        Every client falls back to its own KNOWN_MODELS list when the API is
        unreachable, so this only returns empty for a name we don't handle.
        """
        clients = {
            "ollama": self.ollama,
            "openai": self.openai,
            "deepseek": self.deepseek,
            "kimi": self.kimi,
            "gemini": self.gemini,
            "anthropic": self.anthropic,
            "qwen": self.qwen,
        }
        client = clients.get(provider)
        if client is None:
            return []
        try:
            return list(client.list_models())
        except Exception:
            return []

    # ── Explainable provider/model recommendations ───────────────────────────

    @staticmethod
    def _find_model_index(combo, wanted: str) -> int:
        """Locate `wanted` in a model combo, tolerating dated API model ids.

        Providers return ids like "claude-sonnet-4-6-20260112" from the live API
        but bare names like "claude-sonnet-4-6" from the offline fallback list,
        so an exact match alone would silently miss. Tries exact, then prefix,
        then substring, and returns -1 when nothing matches.
        """
        if not wanted:
            return -1

        exact = combo.findText(wanted)
        if exact >= 0:
            return exact

        lowered = wanted.lower()
        for i in range(combo.count()):
            if combo.itemText(i).lower().startswith(lowered):
                return i
        for i in range(combo.count()):
            if lowered in combo.itemText(i).lower():
                return i
        # Media dropdowns display a friendly label but store MediaModel as data.
        for i in range(combo.count()):
            data = combo.itemData(i)
            if getattr(data, "model_id", "").lower() == lowered:
                return i
        return -1

    @staticmethod
    def _find_provider_index(combo, provider: str) -> int:
        wanted = provider.casefold()
        return next((i for i in range(combo.count())
                     if combo.itemText(i).casefold() == wanted), -1)

    def _paint_recommended_item(self, combo, index: int, tooltip: str,
                                *, score: float = 0.0,
                                confidence: str = "low",
                                badge: str = "BEST FIT") -> None:
        """Attach semantic recommendation data without changing item text."""
        if combo is None:
            return

        for i in range(combo.count()):
            was_recommended = bool(combo.itemData(i, RECOMMENDED_ROLE))
            combo.setItemData(i, False, RECOMMENDED_ROLE)
            combo.setItemData(i, None, RECOMMENDATION_REASON_ROLE)
            combo.setItemData(i, None, RECOMMENDATION_SCORE_ROLE)
            combo.setItemData(i, None, RECOMMENDATION_CONFIDENCE_ROLE)
            combo.setItemData(i, None, RECOMMENDATION_BADGE_ROLE)
            if was_recommended:
                combo.setItemData(i, "", Qt.ToolTipRole)

        if index < 0:
            return

        combo.setItemData(index, True, RECOMMENDED_ROLE)
        combo.setItemData(index, tooltip, RECOMMENDATION_REASON_ROLE)
        combo.setItemData(index, float(score), RECOMMENDATION_SCORE_ROLE)
        combo.setItemData(index, confidence, RECOMMENDATION_CONFIDENCE_ROLE)
        combo.setItemData(index, badge, RECOMMENDATION_BADGE_ROLE)
        combo.setItemData(index, tooltip, Qt.ToolTipRole)

    def _recommendation_task(self, agent_key: str) -> str:
        if agent_key == "chat":
            parts = [getattr(self, "tool_box", None),
                     getattr(self, "command_box", None)]
            text = " ".join(w.currentText() for w in parts if w is not None)
            prompt = getattr(self, "input_box", None)
            if prompt is not None:
                text += " " + prompt.toPlainText()[:240]
            return text.strip()
        values = []
        for name in AGENT_CONTEXT_WIDGETS.get(agent_key, ()):
            widget = getattr(self, name, None)
            if widget is not None:
                values.append(widget.currentText())
        return " ".join(values)

    def _provider_permission(self, provider: str) -> bool:
        """Whether the user has permitted this provider for paid/external work."""
        key = provider.casefold()
        if key in {"ollama", "local", "pexels"}:
            return True
        checkbox = getattr(self, f"allow_{key}_checkbox", None)
        return bool(checkbox is not None and checkbox.isChecked())

    def _text_recommendations(self, agent_key: str):
        widgets = AGENT_SETUP_WIDGETS.get(agent_key)
        if not widgets:
            return None, None
        provider_box = getattr(self, widgets[0], None)
        model_box = getattr(self, widgets[1], None)
        if provider_box is None or model_box is None:
            return None, None

        providers = [provider_box.itemText(i) for i in range(provider_box.count())]
        if agent_key == "chat" and getattr(self, "execution_mode_box", None) is not None:
            mode = self.execution_mode_box.currentText()
            allowed_cloud = [
                provider for provider in providers if provider != "ollama"
                and getattr(self, f"allow_{provider}_checkbox", None) is not None
                and getattr(self, f"allow_{provider}_checkbox").isChecked()
            ]
            if mode == "Local only":
                providers = [provider for provider in providers if provider == "ollama"]
            elif mode == "Cloud only":
                # With no permission checked, rank cloud choices as setup
                # targets; once permissions exist they become a hard filter.
                providers = allowed_cloud or [p for p in providers if p != "ollama"]
            else:
                providers = [p for p in providers
                             if p == "ollama" or p in allowed_cloud]
        selected = provider_box.currentText()
        live = {selected: [model_box.itemText(i) for i in range(model_box.count())]}
        candidates = text_candidates(providers, live)
        candidates = [
            replace(item, available=(
                bool(item.available and self._provider_permission(item.provider))
                if item.provider.casefold() != "ollama"
                else bool(selected == "ollama"
                          and model_box.property("imprintModelsLive"))
            ))
            for item in candidates
        ]
        profile = profile_for(agent_key)
        base = RecommendationContext(
            agent=agent_key,
            task=self._recommendation_task(agent_key),
            budget_remaining=max(0.0, self.session_budget_eur - self.session_cost_total),
            priority=("privacy" if agent_key == "chat"
                      and getattr(self, "execution_mode_box", None) is not None
                      and self.execution_mode_box.currentText() == "Local only"
                      else "balanced"),
        )
        provider_result = self.recommendation_engine.recommend(profile, candidates, base)
        model_result = self.recommendation_engine.recommend(
            profile, candidates,
            RecommendationContext(**{**base.__dict__, "selected_provider": selected}),
        )
        return provider_result, model_result

    def refresh_recommendation_marks(self, agent_key: str) -> None:
        """Mark the best provider overall and best model within the selection."""
        widgets = AGENT_SETUP_WIDGETS.get(agent_key)
        if not widgets:
            return
        provider_box = getattr(self, widgets[0], None)
        model_box = getattr(self, widgets[1], None)
        provider_result, model_result = self._text_recommendations(agent_key)

        if provider_box is not None and provider_result is not None:
            tooltip = (f"Best provider for {AGENT_PRETTY_NAMES.get(agent_key, agent_key)}: "
                       f"{provider_result.candidate.provider}\n{provider_result.reason}\n"
                       f"Confidence: {provider_result.confidence}")
            idx = self._find_provider_index(provider_box,
                                            provider_result.candidate.provider)
            self._paint_recommended_item(
                provider_box, idx, tooltip, score=provider_result.score,
                confidence=provider_result.confidence, badge=provider_result.badge,
            )
            provider_box.setToolTip(tooltip)

        if model_box is not None and model_result is not None:
            tooltip = (f"Best {provider_box.currentText()} model for "
                       f"{AGENT_PRETTY_NAMES.get(agent_key, agent_key)}: "
                       f"{model_result.candidate.label}\n{model_result.reason}\n"
                       f"Confidence: {model_result.confidence}")
            idx = self._find_model_index(model_box, model_result.candidate.model_id)
            self._paint_recommended_item(
                model_box, idx, tooltip, score=model_result.score,
                confidence=model_result.confidence, badge=model_result.badge,
            )
            model_box.setToolTip(tooltip)
            self.mark_oversized_models(model_box)

    def _on_recommended_provider_changed(self, agent_key: str) -> None:
        """Select the best model inside a newly chosen provider, then annotate."""
        widgets = AGENT_SETUP_WIDGETS.get(agent_key)
        if widgets:
            provider_box = getattr(self, widgets[0], None)
            model_box = getattr(self, widgets[1], None)
            if provider_box is not None and model_box is not None:
                _provider_result, model_result = self._text_recommendations(agent_key)
                idx = (-1 if model_result is None else
                       self._find_model_index(model_box,
                                              model_result.candidate.model_id))
                if idx >= 0:
                    model_box.setCurrentIndex(idx)
        self.refresh_recommendation_marks(agent_key)

    def apply_agent_recommendation(self, agent_key: str) -> None:
        """Pre-select the current best provider and its best model."""
        widgets = AGENT_SETUP_WIDGETS.get(agent_key)
        if not widgets:
            return
        provider_box = getattr(self, widgets[0], None)
        model_box = getattr(self, widgets[1], None)
        provider_result, _model_result = self._text_recommendations(agent_key)
        if provider_box is not None and provider_result is not None:
            idx = self._find_provider_index(provider_box,
                                            provider_result.candidate.provider)
            if idx >= 0:
                provider_box.setCurrentIndex(idx)
        if agent_key == "chat":
            self.load_provider_models()
        else:
            panel = getattr(self, f"{agent_key}_panel_base", None)
            if panel is not None:
                panel.load_models()
        _provider_result, model_result = self._text_recommendations(agent_key)
        if model_box is not None and model_result is not None:
            idx = self._find_model_index(model_box, model_result.candidate.model_id)
            if idx >= 0:
                model_box.setCurrentIndex(idx)
        self.refresh_recommendation_marks(agent_key)

    def _install_audiobook_recommendation(self) -> None:
        """Narrator has a voice selector rather than a provider/model pair."""
        voice_box = getattr(self, "audiobook_voice_box", None)
        if voice_box is None:
            return
        voice = "alloy"
        tooltip = ("Best neutral narration voice for long listening sessions. "
                   "Voice fit is editorial rather than provider-ranked.")
        idx = voice_box.findText(voice)
        if idx >= 0:
            voice_box.setCurrentIndex(idx)
        self._paint_recommended_item(voice_box, idx, tooltip)
        voice_box.setToolTip(tooltip)

    def refresh_video_recommendations(self) -> None:
        provider_box = getattr(self, "video_visual_provider_box", None)
        model_box = getattr(self, "video_visual_model_box", None)
        if provider_box is None or model_box is None:
            return
        from services.media_catalog import MODELS

        duration_text = self.video_length_box.currentText().rstrip("s")
        duration = int(duration_text) if duration_text.isdigit() else None
        candidates = [media_candidate(item, duration) for item in MODELS]
        candidates = [
            replace(item, available=bool(
                item.available and self._provider_permission(item.provider)))
            if item.provider.casefold() not in {"local", "pexels"} else item
            for item in candidates
        ]
        if self.video_format_box.currentText() == "Long-form":
            candidates = [item for item in candidates if item.kind != "direct_video"]
        context = RecommendationContext(
            agent="video", modality="visual",
            task=self.video_format_box.currentText(),
            aspect=self.video_aspect_box.currentText(), duration=duration,
            budget_remaining=max(0.0, self.session_budget_eur - self.session_cost_total),
        )
        profile = profile_for("video")
        overall = self.recommendation_engine.recommend(profile, candidates, context)
        within = self.recommendation_engine.recommend(
            profile, candidates,
            RecommendationContext(**{**context.__dict__,
                                     "selected_provider": provider_box.currentText()}),
        )
        if overall:
            tip = (f"Best visual provider for this format: {overall.candidate.provider}\n"
                   f"{overall.reason}\nConfidence: {overall.confidence}")
            self._paint_recommended_item(
                provider_box, self._find_provider_index(provider_box,
                                                        overall.candidate.provider),
                tip, score=overall.score, confidence=overall.confidence,
                badge=overall.badge,
            )
            provider_box.setToolTip(tip)
        if within:
            tip = (f"Best {provider_box.currentText()} visual model for this format: "
                   f"{within.candidate.label}\n{within.reason}\n"
                   f"Confidence: {within.confidence}")
            self._paint_recommended_item(
                model_box, self._find_model_index(model_box, within.candidate.model_id),
                tip, score=within.score, confidence=within.confidence,
                badge=within.badge,
            )
            model_box.setToolTip(tip)

    def _refresh_fiverr_image_recommendation(self) -> None:
        combo = getattr(self, "fiverr_image_model_box", None)
        if combo is None:
            return
        from services.media_catalog import find_model
        candidates = [media_candidate(found) for i in range(combo.count())
                      if (found := find_model("OpenAI", combo.itemText(i))) is not None]
        result = self.recommendation_engine.recommend(
            profile_for("fiverr"), candidates,
            RecommendationContext(agent="fiverr", modality="visual", task="client image"),
        )
        if result:
            tip = (f"Best image model for Client Gigs: {result.candidate.label}\n"
                   f"{result.reason}\nConfidence: {result.confidence}")
            self._paint_recommended_item(
                combo, self._find_model_index(combo, result.candidate.model_id), tip,
                score=result.score, confidence=result.confidence, badge=result.badge,
            )
            combo.setToolTip(tip)

    def refresh_all_recommendations(self) -> None:
        """Recompute after shared constraints such as budget or permissions change."""
        if not hasattr(self, "recommendation_engine"):
            return
        for agent_key in AGENT_SETUP_WIDGETS:
            self.refresh_recommendation_marks(agent_key)
        self.refresh_video_recommendations()
        self._refresh_fiverr_image_recommendation()

    def install_agent_recommendations(self) -> None:
        """Bind every visible provider/model selector to the shared engine."""
        self._install_audiobook_recommendation()
        for agent_key in AGENT_SETUP_WIDGETS:
            widgets = AGENT_SETUP_WIDGETS[agent_key]
            provider_box = getattr(self, widgets[0], None)
            model_box = getattr(self, widgets[1], None)
            try:
                self.apply_agent_recommendation(agent_key)
            except Exception as e:
                print(f"[Recommendations] {agent_key}: {e}")
            if provider_box is not None:
                provider_box.currentTextChanged.connect(
                    lambda _t, k=agent_key: self._on_recommended_provider_changed(k)
                )
            if model_box is not None:
                model_box.currentTextChanged.connect(
                    lambda _t, k=agent_key: self.refresh_recommendation_marks(k)
                )
            for name in AGENT_CONTEXT_WIDGETS.get(agent_key, ()):
                widget = getattr(self, name, None)
                if widget is not None:
                    widget.currentTextChanged.connect(
                        lambda _t, k=agent_key: self.refresh_recommendation_marks(k)
                    )

        self.refresh_video_recommendations()
        self._refresh_fiverr_image_recommendation()
        for widget in (getattr(self, "video_format_box", None),
                       getattr(self, "video_aspect_box", None),
                       getattr(self, "video_length_box", None)):
            if widget is not None:
                widget.currentTextChanged.connect(self.refresh_video_recommendations)
        if getattr(self, "video_visual_provider_box", None) is not None:
            self.video_visual_provider_box.currentTextChanged.connect(
                self.refresh_video_recommendations)
        if getattr(self, "video_visual_model_box", None) is not None:
            self.video_visual_model_box.currentTextChanged.connect(
                self.refresh_video_recommendations)
        for provider in ("openai", "deepseek", "kimi", "gemini", "anthropic",
                         "qwen", "higgsfield"):
            checkbox = getattr(self, f"allow_{provider}_checkbox", None)
            if checkbox is not None:
                checkbox.stateChanged.connect(
                    lambda *_args: self.refresh_all_recommendations())

    def build_ui(self):
        """Header bar over three columns; the outer two are fixed.

        This replaced a QSplitter. A splitter lets the user drag a pane below
        the minimum width its own children need, and Qt resolves that by
        letting widgets overlap rather than by refusing — which is where every
        overlapping-control bug in this app came from. Two widths you cannot
        drag are worth more than three you can.
        """
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header = self.build_header_bar()
        left_widget = self.build_left_panel()
        center_widget = self.build_center_panel()
        right_widget = self.build_right_panel()
        self.update_recommendation_label()

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(left_widget)
        body.addWidget(center_widget, 1)
        body.addWidget(right_widget)

        outer_layout.addWidget(header)
        outer_layout.addLayout(body, 1)

        # Apply the stylesheet before installing the custom combo delegate.
        # Qt replaces item delegates while polishing a new stylesheet.
        self.apply_global_style()

        # After every panel exists: a combo sized to its longest item pins the
        # control columns wider than the panes they live in, which is what cut
        # the fields off down the right-hand edge.
        let_combos_shrink(self)

    def build_header_bar(self) -> QWidget:
        """Brand, mode tabs, status and utilities on one line.

        These three were previously on three different alignment axes — the
        wordmark pinned to the far left of the rail, the mode tabs centred over
        the canvas, and the page title starting a third of the way across. One
        row, one left edge, and the eye has a single place to start.
        """
        header = QFrame()
        header.setObjectName("AppHeader")
        header.setFixedHeight(HEADER_HEIGHT)
        row = QHBoxLayout(header)
        row.setContentsMargins(LG, 0, LG, 0)
        row.setSpacing(0)

        dot = QLabel("●")
        dot.setObjectName("WordmarkDot")
        row.addWidget(dot)
        row.addSpacing(SM)
        brand = QLabel("IMPRINT")
        brand.setObjectName("Wordmark")
        row.addWidget(brand)

        row.addSpacing(LG)
        divider = QFrame()
        divider.setObjectName("HeaderDivider")
        divider.setFixedSize(1, 22)
        row.addWidget(divider)
        row.addSpacing(MD)

        # Five outcome-oriented workspaces replace Sentinel's long agent menu.
        self.workspace_tabs = QTabBar()
        self.workspace_tabs.setObjectName("WorkspaceTabs")
        self.workspace_tabs.setExpanding(False)
        self.workspace_tabs.setDrawBase(False)
        # These are product areas, not disposable document tabs. Qt's default
        # ElideRight turned "Audio & Music" and "Video & Ads" into ambiguous
        # labels even when the header had enough room. Keep the complete names
        # and fall back to the native scroll affordance only at narrow widths.
        self.workspace_tabs.setElideMode(Qt.ElideNone)
        self.workspace_tabs.setUsesScrollButtons(True)
        self.workspace_tabs.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        for workspace_name in WORKSPACES:
            self.workspace_tabs.addTab(workspace_name)
        # Connected only after every tab exists: addTab on an empty bar sets the
        # current index and would fire the handler before the panels are built.
        self.workspace_tabs.currentChanged.connect(self._workspace_changed)
        row.addWidget(self.workspace_tabs, 0, Qt.AlignVCenter)

        row.addStretch()

        self.project_context_pill = QLabel("")
        self.project_context_pill.setObjectName("StatusPill")
        self.project_context_pill.setMaximumWidth(145)
        self.project_context_pill.hide()
        row.addWidget(self.project_context_pill)
        row.addSpacing(SM)

        self.agent_status_pill = QLabel("●  Ready")
        self.agent_status_pill.setObjectName("StatusPill")
        row.addWidget(self.agent_status_pill)
        row.addSpacing(LG)

        self.agent_docs_btn = quiet("Docs")
        self.agent_docs_btn.setFixedWidth(56)
        self.agent_docs_btn.clicked.connect(self.show_agent_docs)
        row.addWidget(self.agent_docs_btn)

        self.tooltips_toggle_btn = quiet("Tooltips: On")
        self.tooltips_toggle_btn.setFixedWidth(110)
        self.tooltips_toggle_btn.setCheckable(True)
        self.tooltips_toggle_btn.setChecked(True)
        self.tooltips_toggle_btn.clicked.connect(self._toggle_tooltips)
        row.addWidget(self.tooltips_toggle_btn)

        self.settings_btn = quiet("Settings")
        self.settings_btn.setFixedWidth(78)
        self.settings_btn.clicked.connect(self.show_settings)
        row.addWidget(self.settings_btn)

        return header

    def build_left_panel(self) -> QWidget:
        """The project rail. Projects only — navigation lives in the header."""
        left_widget = rail("RailLeft", RAIL_LEFT_WIDTH)
        left_outer = QVBoxLayout(left_widget)
        left_outer.setContentsMargins(0, 0, 0, 0)
        left_body = QWidget()
        left_body.setObjectName("Transparent")
        left_outer.addWidget(scrollable(left_body))
        left_layout = QVBoxLayout(left_body)
        left_layout.setContentsMargins(MD, LG, MD, LG)
        left_layout.setSpacing(MD)

        # Agent navigation lives in the workspace tabs. The rail is reserved
        # for projects, where persistent context is genuinely useful.
        self.agent_buttons = {}

        left_layout.addWidget(section("Projects"))

        self.history_project_filter = QComboBox()
        self.history_project_filter.currentIndexChanged.connect(self._switch_project)
        left_layout.addWidget(self.history_project_filter)

        self.active_project_label = QLabel("No project context")
        self.active_project_label.setObjectName("SettingsHelp")
        self.active_project_label.setWordWrap(True)
        left_layout.addWidget(self.active_project_label)

        # Narrow the list to one agent. Populated from the chats that exist, so
        # it only ever offers agents you have actually used.
        self.history_agent_filter = QComboBox()
        self.history_agent_filter.addItem(ALL_AGENTS_FILTER)
        self.history_agent_filter.currentTextChanged.connect(self.load_history_list)
        left_layout.addWidget(self.history_agent_filter)

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Search saved chats")
        self.history_search.textChanged.connect(self.load_history_list)
        left_layout.addWidget(self.history_search)

        left_layout.addWidget(section("Saved chats"))
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.open_selected_chat)
        # Double-click renames: chat_title_from_data already prefers a stored
        # "title" over the truncated first prompt, it was just never written.
        self.history_list.itemDoubleClicked.connect(self.rename_selected_chat)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._chat_context_menu)
        # The list takes the rail's spare height rather than being capped at
        # 200px with the buttons stranded at the bottom of the window.
        self.history_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_layout.addWidget(self.history_list, 1)

        left_layout.addWidget(rule())

        self.new_project_btn = QPushButton("New Project")
        self.new_project_btn.clicked.connect(self.create_project)
        left_layout.addWidget(self.new_project_btn)

        self.project_defaults_btn = quiet("Save Current Setup")
        self.project_defaults_btn.setToolTip(
            "Use this agent, provider and model when this project is opened."
        )
        self.project_defaults_btn.setEnabled(False)
        self.project_defaults_btn.clicked.connect(self.save_project_defaults)
        left_layout.addWidget(self.project_defaults_btn)

        self.new_chat_btn = quiet("New Chat")
        self.new_chat_btn.clicked.connect(self.new_chat)
        left_layout.addWidget(self.new_chat_btn)

        # Destructive and rarely wanted: quiet, and below the thing it acts on.
        self.delete_chat_btn = quiet("Remove Chat")
        self.delete_chat_btn.clicked.connect(self.delete_selected_chat)
        left_layout.addWidget(self.delete_chat_btn)

        return left_widget

    def build_center_panel(self) -> QWidget:
        center_widget = QWidget()
        center_widget.setObjectName("Transparent")
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(LG + SM, LG + SM, LG + SM, LG + SM)
        center_layout.setSpacing(MD)

        # The workspace tabs moved to the header bar. What stays here is the
        # stage switcher, which appears only when a workspace contains two
        # related tools (Draft/Publish or Audiobooks/Music).
        self.workspace_tool_row = QWidget()
        tool_row = QHBoxLayout(self.workspace_tool_row)
        tool_row.setContentsMargins(0, 0, 0, 0)
        tool_row.setSpacing(6)
        self.workspace_tool_buttons = {}
        for agent_name, label in WORKSPACE_LABELS.items():
            button = QPushButton(label)
            button.setObjectName("WorkspaceTool")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked, name=agent_name: self.select_agent(name)
            )
            tool_row.addWidget(button)
            self.workspace_tool_buttons[agent_name] = button
        tool_row.addStretch()
        center_layout.addWidget(self.workspace_tool_row)

        # ── Page title ──────────────────────────────────────────────────
        # Docs, tooltips and the status pill moved to the header bar: they are
        # application chrome, not part of this page, and having them here put a
        # row of controls between the title and the form it belongs to.
        self.agent_title_label = QLabel("Chat")
        self.agent_title_label.setObjectName("AgentTitle")
        center_layout.addWidget(self.agent_title_label)

        self.agent_subtitle_label = QLabel("")
        self.agent_subtitle_label.setObjectName("AgentSubtitle")
        self.agent_subtitle_label.setWordWrap(True)
        center_layout.addWidget(self.agent_subtitle_label)

        self.normal_panel = QWidget()
        normal_layout = QVBoxLayout(self.normal_panel)
        normal_layout.setContentsMargins(0, 0, 0, 0)
        normal_layout.setSpacing(10)

        # Row 1: command only
        top_row_1 = QHBoxLayout()

        self.agent_box = QComboBox()
        # Shared general-chat panel; the selector itself is hidden because the
        # workspace tabs already choose the agent.
        # The catalog, not config/agents.json plus an accumulating patch list,
        # defines the real roster.
        self.agent_box.addItems(WORKSPACE_LABELS)
        self.agent_box.hide()

        self.tool_label = QLabel("Tool:")
        top_row_1.addWidget(self.tool_label)

        self.tool_box = QComboBox()
        self.tool_box.addItems(self.tool_prompts.keys())

        self.tool_box.setMinimumWidth(140)
        top_row_1.addWidget(self.tool_box)

        self.command_label = QLabel("Command:")
        top_row_1.addWidget(self.command_label)

        self.command_box = QComboBox()
        self.command_box.addItems(self.commands.keys())
        self.command_box.setMinimumWidth(180)
        top_row_1.addWidget(self.command_box)

        top_row_1.addStretch()
        normal_layout.addLayout(top_row_1)

        # Row 2: provider, model, model tools
        top_row_2_container = QWidget()
        top_row_2 = FlowLayout(top_row_2_container, spacing=6)

        self.provider_box = QComboBox()
        self.provider_box.addItems(["ollama", "openai", "deepseek", "kimi", "gemini", "anthropic", "qwen"])
        self.provider_box.setMinimumWidth(120)
        top_row_2.addWidget(field("Provider", self.provider_box))

        self.model_box = QComboBox()
        self.model_box.setMinimumWidth(180)
        top_row_2.addWidget(field("Model", self.model_box))

        self.refresh_models_btn = QPushButton("Refresh Models")


        self.refresh_models_btn.setObjectName("ChipBtn")
        self.refresh_models_btn.clicked.connect(self.load_provider_models)
        top_row_2.addWidget(self.refresh_models_btn)

        # Offers a one-click pull of Meta's Muse Glimmer. Hidden once the model
        # is installed, since it is then just another entry in the model box.
        self.get_muse_btn = QPushButton("Get Muse Glimmer")
        self.get_muse_btn.setObjectName("ChipBtn")
        self.get_muse_btn.clicked.connect(self.pull_muse_glimmer)
        top_row_2.addWidget(self.get_muse_btn)

        self.model_guide_btn = QPushButton("Model Guide")


        self.model_guide_btn.setObjectName("ChipBtn")
        self.model_guide_btn.clicked.connect(self.show_model_guide)
        top_row_2.addWidget(self.model_guide_btn)

        self.docs_btn = QPushButton("Docs")


        self.docs_btn.setObjectName("ChipBtn")
        self.docs_btn.clicked.connect(self.show_docs)
        top_row_2.addWidget(self.docs_btn)

        normal_layout.addWidget(top_row_2_container)
        
        self.model_box.currentTextChanged.connect(self.save_provider_model_preference)

        # Row 3: execution mode and API permissions — wraps when the pane narrows.
        top_row_3_container = QWidget()
        top_row_3 = FlowLayout(top_row_3_container, spacing=6)

        self.execution_mode_box = QComboBox()
        self.execution_mode_box.addItems(["Local only", "Hybrid allowed", "Cloud only"])
        self.execution_mode_box.setMinimumWidth(120)
        top_row_3.addWidget(field("Mode", self.execution_mode_box))

        self.allow_openai_checkbox = QCheckBox("OpenAI")
        self.allow_openai_checkbox.setChecked(False)
        top_row_3.addWidget(self.allow_openai_checkbox)

        self.allow_deepseek_checkbox = QCheckBox("DeepSeek")
        self.allow_deepseek_checkbox.setChecked(False)
        top_row_3.addWidget(self.allow_deepseek_checkbox)

        self.allow_kimi_checkbox = QCheckBox("Kimi")
        self.allow_kimi_checkbox.setChecked(False)
        top_row_3.addWidget(self.allow_kimi_checkbox)

        self.allow_gemini_checkbox = QCheckBox("Gemini")
        self.allow_gemini_checkbox.setChecked(False)
        top_row_3.addWidget(self.allow_gemini_checkbox)

        self.allow_anthropic_checkbox = QCheckBox("Anthropic")
        self.allow_anthropic_checkbox.setChecked(False)
        top_row_3.addWidget(self.allow_anthropic_checkbox)

        self.allow_qwen_checkbox = QCheckBox("Qwen")
        self.allow_qwen_checkbox.setChecked(False)
        top_row_3.addWidget(self.allow_qwen_checkbox)

        self.allow_higgsfield_checkbox = QCheckBox("Higgsfield")
        self.allow_higgsfield_checkbox.setChecked(False)
        self.allow_higgsfield_checkbox.setToolTip(
            "Allow paid promo-video requests from the Creator workspace.")
        top_row_3.addWidget(self.allow_higgsfield_checkbox)

        self.allow_elevenlabs_checkbox = QCheckBox("ElevenLabs")
        self.allow_elevenlabs_checkbox.setChecked(False)
        self.allow_elevenlabs_checkbox.setToolTip(
            "Allow paid ElevenLabs narration for Manuscript shorts. The "
            "default narrator is the free on-device voice.")
        top_row_3.addWidget(self.allow_elevenlabs_checkbox)

        normal_layout.addWidget(top_row_3_container)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("Type your message here...")
        self.input_box.setMinimumHeight(190)
        normal_layout.addWidget(self.input_box)

        # Single action row — wraps instead of truncating when the pane narrows.
        actions_container = QWidget()
        actions_row = FlowLayout(actions_container, spacing=6)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedHeight(34)
        self.send_btn.setObjectName("PrimaryAction")
        self.send_btn.clicked.connect(self.send_prompt)
        actions_row.addWidget(self.send_btn)

        self.stop_chat_btn = QPushButton("Stop")
        self.stop_chat_btn.setFixedHeight(34)
        self.stop_chat_btn.setEnabled(False)
        self.stop_chat_btn.setObjectName("DangerAction")
        self.stop_chat_btn.clicked.connect(self.stop_current_task)
        actions_row.addWidget(self.stop_chat_btn)

        self.auto_route_btn = QPushButton("Auto Route")
        self.auto_route_btn.setFixedHeight(32)
        self.auto_route_btn.clicked.connect(self.auto_route_agent)
        actions_row.addWidget(self.auto_route_btn)

        self.recommend_setup_btn = QPushButton("Use Recommended")
        self.recommend_setup_btn.setFixedHeight(32)
        self.recommend_setup_btn.clicked.connect(self.apply_recommended_setup)
        actions_row.addWidget(self.recommend_setup_btn)

        # "Auto-Apply" modifies "Use Recommended", so it follows it directly. Its
        # own trailing padding provides the gap before the cost/export buttons —
        # a spacer item would wrap as if it were a control.
        self.auto_recommend_checkbox = QCheckBox("Auto-Apply")
        self.auto_recommend_checkbox.setChecked(False)
        actions_row.addWidget(self.auto_recommend_checkbox)

        self.estimate_btn = QPushButton("Estimate Cost")
        self.estimate_btn.setFixedHeight(32)
        self.estimate_btn.clicked.connect(self.show_cost_estimate_popup)
        actions_row.addWidget(self.estimate_btn)

        self.export_btn = QPushButton("Export Report")
        self.export_btn.setFixedHeight(32)
        self.export_btn.clicked.connect(self.export_report)
        actions_row.addWidget(self.export_btn)

        normal_layout.addWidget(actions_container)

        # ===== INPUT =====
        self.input_box.textChanged.connect(self.update_live_cost_estimate)
        self.input_box.textChanged.connect(self.update_recommendation_label)
        self.input_box.textChanged.connect(self.maybe_auto_apply_recommendation)

        # ===== TOOL / COMMAND =====
        self.command_box.currentTextChanged.connect(self.update_live_cost_estimate)
        self.command_box.currentTextChanged.connect(self.update_recommendation_label)

        self.tool_box.currentTextChanged.connect(self.update_live_cost_estimate)
        self.tool_box.currentTextChanged.connect(self.update_recommendation_label)

        # ===== PROVIDER =====
        self.provider_box.currentTextChanged.connect(self.load_provider_models)
        self.provider_box.currentTextChanged.connect(self.update_live_cost_estimate)
        self.provider_box.currentTextChanged.connect(self.update_recommendation_label)

        # ===== MODEL =====
        self.model_box.currentTextChanged.connect(self.update_live_cost_estimate)

        # ===== MODE =====
        self.execution_mode_box.currentTextChanged.connect(self.update_live_cost_estimate)
        self.execution_mode_box.currentTextChanged.connect(self.update_recommendation_label)

        # ===== API CHECKBOXES =====
        self.allow_openai_checkbox.stateChanged.connect(self.update_live_cost_estimate)
        self.allow_openai_checkbox.stateChanged.connect(self.update_recommendation_label)

        self.allow_deepseek_checkbox.stateChanged.connect(self.update_live_cost_estimate)
        self.allow_deepseek_checkbox.stateChanged.connect(self.update_recommendation_label)

        self.allow_kimi_checkbox.stateChanged.connect(self.update_live_cost_estimate)
        self.allow_kimi_checkbox.stateChanged.connect(self.update_recommendation_label)

        self.allow_gemini_checkbox.stateChanged.connect(self.update_live_cost_estimate)
        self.allow_gemini_checkbox.stateChanged.connect(self.update_recommendation_label)

        self.allow_anthropic_checkbox.stateChanged.connect(self.update_live_cost_estimate)
        self.allow_anthropic_checkbox.stateChanged.connect(self.update_recommendation_label)

        self.chat_progress = QProgressBar()
        self.chat_progress.setMinimum(0)
        self.chat_progress.setMaximum(0)
        self.chat_progress.hide()
        normal_layout.addWidget(self.chat_progress)

        self.chat_status_label = QLabel("")
        self.chat_status_label.hide()
        normal_layout.addWidget(self.chat_status_label)

        center_layout.addWidget(self.normal_panel)

        # Built from the same list update_agent_ui switches on, so an agent
        # cannot be constructed but unreachable, or reachable but never built.
        for _panel_name in CUSTOM_PANELS:
            getattr(self, f"build_{_panel_name}_panel")()
            center_layout.addWidget(getattr(self, f"{_panel_name}_panel"))

        self.output_label = micro("Output")
        self.output_label.hide()
        center_layout.addWidget(self.output_label)

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setMinimumHeight(130)
        self.output_box.hide()
        center_layout.addWidget(self.output_box, 1)

        self.load_provider_models()

        return center_widget

    def show_output_area(self):
        """Reveal the output label and box. Called when content arrives."""
        if hasattr(self, "output_label") and hasattr(self, "output_box"):
            self.output_label.setVisible(True)
            self.output_box.setVisible(True)

    def hide_output_area(self):
        """Hide the output label and box (e.g. after New Chat clears state)."""
        if hasattr(self, "output_label") and hasattr(self, "output_box"):
            self.output_label.setVisible(False)
            self.output_box.setVisible(False)
    
    def build_audiobook_panel(self):
        """Compose Audiobook's owned Convert and Listen workspace."""
        self.audiobook_panel = AudiobookPanel(self)

    def refresh_audiobook_library(self):
        """Compatibility entry point for the umbrella's workspace switch."""
        self.audiobook_panel.refresh_library()

    def play_selected_audiobook(self):
        self.audiobook_panel.play_selected()

    def restart_selected_audiobook(self):
        self.audiobook_panel.restart_selected()

    def reveal_selected_audiobook(self):
        self.audiobook_panel.reveal_selected()

    def build_author_panel(self):
        self.author_panel = QWidget()
        self.author_panel.setObjectName("AuthorPanel")
        layout = QVBoxLayout(self.author_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Project bar ──────────────────────────────────────────────────────
        # A grid, not a FlowLayout. FlowLayout packs each control against the
        # previous one, so "Tone:" and "POV:" landed at whatever x the row
        # before them happened to end on — which is most of why this screen
        # read as ragged. Equal column stretch puts row two's labels directly
        # under row one's.
        project_bar = QWidget()
        project_bar.setObjectName("AuthorProjectBar")

        self.author_title_input = line_edit("Project title…")
        self.author_name_input = line_edit("Pen name…")
        self.author_content_type_box = combo(["Fiction", "Non-Fiction"])
        self.author_content_type_box.currentTextChanged.connect(
            self._author_on_content_type_changed)
        self.author_genre_box = combo([
            "Literary Fiction", "Thriller", "Fantasy", "Sci-Fi", "Horror",
            "Romance", "Historical", "Mystery", "Short Story", "Screenplay",
            "Poetry", "Blog / Essay", "Other",
        ])
        self.author_tone_box = combo([
            "Neutral", "Dark", "Humorous", "Lyrical", "Tense", "Romantic",
            "Gritty", "Whimsical", "Philosophical", "Commercial",
        ])
        self.author_pov_box = combo([
            "Third Person Limited", "First Person",
            "Third Person Omniscient", "Second Person",
        ])

        # At desktop width these six short identity fields belong on one line.
        # The old 3×2 grid spent a quarter of the available canvas on empty
        # input width and pushed the actual manuscript below the fold.
        pb_layout = form_grid([
            ("Title", self.author_title_input),
            ("Author", self.author_name_input),
            ("Type", self.author_content_type_box),
            ("Genre", self.author_genre_box),
            ("Tone", self.author_tone_box),
            ("Point of view", self.author_pov_box),
        ], columns=6)
        pb_layout.setContentsMargins(MD, SM, MD, SM)
        project_bar.setLayout(pb_layout)

        layout.addWidget(project_bar)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        divider.setObjectName("CardDivider")
        layout.addWidget(divider)

        self.author_next_step_label = QLabel("")
        self.author_next_step_label.setWordWrap(True)
        self.author_next_step_label.setObjectName("NextStepBanner")
        layout.addWidget(self.author_next_step_label)

        # ── Book Profile (collapsed by default — persisted, injected into every mode) ──
        self.author_profile_section = CollapsibleSection(
            "Book Profile", expanded=False)

        self.author_profile_hook_input = QLineEdit()
        self.author_profile_hook_input.setPlaceholderText("One-sentence pitch — the core promise of the book…")
        self.author_profile_reader_input = QLineEdit()
        self.author_profile_reader_input.setPlaceholderText("e.g. Women 25-40 navigating modern dating apps")
        self.author_profile_comps_input = QLineEdit()
        self.author_profile_comps_input.setPlaceholderText("e.g. For readers of [Title A] and [Title B]")
        self.author_profile_path_box = QComboBox()
        self.author_profile_path_box.addItems(["Undecided", "Self-Publishing (KDP)", "Traditional"])

        profile_form = QWidget()
        profile_form.setObjectName("AuthorProfileForm")
        profile_grid = QGridLayout(profile_form)
        profile_grid.setContentsMargins(MD, XS, MD, SM)
        profile_grid.setHorizontalSpacing(MD)
        profile_grid.setVerticalSpacing(0)
        profile_grid.addWidget(field("Hook", self.author_profile_hook_input), 0, 0)
        profile_grid.addWidget(field("Target reader", self.author_profile_reader_input), 0, 1)
        profile_grid.addWidget(field("Comp titles", self.author_profile_comps_input), 0, 2)
        profile_grid.addWidget(field("Publishing path", self.author_profile_path_box), 0, 3)
        self.author_profile_save_btn = QPushButton("Save Profile")
        self.author_profile_save_btn.clicked.connect(self.author_save_profile)
        self.author_profile_save_btn.setMinimumWidth(120)
        profile_grid.addWidget(self.author_profile_save_btn, 0, 4, Qt.AlignBottom)
        for column in range(4):
            profile_grid.setColumnStretch(column, 1)
        self.author_profile_section.addWidget(profile_form)

        layout.addWidget(self.author_profile_section)

        # ── Main workspace ────────────────────────────────────────────────────
        # Compose is a shallow deck above the document, not a second vertical
        # application squeezed into a narrow scrolling sidebar. The previous
        # sidebar made Direction, Task and Model mutually invisible at laptop
        # height and stole a quarter of the writing canvas.
        write_page = QWidget()
        write_page.setObjectName("AuthorWritePage")
        write_layout = QVBoxLayout(write_page)
        write_layout.setContentsMargins(0, 0, 0, 0)
        write_layout.setSpacing(SM)

        compose_card = QFrame()
        compose_card.setObjectName("AuthorComposeCard")
        self.author_compose_card = compose_card
        compose_layout = QVBoxLayout(compose_card)
        compose_layout.setContentsMargins(MD, SM, MD, SM)
        compose_layout.setSpacing(SM)
        compose_layout.addWidget(section("Compose"))

        compose_grid = QGridLayout()
        compose_grid.setHorizontalSpacing(MD)
        compose_grid.setVerticalSpacing(0)

        self.author_direction_input = QLineEdit()
        self.author_direction_input.setPlaceholderText(
            "What happens next? One concrete instruction beats a paragraph."
        )
        self.author_direction_field = field(
            "Direction", self.author_direction_input)
        compose_grid.addWidget(self.author_direction_field, 0, 0)

        self.author_task_box = QComboBox()
        # Populated by _author_on_content_type_changed() after construction.
        self.author_task_field = field("Task", self.author_task_box)
        compose_grid.addWidget(self.author_task_field, 0, 1)

        self.author_panel_base = AgentPanel(
            self, "author",
            providers=("ollama", "openai", "deepseek", "kimi", "gemini", "anthropic", "qwen"),
            default_provider="anthropic")
        self.author_provider_box = self.author_panel_base.provider_box
        self.author_model_box = self.author_panel_base.model_box
        self.author_provider_field = field("Provider", self.author_provider_box)
        self.author_model_field = field("Model", self.author_model_box)
        compose_grid.addWidget(self.author_provider_field, 0, 2)
        compose_grid.addWidget(self.author_model_field, 0, 3)

        self.author_compose_actions = QWidget()
        compose_actions = QHBoxLayout(self.author_compose_actions)
        compose_actions.setContentsMargins(0, 0, 0, 0)
        compose_actions.setSpacing(SM)
        self.author_write_btn = QPushButton("Write")
        self.author_write_btn.setObjectName("PrimaryAction")
        self.author_write_btn.setMinimumWidth(130)
        self.author_write_btn.clicked.connect(self.author_write)
        compose_actions.addWidget(self.author_write_btn)

        self.author_continue_btn = QPushButton("Continue")
        self.author_continue_btn.setObjectName("SecondaryAction")
        self.author_continue_btn.clicked.connect(self.author_continue)
        compose_actions.addWidget(self.author_continue_btn)

        self.author_stop_btn = QPushButton("Stop")
        self.author_stop_btn.setEnabled(False)
        self.author_stop_btn.setObjectName("DangerAction")
        self.author_stop_btn.clicked.connect(self.author_stop)
        compose_actions.addWidget(self.author_stop_btn)
        compose_actions.addStretch()
        compose_grid.addWidget(
            self.author_compose_actions, 0, 4, Qt.AlignBottom)

        compose_grid.setColumnStretch(0, 3)
        compose_grid.setColumnStretch(1, 1)
        compose_grid.setColumnStretch(2, 1)
        compose_grid.setColumnStretch(3, 2)
        compose_grid.setColumnStretch(4, 0)
        self.author_compose_grid = compose_grid
        compose_layout.addLayout(compose_grid)
        write_layout.addWidget(compose_card)

        # The manuscript is the dominant surface and always remains visible.
        self.author_tabs = QTabWidget()

        self.author_draft_box = QTextEdit()
        self.author_draft_box.setPlaceholderText(
            "Your draft appears here. You can type and edit directly alongside the AI."
        )
        self.author_tabs.addTab(self.author_draft_box, "Draft")

        self.author_outline_box = QTextEdit()
        self.author_outline_box.setPlaceholderText("Chapter and scene outline…")
        self.author_tabs.addTab(self.author_outline_box, "Outline")

        self.author_characters_box = QTextEdit()
        self.author_characters_box.setPlaceholderText("Character profiles, arcs, relationships…")
        self.author_tabs.addTab(self.author_characters_box, "Characters")

        self.author_world_box = QTextEdit()
        self.author_world_box.setPlaceholderText("World-building notes, lore, setting, rules…")
        self.author_tabs.addTab(self.author_world_box, "World Notes")

        self.author_chapters_tab = QWidget()
        ct_layout = QVBoxLayout(self.author_chapters_tab)
        ct_layout.setContentsMargins(6, 6, 6, 6)
        ct_layout.setSpacing(6)

        self.author_chapters_stats_label = QLabel("No chapters detected yet.")
        self.author_chapters_stats_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTE};")
        ct_layout.addWidget(self.author_chapters_stats_label)

        self.author_chapters_list = QListWidget()
        self.author_chapters_list.itemDoubleClicked.connect(self._author_jump_to_chapter)
        ct_layout.addWidget(self.author_chapters_list, 1)

        author_chapters_refresh_btn = QPushButton("Refresh Chapters")
        author_chapters_refresh_btn.clicked.connect(self._author_refresh_chapters)
        ct_layout.addWidget(author_chapters_refresh_btn)

        self._author_chapter_offsets: list = []
        self.author_tabs.addTab(self.author_chapters_tab, "Chapters")
        self.author_tabs.currentChanged.connect(self._author_on_tab_changed)

        write_layout.addWidget(self.author_tabs, 1)

        # Document actions stay in one predictable footer. Counts are compact
        # status chips; they no longer occupy two stacked group boxes.
        document_bar = QFrame()
        document_bar.setObjectName("AuthorDocumentBar")
        document_actions = QHBoxLayout(document_bar)
        document_actions.setContentsMargins(MD, SM, MD, SM)
        document_actions.setSpacing(SM)

        self.author_word_metric = QWidget()
        self.author_word_metric.setObjectName("CompactMetric")
        word_metric_layout = QHBoxLayout(self.author_word_metric)
        word_metric_layout.setContentsMargins(SM, 0, SM, 0)
        word_metric_layout.setSpacing(SM)
        word_metric_layout.addWidget(micro("Words"))
        self.author_word_count_label = QLabel("0")
        self.author_word_count_label.setObjectName("CompactMetricValue")
        word_metric_layout.addWidget(self.author_word_count_label)
        document_actions.addWidget(self.author_word_metric)

        self.author_scene_metric = QWidget()
        self.author_scene_metric.setObjectName("CompactMetric")
        scene_metric_layout = QHBoxLayout(self.author_scene_metric)
        scene_metric_layout.setContentsMargins(SM, 0, SM, 0)
        scene_metric_layout.setSpacing(SM)
        scene_metric_layout.addWidget(micro("Scenes"))
        self.author_scene_count_label = QLabel("0")
        self.author_scene_count_label.setObjectName("CompactMetricValue")
        scene_metric_layout.addWidget(self.author_scene_count_label)
        document_actions.addWidget(self.author_scene_metric)

        self.author_save_btn = QPushButton("Save Draft")
        self.author_save_btn.setEnabled(False)
        self.author_save_btn.clicked.connect(self.author_save)
        document_actions.addWidget(self.author_save_btn)

        document_actions.addStretch()
        self.author_export_label = micro("Export")
        document_actions.addWidget(self.author_export_label)

        self.author_export_author_input = QLineEdit()
        self.author_export_author_input.setPlaceholderText("Author name")
        self.author_export_author_input.setMinimumWidth(100)
        self.author_export_author_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed)
        document_actions.addWidget(self.author_export_author_input, 1)

        self.author_export_format_box = QComboBox()
        self.author_export_format_box.setObjectName("CompactCombo")
        self.author_export_format_box.addItems(["EPUB", "DOCX", "PDF"])
        self.author_export_format_box.setFixedWidth(100)
        document_actions.addWidget(self.author_export_format_box)
        self.author_export_btn = QPushButton("Export Book")
        self.author_export_btn.clicked.connect(self.author_export_book)
        document_actions.addWidget(self.author_export_btn)

        self.author_clear_btn = quiet("Clear")
        self.author_clear_btn.setFixedWidth(62)
        self.author_clear_btn.clicked.connect(self.author_clear)
        document_actions.addWidget(self.author_clear_btn)
        self.author_document_bar = document_bar
        self.author_document_bar.setFixedHeight(58)
        write_layout.addWidget(document_bar)

        # ── Mode toggle row: Write | Publish & Market ────────────────────────
        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)

        self.author_mode_write_btn = QPushButton("Write")
        self.author_mode_write_btn.setCheckable(True)
        self.author_mode_write_btn.setChecked(True)
        self.author_mode_write_btn.setMinimumHeight(32)
        self.author_mode_write_btn.setObjectName("WorkspaceTool")
        self.author_mode_write_btn.clicked.connect(lambda: self._author_set_mode("write"))
        mode_row.addWidget(self.author_mode_write_btn)

        # "&&", not "&": Qt reads a single ampersand in button text as a mnemonic
        # marker and swallows it, so this rendered as "Publish_Market" with the
        # M underlined. Same trap CollapsibleSection documents for its titles.
        self.author_mode_pubmkt_btn = QPushButton("Publish && Market")
        self.author_mode_pubmkt_btn.setCheckable(True)
        self.author_mode_pubmkt_btn.setMinimumHeight(32)
        self.author_mode_pubmkt_btn.setObjectName("WorkspaceTool")
        self.author_mode_pubmkt_btn.clicked.connect(lambda: self._author_set_mode("pubmkt"))
        mode_row.addWidget(self.author_mode_pubmkt_btn)
        mode_row.addStretch()

        layout.addLayout(mode_row)

        # ── Content stack (Write / Publish & Market) ─────────────────────────
        self.author_content_stack = QStackedWidget()
        self.author_content_stack.addWidget(write_page)   # page 0: write

        # ── Publish & Market composite widget ────────────────────────────────
        pubmkt_widget = QWidget()
        pm_layout = QVBoxLayout(pubmkt_widget)
        pm_layout.setContentsMargins(0, 4, 0, 0)
        pm_layout.setSpacing(6)

        # Sub-mode toggle: Publish | Market
        sub_row = QHBoxLayout()
        sub_row.setSpacing(0)

        self.author_sub_publish_btn = QPushButton("Publish")
        self.author_sub_publish_btn.setCheckable(True)
        self.author_sub_publish_btn.setChecked(True)
        self.author_sub_publish_btn.setMinimumHeight(28)
        self.author_sub_publish_btn.setObjectName("WorkspaceTool")
        self.author_sub_publish_btn.clicked.connect(lambda: self._author_set_sub_mode("publish"))
        sub_row.addWidget(self.author_sub_publish_btn)

        self.author_sub_market_btn = QPushButton("Market")
        self.author_sub_market_btn.setCheckable(True)
        self.author_sub_market_btn.setMinimumHeight(28)
        self.author_sub_market_btn.setObjectName("WorkspaceTool")
        self.author_sub_market_btn.clicked.connect(lambda: self._author_set_sub_mode("market"))
        sub_row.addWidget(self.author_sub_market_btn)
        sub_row.addStretch()

        pm_layout.addLayout(sub_row)

        self.author_sub_stack = QStackedWidget()

        # ── Publish page ──────────────────────────────────────────────────────
        publish_page = QWidget()
        pub_outer = QVBoxLayout(publish_page)
        pub_outer.setContentsMargins(0, 0, 0, 0)
        pub_outer.setSpacing(SM)

        pub_ctrl = QFrame()
        pub_ctrl.setObjectName("AuthorPubCtrl")
        pc = QVBoxLayout(pub_ctrl)
        pc.setContentsMargins(MD, SM, MD, SM)
        pc.setSpacing(SM)

        self.author_pub_type_box = QComboBox()
        self.author_pub_type_box.addItems([
            "Synopsis — 1 Page", "Synopsis — 3 Page", "Query Letter",
            "Book Proposal", "Back-Cover Blurb", "Author Bio", "Chapter Breakdown",
        ])
        self.author_pub_wordcount_input = QLineEdit()
        self.author_pub_wordcount_input.setPlaceholderText("e.g. 80,000")
        self.author_pub_comps_input = QLineEdit()
        self.author_pub_comps_input.setPlaceholderText("e.g. Gone Girl meets Dark Places")
        self.author_pub_pitch_tone_box = QComboBox()
        self.author_pub_pitch_tone_box.addItems(["Professional", "Conversational", "High-Concept"])
        self.author_pub_notes_input = QTextEdit()
        self.author_pub_notes_input.setPlaceholderText("Target audience, themes, hook, extra context…")
        self.author_pub_notes_input.setFixedHeight(52)

        pub_fields = QGridLayout()
        pub_fields.setHorizontalSpacing(MD)
        pub_fields.setVerticalSpacing(0)
        pub_fields.addWidget(field("Output Type", self.author_pub_type_box), 0, 0)
        pub_fields.addWidget(field("Word Count Target", self.author_pub_wordcount_input), 0, 1)
        pub_fields.addWidget(field("Comp Titles", self.author_pub_comps_input), 0, 2)
        pub_fields.addWidget(field("Pitch Tone", self.author_pub_pitch_tone_box), 0, 3)
        pub_fields.addWidget(field("Extra Notes", self.author_pub_notes_input), 0, 4, 1, 2)
        for column in range(6):
            pub_fields.setColumnStretch(column, 1)
        pc.addLayout(pub_fields)

        pub_actions = QHBoxLayout()
        pub_actions.setSpacing(SM)

        self.author_pub_generate_btn = QPushButton("Generate")
        self.author_pub_generate_btn.setMinimumWidth(130)
        self.author_pub_generate_btn.setObjectName("PrimaryAction")
        self.author_pub_generate_btn.clicked.connect(self.author_pub_generate)
        pub_actions.addWidget(self.author_pub_generate_btn)

        self.author_pub_stop_btn = QPushButton("Stop")
        self.author_pub_stop_btn.setEnabled(False)
        self.author_pub_stop_btn.setObjectName("DangerAction")
        self.author_pub_stop_btn.clicked.connect(self.author_pub_stop)
        pub_actions.addWidget(self.author_pub_stop_btn)

        self.author_pub_copy_btn = QPushButton("Copy to Clipboard")
        self.author_pub_copy_btn.clicked.connect(self.author_pub_copy)
        pub_actions.addWidget(self.author_pub_copy_btn)

        self.author_pub_save_btn = QPushButton("Save as File")
        self.author_pub_save_btn.setEnabled(False)
        self.author_pub_save_btn.clicked.connect(self.author_pub_save)
        pub_actions.addWidget(self.author_pub_save_btn)
        pub_actions.addStretch()
        pc.addLayout(pub_actions)

        pub_outer.addWidget(pub_ctrl)

        self.author_pub_output = QTextEdit()
        self.author_pub_output.setPlaceholderText(
            "Generated publishing document appears here. Fully editable."
        )
        pub_outer.addWidget(self.author_pub_output, 1)

        self.author_sub_stack.addWidget(publish_page)   # sub-page 0

        # ── Market page ───────────────────────────────────────────────────────
        market_page = QWidget()
        mkt_outer = QVBoxLayout(market_page)
        mkt_outer.setContentsMargins(0, 0, 0, 0)
        mkt_outer.setSpacing(SM)

        mkt_ctrl = QFrame()
        mkt_ctrl.setObjectName("AuthorMktCtrl")
        mc = QVBoxLayout(mkt_ctrl)
        mc.setContentsMargins(MD, SM, MD, SM)
        mc.setSpacing(SM)

        self.author_mkt_platform_box = QComboBox()
        self.author_mkt_platform_box.addItems([
            "Amazon Description", "KDP Listing", "Goodreads Blurb", "Instagram Post",
            "Twitter / X Thread", "TikTok Caption", "Pinterest Pin Description",
            "YouTube Description", "Newsletter", "Press Release", "Book Club Questions",
            "ARC Outreach Email", "Launch Team Email", "Podcast Pitch", "Author Website Bio",
        ])
        self.author_mkt_hook_input = QLineEdit()
        self.author_mkt_hook_input.setPlaceholderText("One sentence that sells the book")
        self.author_mkt_comps_input = QLineEdit()
        self.author_mkt_comps_input.setPlaceholderText("e.g. Reaper's Creek meets Harlan Coben")
        self.author_mkt_tone_box = QComboBox()
        self.author_mkt_tone_box.addItems(["Punchy", "Literary", "Warm", "Hype", "Mysterious"])
        self.author_mkt_notes_input = QTextEdit()
        self.author_mkt_notes_input.setPlaceholderText("Target audience, mood, key themes…")
        self.author_mkt_notes_input.setFixedHeight(52)

        mkt_fields = QGridLayout()
        mkt_fields.setHorizontalSpacing(MD)
        mkt_fields.setVerticalSpacing(0)
        mkt_fields.addWidget(field("Platform", self.author_mkt_platform_box), 0, 0)
        mkt_fields.addWidget(field("Hook / Logline", self.author_mkt_hook_input), 0, 1)
        mkt_fields.addWidget(field("Comp Titles", self.author_mkt_comps_input), 0, 2)
        mkt_fields.addWidget(field("Tone", self.author_mkt_tone_box), 0, 3)
        mkt_fields.addWidget(field("Extra Notes", self.author_mkt_notes_input), 0, 4, 1, 2)
        for column in range(6):
            mkt_fields.setColumnStretch(column, 1)
        mc.addLayout(mkt_fields)

        mkt_actions = QHBoxLayout()
        mkt_actions.setSpacing(SM)

        self.author_mkt_generate_btn = QPushButton("Generate")
        self.author_mkt_generate_btn.setMinimumWidth(130)
        self.author_mkt_generate_btn.setObjectName("PrimaryAction")
        self.author_mkt_generate_btn.clicked.connect(self.author_mkt_generate)
        mkt_actions.addWidget(self.author_mkt_generate_btn)

        self.author_mkt_stop_btn = QPushButton("Stop")
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_mkt_stop_btn.setObjectName("DangerAction")
        self.author_mkt_stop_btn.clicked.connect(self.author_mkt_stop)
        mkt_actions.addWidget(self.author_mkt_stop_btn)

        self.author_mkt_copy_btn = QPushButton("Copy to Clipboard")
        self.author_mkt_copy_btn.clicked.connect(self.author_mkt_copy)
        mkt_actions.addWidget(self.author_mkt_copy_btn)

        self.author_mkt_save_btn = QPushButton("Save as File")
        self.author_mkt_save_btn.setEnabled(False)
        self.author_mkt_save_btn.clicked.connect(self.author_mkt_save)
        mkt_actions.addWidget(self.author_mkt_save_btn)
        mkt_actions.addStretch()
        mc.addLayout(mkt_actions)

        mkt_outer.addWidget(mkt_ctrl)

        self.author_mkt_output = QTextEdit()
        self.author_mkt_output.setPlaceholderText(
            "Generated marketing copy appears here. Fully editable."
        )
        mkt_outer.addWidget(self.author_mkt_output, 1)

        self.author_sub_stack.addWidget(market_page)   # sub-page 1

        pm_layout.addWidget(self.author_sub_stack, 1)
        self.author_content_stack.addWidget(pubmkt_widget)   # page 1

        layout.addWidget(self.author_content_stack, 1)

        self.author_status_label = QLabel("")
        self.author_status_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTE}; padding: 2px 4px;")
        layout.addWidget(self.author_status_label)

        self.author_draft_box.textChanged.connect(self._author_update_counts)

        # Apply the compact state once during construction; subsequent window
        # changes are handled by eventFilter on the panel itself.
        self._adapt_author_layout(self.author_panel.width())

        self.author_panel.hide()

        self.author_load_models()

        self._author_on_content_type_changed(self.author_content_type_box.currentText())
        self._author_load_profile()

    # ── Music Agent Panel ─────────────────────────────────────────────────────
    def build_music_panel(self):
        """Compose Music's independently owned panel into the umbrella."""
        self.music_panel = MusicPanel(self)

    # ── NFL Prop Bet Panel ───────────────────────────────────────────────────
    # ── OSINT Light panel ────────────────────────────────────────────────────
    # ── OSINT Pro (Heavy) panel ──────────────────────────────────────────────
    # ── OSINT Light handlers ──────────────────────────────────────────────────
    # ── OSINT Pro (Heavy) handlers ───────────────────────────────────────────
    # ── OSINT Pro image helpers ──────────────────────────────────────────────
    # ── Web Design panel ────────────────────────────────────────────────────
    def build_webdesign_panel(self):
        """Compose the Site Builder's independently owned workspace."""
        self.webdesign_panel = WebdesignPanel(self)

    # ── Wi-Fi Adapter panel ──────────────────────────────────────────────────
    # ── Wi-Fi handlers ───────────────────────────────────────────────────────
    # ── NFL Prop Bet handlers ────────────────────────────────────────────────
    # ── Season Model handlers ────────────────────────────────────────────────
    # ── Fiverr Agent Panel ───────────────────────────────────────────────────
    def build_fiverr_panel(self):
        """Client gigs: logo concepts, a delivery message, a gig listing.

        Rebuilt on the shared form idiom. Three things changed beyond looks:

        * The image model is now a control. "Generate Logos" is the only button
          on this page that spends money per click, and until now the model it
          used was hardcoded and invisible — the one visible model box drives
          the *text* outputs only, which is why nothing appeared to recommend
          GPT Image for the graphics work it was already doing.
        * The Status / Est. Cost / Order Log sidebar is gone. Status is a line
          under the buttons, the cost estimate sits beside the button that
          incurs it, and the order log is a tab rather than a 190px column
          with a three-column table squeezed into it.
        * Stop is hidden until there is something to stop, so the action row
          is three buttons with one clear answer instead of four.
        """
        from PySide6.QtWidgets import (
            QHeaderView, QSpinBox, QTableWidget,
        )
        from services.openai_client import IMAGE_MODELS, DEFAULT_IMAGE_MODEL

        self.fiverr_panel = QWidget()
        self.fiverr_panel.setObjectName("FiverrPanel")
        outer = QVBoxLayout(self.fiverr_panel)
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
        self.fiverr_count_spin.valueChanged.connect(self._fiverr_update_estimate)

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
            self, "fiverr",
            providers=("anthropic", "openai", "deepseek", "kimi", "gemini",
                       "qwen", "ollama"),
            default_provider="anthropic")
        self.fiverr_provider_box = self.fiverr_panel_base.provider_box
        self.fiverr_model_box = self.fiverr_panel_base.model_box

        self.fiverr_image_model_box = combo(list(IMAGE_MODELS),
                                            DEFAULT_IMAGE_MODEL)
        self.fiverr_image_model_box.currentTextChanged.connect(
            self._fiverr_update_estimate)

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
        self.fiverr_generate_btn.clicked.connect(self.fiverr_generate_logos)
        actions.addWidget(self.fiverr_generate_btn)

        self.fiverr_delivery_btn = QPushButton("Delivery Message")
        self.fiverr_delivery_btn.clicked.connect(self.fiverr_write_delivery)
        actions.addWidget(self.fiverr_delivery_btn)

        self.fiverr_gig_btn = QPushButton("Gig Description")
        self.fiverr_gig_btn.clicked.connect(self.fiverr_write_gig)
        actions.addWidget(self.fiverr_gig_btn)

        # Hidden rather than disabled: a permanently greyed button is chrome.
        self.fiverr_stop_btn = QPushButton("Stop")
        self.fiverr_stop_btn.setObjectName("DangerAction")
        self.fiverr_stop_btn.clicked.connect(self.fiverr_stop)
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
        self.fiverr_preview_status = QLabel("No logos yet — fill in the brief and generate.")
        self.fiverr_preview_status.setObjectName("EstimateLine")
        preview_top.addWidget(self.fiverr_preview_status)
        preview_top.addStretch()
        self.fiverr_save_images_btn = quiet("Save All Images")
        self.fiverr_save_images_btn.setEnabled(False)
        self.fiverr_save_images_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.fiverr_save_images_btn.clicked.connect(self.fiverr_save_images)
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
        self.fiverr_clear_btn.clicked.connect(self.fiverr_clear)
        clear_row.addWidget(self.fiverr_clear_btn)
        orders_layout.addLayout(clear_row)
        self.fiverr_tabs.addTab(orders_widget, "Orders")

        layout.addWidget(self.fiverr_tabs, 1)

        self._fiverr_update_estimate()
        self.fiverr_panel.hide()
        self.fiverr_load_models()

    def _fiverr_update_estimate(self, *_args):
        """Keep the per-image estimate next to the button that spends it.

        Priced from `config/pricing.json`, the same table the budget guard now
        reads, so what the label promises and what gets billed are one number.
        """
        from services.per_unit_pricing import describe, image_cost_eur
        model = self.fiverr_image_model_box.currentText()
        count = self.fiverr_count_spin.value()
        unit = f"{count} image{'s' if count != 1 else ''}"
        self.fiverr_cost_label.setText(
            describe(image_cost_eur(model, count), unit))

    # ── Social ───────────────────────────────────────────────────────────────
    def build_social_panel(self):
        """The public funnel for whatever the studio just made.

        Every other mode produces something that then needs an audience, and
        each had grown half a promotion story — Publish schedules quote
        graphics, Creator drafts one promo post — while nobody owned the funnel
        itself.

        Two things it deliberately does not do. It does not post on a timer:
        the schedule is a plan the user works through, and a tool that posts
        unattended is how an account gets banned for something its owner never
        saw. And it does not pretend every platform is postable — three are,
        today, and the Accounts tab says exactly what stands in the way of the
        rest rather than offering eight buttons of which five fail.
        """
        from services import social_platforms

        self.social_panel = QWidget()
        self.social_panel.setObjectName("SocialPanel")
        outer = QVBoxLayout(self.social_panel)
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
            self._social_campaign_changed)
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
        self.social_new_campaign_btn.clicked.connect(self.social_new_campaign)
        campaign_actions.addWidget(self.social_new_campaign_btn)
        self.social_save_campaign_btn = QPushButton("Save Campaign")
        self.social_save_campaign_btn.clicked.connect(self.social_save_campaign)
        campaign_actions.addWidget(self.social_save_campaign_btn)
        self.social_delete_campaign_btn = quiet("Delete campaign")
        self.social_delete_campaign_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.social_delete_campaign_btn.clicked.connect(self.social_delete_campaign)
        campaign_actions.addWidget(self.social_delete_campaign_btn)
        campaign_actions.addStretch()
        layout.addLayout(campaign_actions)

        # ── Compose ─────────────────────────────────────────────────────
        layout.addWidget(section("Compose"))

        self.social_platform_box = combo(list(social_platforms.names()))
        self.social_platform_box.currentTextChanged.connect(self._social_platform_changed)
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
            self, "social",
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
        self.social_write_btn.clicked.connect(self.social_write)
        actions.addWidget(self.social_write_btn)

        # The cooperation with Video: Social does not render anything itself,
        # it asks the video pipeline for a clip sized for the platform.
        self.social_clip_btn = QPushButton("Make a Clip")
        self.social_clip_btn.setToolTip(
            "Write a brief and hand it to the Video pipeline as a vertical "
            "clip for this platform.")
        self.social_clip_btn.clicked.connect(self.social_make_clip)
        actions.addWidget(self.social_clip_btn)

        self.social_schedule_btn = QPushButton("Schedule Drafts")
        self.social_schedule_btn.setToolTip(
            "Spread the campaign's undated drafts across the coming weeks at "
            "each platform's own cadence.")
        self.social_schedule_btn.clicked.connect(self.social_schedule_drafts)
        actions.addWidget(self.social_schedule_btn)

        self.social_stop_btn = QPushButton("Stop")
        self.social_stop_btn.setObjectName("DangerAction")
        self.social_stop_btn.clicked.connect(self.social_stop)
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
        self.social_save_draft_btn.clicked.connect(self.social_save_draft)
        draft_actions.addWidget(self.social_save_draft_btn)
        drafts.addLayout(draft_actions)
        self.social_draft_box.textChanged.connect(self._social_update_limit)
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
        self.social_copy_btn.clicked.connect(self.social_copy_selected)
        schedule_actions.addWidget(self.social_copy_btn)
        self.social_mark_posted_btn = QPushButton("Mark Posted")
        self.social_mark_posted_btn.setToolTip(
            "For the platforms you post by hand.")
        self.social_mark_posted_btn.clicked.connect(self.social_mark_posted)
        schedule_actions.addWidget(self.social_mark_posted_btn)
        self.social_metrics_btn = QPushButton("Record metrics")
        self.social_metrics_btn.setToolTip(
            "Enter observed reach and clicks for the selected posted item, with source and date window.")
        self.social_metrics_btn.clicked.connect(self.social_record_metrics)
        schedule_actions.addWidget(self.social_metrics_btn)
        self.social_post_btn = QPushButton("Post Now")
        self.social_post_btn.setObjectName("WarnAction")
        self.social_post_btn.setToolTip(
            "Publishes this one post through the platform's API. Only enabled "
            "where that is configured.")
        self.social_post_btn.clicked.connect(self.social_post_selected)
        schedule_actions.addWidget(self.social_post_btn)
        self.social_delete_post_btn = quiet("Delete")
        self.social_delete_post_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.social_delete_post_btn.clicked.connect(self.social_delete_post)
        schedule_actions.addWidget(self.social_delete_post_btn)
        schedule.addWidget(schedule_actions_container)
        self.social_tabs.addTab(schedule_page, "Schedule")

        analytics_page = QWidget()
        analytics_page.setObjectName("Transparent")
        analytics_layout = QVBoxLayout(analytics_page)
        analytics_layout.setContentsMargins(MD, MD, MD, MD)
        analytics_layout.setSpacing(MD)
        analytics_note = QLabel(
            "Observed post metrics only. Click-through rate is clicks ÷ reach for the same "
            "post and window; it does not prove sales or compare different audiences fairly.")
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
        self.social_refresh_accounts_btn.clicked.connect(self.social_refresh_accounts)
        refresh_row.addWidget(self.social_refresh_accounts_btn)
        accounts.addLayout(refresh_row)
        self.social_tabs.addTab(accounts_page, "Accounts")

        layout.addWidget(self.social_tabs, 1)

        self.social_worker = None
        self.social_panel_base.load_models()
        self.social_refresh_campaigns()
        self.social_refresh_accounts()
        self._social_platform_changed(self.social_platform_box.currentText())
        self.social_panel.hide()

    # ── Social handlers ──────────────────────────────────────────────────────
    def social_refresh_campaigns(self):
        from services import social_store
        self.social_campaign_box.blockSignals(True)
        self.social_campaign_box.clear()
        for campaign in social_store.list_campaigns():
            self.social_campaign_box.addItem(
                campaign["name"] or campaign["subject"] or "Untitled",
                campaign["id"])
        self.social_campaign_box.blockSignals(False)
        self._social_campaign_changed(self.social_campaign_box.currentIndex())

    def social_current_campaign(self) -> dict | None:
        from services import social_store
        campaign_id = self.social_campaign_box.currentData()
        return social_store.get_campaign(campaign_id) if campaign_id else None

    def _social_campaign_changed(self, _index):
        campaign = self.social_current_campaign()
        if not campaign:
            for widget in (self.social_subject_input, self.social_goal_input,
                           self.social_audience_input, self.social_links_input):
                widget.clear()
            self.social_refresh_schedule()
            return
        self.social_subject_input.setText(campaign.get("subject", ""))
        self.social_kind_box.setCurrentText(campaign.get("subject_kind", "other"))
        self.social_goal_input.setText(campaign.get("goal", ""))
        self.social_audience_input.setText(campaign.get("audience", ""))
        self.social_links_input.setText(campaign.get("links", ""))
        self.social_refresh_schedule()

    def social_new_campaign(self):
        from services import social_store
        subject = self.social_subject_input.text().strip() or "Untitled"
        campaign_id = social_store.create_campaign(
            name=subject, subject=subject,
            subject_kind=self.social_kind_box.currentText(),
            goal=self.social_goal_input.text().strip(),
            audience=self.social_audience_input.text().strip(),
            links=self.social_links_input.text().strip())
        self.social_refresh_campaigns()
        index = self.social_campaign_box.findData(campaign_id)
        if index >= 0:
            self.social_campaign_box.setCurrentIndex(index)
        self.social_status_label.setText(f"Created “{subject}”")

    def social_save_campaign(self):
        from services import social_store
        campaign = self.social_current_campaign()
        if not campaign:
            self.social_new_campaign()
            return
        subject = self.social_subject_input.text().strip()
        social_store.update_campaign(
            campaign["id"], name=subject or campaign["name"], subject=subject,
            subject_kind=self.social_kind_box.currentText(),
            goal=self.social_goal_input.text().strip(),
            audience=self.social_audience_input.text().strip(),
            links=self.social_links_input.text().strip())
        self.social_refresh_campaigns()
        self.social_status_label.setText("Saved")

    def social_delete_campaign(self):
        from services import social_store
        campaign = self.social_current_campaign()
        if not campaign:
            return
        confirm = QMessageBox.question(
            self, "Delete campaign",
            f"Delete “{campaign['name']}” and all of its posts?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        social_store.delete_campaign(campaign["id"])
        self.social_refresh_campaigns()

    def _social_platform(self):
        from services import social_platforms
        return social_platforms.get(
            social_platforms.key_for_name(self.social_platform_box.currentText()))

    def _social_platform_changed(self, _name=""):
        self._social_update_limit()

    def _social_update_limit(self):
        """Character count against the platform ceiling, live.

        The limit is in the prompt and models overshoot it anyway; posting an
        over-length draft is a rejected API call at the worst moment, so the
        count is visible while editing rather than checked at submit.
        """
        platform = self._social_platform()
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

    # ── Writing ──────────────────────────────────────────────────────────────
    def social_write(self):
        campaign = self.social_current_campaign()
        if not campaign:
            QMessageBox.warning(self, "No Campaign",
                                "Create a campaign first.")
            return
        platform = self._social_platform()
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
        token = self.authorize_request("social", provider, model,
                                       messages[-1]["content"],
                                       label=f"{platform.key} post")
        if not token:
            return
        self._social_request_token = token

        self.social_write_btn.setEnabled(False)
        self.social_stop_btn.show()
        self.social_stop_btn.setEnabled(True)
        self.social_status_label.setText(f"Writing for {platform.name}…")

        self.social_worker = self._new_chat_worker(provider, model,
                                        messages, "")
        self.social_worker.finished_signal.connect(self._social_on_written)
        self.social_worker.usage_signal.connect(
            lambda u, t=token: self.note_request_usage(t, u))
        self.social_worker.error_signal.connect(self._social_on_error)
        self.social_worker.start()

    def _social_on_written(self, response: str):
        token = getattr(self, "_social_request_token", None)
        self._social_request_token = None
        if token:
            self.record_request(token, response)
        variants = split_variants(response)
        separator = "\n\n" + "—" * 30 + "\n\n"
        self.social_draft_box.setPlainText(separator.join(variants))
        self.social_status_label.setText(
            f"{len(variants)} variant(s) — edit, then Save to Schedule")
        self._social_reset_buttons()
        self.social_tabs.setCurrentIndex(0)

    def _social_on_error(self, error: str):
        token = getattr(self, "_social_request_token", None)
        self._social_request_token = None
        if token:
            self.abandon_request(token)
        self.social_status_label.setText(f"[Error] {error}")
        self._social_reset_buttons()

    def _social_reset_buttons(self):
        self.social_write_btn.setEnabled(True)
        self.social_stop_btn.setEnabled(False)
        self.social_stop_btn.hide()

    def social_stop(self):
        # ChatWorker has cancel(), not stop() — calling the latter raised
        # AttributeError, left the worker running and the authorized request
        # unresolved.
        if self.social_worker is not None:
            self.social_worker.cancel()
        token = getattr(self, "_social_request_token", None)
        self._social_request_token = None
        if token:
            self.abandon_request(token, reason="stopped")
        self._social_reset_buttons()

    # ── Clips, via the Video pipeline ────────────────────────────────────────
    def social_make_clip(self):
        """Ask the Video mode for a clip sized for this platform.

        Social owns no rendering of its own. It writes a topic brief and hands
        it to the same `produce()` the Video tab uses, with the platform's
        aspect and a short length — which is why adding video to social cost a
        brief-writing prompt rather than a second video pipeline.
        """
        from agents.video import video_studio

        campaign = self.social_current_campaign()
        if not campaign:
            QMessageBox.warning(self, "No Campaign", "Create a campaign first.")
            return
        if not video_studio.available():
            QMessageBox.warning(self, "Video Unavailable",
                                video_studio.unavailable_reason())
            return
        platform = self._social_platform()
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
        token = self.authorize_request("social", provider, model,
                                       messages[-1]["content"],
                                       label="clip brief")
        if not token:
            return
        self._social_brief_token = token

        self.social_write_btn.setEnabled(False)
        self.social_clip_btn.setEnabled(False)
        self.social_status_label.setText("Writing the clip brief…")
        self._social_pending_clip = (platform.key, seconds)

        self.social_worker = self._new_chat_worker(provider, model,
                                        messages, "")
        self.social_worker.finished_signal.connect(self._social_on_clip_brief)
        self.social_worker.usage_signal.connect(
            lambda u, t=token: self.note_request_usage(t, u))
        self.social_worker.error_signal.connect(self._social_on_clip_error)
        self.social_worker.start()

    def _social_on_clip_brief(self, brief: str):
        from agents.video import video_studio
        from services.per_unit_pricing import eur_per_usd

        token = getattr(self, "_social_brief_token", None)
        self._social_brief_token = None
        if token:
            self.record_request(token, brief)
        platform_key, seconds = getattr(self, "_social_pending_clip",
                                        ("tiktok", 30))
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
            self._social_clip_done()
            return

        # A "video"-keyed request from Social: keeping the token is what
        # stops a concurrent Video-tab failure from popping this render's
        # pending context (and vice versa).
        video_token = self.authorize_request(
            "video", "openai", "vidforge-pipeline", topic,
            label=f"{platform_key} clip", flat_cost_eur=cost_eur)
        if not video_token:
            self._social_clip_done()
            return
        self._social_clip_video_token = video_token

        self.social_status_label.setText("Rendering clip — see the Video tab")
        self.social_worker = None
        self._social_clip_worker = VideoWorker(topic=topic, overrides=overrides)
        self._social_clip_worker.progress_signal.connect(
            lambda pct, detail: self.social_status_label.setText(
                f"Rendering clip… {pct}%"))
        self._social_clip_worker.done_signal.connect(self._social_on_clip_done)
        self._social_clip_worker.error_signal.connect(self._social_on_clip_error)
        self._social_clip_worker.start()

    def _social_on_clip_done(self, slug: str, path: str):
        from services import social_store
        token = getattr(self, "_social_clip_video_token", None)
        self._social_clip_video_token = None
        if token:
            self.record_request(token, f"social clip {slug}")
        campaign = self.social_current_campaign()
        platform_key, _seconds = getattr(self, "_social_pending_clip",
                                         ("tiktok", 30))
        if campaign:
            social_store.add_post(
                campaign["id"], platform_key,
                self.social_draft_box.toPlainText().strip(),
                fmt="clip", media_path=path,
                angle=self.social_angle_box.currentText())
            self.social_refresh_schedule()
        self.social_status_label.setText(f"Clip ready — {Path(path).name}")
        self._social_clip_done()
        self.refresh_video_library()

    def _social_on_clip_error(self, error: str):
        # The error can arrive from either stage: brief (its token pending)
        # or render (the video token pending). Abandon exactly what this
        # flow authorized, never by agent name.
        for attr in ("_social_brief_token", "_social_clip_video_token"):
            token = getattr(self, attr, None)
            setattr(self, attr, None)
            if token:
                self.abandon_request(token)
        self.social_status_label.setText(f"[Error] {error}")
        self._social_clip_done()

    def _social_clip_done(self):
        self.social_write_btn.setEnabled(True)
        self.social_clip_btn.setEnabled(True)
        self._social_reset_buttons()

    # ── Schedule ─────────────────────────────────────────────────────────────
    def social_save_draft(self):
        """Split the editor on its variant separators and store each as a post."""
        from services import social_store
        campaign = self.social_current_campaign()
        if not campaign:
            QMessageBox.warning(self, "No Campaign", "Create a campaign first.")
            return
        text = self.social_draft_box.toPlainText().strip()
        if not text:
            return
        platform = self._social_platform()
        pieces = [p.strip() for p in text.split("—" * 30)]
        pieces = [p for p in pieces if p]
        for piece in pieces:
            social_store.add_post(campaign["id"], platform.key, piece,
                                  fmt="text", angle=self.social_angle_box.currentText())
        self.social_refresh_schedule()
        self.social_tabs.setCurrentIndex(1)
        self.social_status_label.setText(
            f"{len(pieces)} post(s) saved to the schedule")

    def social_schedule_drafts(self):
        """Give every undated draft a date at its platform's own cadence."""
        from datetime import date

        from services import social_store
        campaign = self.social_current_campaign()
        if not campaign:
            return
        undated = [p for p in social_store.list_posts(campaign["id"])
                   if not p.get("scheduled_for")]
        if not undated:
            self.social_status_label.setText("Nothing undated to schedule")
            return

        platforms = sorted({p["platform"] for p in undated})
        slots = social_store.build_schedule(platforms, weeks=4,
                                            start=date.today())
        by_platform: dict[str, list] = {}
        for day, platform_key in slots:
            by_platform.setdefault(platform_key, []).append(day)

        scheduled = 0
        for post in undated:
            days = by_platform.get(post["platform"], [])
            if not days:
                continue
            social_store.update_post(post["id"],
                                     scheduled_for=days.pop(0).isoformat(),
                                     status="scheduled")
            scheduled += 1
        self.social_refresh_schedule()
        self.social_status_label.setText(f"{scheduled} post(s) scheduled")

    def social_refresh_schedule(self):
        from PySide6.QtWidgets import QTableWidgetItem

        from services import social_platforms, social_store
        if not hasattr(self, "social_schedule_table"):
            return
        campaign = self.social_current_campaign()
        posts = social_store.list_posts(campaign["id"]) if campaign else []
        self.social_schedule_table.setRowCount(0)
        for post in posts:
            row = self.social_schedule_table.rowCount()
            self.social_schedule_table.insertRow(row)
            platform = social_platforms.get(post["platform"])
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
        self.social_refresh_analytics(posts)

    def social_refresh_analytics(self, posts: list[dict] | None = None):
        from services import social_store
        if posts is None:
            campaign = self.social_current_campaign()
            posts = social_store.list_posts(campaign["id"]) if campaign else []
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

    def social_record_metrics(self):
        from services import social_store
        post = self._selected_social_post()
        if not post:
            QMessageBox.information(self, "Select a post", "Select a posted row in Schedule first.")
            return
        if post["status"] != "posted":
            QMessageBox.information(self, "Not posted", "Only posted items have observed metrics.")
            return
        reach, ok = QInputDialog.getInt(
            self, "Record reach", "Unique accounts reached:", int(post["reach"]), 0, 1_000_000_000)
        if not ok:
            return
        clicks, ok = QInputDialog.getInt(
            self, "Record clicks", "Link clicks:", int(post["clicks"]), 0, 1_000_000_000)
        if not ok:
            return
        source, ok = QInputDialog.getText(
            self, "Metric source", "Platform report or export:", text=post["metric_source"])
        if not ok:
            return
        window, ok = QInputDialog.getText(
            self, "Measurement window", "For example 2026-09-01 to 2026-09-07:",
            text=post["metric_window"])
        if not ok:
            return
        try:
            social_store.record_metrics(post["id"], reach=reach, clicks=clicks,
                                        source=source, window=window)
        except ValueError as exc:
            QMessageBox.warning(self, "Metrics not saved", str(exc))
            return
        self.social_refresh_schedule()
        self.social_tabs.setCurrentIndex(2)

    def _selected_social_post(self) -> dict | None:
        from services import social_store
        row = self.social_schedule_table.currentRow()
        if row < 0:
            return None
        item = self.social_schedule_table.item(row, 0)
        post_id = item.data(Qt.UserRole) if item else None
        return social_store.get_post(post_id) if post_id else None

    def social_copy_selected(self):
        post = self._selected_social_post()
        if not post:
            return
        QApplication.clipboard().setText(post["body"])
        self.social_status_label.setText("Copied")

    def social_mark_posted(self):
        from services import social_store
        post = self._selected_social_post()
        if not post:
            return
        social_store.mark_posted(post["id"])
        self.social_refresh_schedule()

    def social_delete_post(self):
        from services import social_store
        post = self._selected_social_post()
        if not post:
            return
        social_store.delete_post(post["id"])
        self.social_refresh_schedule()

    def social_post_selected(self):
        """Publish one post. Never more than one, never unattended."""
        from services import social_platforms, social_publishing, social_store

        post = self._selected_social_post()
        if not post:
            return
        platform = social_platforms.get(post["platform"])
        publisher = social_publishing.publisher_for(post["platform"])
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
            social_store.mark_failed(post["id"], str(exc))
            self.social_refresh_schedule()
            QMessageBox.warning(self, "Post failed", str(exc))
            self.social_status_label.setText("[Error] post failed")
            return
        social_store.mark_posted(post["id"], result.permalink)
        self.social_refresh_schedule()
        self.social_status_label.setText(f"Posted — {result.permalink or 'done'}")

    def social_refresh_accounts(self):
        """What can post today, and what stands in the way of the rest."""
        from services import social_publishing

        rows = []
        for name, ready, note in social_publishing.status_lines():
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

    # ── Video (vidforge) ─────────────────────────────────────────────────────
    def build_video_panel(self):
        """Topic in, finished video out — vidforge driven in-process.

        The pipeline is not vendored. `vidforge` is its own git repository
        nested at `imprint/vidforge/`, and `agents/video/studio.py` imports
        it: one checkout, one pipeline, two front doors. See that module for
        why a second copy would have been the worse trade.

        Long-form and social clips are the same `produce()` call with different
        numbers — the pipeline already sizes every stage from `video.width` /
        `video.height` and the script from a target length — so Format is a
        set of config overrides rather than a second rendering path. That is
        what lets the Social mode ask this panel for a clip instead of growing
        a video pipeline of its own.
        """
        from agents.video import video_studio
        from services.media_catalog import MEDIA_PROVIDERS

        self.video_panel = QWidget()
        self.video_panel.setObjectName("VideoPanel")
        outer = QVBoxLayout(self.video_panel)
        outer.setContentsMargins(0, 0, 0, 0)

        # A checkout of imprint alone has no vidforge. Explain that in place of
        # a form that cannot work, rather than failing on the first click.
        if not video_studio.available():
            notice = QLabel(video_studio.unavailable_reason())
            notice.setObjectName("EstimateLine")
            notice.setWordWrap(True)
            notice.setAlignment(Qt.AlignTop)
            outer.addWidget(notice)
            outer.addStretch()
            self.video_panel.hide()
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
        self.video_format_box.currentTextChanged.connect(self._video_format_changed)
        self.video_aspect_box = combo(list(video_studio.ASPECTS),
                                      video_studio.DEFAULT_ASPECT)
        self.video_aspect_box.currentTextChanged.connect(self._video_update_estimate)
        self.video_length_box = combo([f"{n}s" for n in video_studio.CLIP_SECONDS],
                                      "30s")
        self.video_length_box.currentTextChanged.connect(self._video_update_estimate)

        self.video_visual_provider_box = combo(list(MEDIA_PROVIDERS), "OpenAI")
        self.video_visual_model_box = QComboBox()
        self.video_visual_provider_box.currentTextChanged.connect(
            self._video_visual_provider_changed)
        self.video_visual_model_box.currentIndexChanged.connect(
            self._video_visual_model_changed)

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
        self.video_render_btn.clicked.connect(self.video_render)
        actions.addWidget(self.video_render_btn)

        self.video_folder_btn = QPushButton("Open Output Folder")
        self.video_folder_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(video_studio.output_root()))))
        actions.addWidget(self.video_folder_btn)

        self.video_stop_btn = QPushButton("Stop")
        self.video_stop_btn.setObjectName("DangerAction")
        self.video_stop_btn.clicked.connect(self.video_stop)
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
        self.video_play_btn.clicked.connect(self.video_play_selected)
        lib_actions.addWidget(self.video_play_btn)
        self.video_reveal_btn = QPushButton("Show in Finder")
        self.video_reveal_btn.clicked.connect(self.video_reveal_selected)
        lib_actions.addWidget(self.video_reveal_btn)
        self.video_refresh_btn = quiet("Rescan")
        self.video_refresh_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.video_refresh_btn.clicked.connect(self.refresh_video_library)
        lib_actions.addWidget(self.video_refresh_btn)
        lib.addLayout(lib_actions)
        self.video_tabs.addTab(library_page, "Library")

        layout.addWidget(self.video_tabs, 1)

        self.video_worker = None
        self.video_estimate_worker = None
        self._video_request_token = None
        self._video_external_context = {}
        self._video_active_kind = ""
        self._video_visual_provider_changed(
            self.video_visual_provider_box.currentText())
        self._video_format_changed(self.video_format_box.currentText())
        self.video_panel.hide()

    # ── Video handlers ───────────────────────────────────────────────────────
    def _video_visual_provider_changed(self, provider: str):
        """List only media models that have a real execution path."""
        from services.media_catalog import MODELS

        self.video_visual_model_box.blockSignals(True)
        self.video_visual_model_box.clear()
        for option in MODELS:
            if option.provider == provider:
                self.video_visual_model_box.addItem(option.label, option)
        self.video_visual_model_box.blockSignals(False)
        self._video_visual_model_changed()

    def _video_media_selection(self):
        return self.video_visual_model_box.currentData()

    def _video_set_lengths(self, values: tuple[int, ...], preferred: int) -> None:
        current = self.video_length_box.currentText()
        wanted = current if current in {f"{n}s" for n in values} else f"{preferred}s"
        self.video_length_box.blockSignals(True)
        self.video_length_box.clear()
        self.video_length_box.addItems([f"{n}s" for n in values])
        self.video_length_box.setCurrentText(wanted)
        self.video_length_box.blockSignals(False)

    def _video_visual_model_changed(self, *_args):
        from agents.video import video_studio

        selection = self._video_media_selection()
        if selection is None:
            return
        direct = selection.kind == "direct_video"
        if direct:
            self.video_format_box.setCurrentText("Social clip")
            self.video_format_box.setEnabled(False)
            durations = selection.durations or (4, 8, 12)
            preferred = 8 if 8 in durations else durations[0]
            self._video_set_lengths(durations, preferred)
            if self.video_aspect_box.currentText() not in selection.aspects:
                wanted = ("Vertical 9:16" if "Vertical 9:16" in selection.aspects
                          else selection.aspects[0])
                self.video_aspect_box.setCurrentText(wanted)
        else:
            self.video_format_box.setEnabled(True)
            self._video_set_lengths(video_studio.CLIP_SECONDS, 30)

        if selection.provider == "OpenAI" and selection.kind == "scene_images":
            note = (
                f"{selection.note} One image is generated for each scene. "
                "DALL·E 2 and 3 are not listed because OpenAI retired and "
                "removed both APIs. Sora is no longer offered — its Videos "
                "API shut down on 24 September 2026 with no successor; "
                "choose Gemini, Qwen or Higgsfield for direct video.")
        else:
            note = selection.note
        self.video_visual_note.setText(note)
        self._video_format_changed(self.video_format_box.currentText())

    def _video_format_changed(self, fmt: str):
        """Clip controls only apply to a clip."""
        is_clip = fmt == "Social clip"
        self.video_aspect_field.setVisible(is_clip)
        self.video_length_field.setVisible(is_clip)
        if is_clip and self.video_aspect_box.currentText() == "Landscape 16:9":
            self.video_aspect_box.setCurrentText("Vertical 9:16")
        self._video_update_estimate()

    def _video_overrides(self) -> dict:
        from agents.video import video_studio
        selection = self._video_media_selection()
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

    def _video_estimate(self) -> dict:
        from agents.video import video_studio
        from services.media_catalog import direct_video_cost_usd

        selection = self._video_media_selection()
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
            cfg = video_studio.load_config(self._video_overrides())
        except Exception:
            return {}
        return video_studio.pre_estimate(cfg)

    def _video_update_estimate(self, *_args):
        """What the run will cost, beside the button that starts it.

        A render is billed per image, per character of narration and per audio
        minute — none of which the token cost model can express. The number
        comes from vidforge's own per-stage arithmetic and is handed to the
        budget guard as a flat cost, so it counts against the caps rather than
        landing as €0.00.
        """
        from services.per_unit_pricing import eur_per_usd
        estimate = self._video_estimate()
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

    def video_render(self):
        from agents.video import video_studio
        from services.per_unit_pricing import eur_per_usd

        if self.video_worker is not None and self.video_worker.isRunning():
            return
        selection = self._video_media_selection()
        if selection is not None and selection.kind == "direct_video":
            self._video_render_direct(selection)
            return
        estimate = self._video_estimate()
        if not estimate:
            QMessageBox.warning(self, "Video Unavailable",
                                video_studio.unavailable_reason())
            return

        topic = self.video_topic_input.text().strip()
        cost_eur = round(estimate["total"] * eur_per_usd(), 4)
        token = self.authorize_request(
                "video", "openai", "vidforge-pipeline",
                topic or "next topic from topics.txt",
                label=self.video_format_box.currentText().lower(),
                flat_cost_eur=cost_eur)
        if not token:
            return
        self._video_request_token = token

        self._video_begin("pipeline", can_cancel=True)

        self.video_worker = VideoWorker(topic=topic,
                                        overrides=self._video_overrides())
        self.video_worker.stage_signal.connect(
            lambda _key, label: self.video_status_label.setText(f"{label}…"))
        self.video_worker.progress_signal.connect(self._video_on_progress)
        self.video_worker.log_signal.connect(self.video_log.append)
        self.video_worker.done_signal.connect(self._video_on_done)
        self.video_worker.error_signal.connect(self._video_on_error)
        self.video_worker.start()

    def _video_begin(self, kind: str, *, can_cancel: bool) -> None:
        self._video_active_kind = kind
        self.video_log.clear()
        self.video_progress.setValue(0)
        self.video_status_label.setText("Starting…")
        self.video_render_btn.setEnabled(False)
        self.video_stop_btn.setText(
            "Stop" if kind == "pipeline"
            else "Cancel" if can_cancel else "Cannot Cancel")
        self.video_stop_btn.setEnabled(can_cancel)
        self.video_stop_btn.show()

    def _video_direct_parameters(self) -> tuple[int, str]:
        seconds = int(self.video_length_box.currentText().rstrip("s") or 4)
        aspect = self.video_aspect_box.currentText()
        provider_aspect = {
            "Landscape 16:9": "16:9",
            "Vertical 9:16": "9:16",
            "Square 1:1": "1:1",
        }.get(aspect, "16:9")
        return seconds, provider_aspect

    def _video_render_direct(self, selection) -> None:
        from agents.video import video_studio

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
        seconds, provider_aspect = self._video_direct_parameters()
        self._video_external_context = {
            "slug": "", "path": "", "topic": topic,
            "provider": selection.provider.lower(), "model": selection.model_id,
            "seconds": seconds, "job_id": "", "provider_completed": False,
            "cancel_requested": False,
        }

        if selection.provider in {"Gemini", "Qwen"}:
            from services.media_catalog import direct_video_cost_usd
            from services.per_unit_pricing import eur_per_usd

            provider_key = selection.provider.lower()
            client = self.gemini if selection.provider == "Gemini" else self.qwen
            checkbox = (self.allow_gemini_checkbox if selection.provider == "Gemini"
                        else self.allow_qwen_checkbox)
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
            token = self.authorize_request(
                "video", provider_key, selection.model_id, topic,
                label="direct video", flat_cost_eur=round(
                    cost_usd * eur_per_usd(), 6))
            if not token:
                return
            self._video_request_token = token
            try:
                slug, output_path = video_studio.external_output_path(
                    topic, selection.model_id)
            except Exception as exc:
                self._video_on_error(str(exc))
                return
            self._video_external_context.update({
                "slug": slug, "path": str(output_path),
            })
            active_kind = f"{provider_key}-video"
            self._video_begin(active_kind, can_cancel=False)
            self.video_status_label.setText(
                f"Submitting to {selection.provider}… The provider has no safe "
                "cancel operation after submission, so Imprint will preserve "
                "the result locally.")
            self.video_worker = VideoGenerationWorker(
                client, topic, output_path, provider=selection.provider,
                model=selection.model_id, seconds=seconds,
                aspect_ratio=provider_aspect)
            self.video_worker.status_signal.connect(
                self.video_status_label.setText)
            self.video_worker.progress_signal.connect(self._video_on_progress)
            self.video_worker.job_signal.connect(self._video_external_job)
            self.video_worker.done_signal.connect(self._video_external_done)
            self.video_worker.error_signal.connect(self._video_on_error)
            self.video_worker.start()
            return

        if selection.provider == "Higgsfield":
            client = HiggsfieldClient()
            if not client.configured:
                QMessageBox.information(
                    self, "Higgsfield Key Needed",
                    "Set HF_API_KEY_ID and HF_API_KEY_SECRET in Imprint's "
                    "private .env file.")
                return
            if not self.allow_higgsfield_checkbox.isChecked():
                QMessageBox.warning(
                    self, "Higgsfield Not Enabled",
                    "Enable Higgsfield in the API permissions row first.")
                return
            self._video_begin("higgsfield-estimate", can_cancel=True)
            self.video_status_label.setText("Preparing Higgsfield estimate…")
            self.video_estimate_worker = HiggsfieldEstimateWorker(
                client, topic, duration=seconds,
                aspect_ratio=provider_aspect, resolution="720",
                model=selection.model_id)
            self.video_worker = self.video_estimate_worker
            self.video_estimate_worker.status_signal.connect(
                self.video_status_label.setText)
            self.video_estimate_worker.done_signal.connect(
                lambda request, estimate, c=client:
                self._video_higgsfield_estimated(c, request, estimate))
            self.video_estimate_worker.error_signal.connect(self._video_on_error)
            self.video_estimate_worker.start()

    def _video_higgsfield_estimated(self, client, request, estimate) -> None:
        from services.per_unit_pricing import eur_per_usd

        context = self._video_external_context
        if context.get("cancel_requested"):
            self._video_reset("Estimate cancelled.")
            return
        token = self.authorize_request(
            "video", "higgsfield", request.endpoint, context["topic"],
            label="direct video", flat_cost_eur=round(
                estimate.usd * eur_per_usd(), 6))
        if not token:
            self._video_reset("Render not approved.")
            return
        self._video_request_token = token
        from agents.video import video_studio
        try:
            slug, output_path = video_studio.external_output_path(
                context["topic"], context["model"])
        except Exception as exc:
            self._video_on_error(str(exc))
            return
        context.update({
            "slug": slug, "path": str(output_path),
            "model": request.endpoint,
        })
        self._video_begin("higgsfield", can_cancel=True)
        self.video_worker = HiggsfieldWorker(
            client, context["topic"], context["path"],
            prepared_request=request)
        self.video_worker.status_signal.connect(self.video_status_label.setText)
        self.video_worker.job_signal.connect(self._video_external_job)
        self.video_worker.done_signal.connect(self._video_external_done)
        self.video_worker.error_signal.connect(self._video_on_error)
        self.video_worker.start()

    def _video_external_job(self, job) -> None:
        self._video_external_context["job_id"] = getattr(
            job, "job_id", "")
        if getattr(job, "status", "") == "completed":
            # The provider has already produced the billable asset. Preserve
            # that fact even if saving it to disk or indexing it later fails.
            self._video_external_context["provider_completed"] = True

    def _video_external_done(self, path: str) -> None:
        from agents.video import video_studio

        context = self._video_external_context
        try:
            video_studio.record_external(
                slug=context["slug"], path=Path(path), topic=context["topic"],
                provider=context["provider"], model=context["model"],
                seconds=context["seconds"], job_id=context.get("job_id", ""))
        except Exception as exc:
            self._video_on_error(
                f"The provider completed the clip, but Imprint could not add "
                f"it to the library: {exc}")
            return
        self._video_on_done(context["slug"], path)

    def _video_on_progress(self, percent: int, detail: str):
        self.video_progress.setValue(percent)
        if detail:
            self.video_status_label.setText(detail)

    def _video_on_done(self, slug: str, path: str):
        # Never fall back to the agent name: with the Social clip flow also
        # authorizing under "video", a name lookup can pop the other flow's
        # pending context.
        token, self._video_request_token = self._video_request_token, None
        if token:
            self.record_request(token, f"rendered {slug}")
        self._video_reset(f"Done — {Path(path).name}")
        self.refresh_video_library()

    def _video_on_error(self, error: str):
        provider_completed = (
            self._video_active_kind in {
                "higgsfield", "gemini-video", "qwen-video"}
            and self._video_external_context.get("provider_completed", False)
        )
        token, self._video_request_token = self._video_request_token, None
        if token and provider_completed:
            self.record_request(
                token, "provider completed render; local save/index failed")
        elif token:
            # A failed or cancelled render releases the whole-video reserve.
            self.abandon_request(token)
        self.video_log.append(error)
        self._video_reset(f"[Error] {error}")

    def _video_reset(self, status: str) -> None:
        self.video_status_label.setText(status)
        self.video_render_btn.setEnabled(True)
        self.video_stop_btn.setEnabled(False)
        self.video_stop_btn.hide()
        self._video_active_kind = ""
        self._video_visual_model_changed()

    def video_stop(self):
        if self._video_active_kind in {"gemini-video", "qwen-video"}:
            provider = {
                "gemini-video": "Gemini", "qwen-video": "Wan",
            }[self._video_active_kind]
            self.video_status_label.setText(
                f"{provider} has no safe cancel operation here. Imprint will "
                "keep watching and "
                "save the paid result.")
            return
        if self.video_worker is not None:
            if self._video_active_kind == "higgsfield-estimate":
                self._video_external_context["cancel_requested"] = True
            self.video_worker.cancel()
            if self._video_active_kind.startswith("higgsfield"):
                self.video_status_label.setText("Requesting cancellation…")
            else:
                self.video_status_label.setText("Cancelling after this stage…")

    def refresh_video_library(self):
        from agents.video import video_studio
        if not hasattr(self, "video_library_table"):
            return
        entries = video_studio.library()
        self.video_library_table.setRowCount(0)
        from PySide6.QtWidgets import QTableWidgetItem
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

    def _selected_video_path(self) -> Path | None:
        row = self.video_library_table.currentRow()
        if row < 0:
            return None
        item = self.video_library_table.item(row, 0)
        raw = item.data(Qt.UserRole) if item else ""
        return Path(raw) if raw else None

    def video_play_selected(self):
        path = self._selected_video_path()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                self, "Not on disk",
                "That render is in the library but its file is missing — it "
                "was probably cancelled before the assembly stage.")

    def video_reveal_selected(self):
        path = self._selected_video_path()
        target = path.parent if path else None
        if target and target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    # ── OnlyFans venture intelligence ────────────────────────────────────────
    def build_onlyfans_panel(self):
        """Business intelligence stays with the venture, not the making tool."""
        self.onlyfans_panel = QWidget()
        self.onlyfans_panel.setObjectName("OnlyFansPanel")
        layout = QVBoxLayout(self.onlyfans_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.onlyfans_dashboard = OnlyFansDashboard()
        self.onlyfans_dashboard.campaign_requested.connect(
            self._onlyfans_create_campaign)
        self.onlyfans_dashboard.teaser_requested.connect(
            self._onlyfans_generate_teaser)
        layout.addWidget(self.onlyfans_dashboard)
        self.onlyfans_panel.hide()

    def _onlyfans_create_campaign(self, context: dict) -> None:
        """Carry a selected business signal into the shared Creator tool."""
        self.select_agent("creator")
        self.creator_platform_box.setCurrentText("OnlyFans")
        self.creator_kind_box.setCurrentText("campaign")
        self.creator_brief_input.setPlainText(format_creator_brief(context))
        self.creator_tabs.setCurrentIndex(0)
        self.creator_status_label.setText(
            "OnlyFans opportunity loaded — choose an account, review the brief, then Draft.")
        self.creator_brief_input.setFocus()

    def _onlyfans_generate_teaser(self, context: dict) -> None:
        """Generate a real SFW clip through Creator's Higgsfield pipeline."""
        self._onlyfans_create_campaign(context)
        self.creator_generate_video()

    # ── Creator (shared content production) ──────────────────────────────────
    def build_creator_panel(self):
        """Plan and draft content for any Imprint venture or platform.

        Deliberately has no send path. There is no OnlyFans API to post
        through, and the automation their terms allow is the kind that assists
        a human rather than replacing one — so everything here produces a draft
        the user reviews and sends by hand.

        The 210px right sidebar is gone. It held eleven label-above-control
        pairs and eight buttons stacked in one column, every one of them
        truncated at that width. The compose controls now sit in the main
        column like every other panel, and the four data actions moved into the
        tabs they act on: Add Media into Media, Add Performer Record into
        Records, Record Revenue and Import Earnings CSV into Earnings.
        """
        self.creator_panel = QWidget()
        self.creator_panel.setObjectName("CreatorPanel")
        outer = QVBoxLayout(self.creator_panel)
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
        self.creator_account_box.currentIndexChanged.connect(self._creator_account_changed)
        self.creator_handle_input = line_edit("@handle")
        self.creator_platform_box = combo([
            "General", "OnlyFans", "Writing / Publishing", "Music",
            "AltMerch", "Instagram", "TikTok", "X / Twitter", "Reddit",
            "YouTube", "Other",
        ], "General")
        self.creator_platform_box.currentTextChanged.connect(
            self._creator_update_policy_status)
        self.creator_type_box = combo(["own", "managed", "persona"])
        self.creator_type_box.currentTextChanged.connect(self._creator_type_changed)
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
        self.creator_save_account_btn.clicked.connect(self.creator_save_account)
        account_actions.addWidget(self.creator_save_account_btn)
        self.creator_delete_account_btn = quiet("Remove profile")
        self.creator_delete_account_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.creator_delete_account_btn.clicked.connect(self.creator_delete_account)
        account_actions.addWidget(self.creator_delete_account_btn)
        account_actions.addStretch()
        layout.addLayout(account_actions)

        policy_row = QHBoxLayout()
        self.creator_policy_status = QLabel("")
        self.creator_policy_status.setObjectName("EstimateLine")
        self.creator_policy_status.setWordWrap(True)
        policy_row.addWidget(self.creator_policy_status, 1)
        self.creator_policy_btn = quiet("Review platform policy")
        self.creator_policy_btn.clicked.connect(self.creator_review_policy)
        policy_row.addWidget(self.creator_policy_btn)
        layout.addLayout(policy_row)
        self._creator_update_policy_status(self.creator_platform_box.currentText())

        # ── Compose ─────────────────────────────────────────────────────
        layout.addWidget(section("Compose"))

        self.creator_kind_box = combo(
            ["post", "caption", "campaign", "posting_plan", "promo_assets",
             "hooks", "bio", "ppv", "welcome", "promo"])
        self.creator_kind_box.currentTextChanged.connect(self._creator_kind_changed)
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
            self, "creator",
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
        self.creator_generate_btn.clicked.connect(self.creator_generate)
        actions.addWidget(self.creator_generate_btn)

        self.creator_schedule_btn = QPushButton("Add to Calendar")
        self.creator_schedule_btn.clicked.connect(self.creator_schedule)
        actions.addWidget(self.creator_schedule_btn)

        self.creator_video_btn = QPushButton("Generate Teaser")
        self.creator_video_btn.setToolTip(
            "Render a promo teaser with Higgsfield. Paid, and subject to their "
            "content rules.")
        self.creator_video_btn.clicked.connect(self.creator_generate_video)
        actions.addWidget(self.creator_video_btn)

        self.creator_video_cancel_btn = QPushButton("Cancel Teaser")
        self.creator_video_cancel_btn.setObjectName("DangerAction")
        self.creator_video_cancel_btn.clicked.connect(self.creator_cancel_video)
        self.creator_video_cancel_btn.hide()
        actions.addWidget(self.creator_video_cancel_btn)

        self.creator_stop_btn = QPushButton("Stop")
        self.creator_stop_btn.setObjectName("DangerAction")
        self.creator_stop_btn.clicked.connect(self.creator_stop)
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
        self.creator_revenue_btn.clicked.connect(self.creator_record_outcome)
        self.creator_import_btn = QPushButton("Import Earnings CSV")
        self.creator_import_btn.clicked.connect(self.creator_import_earnings)
        self.creator_tabs.addTab(
            self._creator_tab_with_actions(
                self.creator_earnings_view,
                [self.creator_import_btn, self.creator_revenue_btn]),
            "Earnings")

        self.creator_voice_tab = self._build_creator_voice_tab()
        self.creator_tabs.addTab(self.creator_voice_tab, "Voice")

        self.creator_media_table = QTableWidget(0, 4)
        self.creator_media_table.setHorizontalHeaderLabels(
            ["File", "Kind", "Source", "Caption"])
        self.creator_media_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.creator_add_media_btn = QPushButton("Add Media")
        self.creator_add_media_btn.clicked.connect(self.creator_add_media)
        self.creator_tabs.addTab(
            self._creator_tab_with_actions(
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
        self.creator_add_performer_btn.clicked.connect(self.creator_add_performer)
        self.creator_tabs.addTab(
            self._creator_tab_with_actions(
                self.creator_records_table, [self.creator_add_performer_btn]),
            "Records")

        layout.addWidget(self.creator_tabs, 1)

        self.creator_worker = None
        self.creator_video_estimate_worker = None
        self.creator_video_worker = None
        self._creator_video_context = {}
        self.creator_panel.hide()
        self._creator_type_changed(self.creator_type_box.currentText())
        self._creator_kind_changed(self.creator_kind_box.currentText())
        self.creator_refresh_accounts()

    @staticmethod
    def _creator_tab_with_actions(body: QWidget, buttons: list) -> QWidget:
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

    # ── Creator handlers ─────────────────────────────────────────────────────
    def _creator_type_changed(self, account_type: str):
        """Consent fields matter for managed accounts; disclosure for personas."""
        is_managed = account_type == "managed"
        is_persona = account_type == "persona"
        self.creator_consent_field.setVisible(is_managed)
        self.creator_disclosure_field.setVisible(is_persona)

    def _creator_update_policy_status(self, platform: str):
        if not hasattr(self, "creator_policy_status"):
            return
        policy = get_policy(platform)
        review = policy["reviewed_on"] or "not reviewed"
        self.creator_policy_status.setText(
            f"{platform} policy · {review} · synthetic personas: "
            f"{policy['synthetic_persona']} · publishing: "
            f"{policy['publishing_method'].replace('_', ' ')}")

    def creator_review_policy(self):
        platform = self.creator_platform_box.currentText()
        dialog = CreatorPolicyDialog(platform, get_policy(platform), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            save_policy(platform, **dialog.values())
        except ValueError as exc:
            QMessageBox.warning(self, "Policy not saved", str(exc))
            return
        self._creator_update_policy_status(platform)

    def _creator_kind_changed(self, kind: str):
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
        self._creator_reflow_compose(wanted)

    def _creator_reflow_compose(self, wanted: list) -> None:
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

    def creator_refresh_accounts(self):
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
            self._note_failure("creator: load accounts", exc)
        self.creator_account_box.blockSignals(False)
        if self.creator_account_box.count():
            self._creator_account_changed(self.creator_account_box.currentIndex())

    def _creator_account_changed(self, index: int):
        account = self.creator_current_account()
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
        self.creator_refresh_calendar()
        self.creator_refresh_earnings()
        self.creator_load_voice_tab()
        self.creator_refresh_media()
        self.creator_refresh_records()
        self.creator_refresh_agency()

    def creator_current_account(self) -> dict | None:
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
            self._note_failure("creator: read account", exc)
            return None

    def creator_save_account(self):
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
            self._note_failure("creator: save account", exc, self.creator_status_label)
            return
        self.creator_status_label.setText(f"Saved {handle}.")
        self.creator_refresh_accounts()

    def creator_delete_account(self):
        account = self.creator_current_account()
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
            self._note_failure("creator: delete account", exc)
            return
        self.creator_refresh_accounts()

    # ── Drafting ─────────────────────────────────────────────────────────────
    def creator_generate(self):
        account = self.creator_current_account()
        if not account:
            QMessageBox.warning(self, "No Profile",
                                "Add a content profile before drafting.")
            return

        agent = self.agent_instances["creator"]
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
        token = self.authorize_request("creator", provider, model,
                                       messages[-1]["content"], label=kind)
        if not token:
            return
        self._creator_request_token = token

        self.creator_generate_btn.setEnabled(False)
        self._creator_last_generation_cost_eur = 0.0
        self.creator_stop_btn.setEnabled(True)
        self.creator_stop_btn.show()
        self.creator_status_label.setText(f"Drafting {kind}…")
        self.creator_output.clear()

        self.creator_worker = self._new_chat_worker(provider, model, messages, "")
        self.creator_worker.finished_signal.connect(self._creator_on_finished)
        self.creator_worker.error_signal.connect(self._creator_on_error)
        self.creator_worker.start()

    def _creator_on_finished(self, response: str):
        self.creator_output.setPlainText(response)
        token = getattr(self, "_creator_request_token", None)
        self._creator_request_token = None
        if token:
            self.record_request(token, response)
        self._creator_last_generation_cost_eur = float(self.last_request_cost or 0)
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText("Draft ready — review before posting.")

    def _creator_on_error(self, error: str):
        token = getattr(self, "_creator_request_token", None)
        self._creator_request_token = None
        if token:
            self.abandon_request(token)
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText(f"[Error] {error}")

    def creator_stop(self):
        # cancel(), never terminate(): killing a QThread that is inside a
        # Python call or holds the GIL is a crash/deadlock, and the worker
        # checks its flag at the next safe point anyway.
        if self.creator_worker is not None and self.creator_worker.isRunning():
            self.creator_worker.cancel()
        token = getattr(self, "_creator_request_token", None)
        self._creator_request_token = None
        if token:
            self.abandon_request(token, reason="stopped")
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText("Stopped.")

    # ── Calendar ─────────────────────────────────────────────────────────────
    def creator_schedule(self):
        account = self.creator_current_account()
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
                      float(getattr(self, "_creator_last_generation_cost_eur", 0.0))))
                conn.commit()
        except Exception as exc:
            self._note_failure("creator: schedule", exc, self.creator_status_label)
            return
        self.creator_refresh_calendar()
        self.creator_tabs.setCurrentIndex(1)

    def creator_refresh_calendar(self):
        account = self.creator_current_account()
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
            self._note_failure("creator: load calendar", exc)
            return
        # Row order maps to content ids so revenue can attach to a selection.
        self._creator_calendar_ids = [row["id"] for row in rows]
        for row in rows:
            r = self.creator_calendar_table.rowCount()
            self.creator_calendar_table.insertRow(r)
            for col, value in enumerate([
                    row["scheduled_for"], row["kind"], row["title"],
                    f"{row['price_usd']:.2f}" if row["price_usd"] else "",
                    f"{row['status']}"
                    + (f"  (${row['revenue_usd']:,.2f})" if row["revenue_usd"] else "")]):
                self.creator_calendar_table.setItem(r, col, QTableWidgetItem(str(value)))

    # ── Promo video ──────────────────────────────────────────────────────────
    def creator_generate_video(self):
        account = self.creator_current_account()
        if not account:
            QMessageBox.warning(self, "No Account", "Add an account first.")
            return
        agent = self.agent_instances["creator"]
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
        if not self.allow_higgsfield_checkbox.isChecked():
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

        output_dir = Path(BASE_DIR) / "output" / "creator" / str(account["id"])
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = output_dir / f"teaser-{stamp}.mp4"

        row = self.creator_calendar_table.currentRow()
        content_id = None
        if row >= 0 and row < len(getattr(self, "_creator_calendar_ids", [])):
            content_id = self._creator_calendar_ids[row]

        self._creator_video_context = {
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

        self.creator_video_estimate_worker = HiggsfieldEstimateWorker(
            client, prompt, reference_image=references[0] if references else None)
        self.creator_video_estimate_worker.status_signal.connect(
            self.creator_video_status.setText)
        self.creator_video_estimate_worker.done_signal.connect(
            lambda request, estimate, c=client:
            self._creator_video_estimated(c, request, estimate))
        self.creator_video_estimate_worker.error_signal.connect(
            self._creator_video_error)
        self.creator_video_estimate_worker.start()

    def _creator_video_estimated(self, client, request, estimate):
        """Show the provider's exact price before authorising generation."""
        context = self._creator_video_context
        if not context:
            return
        if context.get("cancel_requested"):
            self._creator_video_reset("Cancelled.")
            return
        from services.per_unit_pricing import eur_per_usd
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

        token = self.authorize_request(
            "creator", "higgsfield", request.endpoint,
            context["prompt"], label="promo teaser", flat_cost_eur=cost_eur)
        if not token:
            self._creator_video_reset("Render not approved.")
            return
        context["request_token"] = token

        self.creator_video_worker = HiggsfieldWorker(
            client, context["prompt"], context["output_path"],
            prepared_request=request)
        self.creator_video_worker.status_signal.connect(
            self.creator_video_status.setText)
        self.creator_video_worker.job_signal.connect(
            self._creator_video_job_update)
        self.creator_video_worker.done_signal.connect(
            lambda path, aid=context["account_id"]:
            self._creator_video_done(aid, path))
        self.creator_video_worker.error_signal.connect(
            self._creator_video_error)
        self.creator_video_worker.start()

    def creator_cancel_video(self):
        """Cancel preparation, or ask Higgsfield to cancel a queued render."""
        if self._creator_video_context:
            self._creator_video_context["cancel_requested"] = True
        estimate_worker = self.creator_video_estimate_worker
        render_worker = self.creator_video_worker
        if estimate_worker is not None and estimate_worker.isRunning():
            estimate_worker.cancel()
            self.creator_video_status.setText("Cancelling estimate…")
        elif render_worker is not None and render_worker.isRunning():
            render_worker.cancel()
            self.creator_video_status.setText(
                "Cancellation requested. If rendering already began, "
                "Higgsfield will finish and Imprint will save the result.")
        self.creator_video_cancel_btn.setEnabled(False)

    def _creator_video_job_update(self, job):
        """Persist every provider state transition for recovery and support."""
        context = self._creator_video_context
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
            self._note_failure("creator: track Higgsfield job", exc,
                               self.creator_video_status)

    def _creator_video_done(self, account_id: int, path: str):
        """Store the render in the media library rather than leaving it on disk."""
        context = self._creator_video_context
        self.record_request(context.get("request_token") or "creator",
                            f"teaser: {Path(path).name}")
        self._creator_store_media(account_id, path, source="higgsfield",
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
                self._note_failure("creator: attach teaser", exc,
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
                self._note_failure("creator: save teaser path", exc,
                                   self.creator_video_status)
        note = f"Saved: {Path(path).name}"
        if attached:
            note += " · attached to the selected calendar item"
        self._creator_video_reset(note)
        self.creator_refresh_media()
        if attached:
            self.creator_refresh_calendar()

    def _creator_video_error(self, error: str):
        context = self._creator_video_context
        token = context.get("request_token") if context else None
        if token:
            if context.get("provider_completed"):
                # A completed render is charged even if the local download
                # later fails; keep spend accounting honest.
                self.record_request(token, f"render completed; local error: {error}")
            else:
                self.abandon_request(token)
        self._creator_video_reset(f"[Error] {error}")

    def _creator_video_reset(self, status: str):
        self.creator_video_btn.setEnabled(True)
        self.creator_video_cancel_btn.setEnabled(False)
        self.creator_video_cancel_btn.hide()
        self.creator_video_status.setText(status)

    # ── Earnings ─────────────────────────────────────────────────────────────
    def creator_import_earnings(self):
        """Import an earnings CSV exported from the platform.

        The same shape as the KDP importer, and for the same reason: no API, so
        the numbers only exist here once the statement is exported and read in.
        """
        account = self.creator_current_account()
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
            self._note_failure("creator: import earnings", exc,
                               self.creator_status_label)
            return
        self.creator_status_label.setText(
            f"Imported {summary['rows']} rows from {Path(path).name}.")
        self.creator_refresh_earnings()
        self.creator_tabs.setCurrentIndex(2)

    def creator_refresh_earnings(self):
        account = self.creator_current_account()
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
            self._note_failure("creator: load earnings", exc)
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

    def creator_load_models(self):
        """Kept as a method so existing call sites stay put."""
        self.creator_panel_base.load_models()

    def _build_creator_voice_tab(self) -> QWidget:
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
        save_btn.clicked.connect(self.creator_save_voice)
        layout.addWidget(save_btn)
        return page

    def creator_save_voice(self):
        account = self.creator_current_account()
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

    def creator_load_voice_tab(self):
        account = self.creator_current_account()
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

    # ── Media library ────────────────────────────────────────────────────────
    def creator_add_media(self):
        account = self.creator_current_account()
        if not account:
            QMessageBox.warning(self, "No Account", "Select an account first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Media", "",
            "Media (*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.m4a *.mp3)")
        if not paths:
            return
        for path in paths:
            self._creator_store_media(account["id"], path, source="upload")
        self.creator_refresh_media()
        self.creator_tabs.setCurrentWidget(self.creator_media_table)

    def _creator_store_media(self, account_id: int, path: str,
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
            self._note_failure("creator: store media", exc)

    def creator_refresh_media(self):
        account = self.creator_current_account()
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
            self._note_failure("creator: load media", exc)
            return
        for row in rows:
            r = self.creator_media_table.rowCount()
            self.creator_media_table.insertRow(r)
            for col, value in enumerate([Path(row["path"]).name, row["kind"],
                                         row["source"], row["caption"]]):
                self.creator_media_table.setItem(r, col, QTableWidgetItem(str(value)))

    # ── Performer records ────────────────────────────────────────────────────
    def creator_add_performer(self):
        """Record that age/identity records exist for someone depicted.

        Deliberately records *that* documents are held and where — not the
        documents. In the US, 18 U.S.C. 2257 puts this obligation on the
        producer; storing scans of passports in an app database would create a
        second problem rather than solve the first.
        """
        account = self.creator_current_account()
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
            self._note_failure("creator: add performer", exc)
            return
        self.creator_refresh_records()
        self.creator_tabs.setCurrentWidget(self.creator_records_table)

    def creator_refresh_records(self):
        account = self.creator_current_account()
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
            self._note_failure("creator: load records", exc)
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

    # ── Revenue attribution ──────────────────────────────────────────────────
    def creator_record_outcome(self):
        """Attach a source-labelled observation to the selected calendar item."""
        row = self.creator_calendar_table.currentRow()
        ids = getattr(self, "_creator_calendar_ids", [])
        if row < 0 or row >= len(ids):
            QMessageBox.information(
                self, "Select an item",
                "Select an asset on Calendar first, then return to Earnings.")
            return
        with get_connection() as conn:
            item = conn.execute(
                "SELECT * FROM creator_content WHERE id=?", (ids[row],)).fetchone()
        if item is None:
            QMessageBox.warning(self, "Missing item", "The selected asset no longer exists.")
            return
        dialog = CreatorOutcomeDialog(dict(item), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            record_outcome(ids[row], **dialog.values())
        except ValueError as exc:
            QMessageBox.warning(self, "Outcome not saved", str(exc))
            return
        self.creator_refresh_calendar()
        self.creator_refresh_earnings()
        self.creator_tabs.setCurrentIndex(2)

    def creator_record_revenue(self):
        """Attach what a calendar item earned, closing the loop to the drafter."""
        row = self.creator_calendar_table.currentRow()
        ids = getattr(self, "_creator_calendar_ids", [])
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
        self.creator_refresh_calendar()
        self.creator_refresh_earnings()

    # ── Agency ───────────────────────────────────────────────────────────────
    def creator_refresh_agency(self):
        self.creator_agency_table.setRowCount(0)
        try:
            rows = agency_overview()
        except Exception as exc:
            self._note_failure("creator: agency overview", exc)
            return
        for row in rows:
            r = self.creator_agency_table.rowCount()
            self.creator_agency_table.insertRow(r)
            for col, value in enumerate([
                    row["handle"], row["account_type"],
                    row["consent_holder"] or "—",
                    f"{row['net']:,.2f}", row["subscribers"], row["drafts"]]):
                self.creator_agency_table.setItem(r, col, QTableWidgetItem(str(value)))

    # ── Fiverr handlers ──────────────────────────────────────────────────────
    def fiverr_load_models(self):
        """Kept as a method so existing call sites stay put."""
        self.fiverr_panel_base.load_models()

    def _fiverr_get_brief(self) -> dict:
        return {
            "business_name": self.fiverr_name_input.text().strip(),
            "industry": self.fiverr_industry_input.text().strip(),
            "style": self.fiverr_style_box.currentText(),
            "colors": self.fiverr_colors_input.text().strip(),
            "notes": self.fiverr_notes_input.toPlainText().strip(),
        }

    def fiverr_generate_logos(self):
        brief = self._fiverr_get_brief()
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

        agent = self.agent_instances["fiverr"]
        messages = agent.build_image_prompt_request(brief)

        self.fiverr_status_label.setText("Building image prompt...")
        self.fiverr_generate_btn.setEnabled(False)
        self.fiverr_delivery_btn.setEnabled(False)
        self.fiverr_gig_btn.setEnabled(False)
        self.fiverr_stop_btn.setEnabled(True)
        self.fiverr_stop_btn.show()
        self._fiverr_clear_logo_grid()

        # Keep the token: "fiverr" is shared by the prompt request and the
        # image request that follows it, plus the delivery/gig text flows.
        token = self.authorize_request(
            "fiverr", provider, model,
            messages[-1]["content"] if messages else "")
        if not token:
            # Refused — re-enable the buttons disabled above, or the panel
            # stays stuck until restart.
            self._fiverr_reset_buttons()
            return
        self._fiverr_prompt_token = token
        self.fiverr_text_worker = self._new_chat_worker(provider, model, messages, "")
        self.fiverr_text_worker.finished_signal.connect(self._fiverr_on_prompt_ready)
        self.fiverr_text_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.fiverr_text_worker.error_signal.connect(self._fiverr_on_text_error)
        self.fiverr_text_worker.start()
        self._fiverr_pending_count = count
        self._fiverr_pending_brief = brief

    def _fiverr_on_prompt_ready(self, image_prompt: str):
        from services.per_unit_pricing import image_cost_eur
        token = getattr(self, "_fiverr_prompt_token", None)
        self._fiverr_prompt_token = None
        if token:
            self.record_request(token, image_prompt)
        image_prompt = image_prompt.strip()
        count = self._fiverr_pending_count
        brief = self._fiverr_pending_brief
        save_dir = DATA_DIR / "fiverr_output" / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.fiverr_status_label.setText(f"Generating {count} concept(s)...")

        # The images are a second paid request, billed per image rather than
        # per token. Until the guard learned per-unit costs this ran entirely
        # outside the budget caps.
        image_model = self.fiverr_image_model_box.currentText()
        image_cost = image_cost_eur(image_model, count)
        if image_cost is None:
            # A rate of 0 means unknown, not free. Coercing None to 0.0 here
            # authorized unpriced models at €0.00 against every cap; refusing
            # is the same posture the per-unit table documents. (Passing None
            # through is no better — authorize_request would fall back to
            # pricing the ~200-char prompt as a chat request.)
            QMessageBox.warning(
                self, "No Price Configured",
                f"{image_model} has no per-image rate in config/pricing.json, "
                "so the logo images cannot be billed against the budget caps. "
                "Add a rate (0 means unknown) before generating.")
            self._fiverr_reset_buttons()
            return
        image_token = self.authorize_request(
            "fiverr", "openai", image_model,
            f"{count} logo concepts: {image_prompt[:200]}",
            label="logo images",
            flat_cost_eur=image_cost)
        if not image_token:
            self._fiverr_reset_buttons()
            return
        self._fiverr_image_token = image_token

        self.fiverr_image_worker = FiverrImageWorker(
            self.openai, image_prompt, count, save_dir,
            image_model=image_model)
        self.fiverr_image_worker.image_ready_signal.connect(self._fiverr_on_image_ready)
        self.fiverr_image_worker.all_done_signal.connect(self._fiverr_on_all_done)
        self.fiverr_image_worker.error_signal.connect(self._fiverr_on_image_error)
        self.fiverr_image_worker.status_signal.connect(lambda s: self.fiverr_status_label.setText(s))
        self.fiverr_image_worker.start()

        row = self.fiverr_order_table.rowCount()
        self.fiverr_order_table.insertRow(row)
        from PySide6.QtWidgets import QTableWidgetItem
        self.fiverr_order_table.setItem(row, 0, QTableWidgetItem(brief.get("business_name", "")))
        self.fiverr_order_table.setItem(row, 1, QTableWidgetItem(str(count)))
        self.fiverr_order_table.setItem(row, 2, QTableWidgetItem("Generating"))
        self._fiverr_order_row = row

    def _fiverr_on_image_ready(self, path: str, index: int):
        from PySide6.QtGui import QPixmap
        lbl = QLabel()
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl.setPixmap(pixmap)
        else:
            lbl.setText(f"[Concept {index + 1}]")
        lbl.setToolTip(path)
        lbl.setAlignment(Qt.AlignCenter)
        self.fiverr_logo_grid_layout.addWidget(lbl)
        self._fiverr_image_paths.append(path)
        self.fiverr_preview_status.setText(f"Concept {index + 1} ready — {Path(path).name}")
        self.fiverr_tabs.setCurrentIndex(0)

    def _fiverr_reset_buttons(self):
        """Back to idle. Every exit path from a run goes through here."""
        self.fiverr_generate_btn.setEnabled(True)
        self.fiverr_delivery_btn.setEnabled(True)
        self.fiverr_gig_btn.setEnabled(True)
        self.fiverr_stop_btn.setEnabled(False)
        self.fiverr_stop_btn.hide()

    def _fiverr_on_all_done(self, paths: list):
        self._fiverr_image_paths = paths
        self.fiverr_status_label.setText(f"Done — {len(paths)} logo(s) generated.")
        # Closes out the image request authorised in _fiverr_on_prompt_ready,
        # billing the per-image cost it was authorised against.
        token = getattr(self, "_fiverr_image_token", None)
        self._fiverr_image_token = None
        if token:
            self.record_request(token, f"{len(paths)} logo images")
        self._fiverr_reset_buttons()
        self.fiverr_save_images_btn.setEnabled(True)
        if hasattr(self, "_fiverr_order_row"):
            from PySide6.QtWidgets import QTableWidgetItem
            self.fiverr_order_table.setItem(self._fiverr_order_row, 2, QTableWidgetItem("Done"))

    def _fiverr_on_image_error(self, error: str):
        # A failed render still consumed whatever it managed before failing,
        # but the authorised amount was for the full set — release it rather
        # than bill for images that were never produced.
        token = getattr(self, "_fiverr_image_token", None)
        self._fiverr_image_token = None
        if token:
            self.abandon_request(token)
        self.fiverr_status_label.setText(f"Error: {error}")
        self.fiverr_preview_status.setText(f"[Error] {error}")
        self._fiverr_reset_buttons()
        if hasattr(self, "_fiverr_order_row"):
            from PySide6.QtWidgets import QTableWidgetItem
            self.fiverr_order_table.setItem(self._fiverr_order_row, 2, QTableWidgetItem("Error"))

    def _fiverr_on_text_error(self, error: str):
        # Shared by all three fiverr text flows (prompt, delivery, gig) —
        # they are single-flight via the disabled buttons, so one token
        # attribute covers them.
        token = getattr(self, "_fiverr_prompt_token", None)
        self._fiverr_prompt_token = None
        if token:
            self.abandon_request(token)
        self.fiverr_status_label.setText(f"Error: {error}")
        self._fiverr_reset_buttons()

    def fiverr_write_delivery(self):
        brief = self._fiverr_get_brief()
        provider = self.fiverr_provider_box.currentText()
        model = self.fiverr_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        agent = self.agent_instances["fiverr"]
        messages = agent.build_messages("Write a professional delivery message for this logo order.", brief)
        self.fiverr_delivery_box.clear()
        self.fiverr_status_label.setText("Writing delivery message...")
        self.fiverr_generate_btn.setEnabled(False)
        self.fiverr_delivery_btn.setEnabled(False)
        self.fiverr_gig_btn.setEnabled(False)
        self.fiverr_stop_btn.setEnabled(True)
        self.fiverr_stop_btn.show()
        self.fiverr_tabs.setCurrentIndex(1)
        token = self.authorize_request(
            "fiverr", provider, model,
            messages[-1]["content"] if messages else "")
        if not token:
            self._fiverr_reset_buttons()
            return
        self._fiverr_prompt_token = token
        self.fiverr_text_worker = self._new_chat_worker(provider, model, messages, "")
        self.fiverr_text_worker.token_signal.connect(self._fiverr_on_delivery_token)
        self.fiverr_text_worker.finished_signal.connect(self._fiverr_on_delivery_done)
        self.fiverr_text_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.fiverr_text_worker.error_signal.connect(self._fiverr_on_text_error)
        self.fiverr_text_worker.start()

    def _fiverr_on_delivery_token(self, token: str):
        self.fiverr_delivery_box.moveCursor(QTextCursor.End)
        self.fiverr_delivery_box.insertPlainText(token)

    def _fiverr_on_delivery_done(self, _full: str):
        token = getattr(self, "_fiverr_prompt_token", None)
        self._fiverr_prompt_token = None
        if token:
            self.record_request(token, _full)
        self.fiverr_status_label.setText("Delivery message ready.")
        self.fiverr_generate_btn.setEnabled(True)
        self.fiverr_delivery_btn.setEnabled(True)
        self.fiverr_gig_btn.setEnabled(True)
        self.fiverr_stop_btn.setEnabled(False)
        self.fiverr_stop_btn.hide()

    def fiverr_write_gig(self):
        brief = self._fiverr_get_brief()
        provider = self.fiverr_provider_box.currentText()
        model = self.fiverr_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        agent = self.agent_instances["fiverr"]
        messages = agent.build_messages("Write a complete Fiverr gig description for logo design services.", brief)
        self.fiverr_gig_box.clear()
        self.fiverr_status_label.setText("Writing gig description...")
        self.fiverr_generate_btn.setEnabled(False)
        self.fiverr_delivery_btn.setEnabled(False)
        self.fiverr_gig_btn.setEnabled(False)
        self.fiverr_stop_btn.setEnabled(True)
        self.fiverr_stop_btn.show()
        self.fiverr_tabs.setCurrentIndex(2)
        token = self.authorize_request(
            "fiverr", provider, model,
            messages[-1]["content"] if messages else "")
        if not token:
            self._fiverr_reset_buttons()
            return
        self._fiverr_prompt_token = token
        self.fiverr_text_worker = self._new_chat_worker(provider, model, messages, "")
        self.fiverr_text_worker.token_signal.connect(self._fiverr_on_gig_token)
        self.fiverr_text_worker.finished_signal.connect(self._fiverr_on_gig_done)
        self.fiverr_text_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.fiverr_text_worker.error_signal.connect(self._fiverr_on_text_error)
        self.fiverr_text_worker.start()

    def _fiverr_on_gig_token(self, token: str):
        self.fiverr_gig_box.moveCursor(QTextCursor.End)
        self.fiverr_gig_box.insertPlainText(token)

    def _fiverr_on_gig_done(self, _full: str):
        token = getattr(self, "_fiverr_prompt_token", None)
        self._fiverr_prompt_token = None
        if token:
            self.record_request(token, _full)
        self.fiverr_status_label.setText("Gig description ready.")
        self.fiverr_generate_btn.setEnabled(True)
        self.fiverr_delivery_btn.setEnabled(True)
        self.fiverr_gig_btn.setEnabled(True)
        self.fiverr_stop_btn.setEnabled(False)
        self.fiverr_stop_btn.hide()

    def fiverr_stop(self):
        if self.fiverr_image_worker is not None and self.fiverr_image_worker.isRunning():
            self.fiverr_image_worker.cancel()
        if self.fiverr_text_worker is not None and self.fiverr_text_worker.isRunning():
            self.fiverr_text_worker.cancel()
        # Release whatever this panel has pending — a stopped run must not
        # leave an authorized request dangling for the next flow to clobber.
        for attr in ("_fiverr_prompt_token", "_fiverr_image_token"):
            token = getattr(self, attr, None)
            setattr(self, attr, None)
            if token:
                self.abandon_request(token, reason="stopped")
        self.fiverr_status_label.setText("Stopped.")
        self.fiverr_generate_btn.setEnabled(True)
        self.fiverr_delivery_btn.setEnabled(True)
        self.fiverr_gig_btn.setEnabled(True)
        self.fiverr_stop_btn.setEnabled(False)
        self.fiverr_stop_btn.hide()

    def fiverr_save_images(self):
        if not self._fiverr_image_paths:
            return
        dest_dir = QFileDialog.getExistingDirectory(self, "Choose folder to save logos")
        if not dest_dir:
            return
        import shutil
        for src in self._fiverr_image_paths:
            shutil.copy(src, dest_dir)
        self.fiverr_status_label.setText(f"Saved {len(self._fiverr_image_paths)} image(s).")

    def fiverr_clear(self):
        self._fiverr_clear_logo_grid()
        self.fiverr_delivery_box.clear()
        self.fiverr_gig_box.clear()
        self.fiverr_status_label.setText("Idle")
        self._fiverr_update_estimate()
        self.fiverr_preview_status.setText("No logos generated yet.")
        self.fiverr_save_images_btn.setEnabled(False)
        self._fiverr_image_paths = []

    def _fiverr_clear_logo_grid(self):
        while self.fiverr_logo_grid_layout.count():
            item = self.fiverr_logo_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def author_load_models(self):
        """Kept as a method so existing call sites stay put."""
        self.author_panel_base.load_models()

    def _author_on_content_type_changed(self, content_type: str):
        fiction_tasks = [
            "Write Scene", "Continue Draft", "Generate Outline",
            "Develop Characters", "Build World", "Write Dialogue", "Revise / Improve",
        ]
        nonfiction_tasks = [
            "Write Chapter", "Continue Draft", "Generate Outline",
            "Strengthen Argument", "Add Case Study / Example", "Tighten Structure", "Revise / Improve",
        ]
        tasks = nonfiction_tasks if content_type == "Non-Fiction" else fiction_tasks
        current = self.author_task_box.currentText()
        self.author_task_box.blockSignals(True)
        self.author_task_box.clear()
        self.author_task_box.addItems(tasks)
        if current in tasks:
            self.author_task_box.setCurrentText(current)
        self.author_task_box.blockSignals(False)

    def _compute_next_step_tip(self) -> str:
        """Pick the single most useful next action, checked against real app state.
        Ordered write → publish → market, so it walks the whole book lifecycle."""
        import os

        profile = self._author_get_book_profile()
        draft_words = len(self.author_draft_box.toPlainText().split())
        outline = self.author_outline_box.toPlainText().strip()

        # ── Writing phase ──
        if not profile["title"]:
            return ("Start here — fill in Title, Author and Type in the Project Bar, then open "
                    "Book Profile and click Save Profile. Everything downstream reuses it.")
        if not profile["hook"] or not profile["target_reader"]:
            return ("Complete your Book Profile (Hook + Target reader). These two fields shape "
                    "every blurb, description and social caption you'll generate later.")
        if draft_words == 0 and not outline:
            return ("No draft yet — set Task to Generate Outline, describe the book in Direction, "
                    "and click Write. Outline first is faster than drafting blind.")
        if draft_words == 0:
            return ("Outline exists but no draft — switch Task to "
                    f"{'Write Chapter' if profile['content_type'] == 'Non-Fiction' else 'Write Scene'} "
                    "and start drafting. Use Continue to extend.")
        if draft_words < 5000:
            return (f"Draft is {draft_words:,} words — keep going with Write / Continue. "
                    "Add 'Chapter 1', 'Chapter 2' heading lines as you go so Chapters and Export pick them up.")
        if not self._author_export_done:
            return (f"{draft_words:,} words written — export a formatted copy (EPUB / DOCX / PDF) "
                    "from the Write sidebar to see how it reads as a real book.")

        # ── Publishing phase ──
        todos = self._get_pending_todo_titles()
        if any("Upload to Amazon KDP" in t for t in todos):
            return ("Draft exported. Next: generate a Back-Cover Blurb in Publish mode, then a "
                    "KDP Listing in Market mode — that one output covers your description, categories, "
                    "keywords and pricing. Then create your KDP account and upload.")
        if any("cover files" in t for t in todos):
            return ("Cover files are still on your checklist — KDP needs 3000×4500px at 300dpi. "
                    "This is the one step the app can't do for you; hire a designer or use Canva/Reedsy.")

        # ── Marketing phase ──
        if not os.environ.get("PUBLISHDRIVE_API_KEY", "").strip():
            return ("Book is live-ready. Connect PublishDrive (see the Connections panel) to pull "
                    "real sales data in, or skip it and drop KDP CSV reports into data/kdp_reports/ instead.")
        if any("Create TikTok, Instagram" in t for t in todos):
            return ("Set up your TikTok / Instagram / Pinterest accounts (same username on all three), "
                    "then use Quote Finder → Calendar to batch a few weeks of posts in one pass.")
        if any("TikTokers/BookTokers" in t for t in todos):
            return ("Content pipeline is ready — generate quote graphics and shorts, then pitch "
                    "BookTok creators in your niche with a free copy plus ready-made clips.")
        return ("Core pipeline complete. Keep the Calendar filled, watch sales on the Overview tab, "
                "and work through whatever's left on your Publishing Todos.")

    def _get_pending_todo_titles(self) -> list:
        """Pending, non-engineering todo titles — the advisor only nudges toward real
        publishing/marketing work, never the (Dev) roadmap items."""
        import sqlite3
        from services.database import DB_PATH
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT title FROM manuscript_todos WHERE status != 'done' AND platform != 'engineering'"
            ).fetchall()
            conn.close()
            return [r[0] for r in rows]
        except Exception:
            return []

    def _refresh_next_step_tip(self):
        tip = self._compute_next_step_tip()
        for attr in ("author_next_step_label", "manuscript_next_step_label"):
            label = getattr(self, attr, None)
            if label is not None:
                label.setText(f"Next step:   {tip}")

    def _author_get_book_profile(self) -> dict:
        return {
            "title": self.author_title_input.text().strip(),
            "author": self.author_name_input.text().strip(),
            "content_type": self.author_content_type_box.currentText(),
            "genre": self.author_genre_box.currentText(),
            "hook": self.author_profile_hook_input.text().strip(),
            "target_reader": self.author_profile_reader_input.text().strip(),
            "comp_titles": self.author_profile_comps_input.text().strip(),
            "publishing_path": self.author_profile_path_box.currentText(),
        }

    def _author_build_book_profile_block(self) -> str:
        """Formats the Book Profile into a system-prompt block shared by Write/Publish/Market
        — the point being you set this once and stop re-explaining the book on every request."""
        p = self._author_get_book_profile()
        lines = []
        if p["title"]:
            lines.append(f"Title: {p['title']}")
        if p["author"]:
            lines.append(f"Author: {p['author']}")
        lines.append(f"Content type: {p['content_type']}")
        if p["genre"]:
            lines.append(f"Genre: {p['genre']}")
        if p["hook"]:
            lines.append(f"Hook: {p['hook']}")
        if p["target_reader"]:
            lines.append(f"Target reader: {p['target_reader']}")
        if p["comp_titles"]:
            lines.append(f"Comp titles: {p['comp_titles']}")
        if p["publishing_path"] and p["publishing_path"] != "Undecided":
            lines.append(f"Publishing path: {p['publishing_path']}")
        if not lines:
            return ""
        return (
            "BOOK CONTEXT — ground every response in this; don't ask the user to re-explain it.\n\n"
            + "\n".join(lines)
        )

    def author_save_profile(self):
        import json
        from services.database import save_setting
        save_setting("author_book_profile", json.dumps(self._author_get_book_profile()))
        self.author_status_label.setText("[Saved] Book profile.")
        self._refresh_next_step_tip()

    def _author_load_profile(self):
        import json
        from services.database import get_setting
        raw = get_setting("author_book_profile", "")
        if not raw:
            return
        try:
            profile = json.loads(raw)
        except Exception:
            return
        self.author_title_input.setText(profile.get("title", ""))
        self.author_name_input.setText(profile.get("author", ""))
        if profile.get("content_type"):
            self.author_content_type_box.setCurrentText(profile["content_type"])
        if profile.get("genre"):
            idx = self.author_genre_box.findText(profile["genre"])
            if idx >= 0:
                self.author_genre_box.setCurrentIndex(idx)
        self.author_profile_hook_input.setText(profile.get("hook", ""))
        self.author_profile_reader_input.setText(profile.get("target_reader", ""))
        self.author_profile_comps_input.setText(profile.get("comp_titles", ""))
        if profile.get("publishing_path"):
            self.author_profile_path_box.setCurrentText(profile["publishing_path"])

    def _author_build_prompt(self, direction: str) -> str:
        task = self.author_task_box.currentText()
        genre = self.author_genre_box.currentText()
        tone = self.author_tone_box.currentText()
        pov = self.author_pov_box.currentText()
        title = self.author_title_input.text().strip()
        parts = [f"Task: {task}"]
        if title:
            parts.append(f"Project: {title}")
        parts += [f"Genre: {genre}", f"Tone: {tone}", f"POV: {pov}"]
        if direction:
            parts.append(f"Direction:\n{direction}")
        return "\n".join(parts)

    def _author_build_consistency_context(self, recent_draft_text: str = "") -> str:
        """Auto-inject established Characters/World + a recent-draft excerpt so every
        Write/Continue call stays consistent with the story so far."""
        characters = self.author_characters_box.toPlainText().strip()
        world = self.author_world_box.toPlainText().strip()
        sections = []
        if characters:
            sections.append(f"ESTABLISHED CHARACTERS (stay consistent — do not contradict):\n{characters}")
        if world:
            sections.append(f"ESTABLISHED WORLD (stay consistent — do not contradict):\n{world}")
        if recent_draft_text:
            sections.append(
                "RECENT STORY TEXT (end of the current draft — continue consistently, don't repeat it):\n"
                + recent_draft_text[-3000:]
            )
        if not sections:
            return ""
        return (
            "CONTINUITY CONTEXT — ground every response in this; do not contradict "
            "established characters, world rules, or recent events.\n\n" + "\n\n".join(sections)
        )

    def _author_start_worker(self, provider: str, model: str, prompt: str, recent_draft_text: str = ""):
        agent = self.agent_instances["author"]
        consistency_context = self._author_build_consistency_context(recent_draft_text)
        book_profile_context = self._author_build_book_profile_block()
        content_type = self.author_content_type_box.currentText()
        messages = agent.build_messages(
            prompt, consistency_context=consistency_context,
            book_profile_context=book_profile_context, content_type=content_type,
        )
        # Never replace a worker that is still running: dropping the old
        # QThread object while its thread is alive aborts the whole app with
        # "QThread: Destroyed while thread is still running". A cancelled
        # worker can sit in a blocking backend call for a while.
        if self.author_worker is not None and self.author_worker.isRunning():
            self.author_status_label.setText(
                "[Busy] The previous request is still finishing — one moment.")
            return
        self.author_status_label.setText("[Working…]")
        self.author_write_btn.setEnabled(False)
        self.author_continue_btn.setEnabled(False)
        self.author_stop_btn.setEnabled(True)
        token = self.authorize_request("author", provider, model, prompt)
        if not token:
            # Refused — re-enable the buttons disabled above.
            self.author_write_btn.setEnabled(True)
            self.author_continue_btn.setEnabled(True)
            self.author_stop_btn.setEnabled(False)
            self.author_status_label.setText("")
            return
        self._author_write_token = token
        self.author_worker = self._new_chat_worker(provider, model, messages, prompt)
        self.author_worker.token_signal.connect(self._author_on_token)
        self.author_worker.finished_signal.connect(self._author_on_finished)
        self.author_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.author_worker.error_signal.connect(self._author_on_error)
        self.author_worker.start()

    def author_write(self):
        direction = self.author_direction_input.text().strip()
        if not direction:
            QMessageBox.warning(self, "Missing Input", "Please enter a direction.")
            return
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        self._author_is_continuing = False
        existing = self.author_draft_box.toPlainText().strip()
        self.author_draft_box.clear()
        self._last_author_response = ""
        prompt = self._author_build_prompt(direction)
        self._author_start_worker(provider, model, prompt, recent_draft_text=existing)

    def author_continue(self):
        direction = self.author_direction_input.text().strip()
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return
        existing = self.author_draft_box.toPlainText().strip()
        parts = []
        if existing:
            parts.append(f"Existing draft so far:\n\n{existing}")
        if direction:
            parts.append(f"Continue with:\n{direction}")
        else:
            parts.append("Continue from where the draft left off.")
        continuation_note = "\n\n".join(parts)
        self._author_is_continuing = True
        self._last_author_response = ""
        # Append a separator then stream new content
        if existing:
            cursor = self.author_draft_box.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText("\n\n")
            self.author_draft_box.setTextCursor(cursor)
        prompt = self._author_build_prompt(continuation_note)
        # Recent draft text is already embedded in full inside `continuation_note` above —
        # don't pass it again here, that would just duplicate it in the prompt.
        self._author_start_worker(provider, model, prompt)

    def _author_on_token(self, token: str):
        self._last_author_response += token
        cursor = self.author_draft_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_draft_box.setTextCursor(cursor)

    def _author_update_counts(self):
        text = self.author_draft_box.toPlainText()
        word_count = len(text.split()) if text.strip() else 0
        self.author_word_count_label.setText(str(word_count))
        scene_count = len(re.findall(
            r"^(chapter|scene|act|part|prologue|epilogue|---|\*\*\*)",
            text, re.MULTILINE | re.IGNORECASE,
        ))
        self.author_scene_count_label.setText(str(scene_count))

    def _author_on_finished(self, full_response: str):
        token = getattr(self, "_author_write_token", None)
        self._author_write_token = None
        if token:
            self.record_request(token, full_response)
        self._populate_author_tabs(full_response)
        word_count = len(self.author_draft_box.toPlainText().split())
        self.author_status_label.setText(f"[Done] {word_count:,} words")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)
        self.author_save_btn.setEnabled(True)
        self._refresh_next_step_tip()

    def _author_on_error(self, error: str):
        token = getattr(self, "_author_write_token", None)
        self._author_write_token = None
        if token:
            self.abandon_request(token)
        self.author_status_label.setText(f"[Error] {error}")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)

    def author_stop(self):
        if self.author_worker is not None and self.author_worker.isRunning():
            self.author_worker.cancel()
        # A stopped run must not leave its authorized request pending.
        token = getattr(self, "_author_write_token", None)
        self._author_write_token = None
        if token:
            self.abandon_request(token, reason="stopped")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)
        self.author_status_label.setText("[Stopped]")

    def author_save(self):
        text = self.author_draft_box.toPlainText()
        if not text.strip():
            return
        title = self.author_title_input.text().strip() or "author_draft"
        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Draft", str(BASE_DIR / f"{safe}.txt"),
            "Text Files (*.txt);;Markdown Files (*.md)"
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.author_status_label.setText(f"[Saved] {path}")

    def author_export_book(self):
        text = self.author_draft_box.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "Nothing to Export", "The Draft tab is empty.")
            return
        fmt = self.author_export_format_box.currentText().lower()
        title = self.author_title_input.text().strip() or "Untitled Manuscript"
        author_name = (
            self.author_export_author_input.text().strip()
            or self.author_name_input.text().strip()
            or "Unknown Author"
        )

        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        filters = {"epub": "EPUB Files (*.epub)", "docx": "DOCX Files (*.docx)", "pdf": "PDF Files (*.pdf)"}
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Book", str(BASE_DIR / f"{safe}.{fmt}"), filters[fmt]
        )
        if not path:
            return

        from services.book_exporter import export_book
        try:
            export_book(text, title, author_name, fmt, Path(path))
            self.author_status_label.setText(f"[Done] Exported {fmt.upper()} to {Path(path).name}")
            self._author_export_done = True
            self._refresh_next_step_tip()
        except Exception as e:
            self.author_status_label.setText(f"[Error] {e}")

    def author_clear(self):
        self._author_clear_displays()
        self.author_direction_input.clear()
        self.author_title_input.clear()
        self.author_status_label.setText("")
        self._last_author_response = ""

    def _author_clear_displays(self):
        for box in (self.author_draft_box, self.author_outline_box,
                    self.author_characters_box, self.author_world_box):
            box.clear()
        self.author_word_count_label.setText("0")
        self.author_scene_count_label.setText("0")
        self.author_save_btn.setEnabled(False)

    def _populate_author_tabs(self, response: str):
        task = self.author_task_box.currentText()
        sections = self._parse_author_sections(response)
        if sections.get("outline"):
            self.author_outline_box.setPlainText(sections["outline"])
        if sections.get("characters"):
            self.author_characters_box.setPlainText(sections["characters"])
        if sections.get("world"):
            self.author_world_box.setPlainText(sections["world"])
        # Route clean content to the appropriate tab based on task
        if task == "Generate Outline" and not sections.get("outline"):
            self.author_outline_box.setPlainText(response)
        elif task == "Develop Characters" and not sections.get("characters"):
            self.author_characters_box.setPlainText(response)
        elif task == "Build World" and not sections.get("world"):
            self.author_world_box.setPlainText(response)
        elif not self._author_is_continuing and not sections.get("outline") and not sections.get("characters"):
            # Fresh write with no section markers — put full response in draft
            self.author_draft_box.setPlainText(sections.get("draft") or response)

    def _parse_author_sections(self, text: str) -> dict:
        patterns = {
            "draft":      r"\[DRAFT\](.*?)(?=\[OUTLINE\]|\[CHARACTER\]|\[WORLD\]|$)",
            "outline":    r"\[OUTLINE\](.*?)(?=\[DRAFT\]|\[CHARACTER\]|\[WORLD\]|$)",
            "characters": r"\[CHARACTER\](.*?)(?=\[DRAFT\]|\[OUTLINE\]|\[WORLD\]|$)",
            "world":      r"\[WORLD\](.*?)(?=\[DRAFT\]|\[OUTLINE\]|\[CHARACTER\]|$)",
        }
        result = {}
        for key, pat in patterns.items():
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            result[key] = m.group(1).strip() if m else ""
        return result

    def _author_on_tab_changed(self, index: int):
        if self.author_tabs.widget(index) is self.author_chapters_tab:
            self._author_refresh_chapters()

    def _author_refresh_chapters(self):
        """Re-derive the chapter list from the current Draft text — chapters aren't a
        separate stored model, they're parsed live from Draft using the same heading
        detection as book export, so there's never a second source of truth to drift."""
        from services.book_exporter import split_into_chapters, find_chapter_offsets

        text = self.author_draft_box.toPlainText()
        self.author_chapters_list.clear()
        self._author_chapter_offsets = []

        if not text.strip():
            self.author_chapters_stats_label.setText("No chapters detected yet — write something in Draft first.")
            return

        chapters = split_into_chapters(text)
        heading_offsets = find_chapter_offsets(text)
        total_words = len(text.split())

        offsets = []
        oi = 0
        for heading, _body in chapters:
            if heading:
                offsets.append(heading_offsets[oi] if oi < len(heading_offsets) else 0)
                oi += 1
            else:
                offsets.append(0)
        self._author_chapter_offsets = offsets

        for i, (heading, body) in enumerate(chapters):
            label = heading or "(untitled opening — no chapter headings found yet)"
            words = len(body.split())
            item = QListWidgetItem(f"{i + 1}. {label}   —   {words:,} words")
            self.author_chapters_list.addItem(item)

        chapter_word = "chapter" if len(chapters) == 1 else "chapters"
        self.author_chapters_stats_label.setText(
            f"{len(chapters)} {chapter_word} · {total_words:,} words total"
        )

    def _author_jump_to_chapter(self, item):
        row = self.author_chapters_list.row(item)
        if row < 0 or row >= len(self._author_chapter_offsets):
            return
        cursor = self.author_draft_box.textCursor()
        cursor.setPosition(self._author_chapter_offsets[row])
        self.author_draft_box.setTextCursor(cursor)
        self.author_tabs.setCurrentWidget(self.author_draft_box)
        self.author_draft_box.ensureCursorVisible()

    # ── Author mode / sub-mode switching ─────────────────────────────────────
    def _author_set_mode(self, mode: str):
        is_write = mode == "write"
        self.author_mode_write_btn.setChecked(is_write)
        self.author_mode_pubmkt_btn.setChecked(not is_write)
        self.author_content_stack.setCurrentIndex(0 if is_write else 1)

    def _author_set_sub_mode(self, mode: str):
        is_pub = mode == "publish"
        self.author_sub_publish_btn.setChecked(is_pub)
        self.author_sub_market_btn.setChecked(not is_pub)
        self.author_sub_stack.setCurrentIndex(0 if is_pub else 1)

    # ── Publish handlers ──────────────────────────────────────────────────────
    def author_pub_generate(self):
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model in the Write sidebar.")
            return

        title   = self.author_title_input.text().strip()
        genre   = self.author_genre_box.currentText()
        tone    = self.author_tone_box.currentText()
        doc_type = self.author_pub_type_box.currentText()
        wc      = self.author_pub_wordcount_input.text().strip()
        comps   = self.author_pub_comps_input.text().strip()
        pitch_tone = self.author_pub_pitch_tone_box.currentText()
        notes   = self.author_pub_notes_input.toPlainText().strip()

        parts = [f"Task: Generate a {doc_type}"]
        if title:
            parts.append(f"Book Title: {title}")
        parts += [f"Genre: {genre}", f"Tone: {tone}", f"Pitch Tone: {pitch_tone}"]
        if wc:
            parts.append(f"Manuscript Word Count: {wc}")
        if comps:
            parts.append(f"Comp Titles: {comps}")
        if notes:
            parts.append(f"Additional Notes:\n{notes}")

        prompt = "\n".join(parts)
        agent = self.agent_instances["author"]
        messages = agent.build_publish_messages(prompt, book_profile_context=self._author_build_book_profile_block())

        self.author_pub_output.clear()
        self.author_status_label.setText(f"[Working…] Generating {doc_type}…")
        self.author_pub_generate_btn.setEnabled(False)
        self.author_pub_stop_btn.setEnabled(True)
        self.author_pub_save_btn.setEnabled(False)

        if self.author_pub_worker is not None and self.author_pub_worker.isRunning():
            self.author_status_label.setText(
                "[Busy] The previous request is still finishing — one moment.")
            return
        token = self.authorize_request("author", provider, model, prompt)
        if not token:
            self.author_pub_generate_btn.setEnabled(True)
            self.author_pub_stop_btn.setEnabled(False)
            self.author_status_label.setText("")
            return
        self._author_pub_token = token
        self.author_pub_worker = self._new_chat_worker(provider, model, messages, prompt)
        self.author_pub_worker.token_signal.connect(self._author_pub_on_token)
        self.author_pub_worker.finished_signal.connect(self._author_pub_on_finished)
        self.author_pub_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.author_pub_worker.error_signal.connect(self._author_pub_on_error)
        self.author_pub_worker.start()

    def _author_pub_on_token(self, token: str):
        cursor = self.author_pub_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_pub_output.setTextCursor(cursor)

    def _author_pub_on_finished(self, full_response: str):
        token = getattr(self, "_author_pub_token", None)
        self._author_pub_token = None
        if token:
            self.record_request(token, full_response)
        self.author_status_label.setText(
            f"[Done] {self.author_pub_type_box.currentText()} generated"
        )
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)
        self.author_pub_save_btn.setEnabled(True)

    def _author_pub_on_error(self, error: str):
        token = getattr(self, "_author_pub_token", None)
        self._author_pub_token = None
        if token:
            self.abandon_request(token)
        self.author_status_label.setText(f"[Error] {error}")
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)

    def author_pub_stop(self):
        if self.author_pub_worker is not None and self.author_pub_worker.isRunning():
            self.author_pub_worker.cancel()
        token = getattr(self, "_author_pub_token", None)
        self._author_pub_token = None
        if token:
            self.abandon_request(token, reason="stopped")
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)
        self.author_status_label.setText("[Stopped]")

    def author_pub_copy(self):
        text = self.author_pub_output.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.author_status_label.setText("[Copied to clipboard]")

    def author_pub_save(self):
        text = self.author_pub_output.toPlainText().strip()
        if not text:
            return
        title = self.author_title_input.text().strip() or "publish"
        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        doc_type = re.sub(r"\s+", "_", self.author_pub_type_box.currentText().lower())
        default_name = f"{safe}_{doc_type}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Publishing Document", str(BASE_DIR / default_name),
            "Text Files (*.txt);;Markdown Files (*.md)"
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.author_status_label.setText(f"[Saved] {path}")

    # ── Market handlers ───────────────────────────────────────────────────────
    def author_mkt_generate(self):
        provider = self.author_provider_box.currentText()
        model = self.author_model_box.currentText()
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model in the Write sidebar.")
            return

        title    = self.author_title_input.text().strip()
        genre    = self.author_genre_box.currentText()
        platform = self.author_mkt_platform_box.currentText()
        hook     = self.author_mkt_hook_input.text().strip()
        comps    = self.author_mkt_comps_input.text().strip()
        mkt_tone = self.author_mkt_tone_box.currentText()
        notes    = self.author_mkt_notes_input.toPlainText().strip()

        parts = [f"Task: Generate {platform} copy"]
        if title:
            parts.append(f"Book Title: {title}")
        parts += [f"Genre: {genre}", f"Tone: {mkt_tone}"]
        if hook:
            parts.append(f"Hook / Logline: {hook}")
        if comps:
            parts.append(f"Comp Titles: {comps}")
        if notes:
            parts.append(f"Additional Notes:\n{notes}")

        prompt = "\n".join(parts)
        agent = self.agent_instances["author"]
        messages = agent.build_market_messages(prompt, book_profile_context=self._author_build_book_profile_block())

        self.author_mkt_output.clear()
        self.author_status_label.setText(f"[Working…] Generating {platform} copy…")
        self.author_mkt_generate_btn.setEnabled(False)
        self.author_mkt_stop_btn.setEnabled(True)
        self.author_mkt_save_btn.setEnabled(False)

        if self.author_mkt_worker is not None and self.author_mkt_worker.isRunning():
            self.author_status_label.setText(
                "[Busy] The previous request is still finishing — one moment.")
            return
        token = self.authorize_request("author", provider, model, prompt)
        if not token:
            self.author_mkt_generate_btn.setEnabled(True)
            self.author_mkt_stop_btn.setEnabled(False)
            self.author_status_label.setText("")
            return
        self._author_mkt_token = token
        self.author_mkt_worker = self._new_chat_worker(provider, model, messages, prompt)
        self.author_mkt_worker.token_signal.connect(self._author_mkt_on_token)
        self.author_mkt_worker.finished_signal.connect(self._author_mkt_on_finished)
        self.author_mkt_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.author_mkt_worker.error_signal.connect(self._author_mkt_on_error)
        self.author_mkt_worker.start()

    def _author_mkt_on_token(self, token: str):
        cursor = self.author_mkt_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_mkt_output.setTextCursor(cursor)

    def _author_mkt_on_finished(self, full_response: str):
        token = getattr(self, "_author_mkt_token", None)
        self._author_mkt_token = None
        if token:
            self.record_request(token, full_response)
        self.author_status_label.setText(
            f"[Done] {self.author_mkt_platform_box.currentText()} copy generated"
        )
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_mkt_save_btn.setEnabled(True)

    def _author_mkt_on_error(self, error: str):
        token = getattr(self, "_author_mkt_token", None)
        self._author_mkt_token = None
        if token:
            self.abandon_request(token)
        self.author_status_label.setText(f"[Error] {error}")
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)

    def author_mkt_stop(self):
        if self.author_mkt_worker is not None and self.author_mkt_worker.isRunning():
            self.author_mkt_worker.cancel()
        token = getattr(self, "_author_mkt_token", None)
        self._author_mkt_token = None
        if token:
            self.abandon_request(token, reason="stopped")
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_status_label.setText("[Stopped]")

    def author_mkt_copy(self):
        text = self.author_mkt_output.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.author_status_label.setText("[Copied to clipboard]")

    def author_mkt_save(self):
        text = self.author_mkt_output.toPlainText().strip()
        if not text:
            return
        title = self.author_title_input.text().strip() or "marketing"
        safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
        platform = re.sub(r"[\s/]+", "_", self.author_mkt_platform_box.currentText().lower())
        default_name = f"{safe}_{platform}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Marketing Copy", str(BASE_DIR / default_name),
            "Text Files (*.txt);;Markdown Files (*.md)"
        )
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.author_status_label.setText(f"[Saved] {path}")

    # ── Manuscript panel builder ──────────────────────────────────────────────
    def build_manuscript_panel(self):
        self.manuscript_panel = QWidget()
        self.manuscript_panel.setObjectName("ManuscriptPanel")
        layout = QVBoxLayout(self.manuscript_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(MD)

        # ── Top bar: period selector + data actions ───────────────────────────
        # The buttons sit on the field's baseline, not the label's, so the row
        # reads as one line instead of a control stepping up over a caption.
        top_bar = QWidget()
        top_bar.setObjectName("Transparent")
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(SM)

        self.manuscript_period_box = combo(
            ["Last 30 days", "This month", "Last 7 days", "All time"])
        period_field = field("Period", self.manuscript_period_box)
        period_field.setFixedWidth(180)
        tb.addWidget(period_field)

        self.manuscript_refresh_btn = QPushButton("Refresh Data")
        self.manuscript_refresh_btn.clicked.connect(self.manuscript_refresh)
        tb.addWidget(self.manuscript_refresh_btn, 0, Qt.AlignBottom)

        self.manuscript_ingest_btn = QPushButton("Ingest KDP CSV")
        self.manuscript_ingest_btn.clicked.connect(self.manuscript_ingest_kdp)
        tb.addWidget(self.manuscript_ingest_btn, 0, Qt.AlignBottom)

        tb.addStretch()
        layout.addWidget(top_bar)

        self.manuscript_next_step_label = QLabel("")
        self.manuscript_next_step_label.setWordWrap(True)
        self.manuscript_next_step_label.setObjectName("NextStepBanner")
        layout.addWidget(self.manuscript_next_step_label)

        # ── Connections: which 3rd-party services are actually configured ─────
        connections_section = CollapsibleSection("Connections", expanded=False)
        self.manuscript_connections_layout = QVBoxLayout()
        self.manuscript_connections_layout.setContentsMargins(4, 2, 4, 2)
        self.manuscript_connections_layout.setSpacing(3)
        connections_container = QWidget()
        connections_container.setLayout(self.manuscript_connections_layout)
        connections_section.addWidget(connections_container)

        connections_refresh_btn = QPushButton("Refresh Status")
        connections_refresh_btn.clicked.connect(self._refresh_connections_status)
        connections_section.addWidget(connections_refresh_btn)

        layout.addWidget(connections_section)
        self._refresh_connections_status()

        self.manuscript_tabs = QTabWidget()
        layout.addWidget(self.manuscript_tabs, 1)

        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(0, 0, 0, 0)

        # ── Main area: metrics display + Q&A sidebar ─────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Left: metrics summary display
        self.manuscript_metrics_box = QTextBrowser()
        self.manuscript_metrics_box.setPlaceholderText("Click Refresh Data to load publishing metrics…")
        splitter.addWidget(self.manuscript_metrics_box)

        # Right: Q&A and todos. Section labels and fields rather than a stack
        # of "Ask about your book:" / "Provider:" / "Model:" colon captions,
        # each of which set its own left edge.
        sidebar = QWidget()
        sidebar.setObjectName("Transparent")
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(MD, 0, 0, 0)
        sb.setSpacing(MD)
        sidebar.setFixedWidth(300)

        sb.addWidget(section("Ask"))
        self.manuscript_query_input = QTextEdit()
        self.manuscript_query_input.setPlaceholderText(
            "What did I earn this month? Which platform performs best?")
        self.manuscript_query_input.setFixedHeight(76)
        sb.addWidget(self.manuscript_query_input)

        # No ollama: the manuscript registry row restricts providers, and a box
        # offering one the validator refuses is a dead option.
        self.manuscript_panel_base = AgentPanel(
            self, "manuscript",
            providers=("anthropic", "openai", "deepseek", "kimi", "gemini", "qwen"))
        self.manuscript_provider_box = self.manuscript_panel_base.provider_box
        self.manuscript_model_box = self.manuscript_panel_base.model_box
        sb.addWidget(field("Provider", self.manuscript_provider_box))
        sb.addWidget(field("Model", self.manuscript_model_box))

        self.manuscript_ask_btn = primary("Ask")
        self.manuscript_ask_btn.clicked.connect(self.manuscript_ask)
        sb.addWidget(self.manuscript_ask_btn)

        sb.addWidget(section("Publishing todos"))
        self.manuscript_todo_list = QListWidget()
        self.manuscript_todo_list.setMinimumHeight(120)
        sb.addWidget(self.manuscript_todo_list, 1)

        self.manuscript_todo_input = line_edit("Add todo…")
        sb.addWidget(self.manuscript_todo_input)

        todo_btn_row = QHBoxLayout()
        todo_btn_row.setSpacing(SM)
        self.manuscript_add_todo_btn = QPushButton("Add")
        self.manuscript_add_todo_btn.clicked.connect(self.manuscript_add_todo)
        self.manuscript_done_todo_btn = QPushButton("Done")
        self.manuscript_done_todo_btn.clicked.connect(self.manuscript_mark_todo_done)
        todo_btn_row.addWidget(self.manuscript_add_todo_btn)
        todo_btn_row.addWidget(self.manuscript_done_todo_btn)
        sb.addLayout(todo_btn_row)

        splitter.addWidget(scrollable(sidebar, min_width=300, max_width=320))
        overview_layout.addWidget(splitter)
        self.manuscript_tabs.addTab(overview_tab, "Overview")

        self.build_manuscript_quote_finder_tab()
        self.manuscript_tabs.addTab(self.manuscript_quote_finder_tab, "Quote Finder")

        self.build_manuscript_graphics_tab()
        self.manuscript_tabs.addTab(self.manuscript_graphics_tab, "Quote Graphics")

        self.build_manuscript_shorts_tab()
        self.manuscript_tabs.addTab(self.manuscript_shorts_tab, "Shorts")

        self.build_manuscript_calendar_tab()
        self.manuscript_tabs.addTab(self.manuscript_calendar_tab, "Calendar")

        # Status bar
        self.manuscript_status_label = QLabel("")
        self.manuscript_status_label.setObjectName("EstimateLine")
        layout.addWidget(self.manuscript_status_label)

        self.manuscript_panel.hide()

    def build_manuscript_quote_finder_tab(self):
        self.manuscript_quote_finder_tab = QWidget()
        layout = QVBoxLayout(self.manuscript_quote_finder_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.quote_finder_text = QTextEdit()
        self.quote_finder_text.setPlaceholderText(
            "Paste a chapter or excerpt here, or load a file below…"
        )
        self.quote_finder_text.setFixedHeight(140)
        layout.addWidget(field("Manuscript text", self.quote_finder_text))

        load_row = QHBoxLayout()
        self.quote_finder_load_btn = QPushButton("Load File…")
        self.quote_finder_load_btn.clicked.connect(self.quote_finder_load_file)
        load_row.addWidget(self.quote_finder_load_btn)
        load_row.addWidget(QLabel("Supports .txt, .pdf, .epub, .mobi"))
        load_row.addStretch()
        layout.addLayout(load_row)

        settings_row_container = QWidget()
        settings_row = FlowLayout(settings_row_container, spacing=6)
        self.quote_finder_count_box = QComboBox()
        self.quote_finder_count_box.addItems(["5", "10", "15", "20"])
        self.quote_finder_count_box.setCurrentText("10")
        settings_row.addWidget(field("Quotes", self.quote_finder_count_box))

        self.quote_finder_theme_box = make_theme_box()
        settings_row.addWidget(field("Theme", self.quote_finder_theme_box))

        self.quote_finder_voice_source_box = make_voice_source_box()
        self.quote_finder_voice_source_box.currentTextChanged.connect(self.quote_finder_load_voices)
        settings_row.addWidget(field("Voice", self.quote_finder_voice_source_box))

        self.quote_finder_voice_box = QComboBox()
        settings_row.addWidget(self.quote_finder_voice_box)

        self.quote_finder_attribution = QLineEdit()
        self.quote_finder_attribution.setPlaceholderText("You Don't Chase")
        settings_row.addWidget(field("Attribution", self.quote_finder_attribution))

        layout.addWidget(settings_row_container)

        self.quote_finder_suggest_btn = QPushButton("Suggest Quotes")
        self.quote_finder_suggest_btn.setMinimumHeight(34)
        self.quote_finder_suggest_btn.clicked.connect(self.quote_finder_suggest)
        layout.addWidget(self.quote_finder_suggest_btn)

        layout.addWidget(micro("Candidates"))
        self.quote_finder_list = QListWidget()
        layout.addWidget(self.quote_finder_list, 1)

        self._quote_finder_short_buttons: list = []
        self._quote_finder_busy = False
        self.quote_finder_load_voices()

    def build_manuscript_graphics_tab(self):
        self.manuscript_graphics_tab = QWidget()
        row = QHBoxLayout(self.manuscript_graphics_tab)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(12)

        # Left: controls
        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        controls.setMaximumWidth(280)

        self.quote_graphic_text = QTextEdit()
        self.quote_graphic_text.setPlaceholderText("You over-text. You explain yourself. You wait.")
        self.quote_graphic_text.setFixedHeight(90)
        cl.addWidget(field("Quote", self.quote_graphic_text))

        self.quote_graphic_attribution = QLineEdit()
        self.quote_graphic_attribution.setPlaceholderText("You Don't Chase")
        cl.addWidget(field("Attribution (optional)", self.quote_graphic_attribution))

        self.quote_graphic_theme_box = make_theme_box()
        cl.addWidget(field("Theme", self.quote_graphic_theme_box))

        self.quote_graphic_size_box = make_size_box()
        cl.addWidget(field("Size", self.quote_graphic_size_box))

        self.quote_graphic_generate_btn = QPushButton("Generate Graphic")
        self.quote_graphic_generate_btn.setMinimumHeight(34)
        self.quote_graphic_generate_btn.clicked.connect(self.manuscript_generate_quote_graphic)
        cl.addWidget(self.quote_graphic_generate_btn)

        self.quote_graphic_open_folder_btn = QPushButton("Open Folder")
        self.quote_graphic_open_folder_btn.clicked.connect(self.manuscript_open_graphics_folder)
        cl.addWidget(self.quote_graphic_open_folder_btn)

        cl.addStretch()
        row.addWidget(controls)

        # Right: preview
        self.quote_graphic_preview = QLabel("Preview will appear here.")
        self.quote_graphic_preview.setAlignment(Qt.AlignCenter)
        self.quote_graphic_preview.setStyleSheet(
            "background: #1a1a1a; border: 1px solid #333; color: #666;"
        )
        self.quote_graphic_preview.setMinimumSize(320, 320)
        row.addWidget(self.quote_graphic_preview, 1)

    def build_manuscript_shorts_tab(self):
        self.manuscript_shorts_tab = QWidget()
        row = QHBoxLayout(self.manuscript_shorts_tab)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(12)

        # Left: controls
        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        controls.setMaximumWidth(280)

        self.shorts_quote_text = QTextEdit()
        self.shorts_quote_text.setPlaceholderText("You over-text. You explain yourself. You wait.")
        self.shorts_quote_text.setFixedHeight(90)
        cl.addWidget(field("Quote (also narrated)", self.shorts_quote_text))

        self.shorts_attribution = QLineEdit()
        self.shorts_attribution.setPlaceholderText("You Don't Chase")
        cl.addWidget(field("Attribution (optional)", self.shorts_attribution))

        self.shorts_theme_box = make_theme_box()
        cl.addWidget(field("Theme", self.shorts_theme_box))

        self.shorts_voice_source_box = make_voice_source_box()
        self.shorts_voice_source_box.currentTextChanged.connect(self.shorts_load_voices)
        cl.addWidget(field("Voice source", self.shorts_voice_source_box))

        self.shorts_voice_box = QComboBox()
        cl.addWidget(self.shorts_voice_box)

        self.shorts_generate_btn = QPushButton("Generate Short")
        self.shorts_generate_btn.setMinimumHeight(34)
        self.shorts_generate_btn.clicked.connect(self.manuscript_generate_short)
        cl.addWidget(self.shorts_generate_btn)

        btn_row = QHBoxLayout()
        self.shorts_play_btn = QPushButton("Play")
        self.shorts_play_btn.setEnabled(False)
        self.shorts_play_btn.clicked.connect(self.manuscript_play_short)
        self.shorts_open_folder_btn = QPushButton("Folder")
        self.shorts_open_folder_btn.clicked.connect(self.manuscript_open_shorts_folder)
        btn_row.addWidget(self.shorts_play_btn)
        btn_row.addWidget(self.shorts_open_folder_btn)
        cl.addLayout(btn_row)

        cl.addStretch()
        row.addWidget(controls)

        # Right: preview (static frame of the short — no inline video player)
        self.shorts_preview = QLabel("Preview will appear here.")
        self.shorts_preview.setAlignment(Qt.AlignCenter)
        self.shorts_preview.setStyleSheet(
            "background: #1a1a1a; border: 1px solid #333; color: #666;"
        )
        self.shorts_preview.setMinimumSize(320, 320)
        row.addWidget(self.shorts_preview, 1)

        self.shorts_load_voices()

    def build_manuscript_calendar_tab(self):
        self.manuscript_calendar_tab = QWidget()
        layout = QVBoxLayout(self.manuscript_calendar_tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        from PySide6.QtWidgets import QDateEdit
        from PySide6.QtCore import QDate

        layout.addWidget(QLabel(
            "Builds a posting schedule from the candidates on the Quote Finder tab — "
            "run Suggest Quotes there first."
        ))

        settings_row = QHBoxLayout()
        self.calendar_weeks_box = QComboBox()
        self.calendar_weeks_box.addItems(["1", "2", "4"])
        settings_row.addWidget(field("Weeks", self.calendar_weeks_box))

        self.calendar_start_date = QDateEdit()
        self.calendar_start_date.setDate(QDate.currentDate())
        self.calendar_start_date.setCalendarPopup(True)
        settings_row.addWidget(field("Start", self.calendar_start_date))

        # Grouped under one caption and pinned to the controls' baseline: bare
        # checkboxes in a row of label-above-input fields otherwise float a
        # label's height above everything beside them.
        platforms = QHBoxLayout()
        platforms.setContentsMargins(0, 0, 0, 0)
        platforms.setSpacing(MD)
        self.calendar_tiktok_check = QCheckBox("TikTok")
        self.calendar_tiktok_check.setChecked(True)
        self.calendar_instagram_check = QCheckBox("Instagram")
        self.calendar_instagram_check.setChecked(True)
        self.calendar_pinterest_check = QCheckBox("Pinterest")
        self.calendar_pinterest_check.setChecked(True)
        for check in (self.calendar_tiktok_check, self.calendar_instagram_check,
                      self.calendar_pinterest_check):
            platforms.addWidget(check)
        platform_box = QWidget()
        platform_box.setObjectName("Transparent")
        platform_box.setLayout(platforms)
        settings_row.addWidget(field("Platforms", platform_box))

        settings_row.addStretch()
        layout.addLayout(settings_row)

        settings_row2 = QHBoxLayout()
        self.calendar_theme_box = make_theme_box()
        settings_row2.addWidget(field("Theme", self.calendar_theme_box))

        self.calendar_voice_source_box = make_voice_source_box()
        self.calendar_voice_source_box.currentTextChanged.connect(self.calendar_load_voices)
        settings_row2.addWidget(field("Voice", self.calendar_voice_source_box))

        self.calendar_voice_box = QComboBox()
        settings_row2.addWidget(field("Narrator", self.calendar_voice_box))

        self.calendar_attribution = QLineEdit()
        self.calendar_attribution.setPlaceholderText("You Don't Chase")
        settings_row2.addWidget(field("Attribution", self.calendar_attribution))

        settings_row2.addStretch()
        layout.addLayout(settings_row2)

        btn_row = QHBoxLayout()
        self.calendar_generate_btn = QPushButton("Generate Calendar")
        self.calendar_generate_btn.setMinimumHeight(34)
        self.calendar_generate_btn.clicked.connect(self.manuscript_generate_calendar)
        btn_row.addWidget(self.calendar_generate_btn)

        self.calendar_export_btn = QPushButton("Export Calendar (CSV)")
        self.calendar_export_btn.clicked.connect(self.manuscript_export_calendar_csv)
        btn_row.addWidget(self.calendar_export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        from PySide6.QtWidgets import QTableWidget
        self.calendar_table = QTableWidget(0, 6)
        self.calendar_table.setHorizontalHeaderLabels(["Date", "Platform", "Format", "Quote", "Caption", ""])
        self.calendar_table.setColumnWidth(0, 90)
        self.calendar_table.setColumnWidth(1, 80)
        self.calendar_table.setColumnWidth(2, 70)
        self.calendar_table.setColumnWidth(3, 260)
        self.calendar_table.setColumnWidth(5, 40)
        self.calendar_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.calendar_table, 1)

        self._calendar_slots = []
        self.calendar_load_voices()

    # ── Manuscript handlers ───────────────────────────────────────────────────
    def manuscript_load_models(self):
        """Kept as a method so existing call sites stay put."""
        self.manuscript_panel_base.load_models()

    def _refresh_connections_status(self):
        """Shows which 3rd-party API keys are actually configured (checked from the running
        process's environment — restart the app after editing .env for changes to appear).
        Services with no API at all (KDP, Draft2Digital, IngramSpark, BookBub, TikTok/IG/Pinterest)
        aren't listed here since there's nothing to check — their account-creation steps are on
        the Publishing Todos list below (hover an item for its notes)."""
        import os

        while self.manuscript_connections_layout.count():
            item = self.manuscript_connections_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        note = QLabel(
            "API-key-based services only — KDP/Draft2Digital/IngramSpark/BookBub/social accounts "
            "have no API to check; see the Publishing Todos below for those."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #777; font-size: 11px;")
        self.manuscript_connections_layout.addWidget(note)

        checks = [
            ("PublishDrive", bool(os.environ.get("PUBLISHDRIVE_API_KEY", "").strip()),
             "publishdrive.com → Settings → API", False),
            ("ElevenLabs", bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()),
             "elevenlabs.io → Profile → API Keys", True),
            ("Anthropic", self.anthropic.key_available(), "console.anthropic.com → API Keys", False),
            ("OpenAI", self.openai.key_available(), "platform.openai.com → API Keys", False),
            ("DeepSeek", self.deepseek.key_available(), "platform.deepseek.com → API Keys", False),
            ("Gemini", self.gemini.key_available(), "aistudio.google.com → API Keys", False),
        ]
        for name, connected, where, optional in checks:
            opt_tag = " (optional)" if optional else ""
            if connected:
                text = f"{name}{opt_tag} — connected"
                color = ACCENT
            else:
                text = f"{name}{opt_tag} — not connected · get a key at {where}"
                color = "#999999"
            row = QLabel(text)
            row.setStyleSheet(f"color: {color}; font-size: 12px;")
            self.manuscript_connections_layout.addWidget(row)

    def manuscript_refresh(self):
        """Fetch PublishDrive data and display summary."""
        from services.publishdrive_client import PublishDriveClient
        import json
        self.manuscript_status_label.setText("[Fetching…]")
        try:
            client = PublishDriveClient()
            data = client.get_last_30_days()
            self.manuscript_metrics_box.setPlainText(json.dumps(data, indent=2))
            self.manuscript_status_label.setText("[Done] Data refreshed.")
            self._manuscript_last_data = json.dumps(data)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def manuscript_ingest_kdp(self):
        """Ingest any new KDP CSV files from data/kdp_reports/."""
        from services.kdp_csv_parser import ingest_new_reports
        ingested = ingest_new_reports()
        if ingested:
            self.manuscript_status_label.setText(f"[Done] Ingested: {', '.join(ingested)}")
        else:
            self.manuscript_status_label.setText("[Info] No new KDP reports found.")

    def manuscript_ask(self):
        """Send a query to ManuscriptAgent with current data as context."""
        query = self.manuscript_query_input.toPlainText().strip()
        if not query:
            return
        provider = self.manuscript_provider_box.currentText()
        model = self.manuscript_model_box.currentText()
        if not model:
            self.manuscript_status_label.setText("[Error] Please select a model.")
            return
        agent = self.agent_instances["manuscript"]
        messages = agent.build_messages(query, context_json=self._manuscript_last_data)
        self.manuscript_status_label.setText("[Thinking…]")
        self.manuscript_ask_btn.setEnabled(False)
        # Keep the token: "manuscript" is shared with the quote-finder and
        # calendar-caption flows. And on refusal, re-enable the button
        # disabled above — it used to stay stuck until restart.
        token = self.authorize_request("manuscript", provider, model, query)
        if not token:
            self.manuscript_ask_btn.setEnabled(True)
            self.manuscript_status_label.setText("")
            return
        self._manuscript_ask_token = token
        self.manuscript_worker = self._new_chat_worker(provider, model, messages, query)
        self.manuscript_worker.token_signal.connect(self._manuscript_on_token)
        self.manuscript_worker.finished_signal.connect(self._manuscript_on_finished)
        self.manuscript_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.manuscript_worker.error_signal.connect(self._manuscript_on_error)
        self.manuscript_worker.start()

    def _manuscript_on_token(self, token: str):
        cursor = self.manuscript_metrics_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.manuscript_metrics_box.setTextCursor(cursor)

    def _manuscript_on_finished(self, _full_response: str):
        token = getattr(self, "_manuscript_ask_token", None)
        self._manuscript_ask_token = None
        if token:
            self.record_request(token, _full_response)
        self.manuscript_status_label.setText("[Done]")
        self.manuscript_ask_btn.setEnabled(True)

    def _manuscript_on_error(self, error: str):
        token = getattr(self, "_manuscript_ask_token", None)
        self._manuscript_ask_token = None
        if token:
            self.abandon_request(token)
        self.manuscript_status_label.setText(f"[Error] {error}")
        self.manuscript_ask_btn.setEnabled(True)

    def manuscript_add_todo(self):
        title = self.manuscript_todo_input.text().strip()
        if not title:
            return
        import sqlite3
        from services.database import DB_PATH
        now = datetime.utcnow().isoformat()
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO manuscript_todos (created_at, updated_at, title) VALUES (?, ?, ?)",
            (now, now, title)
        )
        conn.commit()
        conn.close()
        self.manuscript_todo_input.clear()
        self._load_manuscript_todos()

    def manuscript_mark_todo_done(self):
        item = self.manuscript_todo_list.currentItem()
        if not item:
            return
        todo_id = item.data(Qt.UserRole)
        import sqlite3
        from services.database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE manuscript_todos SET status='done', updated_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), todo_id)
        )
        conn.commit()
        conn.close()
        self._load_manuscript_todos()

    def _load_manuscript_todos(self):
        import sqlite3
        from services.database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, title, status, platform, notes FROM manuscript_todos ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        self.manuscript_todo_list.clear()
        for row_id, title, status, platform, notes in rows:
            # A checkbox glyph pair, not emoji: ✓ and ○ share a baseline and an
            # optical weight, so the list has one left edge. The ℹ️ that used
            # to mark a note sat at the end of the line, at a different size,
            # and only repeated what the tooltip already says.
            check = "✓" if status == "done" else "○"
            tag = f"[{platform}] " if platform else ""
            item = QListWidgetItem(f"{check}  {tag}{title}")
            item.setData(Qt.UserRole, row_id)
            if notes:
                item.setToolTip(notes)
            self.manuscript_todo_list.addItem(item)
        self._refresh_next_step_tip()

    def manuscript_generate_quote_graphic(self):
        quote = self.quote_graphic_text.toPlainText().strip()
        if not quote:
            QMessageBox.warning(self, "Missing Quote", "Please enter a quote.")
            return
        from PySide6.QtGui import QPixmap
        from services.quote_graphics import render_quote_graphic, GRAPHICS_DIR
        import time

        attribution = self.quote_graphic_attribution.text().strip()
        theme = theme_key(self.quote_graphic_theme_box)
        size_name = size_key(self.quote_graphic_size_box)
        output_path = unique_output_path(GRAPHICS_DIR, "quote", ".png")
        try:
            render_quote_graphic(quote, output_path, theme=theme, size_name=size_name, attribution=attribution)
            pixmap = QPixmap(str(output_path))
            scaled = pixmap.scaled(320, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.quote_graphic_preview.setPixmap(scaled)
            self.manuscript_status_label.setText(f"[Done] Saved {output_path.name}")
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def manuscript_open_graphics_folder(self):
        from services.quote_graphics import GRAPHICS_DIR
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(GRAPHICS_DIR)))

    def shorts_load_voices(self):
        from ui.book_widgets import populate_voice_box
        populate_voice_box(self.shorts_voice_box, self.shorts_voice_source_box.currentText())

    def _authorize_short_narration(self, quote: str, use_elevenlabs: bool) -> bool:
        """Guard the paid branch of a shorts render.

        The default narrator is the free on-device voice; only ElevenLabs
        costs money (billed per character against the account's quota), and
        these three sites used to start it with no budget check, no
        confirmation and no usage row. A missing/0 rate means unknown →
        refuse, like every other per-unit path. Keeps the token rather than
        resolving by agent name — "manuscript" is shared by other flows.
        """
        self._shorts_request_token = None
        if not (use_elevenlabs and os.environ.get("ELEVENLABS_API_KEY")):
            return True   # free on-device narrator, nothing to bill
        from services.per_unit_pricing import elevenlabs_tts_cost_eur
        cost = elevenlabs_tts_cost_eur(len(quote))
        if cost is None:
            QMessageBox.warning(
                self, "No Price Configured",
                "ElevenLabs narration has no per-1k-character rate in "
                "config/pricing.json (elevenlabs_tts_per_1k_chars; 0 means "
                "unknown), so it cannot be billed against the budget caps. "
                "Add a rate, or switch the voice source to the free "
                "on-device narrator.")
            return False
        token = self.authorize_request(
            "manuscript", "elevenlabs", "elevenlabs-tts",
            f"short narration · {len(quote)} characters: {quote[:200]}",
            label="short narration", flat_cost_eur=cost)
        if not token:
            return False
        self._shorts_request_token = token
        return True

    def _shorts_resolve_request(self, completed: bool, detail: str = ""):
        """Close out the narration authorized above, by its own token."""
        token = getattr(self, "_shorts_request_token", None)
        self._shorts_request_token = None
        if not token:
            return
        if completed:
            self.record_request(token, detail or "short narration rendered")
        else:
            self.abandon_request(token)

    def manuscript_generate_short(self):
        quote = self.shorts_quote_text.toPlainText().strip()
        if not quote:
            QMessageBox.warning(self, "Missing Quote", "Please enter a quote.")
            return
        from PySide6.QtGui import QPixmap
        from services.quote_graphics import render_quote_graphic
        from services.shorts_generator import SHORTS_DIR
        import time

        attribution = self.shorts_attribution.text().strip()
        theme = theme_key(self.shorts_theme_box)
        use_elevenlabs = self.shorts_voice_source_box.currentText() == "ElevenLabs"
        voice_id = self.shorts_voice_box.currentData() or "default"

        output_path = unique_output_path(SHORTS_DIR, "short", ".mp4")
        image_path = output_path.with_suffix(".png")

        try:
            render_quote_graphic(quote, image_path, theme=theme, size_name="vertical", attribution=attribution)
            pixmap = QPixmap(str(image_path))
            scaled = pixmap.scaled(320, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.shorts_preview.setPixmap(scaled)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if not self._authorize_short_narration(quote, use_elevenlabs):
            return

        self.shorts_generate_btn.setEnabled(False)
        self.shorts_play_btn.setEnabled(False)
        self._last_short_path = ""
        self.manuscript_status_label.setText("[Narrating…]")

        self.shorts_worker = ShortsWorker(quote, image_path, output_path, use_elevenlabs, voice_id)
        self.shorts_worker.status_signal.connect(self.manuscript_status_label.setText)
        self.shorts_worker.done_signal.connect(self._shorts_on_done)
        self.shorts_worker.error_signal.connect(self._shorts_on_error)
        self.shorts_worker.start()

    def _shorts_on_done(self, output_path: str):
        self._shorts_resolve_request(True, f"saved {Path(output_path).name}")
        self._last_short_path = output_path
        self.manuscript_status_label.setText(f"[Done] Saved {Path(output_path).name}")
        self.shorts_generate_btn.setEnabled(True)
        self.shorts_play_btn.setEnabled(True)

    def _shorts_on_error(self, error: str):
        self._shorts_resolve_request(False)
        self.manuscript_status_label.setText(f"[Error] {error}")
        self.shorts_generate_btn.setEnabled(True)

    def manuscript_play_short(self):
        if self._last_short_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_short_path))

    def manuscript_open_shorts_folder(self):
        from services.shorts_generator import SHORTS_DIR
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(SHORTS_DIR)))

    # ── Quote Finder handlers ─────────────────────────────────────────────────
    def quote_finder_load_voices(self):
        from ui.book_widgets import populate_voice_box
        populate_voice_box(self.quote_finder_voice_box, self.quote_finder_voice_source_box.currentText())

    def quote_finder_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Manuscript File", "",
            "Text / Ebook Files (*.txt *.pdf *.epub *.mobi)"
        )
        if not path:
            return
        from services.narrator.converter import load_text
        try:
            text = load_text(Path(path))
            self.quote_finder_text.setPlainText(text)
            self.manuscript_status_label.setText(f"[Loaded] {Path(path).name} ({len(text):,} chars)")
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def quote_finder_suggest(self):
        text = self.quote_finder_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Missing Text", "Paste or load manuscript text first.")
            return
        provider = self.manuscript_provider_box.currentText()
        model = self.manuscript_model_box.currentText()
        if not model:
            self.manuscript_status_label.setText("[Error] Select a model on the Overview tab.")
            return
        count = int(self.quote_finder_count_box.currentText())
        # Cap input to keep cost bounded — plenty of text to find a strong batch of quotes.
        truncated = text[:30000]

        agent = self.agent_instances["manuscript"]
        messages = agent.build_quote_suggestions_messages(truncated, count=count)
        self.manuscript_status_label.setText("[Finding quotes…]")
        self.quote_finder_suggest_btn.setEnabled(False)
        token = self.authorize_request("manuscript", provider, model, truncated)
        if not token:
            self.quote_finder_suggest_btn.setEnabled(True)
            self.manuscript_status_label.setText("")
            return
        self._quote_finder_token = token
        self.quote_finder_worker = self._new_chat_worker(provider, model, messages, truncated)
        self.quote_finder_worker.finished_signal.connect(self._quote_finder_on_finished)
        self.quote_finder_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.quote_finder_worker.error_signal.connect(self._quote_finder_on_error)
        self.quote_finder_worker.start()

    def _quote_finder_on_finished(self, full_response: str):
        token = getattr(self, "_quote_finder_token", None)
        self._quote_finder_token = None
        if token:
            self.record_request(token, full_response)
        self.quote_finder_suggest_btn.setEnabled(True)
        quotes = self._parse_quote_list(full_response)
        self.quote_finder_list.clear()
        self._quote_finder_short_buttons = []
        if not quotes:
            self.manuscript_status_label.setText("[Error] Could not parse quotes from response.")
            return
        for q in quotes:
            item = QListWidgetItem()
            row = self._build_quote_suggestion_row(q)
            item.setSizeHint(row.sizeHint())
            self.quote_finder_list.addItem(item)
            self.quote_finder_list.setItemWidget(item, row)
        self.manuscript_status_label.setText(f"[Done] Found {len(quotes)} quotes.")

    def _quote_finder_on_error(self, error: str):
        token = getattr(self, "_quote_finder_token", None)
        self._quote_finder_token = None
        if token:
            self.abandon_request(token)
        self.quote_finder_suggest_btn.setEnabled(True)
        self.manuscript_status_label.setText(f"[Error] {error}")

    def _parse_quote_list(self, text: str) -> list:
        from services.llm_parsing import parse_string_list
        return parse_string_list(text)

    def _build_quote_suggestion_row(self, quote: str) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(6)

        label = QLabel(quote)
        label.setWordWrap(True)
        h.addWidget(label, 1)

        graphic_btn = QPushButton("Graphic")
        graphic_btn.setFixedWidth(78)
        graphic_btn.setToolTip("Generate quote graphic")
        graphic_btn.clicked.connect(lambda checked=False, q=quote: self.quote_finder_generate_graphic(q))
        h.addWidget(graphic_btn)

        short_btn = QPushButton("Short")
        short_btn.setFixedWidth(70)
        short_btn.setToolTip("Generate narrated short")
        short_btn.clicked.connect(lambda checked=False, q=quote, b=short_btn: self.quote_finder_generate_short(q, b))
        h.addWidget(short_btn)
        self._quote_finder_short_buttons.append(short_btn)

        return row

    def quote_finder_generate_graphic(self, quote: str):
        from services.quote_graphics import render_quote_graphic, GRAPHICS_DIR
        import time
        theme = theme_key(self.quote_finder_theme_box)
        attribution = self.quote_finder_attribution.text().strip()
        output_path = unique_output_path(GRAPHICS_DIR, "quote", ".png")
        try:
            render_quote_graphic(quote, output_path, theme=theme, size_name="square", attribution=attribution)
            self.manuscript_status_label.setText(f"[Done] Saved {output_path.name}")
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")

    def quote_finder_generate_short(self, quote: str, button: QPushButton):
        if self._quote_finder_busy:
            QMessageBox.information(self, "Busy", "A short is already generating — please wait for it to finish.")
            return
        from services.quote_graphics import render_quote_graphic
        from services.shorts_generator import SHORTS_DIR
        import time

        theme = theme_key(self.quote_finder_theme_box)
        attribution = self.quote_finder_attribution.text().strip()
        use_elevenlabs = self.quote_finder_voice_source_box.currentText() == "ElevenLabs"
        voice_id = self.quote_finder_voice_box.currentData() or "default"

        output_path = unique_output_path(SHORTS_DIR, "short", ".mp4")
        image_path = output_path.with_suffix(".png")
        try:
            render_quote_graphic(quote, image_path, theme=theme, size_name="vertical", attribution=attribution)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if not self._authorize_short_narration(quote, use_elevenlabs):
            return

        self._quote_finder_busy = True
        for b in self._quote_finder_short_buttons:
            b.setEnabled(False)
        button.setText("…")
        self.manuscript_status_label.setText("[Narrating…]")

        self.shorts_worker = ShortsWorker(quote, image_path, output_path, use_elevenlabs, voice_id)
        self.shorts_worker.status_signal.connect(self.manuscript_status_label.setText)
        self.shorts_worker.done_signal.connect(lambda path, b=button: self._quote_finder_short_done(path, b))
        self.shorts_worker.error_signal.connect(lambda err, b=button: self._quote_finder_short_error(err, b))
        self.shorts_worker.start()

    def _quote_finder_short_done(self, output_path: str, button: QPushButton):
        self._shorts_resolve_request(True, f"saved {Path(output_path).name}")
        self._last_short_path = output_path
        self.manuscript_status_label.setText(f"[Done] Saved {Path(output_path).name}")
        button.setText("Short")
        self._quote_finder_busy = False
        for b in self._quote_finder_short_buttons:
            b.setEnabled(True)

    def _quote_finder_short_error(self, error: str, button: QPushButton):
        self._shorts_resolve_request(False)
        self.manuscript_status_label.setText(f"[Error] {error}")
        button.setText("⚠")
        self._quote_finder_busy = False
        for b in self._quote_finder_short_buttons:
            b.setEnabled(True)

    # ── Calendar handlers ─────────────────────────────────────────────────────
    def calendar_load_voices(self):
        from ui.book_widgets import populate_voice_box
        populate_voice_box(self.calendar_voice_box, self.calendar_voice_source_box.currentText())

    def _calendar_quotes_from_finder(self) -> list:
        quotes = []
        for i in range(self.quote_finder_list.count()):
            widget = self.quote_finder_list.itemWidget(self.quote_finder_list.item(i))
            if widget:
                label = widget.findChild(QLabel)
                if label:
                    quotes.append(label.text())
        return quotes

    def manuscript_generate_calendar(self):
        quotes = self._calendar_quotes_from_finder()
        if not quotes:
            QMessageBox.warning(self, "No Quotes", "Run 'Suggest Quotes' on the Quote Finder tab first.")
            return

        platforms = []
        if self.calendar_tiktok_check.isChecked():
            platforms.append("TikTok")
        if self.calendar_instagram_check.isChecked():
            platforms.append("Instagram")
        if self.calendar_pinterest_check.isChecked():
            platforms.append("Pinterest")
        if not platforms:
            QMessageBox.warning(self, "No Platforms", "Select at least one platform.")
            return

        provider = self.manuscript_provider_box.currentText()
        model = self.manuscript_model_box.currentText()
        if not model:
            self.manuscript_status_label.setText("[Error] Select a model on the Overview tab.")
            return

        weeks = int(self.calendar_weeks_box.currentText())
        start_date = self.calendar_start_date.date().toPython()

        from services.content_calendar import build_calendar
        slots = build_calendar(quotes, weeks, start_date, platforms)
        if not slots:
            self.manuscript_status_label.setText("[Error] Could not build a calendar.")
            return
        self._calendar_slots = slots

        items = [{"quote": s.quote, "platform": s.platform.lower()} for s in slots]
        items_json = json.dumps(items)
        agent = self.agent_instances["manuscript"]
        messages = agent.build_calendar_caption_messages(items_json)
        self.manuscript_status_label.setText("[Writing captions…]")
        self.calendar_generate_btn.setEnabled(False)
        token = self.authorize_request("manuscript", provider, model, items_json)
        if not token:
            self.calendar_generate_btn.setEnabled(True)
            self.manuscript_status_label.setText("")
            return
        self._calendar_captions_token = token
        self.calendar_worker = self._new_chat_worker(provider, model, messages, items_json)
        self.calendar_worker.finished_signal.connect(self._calendar_on_captions_done)
        self.calendar_worker.usage_signal.connect(lambda u, t=token: self.note_request_usage(t, u))
        self.calendar_worker.error_signal.connect(self._calendar_on_captions_error)
        self.calendar_worker.start()

    def _calendar_on_captions_done(self, full_response: str):
        token = getattr(self, "_calendar_captions_token", None)
        self._calendar_captions_token = None
        if token:
            self.record_request(token, full_response)
        self.calendar_generate_btn.setEnabled(True)
        captions = self._parse_quote_list(full_response)
        for i, slot in enumerate(self._calendar_slots):
            slot.caption = captions[i] if i < len(captions) else ""
        self._populate_calendar_table()
        self.manuscript_status_label.setText(f"[Done] {len(self._calendar_slots)}-post calendar generated.")

    def _calendar_on_captions_error(self, error: str):
        token = getattr(self, "_calendar_captions_token", None)
        self._calendar_captions_token = None
        if token:
            self.abandon_request(token)
        self.calendar_generate_btn.setEnabled(True)
        self._populate_calendar_table()
        self.manuscript_status_label.setText(f"[Error] Captions failed ({error}) — schedule shown, captions blank.")

    def _populate_calendar_table(self):
        from PySide6.QtWidgets import QTableWidgetItem
        self.calendar_table.setRowCount(len(self._calendar_slots))
        for row, slot in enumerate(self._calendar_slots):
            self.calendar_table.setItem(row, 0, QTableWidgetItem(slot.day.strftime("%Y-%m-%d")))
            self.calendar_table.setItem(row, 1, QTableWidgetItem(slot.platform))
            self.calendar_table.setItem(row, 2, QTableWidgetItem(slot.format))
            self.calendar_table.setItem(row, 3, QTableWidgetItem(slot.quote))
            self.calendar_table.setItem(row, 4, QTableWidgetItem(slot.caption))

            btn = QPushButton(
                "Graphic" if slot.format == "graphic" else "Short")
            btn.setFixedWidth(78)
            btn.clicked.connect(lambda checked=False, r=row, b=btn: self.calendar_generate_asset(r, b))
            self.calendar_table.setCellWidget(row, 5, btn)

    def calendar_generate_asset(self, row: int, button: QPushButton):
        if row >= len(self._calendar_slots):
            return
        slot = self._calendar_slots[row]
        from services.quote_graphics import render_quote_graphic
        import time

        theme = theme_key(self.calendar_theme_box)
        attribution = self.calendar_attribution.text().strip()

        if slot.format == "graphic":
            from services.quote_graphics import GRAPHICS_DIR
            output_path = unique_output_path(GRAPHICS_DIR, "quote", ".png")
            try:
                render_quote_graphic(slot.quote, output_path, theme=theme, size_name="square", attribution=attribution)
                self.manuscript_status_label.setText(f"[Done] Saved {output_path.name}")
            except Exception as e:
                self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if self._quote_finder_busy:
            QMessageBox.information(self, "Busy", "A short is already generating — please wait for it to finish.")
            return
        from services.shorts_generator import SHORTS_DIR
        use_elevenlabs = self.calendar_voice_source_box.currentText() == "ElevenLabs"
        voice_id = self.calendar_voice_box.currentData() or "default"
        output_path = unique_output_path(SHORTS_DIR, "short", ".mp4")
        image_path = output_path.with_suffix(".png")
        try:
            render_quote_graphic(slot.quote, image_path, theme=theme, size_name="vertical", attribution=attribution)
        except Exception as e:
            self.manuscript_status_label.setText(f"[Error] {e}")
            return

        if not self._authorize_short_narration(slot.quote, use_elevenlabs):
            return

        self._quote_finder_busy = True
        button.setEnabled(False)
        self.manuscript_status_label.setText("[Narrating…]")
        self.shorts_worker = ShortsWorker(slot.quote, image_path, output_path, use_elevenlabs, voice_id)
        self.shorts_worker.status_signal.connect(self.manuscript_status_label.setText)
        self.shorts_worker.done_signal.connect(lambda path, b=button: self._calendar_short_done(path, b))
        self.shorts_worker.error_signal.connect(lambda err, b=button: self._calendar_short_error(err, b))
        self.shorts_worker.start()

    def _calendar_short_done(self, output_path: str, button: QPushButton):
        self._shorts_resolve_request(True, f"saved {Path(output_path).name}")
        self._last_short_path = output_path
        self.manuscript_status_label.setText(f"[Done] Saved {Path(output_path).name}")
        button.setEnabled(True)
        self._quote_finder_busy = False

    def _calendar_short_error(self, error: str, button: QPushButton):
        self._shorts_resolve_request(False)
        self.manuscript_status_label.setText(f"[Error] {error}")
        button.setEnabled(True)
        self._quote_finder_busy = False

    def manuscript_export_calendar_csv(self):
        if not self._calendar_slots:
            QMessageBox.warning(self, "No Calendar", "Generate a calendar first.")
            return
        import csv
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Calendar", str(BASE_DIR / "content_calendar.csv"), "CSV Files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Platform", "Format", "Quote", "Caption"])
            for slot in self._calendar_slots:
                writer.writerow([slot.day.strftime("%Y-%m-%d"), slot.platform, slot.format, slot.quote, slot.caption])
        self.manuscript_status_label.setText(f"[Done] Exported calendar to {Path(path).name}")

    def build_right_panel(self) -> QWidget:
        """Spend, limits, and the utilities that open a window.

        This was five cards — SYSTEM, ROUTING, SPEND, ACTIONS, API KEYS — each
        with its own border and title bar, stacked inside a scroll area inside
        a panel. The spend card alone was nine lines of prose at one weight
        ("Session Cost: €0.00", "Cost Today: €0.00", …), which is five
        sentences to read before you know whether you can afford a request.

        Now: four numbers, two bars, and the limits that set them. The
        reference material that is only wanted when something looks wrong
        (system load, routing, key status) stays, collapsed, at the bottom.
        """
        right_widget = rail("RailRight", RAIL_RIGHT_WIDTH)
        # The rail scrolls. A QVBoxLayout given less height than its children
        # need compresses them past their own minimums rather than clipping,
        # and at the window's 600px minimum that drew "€0.00" over the caption
        # under it. Same failure the panels already use scrollable() for.
        rail_outer = QVBoxLayout(right_widget)
        rail_outer.setContentsMargins(0, 0, 0, 0)
        rail_body = QWidget()
        rail_body.setObjectName("Transparent")
        rail_scroll = scrollable(rail_body)
        # This rail has a fixed width and every component is designed for it;
        # a one-pixel size-hint mismatch must not create a horizontal scrollbar.
        rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rail_outer.addWidget(rail_scroll)
        layout = QVBoxLayout(rail_body)
        layout.setContentsMargins(MD + XS, LG, MD + XS, LG)
        layout.setSpacing(MD)

        layout.addWidget(section("Spend"))

        stats = QGridLayout()
        stats.setHorizontalSpacing(MD)
        stats.setVerticalSpacing(MD)
        self.session_cost_stat = StatBlock("this session", "€0.00")
        self.today_cost_stat = StatBlock("today", "€0.00")
        self.request_count_stat = StatBlock("requests", "0")
        self.last_request_stat = StatBlock("last request", "—")
        stats.addWidget(self.session_cost_stat, 0, 0)
        stats.addWidget(self.today_cost_stat, 0, 1)
        stats.addWidget(self.request_count_stat, 1, 0)
        stats.addWidget(self.last_request_stat, 1, 1)
        stats.setColumnStretch(0, 1)
        stats.setColumnStretch(1, 1)
        layout.addLayout(stats)

        # "Session remaining: €1 / €1" is two numbers you have to subtract. A
        # bar answers the question before you have read anything.
        self.session_meter = Meter("Session budget")
        self.daily_meter = Meter("Daily budget")
        self.project_meter = Meter("Project budget")
        layout.addWidget(self.session_meter)
        layout.addWidget(self.daily_meter)
        layout.addWidget(self.project_meter)
        self.project_meter.hide()

        self.live_estimate_label = QLabel("No request pending")
        self.live_estimate_label.setObjectName("EstimateLine")
        self.live_estimate_label.setWordWrap(True)
        layout.addWidget(self.live_estimate_label)

        layout.addWidget(section("Limits"))
        limits_row = QHBoxLayout()
        limits_row.setSpacing(SM)
        self.session_budget_input = line_edit("1", str(int(self.session_budget_eur)))
        self.session_budget_input.setAlignment(Qt.AlignRight)
        self.daily_budget_input = line_edit("5", str(int(self.daily_budget_eur)))
        self.daily_budget_input.setAlignment(Qt.AlignRight)
        limits_row.addWidget(field("Session €", self.session_budget_input))
        limits_row.addWidget(field("Daily €", self.daily_budget_input))
        layout.addLayout(limits_row)

        self.save_budget_btn = QPushButton("Save Limits")
        self.save_budget_btn.clicked.connect(self.save_budget_limits)
        layout.addWidget(self.save_budget_btn)

        self.reset_session_budget_btn = quiet("Reset session spend")
        self.reset_session_budget_btn.clicked.connect(self.reset_session_spend)
        layout.addWidget(self.reset_session_budget_btn)

        # ── Utilities: open a window, change nothing. Keep them with the
        # spend controls instead of marooning them below an elastic void. ──
        layout.addWidget(rule())
        layout.addWidget(section("Activity"))
        links = QVBoxLayout()
        links.setSpacing(0)
        self.cost_history_btn = quiet("Cost History")
        self.cost_history_btn.clicked.connect(self.show_cost_history)
        links.addWidget(self.cost_history_btn)

        self.run_log_btn = quiet("Run Log")
        self.run_log_btn.clicked.connect(self.show_run_log)
        links.addWidget(self.run_log_btn)

        self.learn_btn = quiet("Learning Centre")
        self.learn_btn.clicked.connect(self.show_learning_center)
        links.addWidget(self.learn_btn)
        layout.addLayout(links)

        # ── Reference: wanted only when something looks wrong ──────────────
        reference = QVBoxLayout()
        reference.setSpacing(0)

        system_card = CollapsibleSection("System", expanded=False)
        system_body = QWidget()
        system_body.setObjectName("Transparent")
        system_layout = QVBoxLayout(system_body)
        system_layout.setContentsMargins(SM, XS, SM, SM)
        system_layout.setSpacing(SM)
        self.resource_status_card = ResourceStatusCard()
        self.resource_status_card.setStyleSheet(STATUS_CARD_STYLES)
        # Compatibility alias for tooltips and existing extensions.  The old
        # object was one long rich-text QLabel; the new card owns four rows.
        self.resource_label = self.resource_status_card
        system_layout.addWidget(self.resource_status_card)
        self.realtime_monitor_btn = QPushButton("Realtime Monitor")
        self.realtime_monitor_btn.setEnabled(False)
        system_layout.addWidget(self.realtime_monitor_btn)
        system_card.addWidget(system_body)
        reference.addWidget(system_card)

        routing_card = CollapsibleSection("Routing", expanded=False)
        routing_body = QWidget()
        routing_body.setObjectName("Transparent")
        routing_layout = QVBoxLayout(routing_body)
        routing_layout.setContentsMargins(SM, XS, SM, SM)
        routing_layout.setSpacing(XS)
        self.routing_status_card = RoutingStatusCard()
        self.routing_status_card.setStyleSheet(STATUS_CARD_STYLES)
        # These aliases retain the public widget attributes used by tooltips
        # and integrations while avoiding the original paragraph-style UI.
        self.route_result_label = self.routing_status_card.route_value
        self.recommendation_label = self.routing_status_card.reason_label
        routing_layout.addWidget(self.routing_status_card)
        routing_card.addWidget(routing_body)
        reference.addWidget(routing_card)

        keys_card = CollapsibleSection("API keys", expanded=False)
        keys_body = QWidget()
        keys_body.setObjectName("Transparent")
        keys_layout = QVBoxLayout(keys_body)
        keys_layout.setContentsMargins(SM, XS, SM, SM)
        keys_layout.setSpacing(XS)
        self.api_keys_status_card = ApiKeysStatusCard(
            ("OpenAI", "DeepSeek", "Kimi", "Gemini", "Anthropic"))
        self.api_keys_status_card.setStyleSheet(STATUS_CARD_STYLES)
        key_classes = {
            "OpenAI": OpenAIClientWrapper, "DeepSeek": DeepSeekClientWrapper,
            "Kimi": KimiClientWrapper, "Gemini": GeminiClientWrapper,
            "Anthropic": AnthropicClientWrapper,
        }
        for provider, wrapper in key_classes.items():
            self.api_keys_status_card.set_status(
                provider, self.safe_key_status(wrapper))
        self.openai_key_label = self.api_keys_status_card.status_labels["openai"]
        self.deepseek_key_label = self.api_keys_status_card.status_labels["deepseek"]
        self.kimi_key_label = self.api_keys_status_card.status_labels["kimi"]
        self.gemini_key_label = self.api_keys_status_card.status_labels["gemini"]
        self.anthropic_key_label = self.api_keys_status_card.status_labels["anthropic"]
        keys_layout.addWidget(self.api_keys_status_card)
        keys_card.addWidget(keys_body)
        reference.addWidget(keys_card)

        layout.addLayout(reference)
        layout.addStretch()

        return right_widget

    def load_provider_models(self):
        if not hasattr(self, "provider_box") or not hasattr(self, "model_box"):
            return

        provider = self.provider_box.currentText()
        previous_model = self.settings.get(f"default_model_{provider}", "")

        self.model_box.clear()

        try:
            if provider == "ollama":
                try:
                    models = self.ollama.list_models()
                    self.model_box.setProperty("imprintModelsLive", bool(models))
                except Exception:
                    models = []
                    self.model_box.setProperty("imprintModelsLive", False)
                if not models:
                    models = list(OllamaClient.KNOWN_MODELS)

            elif provider == "openai":
                if not self.openai.client:
                    models = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"]
                else:
                    result = self.openai.client.models.list()
                    models = sorted(
                        m.id for m in result.data
                        if any(x in m.id.lower() for x in ["gpt", "o1", "o3", "o4"])
                    )

            elif provider == "deepseek":
                # Try API model list if available. Fallback to known/common names.
                try:
                    if self.deepseek.client:
                        result = self.deepseek.client.models.list()
                        models = sorted(m.id for m in result.data)
                    else:
                        models = []
                except Exception:
                    models = []

                if not models:
                    models = [
                        "deepseek-chat",
                        "deepseek-reasoner",
                        "deepseek-coder",
                        "deepseek-v4-pro",
                        "deepseek-v4-flash",
                    ]

            elif provider == "kimi":
                # Try API model list if available. Fallback to known/common names.
                try:
                    if self.kimi.client:
                        result = self.kimi.client.models.list()
                        models = sorted(m.id for m in result.data)
                    else:
                        models = []
                except Exception:
                    models = []

                if not models:
                    models = self.kimi.KNOWN_MODELS

            elif provider == "gemini":
                try:
                    if self.gemini.client:
                        result = self.gemini.client.models.list()
                        models = sorted(
                            m.name.replace("models/", "")
                            for m in result
                            if "generateContent" in getattr(m, "supported_actions", [])
                            or "generateContent" in getattr(m, "supported_generation_methods", [])
                        )
                    else:
                        models = []
                except Exception:
                    models = []

                if not models:
                    models = list(self.gemini.KNOWN_MODELS)

            elif provider == "anthropic":
                models = self.anthropic.list_models()
            elif provider == "qwen":
                models = self.qwen.list_models()

            else:
                models = []

            self.model_box.addItems(models)

            if previous_model:
                idx = self.model_box.findText(previous_model)
                if idx >= 0:
                    self.model_box.setCurrentIndex(idx)

            self.update_live_cost_estimate()

        except Exception as e:
            self.output_box.append(f"[Model Load Error] {e}")
            
    def save_provider_model_preference(self):
        if getattr(self, "_is_initializing", False):
            return
        if not hasattr(self, "provider_box") or not hasattr(self, "model_box"):
            return

        provider = self.provider_box.currentText()
        model = self.model_box.currentText()

        if not provider or not model:
            return

        self.settings[f"default_model_{provider}"] = model

        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            self.output_box.append(f"[Settings Save Error] {e}")   

    def apply_global_style(self):
        self.setStyleSheet(GLOBAL_STYLESHEET)

    # ── Bug Bounty handlers ───────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────
    # Manager Agent handlers
    # ──────────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────────
    # OP IDENTITY PANEL
    # ──────────────────────────────────────────────────────────────────

    OSINT_TOOLS = [
        # id, display name, category, cost label, signup URL, .env key (or "")
        ("emailrep",       "EmailRep.io",        "Email",    "Free",       "https://emailrep.io",                           ""),
        ("urlscan",        "URLScan.io",          "Domain",   "Free",       "https://urlscan.io/user/register",              "URLSCAN_API_KEY"),
        ("virustotal",     "VirusTotal",          "Threat",   "Free",       "https://www.virustotal.com/gui/join-us",         "VIRUSTOTAL_API_KEY"),
        ("otx",            "AlienVault OTX",      "Threat",   "Free",       "https://otx.alienvault.com/",                   "OTX_API_KEY"),
        ("ipinfo",         "IPinfo.io",           "Network",  "Free",       "https://ipinfo.io/signup",                      "IPINFO_API_KEY"),
        ("abuseipdb",      "AbuseIPDB",           "Network",  "Free",       "https://www.abuseipdb.com/register",            "ABUSEIPDB_API_KEY"),
        ("greynoise",      "GreyNoise",           "Network",  "Free",       "https://www.greynoise.io/signup",               "GREYNOISE_API_KEY"),
        ("censys",         "Censys",              "Network",  "Free",       "https://search.censys.io/register",             "CENSYS_API_KEY"),
        ("securitytrails", "SecurityTrails",      "Domain",   "Free",       "https://securitytrails.com/app/signup",         "SECURITYTRAILS_API_KEY"),
        ("hunter",         "Hunter.io",           "Email",    "Free",       "https://hunter.io/users/sign_up",               "HUNTER_API_KEY"),
        ("breachdirectory","BreachDirectory",     "Breach",   "Free",       "https://breachdirectory.org",                   ""),
        ("hibp",           "HaveIBeenPwned",      "Breach",   "$3.50/mo",   "https://haveibeenpwned.com/API/Key",            "HIBP_API_KEY"),
        ("shodan",         "Shodan",              "Network",  "$49/mo",     "https://account.shodan.io/register",            "SHODAN_API_KEY"),
        ("dehashed",       "DeHashed",            "Breach",   "$5/mo",      "https://dehashed.com/register",                 "DEHASHED_API_KEY"),
        ("snusbase",       "Snusbase",            "Breach",   "$2/mo",      "https://snusbase.com/",                         "SNUSBASE_API_KEY"),
        ("leakcheck",      "LeakCheck",           "Breach",   "Paid",       "https://leakcheck.io/",                         "LEAKCHECK_API_KEY"),
        ("intelx",         "IntelligenceX",       "Dark Web", "Paid",       "https://intelx.io/",                            "INTELX_API_KEY"),
        ("domaintools",    "DomainTools",         "Domain",   "Paid",       "https://www.domaintools.com/",                  "DOMAINTOOLS_API_KEY"),
    ]

    def select_agent(self, agent_name):
        self.agent_box.setCurrentText(agent_name)
        for btn in self.agent_buttons.values():
            btn.setChecked(False)
        if agent_name in self.agent_buttons:
            self.agent_buttons[agent_name].setChecked(True)
        self._sync_workspace_navigation(agent_name)
        self.update_agent_ui(agent_name)

    def _workspace_changed(self, index):
        """Open the last-used tool in the selected workspace."""
        if getattr(self, "_syncing_workspace_tabs", False):
            return
        workspace_name = self.workspace_tabs.tabText(index)
        agents = WORKSPACES.get(workspace_name, ())
        if not agents:
            return
        remembered = getattr(self, "_workspace_last_agent", {}).get(workspace_name)
        self.select_agent(remembered if remembered in agents else agents[0])

    def _sync_workspace_navigation(self, agent_name):
        """Keep the workspace and stage controls aligned with the active tool."""
        workspace_name = next(
            (name for name, agents in WORKSPACES.items() if agent_name in agents),
            None,
        )
        if workspace_name is None or not hasattr(self, "workspace_tabs"):
            return

        if not hasattr(self, "_workspace_last_agent"):
            self._workspace_last_agent = {}
        self._workspace_last_agent[workspace_name] = agent_name

        target_index = list(WORKSPACES).index(workspace_name)
        self._syncing_workspace_tabs = True
        self.workspace_tabs.setCurrentIndex(target_index)
        self._syncing_workspace_tabs = False

        agents_in_workspace = WORKSPACES[workspace_name]
        for name, button in self.workspace_tool_buttons.items():
            button.setVisible(name in agents_in_workspace)
            button.setChecked(name == agent_name)

        # Single-tool workspaces do not need a redundant second navigation row.
        self.workspace_tool_row.setVisible(len(agents_in_workspace) > 1)

    def update_agent_ui(self, agent_name):
        self._current_agent = agent_name  # track for show_agent_docs()
        # ── Update the agent header bar (title + subtitle + status pill) ─
        # From the catalog, not hardcoded copies: the dicts that lived here
        # duplicated AgentSpec.label/.description and had already drifted
        # from them in wording.
        spec = next((s for s in AGENT_SPECS if s.key == agent_name), None)
        if hasattr(self, "agent_title_label"):
            self.agent_title_label.setText(
                spec.label if spec else agent_name.title())
        if hasattr(self, "agent_subtitle_label"):
            self.agent_subtitle_label.setText(spec.description if spec else "")
        if hasattr(self, "agent_status_pill"):
            self.agent_status_pill.setText("●  Ready")
            self.agent_status_pill.setStyleSheet("")

        # One list, not a chain of `is_x` booleans repeated in two blocks.
        # Adding an agent used to mean editing both, and forgetting one is
        # exactly the dangling-name failure that left sentinel_ai raising
        # NameError on every agent click.
        is_custom = agent_name in CUSTOM_PANELS
        self.normal_panel.setVisible(not is_custom)
        for name in CUSTOM_PANELS:
            panel = getattr(self, f"{name}_panel", None)
            if panel is not None:
                panel.setVisible(name == agent_name)
        # Output area only relevant for standard (non-custom) agents like Chat.
        # Within those, auto-hide if there is no content yet — keeps the UI clean.
        standard_agent_with_output = not is_custom
        has_output_content = bool(self.output_box.toPlainText().strip())
        show_output = standard_agent_with_output and has_output_content
        self.output_label.setVisible(show_output)
        self.output_box.setVisible(show_output)

        if agent_name == "audiobook":
            self.output_label.setText("Output Log")
            self.output_box.setPlainText("[Ready] Click Start to begin.")
            self.refresh_audiobook_books()
            self.refresh_audiobook_library()
        elif agent_name == "manuscript":
            from services.kdp_csv_parser import manuscript_seed_todos
            manuscript_seed_todos()
            self._load_manuscript_todos()
            self._refresh_next_step_tip()
        elif agent_name == "author":
            self._refresh_next_step_tip()
        elif agent_name == "video":
            self.refresh_video_library()
        elif agent_name == "onlyfans":
            self.onlyfans_dashboard.refresh()
        elif not is_custom:
            self.output_label.setText("Output")

    def get_audiobook_defaults(self):
        return self.audiobook_panel.defaults()

    def _update_audiobook_source_state(self, empty_message: str = "") -> None:
        self.audiobook_panel._update_source_state(empty_message)

    def refresh_audiobook_books(self):
        self.audiobook_panel.refresh_books()

    def open_audiobook_input_folder(self):
        self.audiobook_panel.open_input_folder()

    def change_audiobook_output_folder(self):
        self.audiobook_panel.change_output_folder()

    def _audiobook_estimate(self, path: Path) -> dict | None:
        return self.audiobook_panel._estimate(path)

    def _audiobook_text(self, path: Path) -> str:
        return self.audiobook_panel._text(path)

    def estimate_audiobook_cost_from_selection(self):
        self.audiobook_panel.estimate_cost_from_selection()

    def start_selected_audiobook_book(self):
        self.audiobook_panel.start_conversion()

    def run_audiobook_live(self, config):
        self.audiobook_panel.run_conversion(config)

    def handle_audiobook_error(self, error):
        self.audiobook_panel.handle_error(error)

    def handle_audiobook_stdout(self):
        self.audiobook_panel.process = self.audiobook_process
        self.audiobook_panel.handle_stdout()

    def handle_audiobook_finished(self):
        self.audiobook_panel.process = self.audiobook_process
        self.audiobook_panel.handle_finished()

    @staticmethod
    def _extract_audiobook_error(output_text: str) -> str:
        return AudiobookPanel.extract_error(output_text)

    def load_models(self):
        self.model_box.clear()
        try:
            models = self.ollama.list_models()
            self.model_box.setProperty("imprintModelsLive", bool(models))
        except Exception:
            models = []
            self.model_box.setProperty("imprintModelsLive", False)
        if not models:
            models = list(OllamaClient.KNOWN_MODELS)
        self.model_box.addItems(models)
        self.update_live_cost_estimate()

    def build_tool_messages(self, selected_tool, full_prompt):
        tool_config = self.tool_prompts.get(selected_tool, {})
        system_prompt = tool_config.get("system", "You are a helpful assistant.")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt},
        ]
        project = self._active_project()
        return with_project_instructions(
            messages, (project or {}).get("instructions", "")
        )

    def _build_chat_request_messages(self, agent_name: str, tool: str,
                                     prompt: str, include_history: bool) -> list[dict]:
        if tool in self.tool_prompts:
            messages = self.build_tool_messages(tool, prompt)
        elif agent_name in self.agent_instances:
            messages = self.agent_instances[agent_name].build_messages(prompt)
        else:
            messages = [{"role": "user", "content": prompt}]
        return (continue_chat_messages(messages, self.current_messages)
                if include_history else messages)

    def _new_chat_worker(self, backend, model, messages, prompt):
        """Snapshot project context before the background request starts."""
        project = self._active_project()
        return ChatWorker(
            self.run_backend, backend, model, messages, prompt,
            project_instructions=(project or {}).get("instructions", ""),
        )

    def _set_route_result(self, agent: str = "", provider: str = "",
                          model: str = "") -> None:
        """Update the structured last-decision card from every run path."""
        if hasattr(self, "routing_status_card"):
            if agent or provider or model:
                self.routing_status_card.set_route(agent, provider, model)
            else:
                self.routing_status_card.reset_route()
            return
        if hasattr(self, "route_result_label"):
            self.route_result_label.setText(
                f"Router: {agent} · {provider} · {model}"
                if agent or provider or model else "Router: not yet computed")

    def auto_route_agent(self):
        raw_text = self.input_box.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Warning", "Please enter text first.")
            return

        # Actually route. This button used to echo the current selection back
        # at the user — RouterAgent existed, was tested, and was never called
        # by the app.
        from agents.router import RouterAgent
        routed = RouterAgent().classify(raw_text)
        if routed != self.agent_box.currentText():
            self.select_agent(routed)
        backend, model = self.resolve_backend_model()
        self._set_route_result(routed, backend, model)

    def resolve_backend_model(self):
        provider = self.provider_box.currentText()
        model = self.model_box.currentText()
        execution_mode = self.execution_mode_box.currentText()

        allowed_apis = {
            "openai": self.allow_openai_checkbox.isChecked(),
            "deepseek": self.allow_deepseek_checkbox.isChecked(),
            "kimi": self.allow_kimi_checkbox.isChecked(),
            "gemini": self.allow_gemini_checkbox.isChecked(),
            "anthropic": self.allow_anthropic_checkbox.isChecked(),
            "qwen": self.allow_qwen_checkbox.isChecked(),
            "higgsfield": self.allow_higgsfield_checkbox.isChecked(),
        }

        if execution_mode == "Local only":
            return "ollama", model if model else "deepseek-r1:8b"

        if execution_mode == "Cloud only":
            if provider == "ollama":
                raise RuntimeError("Cloud only mode selected, but provider is Ollama/local.")

            if provider not in allowed_apis:
                raise RuntimeError(f"Unknown cloud provider: {provider}")

            if not allowed_apis[provider]:
                raise RuntimeError(f"{provider} API is not enabled. Tick the checkbox first.")

            return provider, model

        if execution_mode == "Hybrid allowed":
            if provider == "ollama":
                return "ollama", model if model else "deepseek-r1:8b"

            if provider in allowed_apis and not allowed_apis[provider]:
                raise RuntimeError(f"{provider} API is not enabled. Tick the checkbox first.")

            return provider, model

        return "ollama", model if model else "deepseek-r1:8b"

    def build_user_prompt(self, raw_text: str):
        command_name = self.command_box.currentText()
        prefix = self.commands.get(command_name, "")
        if prefix.strip():
            return command_name, f"{prefix}\n\n{raw_text}"
        return command_name, raw_text

    def send_prompt(self):
        selected_agent = self.agent_box.currentText()

        if selected_agent == "audiobook":
            self.start_selected_audiobook_book()
            return

        raw_text = self.input_box.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Warning", "Please enter text first.")
            return

        selected_tool = self.tool_box.currentText() if hasattr(self, "tool_box") else "General Chat"
        command_name, full_prompt = self.build_user_prompt(raw_text)
        final_backend, final_model = self.resolve_backend_model()

        previous = self._conversation_context_text(selected_agent, selected_tool)
        billable_prompt = f"{previous}\n{full_prompt}" if previous else full_prompt
        estimated_cost, approx_tokens = self.estimate_chat_cost(
            final_backend, final_model, billable_prompt)

        api_permissions = {
            "allow_openai": self.allow_openai_checkbox.isChecked(),
            "allow_deepseek": self.allow_deepseek_checkbox.isChecked(),
            "allow_kimi": self.allow_kimi_checkbox.isChecked(),
            "allow_gemini": self.allow_gemini_checkbox.isChecked(),
            "allow_anthropic": self.allow_anthropic_checkbox.isChecked(),
            "allow_qwen": self.allow_qwen_checkbox.isChecked(),
            "allow_higgsfield": self.allow_higgsfield_checkbox.isChecked(),
            "allow_elevenlabs": self.allow_elevenlabs_checkbox.isChecked(),
        }

        reserved = self._reserved_in_flight_eur()
        validation = self.validator.validate(
            agent_name=selected_agent,
            tool_name=selected_tool,
            provider=final_backend,
            api_permissions=api_permissions,
            session_cost=self.session_cost_total + reserved,
            session_budget=self.session_budget_eur,
            daily_cost=self.usage_tracker.get_today_total() + reserved,
            daily_budget=self.daily_budget_eur,
            estimated_cost=estimated_cost,
            agent_daily_cost=self.usage_tracker.get_agent_today_total(selected_agent),
            **self._project_budget_fields(),
        )
        if not validation.allowed:
            QMessageBox.warning(self, "Request Blocked", validation.reason)
            return

        if not self.confirm_external_api_request(
            final_backend,
            final_model,
            estimated_cost,
            approx_tokens,
        ):
            return

        # Memory pre-flight sits with the other gates, before any UI state is
        # changed. Run it after the worker is armed and a cancel would strand a
        # disabled Send button and an open run-log entry.
        if not self.check_memory_before_request(final_backend, final_model):
            return

        try:
            messages = self._build_chat_request_messages(
                selected_agent, selected_tool, full_prompt, bool(previous))

            self.pending_agent = selected_agent
            self.pending_tool = selected_tool
            self.pending_backend = final_backend
            self.pending_model = final_model
            self.pending_command = command_name
            project = self._active_project()
            self.pending_project = project["id"] if project else None
            self.pending_project_instructions = (project or {}).get("instructions", "")
            self.pending_messages = messages
            self.pending_prompt = full_prompt
            self.pending_billing_prompt = billable_prompt
            self.pending_usage = None

            self.show_output_area()
            if previous:
                self.output_box.append(f"\n\nYou\n{raw_text}\n")
            else:
                self.output_box.clear()
            self.output_box.append("[Working]")
            self.output_box.append(f"Agent: {selected_agent}")
            self.output_box.append(f"Backend: {final_backend}")
            self.output_box.append(f"Model: {final_model}")
            self.output_box.append(f"Command: {command_name}")
            self.output_box.append("")
            self.output_box.append("Starting background worker...\n")

            self._set_route_result(selected_agent, final_backend, final_model)

            self.send_btn.setEnabled(False)
            self.stop_chat_btn.setEnabled(True)

            self.start_chat_timer(final_backend, final_model, full_prompt)

            self.active_run_id = self.run_logger.start(
                agent=selected_agent,
                tool=selected_tool,
                provider=final_backend,
                model=final_model,
                mode=self.execution_mode_box.currentText() if hasattr(self, "execution_mode_box") else "",
                prompt_summary=full_prompt,
            )

            self.chat_worker = self._new_chat_worker(final_backend, final_model, messages, full_prompt)
            self.pending_messages = self.chat_worker.messages
            self.chat_worker.status_signal.connect(self.handle_chat_status)
            self.chat_worker.token_signal.connect(self.handle_chat_token)
            self.chat_worker.finished_signal.connect(self.handle_chat_finished)
            self.chat_worker.usage_signal.connect(self.handle_chat_usage)
            self.chat_worker.error_signal.connect(self.handle_chat_error)
            self.chat_worker.start()

        except Exception as e:
            QMessageBox.warning(self, "Request failed", str(e))

    def confirm_external_api_request(self, backend, model, estimated_cost, approx_tokens):
        if backend == "ollama":
            return True

        message = (
            f"This request will use an external API.\n\n"
            f"Provider: {backend}\n"
            f"Model: {model}\n"
            f"Approx tokens: {approx_tokens}\n"
            f"Estimated cost/quota impact: ~€{estimated_cost:.2f}\n\n"
            f"Continue?"
        )

        result = QMessageBox.question(
            self,
            "Confirm External API Request",
            message,
            QMessageBox.Yes | QMessageBox.No,
        )

        return result == QMessageBox.Yes

    # ── Shared request guard (TODO.md #1) ───────────────────────────────
    # Any agent that can spend money must go through these. Only send_prompt()
    # used to, so the budget caps, the spend counters, the paid-API prompt and
    # Saved Chats all silently ignored every other agent.

    def _note_failure(self, context, exc, widget=None):
        """Record a swallowed exception instead of discarding it.

        These paths deliberately must not raise into the UI, but a bare
        `except: pass` made a failed model listing or history load look exactly
        like "there is nothing here". stderr is captured by the app launcher in
        /tmp/sentinelai_launch.log; when a widget is given, the reason is also
        attached to it as a tooltip so it is visible without reading a log.
        """
        message = f"{context}: {type(exc).__name__}: {exc}"
        print(f"[warn] {message}", file=sys.stderr)
        if widget is not None:
            try:
                widget.setToolTip(f"Last error — {message}")
            except Exception:
                pass

    def current_api_permissions(self) -> dict:
        """The provider checkboxes, as the validator expects them."""
        return {
            "allow_openai": self.allow_openai_checkbox.isChecked(),
            "allow_deepseek": self.allow_deepseek_checkbox.isChecked(),
            "allow_kimi": self.allow_kimi_checkbox.isChecked(),
            "allow_gemini": self.allow_gemini_checkbox.isChecked(),
            "allow_anthropic": self.allow_anthropic_checkbox.isChecked(),
            "allow_qwen": self.allow_qwen_checkbox.isChecked(),
            "allow_higgsfield": self.allow_higgsfield_checkbox.isChecked(),
            "allow_elevenlabs": self.allow_elevenlabs_checkbox.isChecked(),
        }

    def _project_budget_fields(self) -> dict:
        project = self._active_project()
        if not project or project["budget_eur"] is None:
            return {}
        return {
            "project_name": project["name"],
            "project_cost": self.usage_tracker.get_project_today_total(project["id"]),
            "project_budget": float(project["budget_eur"]),
        }

    def authorize_request(self, agent, provider, model, prompt, tool=None,
                          label=None, flat_cost_eur=None) -> bool:
        """Budget-check and confirm one request. False means: do not send it.

        `tool` is a registry tool name and is validated as one — pass it only
        when the request really runs a registered tool (the chat panel does).
        The agent panels pick their own mode ("Person", "Deep Scan", …), which
        is not a registry entry: pass that as `label` instead, so it still shows
        up in the run log and Saved Chats without failing the tool check.

        On success the context record_request() needs is stashed under a fresh
        request token, which is returned. Callers must keep the token and
        resolve with it: agent-name resolution (oldest outstanding request)
        survives only as a migration shim for single-flight panels, and it
        mis-resolves the moment two flows share an agent key — "video" is
        the Video tab and Social clips, "creator" is drafting and the
        teaser. Every flow in this file keeps its token now; do not add a
        new by-name call site.
        """
        # `flat_cost_eur` is for work billed per unit rather than per token —
        # an image, a video render, a minute of speech. Without it the guard
        # prices those at zero and they slip past the caps entirely.
        if flat_cost_eur is not None:
            estimated_cost, approx_tokens = float(flat_cost_eur), 0
        else:
            estimated_cost, approx_tokens = self.estimate_chat_cost(provider, model, prompt)

        # Count what is already authorized but not yet recorded: without it,
        # two concurrent requests could each be validated against the full
        # remaining budget and together sail past the caps.
        reserved = self._reserved_in_flight_eur()
        validation = self.validator.validate(
            agent_name=agent,
            tool_name=tool,
            provider=provider,
            api_permissions=self.current_api_permissions(),
            session_cost=self.session_cost_total + reserved,
            session_budget=self.session_budget_eur,
            daily_cost=self.usage_tracker.get_today_total() + reserved,
            daily_budget=self.daily_budget_eur,
            estimated_cost=estimated_cost,
            agent_daily_cost=self.usage_tracker.get_agent_today_total(agent),
            **self._project_budget_fields(),
        )
        if not validation.allowed:
            QMessageBox.warning(self, "Request Blocked", validation.reason)
            return False

        if not self.confirm_external_api_request(provider, model, estimated_cost, approx_tokens):
            return False

        descriptor = label or tool or "-"
        # Own token rather than the run id: run_logger.start() may return an
        # empty value, and the success signal must stay truthy.
        token = uuid.uuid4().hex
        self._pending_requests[token] = {
            "agent": agent,
            "tool": descriptor,
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "usage": None,
            "flat_cost_eur": flat_cost_eur,
            # The validated estimate, so open requests reserve their cost
            # against the caps until they are recorded or abandoned.
            "estimated_cost": estimated_cost,
            "project": (self._active_project() or {}).get("id"),
            "project_instructions": (self._active_project() or {}).get("instructions", ""),
            "run_id": self.run_logger.start(
                agent=agent,
                tool=descriptor,
                provider=provider,
                model=model,
                mode=self.execution_mode_box.currentText() if hasattr(self, "execution_mode_box") else "",
                prompt_summary=prompt,
            ),
        }
        self._pending_by_agent.setdefault(agent, []).append(token)
        return token

    def _reserved_in_flight_eur(self) -> float:
        """Estimates of every authorized-but-unresolved request."""
        return sum(float(ctx.get("estimated_cost") or 0.0)
                   for ctx in self._pending_requests.values())

    def _resolve_request(self, handle, pop=False):
        """Find one in-flight request from a token or an agent name.

        An agent name resolves to that agent's oldest outstanding request, which
        is the right one for the single-flight panels: they authorise, run, then
        record before starting again.
        """
        token = handle if handle in self._pending_requests else None
        if token is None:
            queue = self._pending_by_agent.get(handle) or []
            token = queue[0] if queue else None
        if token is None:
            return None
        context = self._pending_requests[token]
        if pop:
            del self._pending_requests[token]
            queue = self._pending_by_agent.get(context["agent"])
            if queue and token in queue:
                queue.remove(token)
                if not queue:
                    del self._pending_by_agent[context["agent"]]
        return context

    def note_request_usage(self, agent, usage):
        """Real token counts from the worker, when it reports them."""
        context = self._resolve_request(agent)
        if context is not None:
            context["usage"] = usage

    def record_request(self, agent, response, messages=None):
        """Bill, save and close out a request authorised by authorize_request()."""
        context = self._resolve_request(agent, pop=True)
        if context is None:          # never authorised (or already recorded)
            return

        entry = self.usage_tracker.log_request(
            agent=context["agent"],
            backend=context["provider"],
            model=context["model"],
            prompt_text=context["prompt"] + "\n" + context.get("project_instructions", ""),
            response_text=response,
            usage=context["usage"],
            flat_cost_eur=context.get("flat_cost_eur"),
            project=context.get("project"),
        )

        self.last_request_cost = entry.get("cost_eur", entry.get("estimated_cost", 0.0))
        self.last_tool_name = f"{context['agent']}/{context['tool']} - {context['provider']}"
        self.session_cost_total += entry.get("estimated_cost", 0.0)
        self.session_request_count += 1
        self.update_usage_labels()

        if messages is None:
            messages = [{"role": "user", "content": context["prompt"]}]
        self.history.save_chat(
            agent=context["agent"],
            backend=context["provider"],
            model=context["model"],
            command=context["tool"],
            messages=messages + [{"role": "assistant", "content": response}],
            response=response,
            project=context.get("project"),
            tool=context["tool"],
        )

        if context["run_id"]:
            self.run_logger.finish(
                run_id=context["run_id"],
                status="success",
                input_tokens=entry.get("input_tokens", 0),
                output_tokens=entry.get("output_tokens", 0),
                cost_eur=entry.get("cost_eur", 0.0),
            )

        self.load_history_list()

    def abandon_request(self, agent, reason="error"):
        """Drop a request that failed, so it is not billed and the log closes."""
        context = self._resolve_request(agent, pop=True)
        if context and context["run_id"]:
            self.run_logger.finish(run_id=context["run_id"], status=reason)

    def run_backend(self, backend, model, messages, prompt):
        if backend == "ollama":
            # Runs on the worker thread, so this cannot prompt — it is the hard
            # floor only. Every agent funnels through here, so a model that
            # physically cannot fit is stopped once, for all of them, and the
            # message surfaces via each agent's existing error path instead of
            # freezing the machine for the full request timeout.
            verdict = self.assess_local_model(model)
            if verdict is not None and verdict["level"] == "too_big":
                raise RuntimeError(verdict["message"])

            if hasattr(self.ollama, "chat"):
                return self.ollama.chat(model=model, messages=messages)
            if hasattr(self.ollama, "generate"):
                return self.ollama.generate(model=model, prompt=prompt)

        if backend == "openai":
            if hasattr(self.openai, "stream_chat"):
                return self.openai.stream_chat(messages=messages, model=model)
            if hasattr(self.openai, "chat"):
                return self.openai.chat(messages=messages, model=model)
            if hasattr(self.openai, "generate"):
                return self.openai.generate(prompt, model=model)

        if backend == "deepseek":
            if hasattr(self.deepseek, "stream_chat"):
                return self.deepseek.stream_chat(messages=messages, model=model)
            if hasattr(self.deepseek, "chat"):
                return self.deepseek.chat(messages=messages, model=model)
            if hasattr(self.deepseek, "generate"):
                return self.deepseek.generate(prompt, model=model)

        if backend == "kimi":
            if hasattr(self.kimi, "stream_chat"):
                return self.kimi.stream_chat(messages=messages, model=model)
            if hasattr(self.kimi, "chat"):
                return self.kimi.chat(messages=messages, model=model)
            if hasattr(self.kimi, "generate"):
                return self.kimi.generate(prompt, model=model)

        if backend == "qwen":
            if hasattr(self.qwen, "stream_chat"):
                return self.qwen.stream_chat(messages=messages, model=model)
            if hasattr(self.qwen, "chat"):
                return self.qwen.chat(messages=messages, model=model)
            if hasattr(self.qwen, "generate"):
                return self.qwen.generate(prompt, model=model)

        if backend == "gemini":
            if hasattr(self.gemini, "stream_chat"):
                return self.gemini.stream_chat(messages=messages, model=model)

            if hasattr(self.gemini, "chat"):
                return self.gemini.chat(messages=messages, model=model)

            if hasattr(self.gemini, "generate"):
                return self.gemini.generate(prompt, model=model)

        if backend == "anthropic":
            if hasattr(self.anthropic, "stream_chat"):
                return self.anthropic.stream_chat(messages=messages, model=model)

            if hasattr(self.anthropic, "chat"):
                return self.anthropic.chat(messages=messages, model=model)

        raise RuntimeError(f"No compatible backend method found for backend: {backend}")

    def start_chat_timer(self, backend: str, model: str, prompt: str):
        self.chat_started_at = time.time()
        self.chat_elapsed_seconds = 0
        self.chat_estimated_seconds = self.estimate_chat_seconds(backend, model, prompt)
        self.chat_progress.setMinimum(0)
        self.chat_progress.setMaximum(0)
        self.chat_progress.show()
        self.chat_status_label.show()
        if not hasattr(self, "chat_timer"):
            self.chat_timer = QTimer(self)
            self.chat_timer.timeout.connect(self.update_chat_timer)
        self.chat_timer.start(1000)
        self.update_chat_timer()

    def update_chat_timer(self):
        elapsed = int(time.time() - self.chat_started_at) if self.chat_started_at else self.chat_elapsed_seconds
        remaining = max(0, self.chat_estimated_seconds - elapsed)
        self.chat_status_label.setText(
            f"Processing... elapsed {self.format_seconds(elapsed)} · rough remaining {self.format_seconds(remaining)}"
        )

    def stop_chat_timer(self):
        if hasattr(self, "chat_timer"):
            self.chat_timer.stop()
        self.chat_progress.hide()

    def handle_chat_status(self, text):
        self.output_box.moveCursor(QTextCursor.End)
        self.output_box.insertPlainText(text + "\n")
        self.output_box.ensureCursorVisible()

    def handle_chat_token(self, text):
        self.output_box.moveCursor(QTextCursor.End)
        self.output_box.insertPlainText(text)
        self.output_box.ensureCursorVisible()

    def handle_chat_finished(self, response):
        self.stop_chat_timer()
        self.send_btn.setEnabled(True)
        self.stop_chat_btn.setEnabled(False)

        self.current_messages = self.pending_messages + [{"role": "assistant", "content": response}]
        self.current_chat_agent = self.pending_agent
        self.current_chat_tool = self.pending_tool
        self.current_chat_project = getattr(self, "pending_project", None)
        self.output_box.append("\n\n[Finished]")

        usage_entry = self.usage_tracker.log_request(
            agent=self.pending_agent,
            backend=self.pending_backend,
            model=self.pending_model,
            prompt_text=getattr(self, "pending_billing_prompt", self.pending_prompt)
                        + "\n" + getattr(self, "pending_project_instructions", ""),
            response_text=response,
            usage=self.pending_usage,
            project=getattr(self, "pending_project", None),
        )

        self.last_request_cost = usage_entry.get("cost_eur", usage_entry.get("estimated_cost", 0.0))
        tool = getattr(self, "pending_tool", "General Chat")
        self.last_tool_name = f"{self.pending_agent}/{tool} - {self.pending_backend}"
        self.session_cost_total += usage_entry["estimated_cost"]
        self.session_request_count += 1
        self.update_usage_labels()

        run_id = getattr(self, "active_run_id", None)
        if run_id:
            self.run_logger.finish(
                run_id=run_id,
                status="success",
                input_tokens=usage_entry.get("input_tokens", 0),
                output_tokens=usage_entry.get("output_tokens", 0),
                cost_eur=usage_entry.get("cost_eur", 0.0),
            )
            self.active_run_id = None

        self.history.save_chat(
            agent=self.pending_agent,
            backend=self.pending_backend,
            model=self.pending_model,
            command=self.pending_command,
            messages=self.current_messages,
            response=response,
            project=getattr(self, "pending_project", None),
            tool=tool,
        )

        self.load_history_list()
        self._set_route_result(
            self.pending_agent, self.pending_backend, self.pending_model)

    def handle_chat_error(self, error):
        self.stop_chat_timer()
        self.output_box.append(f"\n[Error]\n{error}")
        self.send_btn.setEnabled(True)
        self.stop_chat_btn.setEnabled(False)

        run_id = getattr(self, "active_run_id", None)
        if run_id:
            self.run_logger.finish(run_id=run_id, status="error", error=error)
            self.active_run_id = None
        
    def handle_chat_usage(self, usage):
        self.pending_usage = usage

    def stop_chat_worker(self):
        # cancel() only — terminate() on a QThread inside a Python call is a
        # crash/deadlock class. The worker now routes a cancel to its error
        # signal from every path, so nothing is billed or saved for it.
        if self.chat_worker is not None and self.chat_worker.isRunning():
            self.chat_worker.cancel()
            self.output_box.append("\n[Stopped] Chat request stopped by user.")
        self.stop_chat_timer()
        self.send_btn.setEnabled(True)
        self.stop_chat_btn.setEnabled(False)

        run_id = getattr(self, "active_run_id", None)
        if run_id:
            self.run_logger.cancel(run_id)
            self.active_run_id = None

    def stop_current_task(self):
        if self.chat_worker is not None and self.chat_worker.isRunning():
            self.stop_chat_worker()
            return

        if self.author_worker is not None and self.author_worker.isRunning():
            self.author_stop()
            return

        if self.author_pub_worker is not None and self.author_pub_worker.isRunning():
            self.author_pub_stop()
            return

        if self.author_mkt_worker is not None and self.author_mkt_worker.isRunning():
            self.author_mkt_stop()
            return

        if self.music_worker is not None and self.music_worker.isRunning():
            self.music_panel.stop()
            return

        if self.webdesign_worker is not None and self.webdesign_worker.isRunning():
            self.webdesign_panel.stop()
            return

        if self.fiverr_image_worker is not None and self.fiverr_image_worker.isRunning():
            self.fiverr_stop()
            return

        if self.fiverr_text_worker is not None and self.fiverr_text_worker.isRunning():
            self.fiverr_stop()
            return

        self.audiobook_panel.stop_conversion()

    def update_resource_label(self):
        stats = self.monitor.snapshot()
        if hasattr(self, "resource_status_card"):
            self.resource_status_card.set_snapshot(stats)
            return

        # Compatibility for lightweight hosts that still expose the old label.
        self.resource_label.setText(
            f"Memory {stats['ram_percent']:.0f}% · "
            f"Processor {stats['cpu_percent']:.0f}% · "
            f"Swap {stats['swap_percent']:.0f}%")

    def update_usage_labels(self):
        """Push spend into the stat blocks and the two budget bars."""
        if not hasattr(self, "session_cost_stat"):
            return
        today_total = self.usage_tracker.get_today_total()
        today_requests = self.usage_tracker.get_total_requests_today()
        tool_name = getattr(self, "last_tool_name", "") or "-"

        self.session_cost_stat.set_value(f"€{self.session_cost_total:.2f}")
        self.today_cost_stat.set_value(f"€{today_total:.2f}")
        self.request_count_stat.set_value(str(today_requests))
        # Detail goes in the tooltip. A caption that grows with its data clips
        # the stat sitting next to it, which is how the rail got ragged.
        self.request_count_stat.setToolTip(
            f"{today_requests} today · {self.session_request_count} this session")

        self.last_request_stat.set_value(f"€{self.last_request_cost:.2f}")
        self.last_request_stat.setToolTip(f"Last request ran: {tool_name}")

        # The bars show spend against the cap. Remaining is the gap, which is
        # the thing you were subtracting for by hand before.
        self.session_meter.set(self.session_cost_total, self.session_budget_eur)
        self.daily_meter.set(today_total, self.daily_budget_eur)
        project = self._active_project()
        if project and project["budget_eur"] is not None:
            self.project_meter.set(
                self.usage_tracker.get_project_today_total(project["id"]),
                float(project["budget_eur"]),
            )
            self.project_meter.show()
        else:
            self.project_meter.hide()

    def start_resource_timer(self):
        self.resource_timer = QTimer(self)
        self.resource_timer.timeout.connect(self.update_resource_label)
        self.resource_timer.start(1000)

    def chat_title_from_data(self, path: Path, data: Optional[dict] = None) -> str:
        try:
            if data is None:
                data = self.history.load_chat(str(path))
            if data.get("title"):
                return data["title"]

            agent = data.get("agent", "chat")
            first_user = ""
            for msg in data.get("messages", []):
                if msg.get("role") == "user":
                    first_user = msg.get("content", "")
                    break

            clean = re.sub(r"\s+", " ", first_user).strip()
            if not clean:
                clean = path.stem
            return f"{agent}: {clean[:52].rstrip()}"
        except Exception:
            return path.stem

    def load_history_list(self):
        """Fill the Saved Chats list, honouring the search box and agent filter.

        Every file is read once here and reused for both the filter options and
        the rows, so adding the filter costs no extra disk reads.
        """
        self.history_list.clear()
        query = self.history_search.text().strip().lower() if hasattr(self, "history_search") else ""
        try:
            loaded = []
            for file in sorted(CHATS_DIR.glob("*.json"), reverse=True):
                try:
                    data = self.history.load_chat(str(file))
                except Exception:
                    data = {}
                loaded.append((file, data))

            self._refresh_history_project_filter()
            self._refresh_history_agent_filter(loaded)
            wanted = (self.history_agent_filter.currentText()
                      if hasattr(self, "history_agent_filter") else ALL_AGENTS_FILTER)
            project_filter = (self.history_project_filter.currentData()
                              if hasattr(self, "history_project_filter") else ALL_PROJECTS_FILTER)
            known_projects = {p["id"] for p in self.registry.list_projects()}

            for file, data in loaded:
                if wanted != ALL_AGENTS_FILTER and data.get("agent", "chat") != wanted:
                    continue
                chat_project = data.get("project") or ""
                if chat_project not in known_projects:
                    chat_project = ""
                if project_filter == UNFILED_PROJECTS_FILTER and chat_project:
                    continue
                if project_filter not in (ALL_PROJECTS_FILTER, UNFILED_PROJECTS_FILTER) \
                        and chat_project != project_filter:
                    continue
                title = self.chat_title_from_data(file, data)
                if query and query not in title.lower():
                    continue
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, str(file))
                self.history_list.addItem(item)
        except Exception as exc:
            self._note_failure("saved chats: load list", exc)

    def _refresh_history_project_filter(self):
        if not hasattr(self, "history_project_filter"):
            return
        combo = self.history_project_filter
        projects = self.registry.list_projects()
        options = [("All projects", ALL_PROJECTS_FILTER),
                   ("Unfiled", UNFILED_PROJECTS_FILTER)]
        options.extend((p["name"], p["id"]) for p in projects)
        existing = [(combo.itemText(i), combo.itemData(i))
                    for i in range(combo.count())]
        if existing == options:
            return
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for name, project_id in options:
            combo.addItem(name, project_id)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _active_project(self) -> dict | None:
        combo = getattr(self, "history_project_filter", None)
        project_id = combo.currentData() if combo is not None else None
        if not project_id or project_id in (ALL_PROJECTS_FILTER, UNFILED_PROJECTS_FILTER):
            return None
        project = self.registry.get_project(project_id)
        return project if project and not project["archived"] else None

    def _switch_project(self, _index=0):
        project = self._active_project()
        if hasattr(self, "project_context_pill"):
            self.project_context_pill.setVisible(bool(project))
            if project:
                self.project_context_pill.setText(
                    self.project_context_pill.fontMetrics().elidedText(
                        f"Project: {project['name']}", Qt.ElideRight, 135
                    )
                )
                self.project_context_pill.setToolTip(
                    f"Active context: {project['name']}"
                )
        if hasattr(self, "active_project_label"):
            self.active_project_label.setText(
                f"Working in {project['name']}" if project else "No project context"
            )
        if hasattr(self, "project_defaults_btn"):
            self.project_defaults_btn.setEnabled(bool(project))
        self.load_history_list()
        if hasattr(self, "update_usage_labels"):
            self.update_usage_labels()
        if hasattr(self, "update_live_cost_estimate"):
            self.update_live_cost_estimate()
        if project:
            self._apply_project_defaults(project)

    def _apply_project_defaults(self, project: dict):
        """Apply defaults only on a project switch, never during normal edits."""
        agent = project.get("default_agent") or ""
        if agent and self.agent_box.findText(agent) >= 0:
            self.select_agent(agent)
        widgets = AGENT_SETUP_WIDGETS.get(agent)
        if not widgets:
            return
        provider_box = getattr(self, widgets[0], None)
        model_box = getattr(self, widgets[1], None)
        provider = project.get("default_provider") or ""
        model = project.get("default_model") or ""
        if provider_box is not None and provider:
            index = provider_box.findText(provider)
            if index >= 0:
                provider_box.setCurrentIndex(index)
        if model_box is not None and model:
            index = model_box.findText(model)
            if index >= 0:
                model_box.setCurrentIndex(index)

    def save_project_defaults(self):
        project = self._active_project()
        if not project:
            return
        agent = self.agent_box.currentText()
        widgets = AGENT_SETUP_WIDGETS.get(agent)
        provider = getattr(self, widgets[0]).currentText() if widgets else ""
        model = getattr(self, widgets[1]).currentText() if widgets else ""
        self.registry.upsert_project(
            project["id"], project["name"],
            instructions=project["instructions"], default_agent=agent,
            default_provider=provider, default_model=model,
            budget_eur=project["budget_eur"],
        )
        self.active_project_label.setText(
            f"Working in {project['name']} · defaults saved"
        )

    def create_project(self):
        name, accepted = QInputDialog.getText(self, "New Project", "Project name:")
        name = name.strip()
        if not accepted or not name:
            return
        project_id = uuid.uuid4().hex[:12]
        self.registry.upsert_project(project_id, name)
        self._refresh_history_project_filter()
        self.history_project_filter.setCurrentIndex(
            self.history_project_filter.findData(project_id)
        )
        self.new_chat()

    def _chat_context_menu(self, point):
        item = self.history_list.itemAt(point)
        if item is None:
            return
        menu = QMenu(self.history_list)
        rename = menu.addAction("Rename chat")
        assign = menu.addMenu("Assign to project")
        actions = {}
        actions[assign.addAction("Unfiled")] = ""
        for project in self.registry.list_projects():
            actions[assign.addAction(project["name"])] = project["id"]
        chosen = menu.exec(self.history_list.mapToGlobal(point))
        if chosen == rename:
            self.rename_selected_chat(item)
        elif chosen in actions:
            self.assign_chat_to_project(item, actions[chosen])

    def assign_chat_to_project(self, item, project_id: str):
        path = item.data(Qt.UserRole)
        try:
            data = self.history.load_chat(path)
            if project_id:
                data["project"] = project_id
            else:
                data.pop("project", None)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            self.load_history_list()
        except Exception as exc:
            self._note_failure("saved chats: assign project", exc)

    def _refresh_history_agent_filter(self, loaded):
        """Keep the filter's options in step with the chats that exist.

        Signals are blocked while repopulating: the combo's own change signal
        calls back into load_history_list, which would recurse.
        """
        if not hasattr(self, "history_agent_filter"):
            return
        agents = sorted({data.get("agent", "chat") for _f, data in loaded})
        options = [ALL_AGENTS_FILTER] + agents
        current = self.history_agent_filter.currentText()
        if options == [self.history_agent_filter.itemText(i)
                       for i in range(self.history_agent_filter.count())]:
            return                                   # nothing changed
        self.history_agent_filter.blockSignals(True)
        self.history_agent_filter.clear()
        self.history_agent_filter.addItems(options)
        # keep the user's selection when its agent still has chats
        self.history_agent_filter.setCurrentText(
            current if current in options else ALL_AGENTS_FILTER
        )
        self.history_agent_filter.blockSignals(False)

    def rename_selected_chat(self, item):
        """Give a saved chat a name of your own instead of its first prompt."""
        path = item.data(Qt.UserRole) or item.text()
        try:
            data = self.history.load_chat(path)
        except Exception as exc:
            self._note_failure("saved chats: open for rename", exc)
            return

        current = data.get("title", "")
        new_title, ok = QInputDialog.getText(
            self, "Rename Chat", "Name for this chat:", text=current
        )
        if not ok:
            return

        new_title = new_title.strip()
        if new_title:
            data["title"] = new_title
        else:
            data.pop("title", None)      # cleared — fall back to the first prompt
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            self._note_failure("saved chats: save new name", exc)
            return
        self.load_history_list()

    def open_selected_chat(self, item):
        filepath = item.data(Qt.UserRole) or item.text()
        try:
            data = self.history.load_chat(filepath)
            project_id = data.get("project") or UNFILED_PROJECTS_FILTER
            index = self.history_project_filter.findData(project_id)
            self.history_project_filter.setCurrentIndex(index if index >= 0 else 1)
            self.show_output_area()
            turns = conversation_turns(data.get("messages", []), data.get("response", ""))
            self.current_messages = turns
            self.output_box.setPlainText("\n\n".join(
                f"{'You' if turn['role'] == 'user' else 'Assistant'}\n"
                f"{turn.get('content') or ''}" for turn in turns
            ))
            self.input_box.clear()
            self.input_box.setPlaceholderText("Type a follow-up to this saved chat...")
            self._set_route_result(
                data.get("agent", ""), data.get("backend", ""),
                data.get("model", ""))

            agent_name = data.get("agent", "chat")
            if self.agent_box.findText(agent_name) >= 0:
                self.select_agent(agent_name)
            tool_name = data.get("tool") or data.get("command") or ""
            if self.tool_box.findText(tool_name) >= 0:
                self.tool_box.setCurrentText(tool_name)
            self.current_chat_agent = agent_name
            self.current_chat_tool = self.tool_box.currentText()
            project = self._active_project()
            self.current_chat_project = project["id"] if project else None
            self.update_live_cost_estimate()

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open saved chat:\n{e}")

    def delete_selected_chat(self):
        item = self.history_list.currentItem()
        if not item:
            QMessageBox.information(self, "No Selection", "Select a saved chat first.")
            return

        filepath = item.data(Qt.UserRole)
        confirm = QMessageBox.question(self, "Delete Chat", f"Delete saved chat?\n\n{item.text()}")
        if confirm != QMessageBox.Yes:
            return

        try:
            Path(filepath).unlink(missing_ok=True)
            self.load_history_list()
        except Exception as e:
            QMessageBox.warning(self, "Delete Failed", str(e))

    def new_chat(self):
        self.current_messages = []
        self.current_chat_agent = ""
        self.current_chat_tool = ""
        self.current_chat_project = None
        self.input_box.clear()
        self.input_box.setPlaceholderText("Type your message here...")
        self.output_box.clear()
        self.hide_output_area()
        self._set_route_result()

    def export_report(self):
        content = self.output_box.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Warning", "No output to export.")
            return
        title = self.agent_box.currentText() + "_report"
        filepath = self.report_exporter.export_text_report(title, content)
        QMessageBox.information(self, "Export Complete", f"Report saved to:\n{filepath}")

    def _show_agent_docs_legacy(self):
        """Legacy single-article renderer retained for bundle recovery only."""
        agent_name = getattr(self, "_current_agent", "chat")

        # Map agent key → doc filename (same as the key for most)
        doc_file_map = {
            "chat": "chat", "fiverr": "fiverr", "creator": "creator",
            "author": "author", "music": "music",
            "webdesign": "webdesign", "audiobook": "audiobook",
            "manuscript": "manuscript",
        }
        doc_key = doc_file_map.get(agent_name, agent_name)

        # The detailed user guide remains the first choice.  Every agent also
        # owns a package README, which is the architecture-level fallback and
        # keeps Docs useful for newly added agent projects before a full guide
        # is written.
        docs_dir = RESOURCE_DIR / "docs" / "agents"
        doc_path = docs_dir / f"{doc_key}.md"
        project_doc_path = RESOURCE_DIR / "agents" / agent_name / "README.md"

        # Read the markdown source
        if doc_path.exists():
            raw_md = doc_path.read_text(encoding="utf-8")
        elif project_doc_path.exists():
            raw_md = project_doc_path.read_text(encoding="utf-8")
        else:
            raw_md = (
                "# No documentation found\n\n"
                f"No documentation file was found for **{agent_name}**.\n\n"
                f"Expected either `{doc_path}` or `{project_doc_path}`"
            )

        # Convert markdown to basic HTML (handles headings, bold, tables, code, lists)
        def md_to_html(text: str) -> str:
            import re
            lines = text.split("\n")
            html_lines = []
            in_table = False
            in_code = False
            i = 0
            while i < len(lines):
                line = lines[i]
                # Code block
                if line.startswith("```"):
                    if not in_code:
                        html_lines.append('<pre style="background:#1e1e1e;color:#d4d4d4;padding:10px;border-radius:6px;font-size:12px;overflow:auto;">')
                        in_code = True
                    else:
                        html_lines.append("</pre>")
                        in_code = False
                    i += 1
                    continue
                if in_code:
                    html_lines.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
                    i += 1
                    continue
                # Table row
                if line.startswith("|"):
                    if not in_table:
                        html_lines.append('<table style="border-collapse:collapse;width:100%;margin:8px 0;">')
                        in_table = True
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    # Skip separator row
                    if all(re.match(r"^[-:]+$", c) for c in cells):
                        i += 1
                        continue
                    is_header = (i == 0 or not lines[i-1].startswith("|")) and \
                                i + 1 < len(lines) and re.match(r"^\|[-| :]+\|$", lines[i+1]) if i+1 < len(lines) else False
                    tag = "th" if is_header else "td"
                    row_html = "".join(
                        f'<{tag} style="border:1px solid #333;padding:6px 10px;text-align:left;">{c}</{tag}>'
                        for c in cells
                    )
                    html_lines.append(f"<tr>{row_html}</tr>")
                    i += 1
                    continue
                else:
                    if in_table:
                        html_lines.append("</table>")
                        in_table = False
                # Headings
                if line.startswith("#### "):
                    html_lines.append(f'<h4 style="color:#e8e8e8;margin:10px 0 4px;">{line[5:]}</h4>')
                elif line.startswith("### "):
                    html_lines.append(f'<h3 style="color:{ACCENT};margin:14px 0 6px;">{line[4:]}</h3>')
                elif line.startswith("## "):
                    html_lines.append(f'<h2 style="color:#ffffff;border-bottom:1px solid #333;padding-bottom:4px;margin:18px 0 8px;">{line[3:]}</h2>')
                elif line.startswith("# "):
                    html_lines.append(f'<h1 style="color:{ACCENT};font-size:20px;margin:0 0 4px;">{line[2:]}</h1>')
                # Blockquote / warning
                elif line.startswith("> "):
                    html_lines.append(f'<blockquote style="border-left:3px solid #f0a000;padding:6px 12px;margin:6px 0;background:#1e1a00;color:#f0c050;">{line[2:]}</blockquote>')
                # Unordered list
                elif line.startswith("- ") or line.startswith("* "):
                    html_lines.append(f'<li style="margin:2px 0;">{line[2:]}</li>')
                # Horizontal rule
                elif line.startswith("---"):
                    html_lines.append('<hr style="border:none;border-top:1px solid #333;margin:12px 0;">')
                # Blank line
                elif line.strip() == "":
                    html_lines.append("<br>")
                # Normal paragraph
                else:
                    html_lines.append(f"<p style='margin:3px 0;'>{line}</p>")
                i += 1
            if in_table:
                html_lines.append("</table>")
            if in_code:
                html_lines.append("</pre>")
            html = "\n".join(html_lines)
            # Inline: **bold**, `code`, *italic*
            html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
            html = re.sub(r"`([^`]+)`", r'<code style="background:#2a2a2a;padding:1px 5px;border-radius:3px;font-size:12px;">\1</code>', html)
            html = re.sub(r"\*(.+?)\*", r"<i>\1</i>", html)
            return html

        html_content = md_to_html(raw_md)
        full_html = f"""
        <html><body style="background:#111111;color:#cccccc;font-family:sans-serif;font-size:13px;padding:4px 8px;">
        {html_content}
        </body></html>
        """

        # Build dialog
        agent_titles = {
            "chat": "CHAT", "fiverr": "ATELIER", "creator": "CREATOR",
            "author": "MANUSCRIPT", "manuscript": "PUBLISHER",
            "music": "MAESTRO", "webdesign": "SITE BUILDER", "audiobook": "NARRATOR", }
        title = agent_titles.get(agent_name, agent_name.upper())

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Docs — {title}")
        dialog.resize(760, 620)
        dialog.setStyleSheet("background-color: #111111;")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        browser = QTextBrowser()
        browser.setHtml(full_html)
        browser.setStyleSheet(
            "QTextBrowser { background: #111111; color: #cccccc; border: none; }"
            "QScrollBar:vertical { background: #1a1a1a; width: 10px; }"
            "QScrollBar::handle:vertical { background: #333333; border-radius: 5px; }"
        )
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("ChipBtn")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setFixedWidth(100)
        layout.addWidget(close_btn, 0, Qt.AlignRight)

        dialog.exec()
        # Freed when this frame's reference drops — parented, it would sit
        # on the window's child list forever (one leak per open).
        dialog.setParent(None)

    def show_agent_docs(self):
        """Open the searchable reference at the currently active agent."""
        from ui.docs_center import show_docs_center
        agent = getattr(self, "_current_agent", "overview")
        return show_docs_center(self, RESOURCE_DIR, start_page=agent)

    def show_model_guide(self):
        from ui.dialogs import show_model_guide as _show_model_guide
        return _show_model_guide(self)
    def show_learning_center(self):
        """Open the operating lesson for the active agent (F1 does the same)."""
        from ui.learning_center import (
            learning_target_for_widget, show_learning_center as _show,
        )
        contextual = learning_target_for_widget(QApplication.focusWidget())
        agent = getattr(self, "_current_agent", "")
        start_page = {
            "author": "draft", "manuscript": "publish",
            "audiobook": "audiobooks", "music": "music",
            "video": "video", "social": "social",
            "webdesign": "site-builder", "fiverr": "client-gigs",
            "creator": "creator", "onlyfans": "onlyfans",
        }.get(agent)
        start_anchor = ""
        if contextual:
            start_page, start_anchor = contextual
        return _show(
            self, RESOURCE_DIR, start_page=start_page,
            start_anchor=start_anchor)

    def show_docs(self, anchor: str = ""):
        """Open the complete searchable technical reference."""
        from ui.docs_center import show_docs_center
        return show_docs_center(
            self, RESOURCE_DIR, start_page="overview", start_anchor=anchor)

    def closeEvent(self, event):
        try:
            audiobook_process = self.audiobook_panel.process
            if (audiobook_process is not None and
                    audiobook_process.state() != QProcess.NotRunning):
                audiobook_process.kill()
            # Every worker, not just chat: quitting mid-run used to leave the
            # others' QThreads to be destroyed while still running (a Qt
            # abort) and lose the paid request's record. cancel() + a short
            # wait; never terminate() — that is the crash class this file
            # just removed.
            for attr in (
                    "chat_worker", "author_worker", "author_pub_worker",
                    "author_mkt_worker", "manuscript_worker",
                    "quote_finder_worker", "calendar_worker", "shorts_worker",
                    "social_worker", "_social_clip_worker", "creator_worker",
                    "creator_video_estimate_worker", "creator_video_worker",
                    "fiverr_text_worker", "fiverr_image_worker",
                    "video_worker", "video_estimate_worker",
                    "muse_pull_worker"):
                worker = getattr(self, attr, None)
                if worker is not None and worker.isRunning():
                    if hasattr(worker, "cancel"):
                        worker.cancel()
                    worker.wait(2000)
        except Exception as exc:
            self._note_failure("shutdown: stop background work", exc)
        event.accept()

# Must differ from Sentinel AI's key: a shared socket name would make launching
# this app hand focus to Sentinel instead of opening a window.
SINGLE_INSTANCE_KEY = "imprint.single-instance"


def _hand_off_to_running_instance() -> bool:
    """True when another copy is already running — it is asked to come forward.

    A local socket is the reliable signal here: a lock file can be left behind by
    a crash, and the .app launcher spawns a fresh python each time, so the OS
    can't dedupe the launch for us.
    """
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_KEY)
    if not probe.waitForConnected(400):
        return False
    probe.write(b"raise")
    probe.waitForBytesWritten(400)
    probe.disconnectFromServer()
    return True


def _selftest() -> int:
    """Check the things only a packaged run can break.

    Three of the four traps in AGENTS.md are invisible from source — there is
    nothing to inherit, nothing to resolve and no bundle to read from until the
    app is frozen. Video mode adds a fourth: vidforge is a nested sibling
    repository imported at runtime, so PyInstaller's static analysis never sees
    it and only a real bundle proves it shipped.

    Run:  /Applications/Imprint.app/Contents/MacOS/Imprint --selftest
    """
    from pathlib import Path as _Path

    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(label)

    print(f"Imprint self-test  (frozen={is_frozen()})")

    # 1. Writable data directory. A frozen app that writes inside its own
    #    bundle breaks its signature and loses everything on reinstall.
    try:
        data_dir = _Path(BASE_DIR)
        probe = data_dir / ".selftest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        inside_bundle = ".app/Contents/" in str(data_dir)
        check("data directory is writable", True, str(data_dir))
        check("data directory is outside the bundle", not inside_bundle)
    except Exception as exc:
        check("data directory is writable", False, str(exc))

    # 2. Database opens and carries the agents the shell switches between.
    try:
        from services.registry import Registry
        # The normal window initializes/migrates the database in GodAI.__init__.
        # --selftest deliberately never constructs that window, so run the same
        # idempotent initialization here before checking a newly added panel.
        init_db()
        registry = Registry()
        visible_agents = {key for keys in WORKSPACES.values() for key in keys}
        missing = [a for a in visible_agents if not registry.is_agent_enabled(a)]
        check("every panel agent is registered", not missing, ", ".join(missing))
    except Exception as exc:
        check("registry is readable", False, str(exc))

    # 3. vidforge, imported rather than vendored — the whole Video mode.
    try:
        from agents.video import video_studio
        ok = video_studio.available()
        check("vidforge imports", ok,
              "" if ok else video_studio.unavailable_reason().split("\n")[0])
        if ok:
            cfg = video_studio.load_config()
            check("vidforge config loads", bool(cfg.get("video.width")))
            check("vidforge output root is writable",
                  video_studio.output_root().is_dir(),
                  str(video_studio.output_root()))
    except Exception as exc:
        check("vidforge imports", False, f"{type(exc).__name__}: {exc}")

    # 4. Libraries that resolve through entry points or data files silently
    #    no-op once packaged unless they were collected.
    for module in ("yaml", "tiktoken", "PIL"):
        try:
            __import__(module)
            check(f"{module} importable", True)
        except Exception as exc:
            check(f"{module} importable", False, str(exc))

    # 5. Read-only resources that are seeded from the bundle on first run.
    for name in ("agents", "docs/agents", "docs/learn", "config"):
        check(f"bundled resource: {name}", (_Path(RESOURCE_DIR) / name).exists())

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())

    app = QApplication([])

    # Second launch: focus the window that is already open and leave. The exit
    # code has to be 0 — the launcher raises an error dialog on anything else.
    if _hand_off_to_running_instance():
        sys.exit(0)

    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)   # clear a socket left by a crash
    instance_server = QLocalServer()
    instance_server.listen(SINGLE_INSTANCE_KEY)

    window = GodAI()
    # Always open in fullscreen. The three panes need ~1000px before the
    # splitter starts squeezing panels, so a small default window is the state
    # the layout looks worst in.
    window.showFullScreen()

    def _raise_existing_window():
        instance_server.nextPendingConnection()      # drain the pending connection
        window.setWindowState(
            (window.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive
        )
        window.show()
        window.raise_()
        window.activateWindow()

    instance_server.newConnection.connect(_raise_existing_window)

    app.exec()
