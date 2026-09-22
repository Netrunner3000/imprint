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

from services import version as app_version
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
from services.database import init_db, save_setting
from services.registry import Registry
from services.validator import Validator
from services.run_logger import RunLogger

from agents.audiobook import AudiobookConnector, AudiobookPanel
from agents.chat import ChatAgent
from agents.author import AuthorAgent
from agents.manuscript import ManuscriptAgent
from agents.webdesign import WebdesignAgent, WebdesignPanel
from agents.music import MusicAgent, MusicPanel
from agents.fiverr import FiverrAgent, FiverrPanel
from agents.video import VideoPanel
from agents.manuscript import ManuscriptPanel, ShortsWorker
from agents.creator import CreatorPanel
from agents.author import AuthorPanel
from agents.creator import (
    CreatorAgent, ConsentError, PROMO_CHANNELS,
)
from agents.catalog import AGENT_SPECS, workspace_map
from agents.recommendation_profiles import profile_for
from services.recommendations import RecommendationContext, RecommendationEngine
from services.recommendations.catalog import (
    media_candidate, text_candidates,
)


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
from ui.workers import ChatWorker, ModelPullWorker, FiverrImageWorker
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
from agents.social import SocialPanel
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
        self._author_export_done: bool = False
        self.author_pub_worker: Optional[ChatWorker] = None
        self.author_mkt_worker: Optional[ChatWorker] = None
        self.manuscript_worker: Optional[ChatWorker] = None
        self.shorts_worker: Optional[ShortsWorker] = None
        self.quote_finder_worker: Optional[ChatWorker] = None
        self.calendar_worker: Optional[ChatWorker] = None
        self._calendar_slots: list = []
        self.music_worker: Optional[ChatWorker] = None
        self.webdesign_worker: Optional[ChatWorker] = None
        self.fiverr_image_worker: Optional[FiverrImageWorker] = None
        self.fiverr_text_worker: Optional[ChatWorker] = None

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
        # Reconcile provider renders that outlived the previous process —
        # real money may be in flight. One event-loop turn later so the
        # first paint is not blocked by job bookkeeping.
        QTimer.singleShot(0, self.video_panel.resume_pending_jobs)

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
        """Handle the global tooltip policy.

        The author panel's responsive footer moved into AuthorPanel's own
        resizeEvent with the Phase 4 extraction.
        """
        if event.type() == QEvent.ToolTip and not self.tooltips_enabled:
            return True
        return super().eventFilter(obj, event)

    def _find_control(self, name):
        """Resolve a named control on the host or any owned agent panel.

        The panels own their widgets since Phase 4. The temporary host
        aliases are being retired package by package, so shared wiring —
        tooltips, recommendation bindings, context watchers — looks a
        control up here instead of assuming it was mirrored onto the host.
        Host attributes still win while aliases remain."""
        widget = getattr(self, name, None)
        if widget is not None:
            return widget
        for key in CUSTOM_PANELS:
            panel = getattr(self, f"{key}_panel", None)
            if panel is not None:
                widget = getattr(panel, name, None)
                if widget is not None:
                    return widget
        return None

    def _set_tooltips(self, mapping: dict):
        """Helper: apply a {widget_attr_name: text} mapping in one call.
        Silently skips attributes that don't exist yet (panel not built)."""
        for attr, text in mapping.items():
            widget = self._find_control(attr)
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
            bar = self._find_control("tool_progress")
            if bar is not None:
                bar.setValue(pct)
        else:
            self._set_chat_status(f"Muse Glimmer: {status}")

    def _on_muse_pull_finished(self, model: str) -> None:
        bar = self._find_control("tool_progress")
        if bar is not None:
            bar.setValue(100)
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
        bar = self._find_control("tool_progress")
        if bar is not None:
            bar.setValue(0)
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
            widget = self._find_control(name)
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
        provider_box = self._find_control(widgets[0])
        model_box = self._find_control(widgets[1])
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
        provider_box = self._find_control(widgets[0])
        model_box = self._find_control(widgets[1])
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
            provider_box = self._find_control(widgets[0])
            model_box = self._find_control(widgets[1])
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
        provider_box = self._find_control(widgets[0])
        model_box = self._find_control(widgets[1])
        provider_result, _model_result = self._text_recommendations(agent_key)
        if provider_box is not None and provider_result is not None:
            idx = self._find_provider_index(provider_box,
                                            provider_result.candidate.provider)
            if idx >= 0:
                provider_box.setCurrentIndex(idx)
        if agent_key == "chat":
            self.load_provider_models()
        else:
            panel = self._find_control(f"{agent_key}_panel_base")
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
        voice_box = self._find_control("audiobook_voice_box")
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
        provider_box = self._find_control("video_visual_provider_box")
        model_box = self._find_control("video_visual_model_box")
        length_box = self._find_control("video_length_box")
        format_box = self._find_control("video_format_box")
        aspect_box = self._find_control("video_aspect_box")
        if None in (provider_box, model_box, length_box, format_box, aspect_box):
            return
        from services.media_catalog import MODELS

        duration_text = length_box.currentText().rstrip("s")
        duration = int(duration_text) if duration_text.isdigit() else None
        candidates = [media_candidate(item, duration) for item in MODELS]
        candidates = [
            replace(item, available=bool(
                item.available and self._provider_permission(item.provider)))
            if item.provider.casefold() not in {"local", "pexels"} else item
            for item in candidates
        ]
        if format_box.currentText() == "Long-form":
            candidates = [item for item in candidates if item.kind != "direct_video"]
        context = RecommendationContext(
            agent="video", modality="visual",
            task=format_box.currentText(),
            aspect=aspect_box.currentText(), duration=duration,
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
        combo = self._find_control("fiverr_image_model_box")
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
            provider_box = self._find_control(widgets[0])
            model_box = self._find_control(widgets[1])
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
                widget = self._find_control(name)
                if widget is not None:
                    widget.currentTextChanged.connect(
                        lambda _t, k=agent_key: self.refresh_recommendation_marks(k)
                    )

        self.refresh_video_recommendations()
        self._refresh_fiverr_image_recommendation()
        for name in ("video_format_box", "video_aspect_box", "video_length_box",
                     "video_visual_provider_box", "video_visual_model_box"):
            widget = self._find_control(name)
            if widget is not None:
                widget.currentTextChanged.connect(self.refresh_video_recommendations)
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

        # The running version, beside the name. Derived from the repository
        # rather than typed, so it cannot drift from the code it labels — see
        # services/version.py. It answers two questions at a glance: which
        # build is open, and whether that build is the current one. A stale
        # bundle says so in amber instead of looking identical to a fresh one.
        row.addSpacing(SM)
        self.version_badge = QLabel(app_version.version_string())
        self.version_badge.setObjectName("VersionBadge")
        self.version_badge.setToolTip(app_version.tooltip())
        if not app_version.staleness()["current"]:
            self.version_badge.setProperty("state", "stale")
        row.addWidget(self.version_badge)

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
        """Compose the Book Author workspace owned by its agent package."""
        self.author_panel = AuthorPanel(self)

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
        """Compose Client Gigs' independently owned workspace."""
        self.fiverr_panel = FiverrPanel(self)

    # ── Social ───────────────────────────────────────────────────────────────
    def build_social_panel(self):
        """Compose the Social workspace owned by its agent package."""
        self.social_panel = SocialPanel(self)

    # ── Social handlers ──────────────────────────────────────────────────────
    # Compatibility delegates: the workspace and its lifecycle live in
    # agents/social/panel.py; these keep existing umbrella bindings and
    # external entry points stable.
    def social_refresh_campaigns(self):
        self.social_panel.refresh_campaigns()

    def social_current_campaign(self):
        return self.social_panel.current_campaign()

    def social_refresh_schedule(self):
        self.social_panel.refresh_schedule()

    def social_refresh_accounts(self):
        self.social_panel.refresh_accounts()

    def social_write(self):
        self.social_panel.write()

    def social_make_clip(self):
        self.social_panel.make_clip()

    def social_stop(self):
        self.social_panel.stop()

    # ── Video (vidforge) ─────────────────────────────────────────────────────
    def build_video_panel(self):
        """Compose the Video workspace owned by its agent package."""
        self.video_panel = VideoPanel(self)

    # ── Video handlers ───────────────────────────────────────────────────────
    # Compatibility delegates: the workspace and its lifecycle live in
    # agents/video/panel.py; these keep existing umbrella bindings and the
    # layout tests' entry points stable.
    def refresh_video_library(self):
        self.video_panel.refresh_library()

    def video_render(self):
        self.video_panel.render()

    def _video_render_direct(self, selection) -> None:
        self.video_panel.render_direct(selection)

    def video_stop(self):
        self.video_panel.stop()

    def video_play_selected(self):
        self.video_panel.play_selected()

    def video_reveal_selected(self):
        self.video_panel.reveal_selected()

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
        panel = self.creator_panel
        panel.creator_platform_box.setCurrentText("OnlyFans")
        panel.creator_kind_box.setCurrentText("campaign")
        panel.creator_brief_input.setPlainText(format_creator_brief(context))
        panel.creator_tabs.setCurrentIndex(0)
        panel.creator_status_label.setText(
            "OnlyFans opportunity loaded — choose an account, review the brief, then Draft.")
        panel.creator_brief_input.setFocus()

    def _onlyfans_generate_teaser(self, context: dict) -> None:
        """Generate a real SFW clip through Creator's Higgsfield pipeline."""
        self._onlyfans_create_campaign(context)
        self.creator_generate_video()

    # ── Creator (shared content production) ──────────────────────────────────
    def build_creator_panel(self):
        """Compose the Brand Creator workspace owned by its agent package."""
        self.creator_panel = CreatorPanel(self)

    # ── Creator handlers ─────────────────────────────────────────────────────
    # Compatibility delegates: the workspace and its lifecycle live in
    # agents/creator/panel.py; these keep existing umbrella bindings, the
    # OnlyFans handoff and the panel tests' entry points stable.
    def creator_load_models(self):
        self.creator_panel.load_models()

    def creator_refresh_accounts(self):
        self.creator_panel.refresh_accounts()

    def creator_current_account(self):
        return self.creator_panel.current_account()

    def _creator_type_changed(self, account_type: str):
        self.creator_panel._type_changed(account_type)

    def _creator_kind_changed(self, kind: str):
        self.creator_panel._kind_changed(kind)

    def _creator_store_media(self, account_id: int, path: str, **kwargs):
        self.creator_panel._store_media(account_id, path, **kwargs)

    def creator_generate(self):
        self.creator_panel.generate()

    def creator_generate_video(self):
        self.creator_panel.generate_video()

    def creator_stop(self):
        self.creator_panel.stop()

    def creator_refresh_calendar(self):
        self.creator_panel.refresh_calendar()

    def creator_refresh_earnings(self):
        self.creator_panel.refresh_earnings()

    def creator_refresh_media(self):
        self.creator_panel.refresh_media()

    # ── Fiverr handlers ──────────────────────────────────────────────────────
    # Client Gigs compatibility entries. The owned panel contains the workflow.
    def fiverr_load_models(self):
        self.fiverr_panel.load_models()

    def _fiverr_update_estimate(self, *_args):
        self.fiverr_panel.update_estimate(*_args)

    def _fiverr_get_brief(self) -> dict:
        return self.fiverr_panel._get_brief()

    def fiverr_generate_logos(self):
        self.fiverr_panel.generate_logos()

    def _fiverr_on_prompt_ready(self, image_prompt: str):
        self.fiverr_panel._on_prompt_ready(image_prompt)

    def _fiverr_on_image_ready(self, path: str, index: int):
        self.fiverr_panel._on_image_ready(path, index)

    def _fiverr_reset_buttons(self):
        self.fiverr_panel._reset_buttons()

    def _fiverr_on_all_done(self, paths: list):
        self.fiverr_panel._on_all_done(paths)

    def _fiverr_on_image_error(self, error: str):
        self.fiverr_panel._on_image_error(error)

    def _fiverr_on_text_error(self, error: str):
        self.fiverr_panel._on_text_error(error)

    def fiverr_write_delivery(self):
        self.fiverr_panel.write_delivery()

    def _fiverr_on_delivery_token(self, token: str):
        self.fiverr_panel._on_delivery_token(token)

    def _fiverr_on_delivery_done(self, full: str):
        self.fiverr_panel._on_delivery_done(full)

    def fiverr_write_gig(self):
        self.fiverr_panel.write_gig()

    def _fiverr_on_gig_token(self, token: str):
        self.fiverr_panel._on_gig_token(token)

    def _fiverr_on_gig_done(self, full: str):
        self.fiverr_panel._on_gig_done(full)

    def fiverr_stop(self):
        self.fiverr_panel.stop()

    def fiverr_save_images(self):
        self.fiverr_panel.save_images()

    def fiverr_clear(self):
        self.fiverr_panel.clear()

    def _fiverr_clear_logo_grid(self):
        self.fiverr_panel._clear_logo_grid()

    # ── Author handlers ──────────────────────────────────────────────────────
    # Compatibility delegates: the workspace and its lifecycle live in
    # agents/author/panel.py; these keep existing umbrella bindings, the
    # global Stop chain and the layout tests' entry points stable. The
    # next-step advisor below stays on the host because Publishing Manager
    # shares its banner and its todo store.
    def author_load_models(self):
        self.author_panel.load_models()

    def _author_set_mode(self, mode: str):
        self.author_panel.set_mode(mode)

    def _author_set_sub_mode(self, mode: str):
        self.author_panel.set_sub_mode(mode)

    def _author_get_book_profile(self) -> dict:
        return self.author_panel.get_book_profile()

    def author_write(self):
        self.author_panel.write()

    def author_continue(self):
        self.author_panel.continue_draft()

    def author_stop(self):
        self.author_panel.stop()

    def author_pub_stop(self):
        self.author_panel.pub_stop()

    def author_mkt_stop(self):
        self.author_panel.mkt_stop()

    def _compute_next_step_tip(self) -> str:
        """Pick the single most useful next action, checked against real app state.
        Ordered write → publish → market, so it walks the whole book lifecycle."""
        import os

        panel = getattr(self, "author_panel", None)
        if panel is None:
            # Advisor asked before the Book Author workspace exists.
            return ("Start here — fill in Title, Author and Type in the Project Bar, then open "
                    "Book Profile and click Save Profile. Everything downstream reuses it.")
        profile = panel.get_book_profile()
        draft_words = len(panel.author_draft_box.toPlainText().split())
        outline = panel.author_outline_box.toPlainText().strip()

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

    # ── Manuscript panel builder ──────────────────────────────────────────────
    def build_manuscript_panel(self):
        """Compose the Publishing Manager workspace owned by its package."""
        self.manuscript_panel = ManuscriptPanel(self)

    # ── Manuscript handlers ───────────────────────────────────────────────────
    # Compatibility delegates: the workspace and its lifecycle live in
    # agents/manuscript/panel.py; these keep existing umbrella bindings and
    # external entry points stable.
    def manuscript_load_models(self):
        self.manuscript_panel.load_models()

    def _refresh_connections_status(self):
        self.manuscript_panel.refresh_connections_status()

    def manuscript_refresh(self):
        self.manuscript_panel.refresh_data()

    def manuscript_ingest_kdp(self):
        self.manuscript_panel.ingest_kdp()

    def manuscript_ask(self):
        self.manuscript_panel.ask()

    def manuscript_add_todo(self):
        self.manuscript_panel.add_todo()

    def manuscript_mark_todo_done(self):
        self.manuscript_panel.mark_todo_done()

    def _load_manuscript_todos(self):
        self.manuscript_panel.load_todos()

    def manuscript_generate_quote_graphic(self):
        self.manuscript_panel.generate_quote_graphic()

    def manuscript_open_graphics_folder(self):
        self.manuscript_panel.open_graphics_folder()

    def shorts_load_voices(self):
        self.manuscript_panel.shorts_load_voices()

    def _authorize_short_narration(self, quote: str, use_elevenlabs: bool) -> bool:
        return self.manuscript_panel._authorize_short_narration(
            quote, use_elevenlabs)

    def _shorts_resolve_request(self, completed: bool, detail: str = ""):
        self.manuscript_panel._shorts_resolve_request(completed, detail)

    def manuscript_generate_short(self):
        self.manuscript_panel.generate_short()

    def manuscript_play_short(self):
        self.manuscript_panel.play_short()

    def manuscript_open_shorts_folder(self):
        self.manuscript_panel.open_shorts_folder()

    def quote_finder_load_voices(self):
        self.manuscript_panel.quote_finder_load_voices()

    def quote_finder_load_file(self):
        self.manuscript_panel.quote_finder_load_file()

    def quote_finder_suggest(self):
        self.manuscript_panel.quote_finder_suggest()

    def quote_finder_generate_graphic(self, quote: str):
        self.manuscript_panel.quote_finder_generate_graphic(quote)

    def quote_finder_generate_short(self, quote, button):
        self.manuscript_panel.quote_finder_generate_short(quote, button)

    def calendar_load_voices(self):
        self.manuscript_panel.calendar_load_voices()

    def manuscript_generate_calendar(self):
        self.manuscript_panel.generate_calendar()

    def calendar_generate_asset(self, row: int, button):
        self.manuscript_panel.calendar_generate_asset(row, button)

    def manuscript_export_calendar_csv(self):
        self.manuscript_panel.export_calendar_csv()

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
            from agents.manuscript import manuscript_seed_todos
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

    def pending_request_snapshot(self, token) -> dict:
        """A copy of an open request's context, for durable job records."""
        context = self._pending_requests.get(token)
        return dict(context) if context else {}

    def restore_request(self, agent, provider, model, prompt, *, label=None,
                        flat_cost_eur=None, project=None, run_id=""):
        """Re-mint the pending context for a request from a previous process.

        Used only when resuming a persisted provider job: the money was
        validated, confirmed and possibly spent before the restart, so this
        never re-validates and never re-asks — a refusal here could orphan a
        paid result. It restores the in-flight reservation so the caps stay
        truthful and the normal record_request / abandon_request close-out
        works.
        """
        token = uuid.uuid4().hex
        self._pending_requests[token] = {
            "agent": agent,
            "tool": label or "-",
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "usage": None,
            "flat_cost_eur": flat_cost_eur,
            "estimated_cost": float(flat_cost_eur or 0.0),
            "project": project,
            "project_instructions": "",
            "run_id": run_id or "",
        }
        self._pending_by_agent.setdefault(agent, []).append(token)
        return token

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
        provider_box = self._find_control(widgets[0])
        model_box = self._find_control(widgets[1])
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
            for worker in getattr(self, "video_resume_workers", ()):
                if worker is not None and worker.isRunning():
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
