import json
import os
import uuid
import re
import subprocess
import sys
import time
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
from PySide6.QtGui import QTextCursor, QDesktopServices, QColor, QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QSizePolicy, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QTextEdit, QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QMessageBox, QCheckBox, QTextBrowser, QSplitter, QLineEdit, QFileDialog,
    QProgressBar, QDialog, QTabWidget, QTabBar, QFrame, QScrollArea, QStackedWidget, QLayout,
    QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView,
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
from services.report_exporter import ReportExporter
from services.usage_tracker import UsageTracker
from services.tool_runner import ToolRunner
from services.database import init_db, get_setting, save_setting, get_connection
from services.registry import Registry
from services.validator import Validator
from services.run_logger import RunLogger

from agents.audiobook_connector import AudiobookConnector
from agents.chat_agent import ChatAgent
from agents.author_agent import AuthorAgent
from agents.manuscript_agent import ManuscriptAgent
from agents.webdesign_agent import WebdesignAgent
from agents.music_agent import MusicAgent
from agents.fiverr_agent import FiverrAgent
from agents.creator_agent import (
    CreatorAgent, ConsentError, PROMO_CHANNELS,
)
from services.higgsfield_client import (
    HiggsfieldClient, ContentPolicyError, check_prompt,
)
from services.creator_csv import ingest_creator_csv
from services.creator_profile import (
    SEGMENTS, load_persona, load_voice, persona_seed, reference_images,
    save_persona, save_voice,
)
from services.creator_insights import (
    account_summary, agency_overview, commission, hook_results, price_history,
    price_points, record_revenue, top_content,
)
from ui.book_widgets import (
    make_theme_box, make_size_box, make_voice_source_box,
    theme_key, size_key, unique_output_path,
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

# The app is organised around creative outcomes, not implementation-level agent
# names. Each workspace remembers its last selected tool during the session.
WORKSPACES = {
    "Write": ("author", "manuscript"),
    "Audio": ("audiobook", "music"),
    "Web": ("webdesign",),
    "Gigs": ("fiverr",),
    "Creator": ("creator",),
}
WORKSPACE_LABELS = {
    "author": "Draft",
    "manuscript": "Publish",
    "audiobook": "Audiobooks",
    "music": "Music",
    "webdesign": "Site Builder",
    "fiverr": "Client Gigs",
    "creator": "Creator",
}

SETTINGS_FILE = CONFIG_DIR / "settings.json"
AGENTS_FILE = CONFIG_DIR / "agents.json"
COMMANDS_FILE = CONFIG_DIR / "commands.json"
TOOL_PROMPTS_FILE = CONFIG_DIR / "tool_prompts.json"
REGISTRY_FILE = CONFIG_DIR / "registry.json"
README_FILE = RESOURCE_DIR / "README.md"

SUPPORTED_EBOOKS = {".pdf", ".epub", ".txt", ".mobi"}

# ── Per-agent recommended setup ──────────────────────────────────────────────
# Single source of truth for "which provider + model is right for THIS agent".
# Each panel pre-selects its entry on startup, and the recommended provider and
# model are painted red in their dropdowns so the user can always see what the
# recommendation was, even after switching to something else mid-session.
#
# `provider` must match an item in that panel's provider box. `model` is matched
# leniently (exact -> prefix -> substring) so a dated API id such as
# "claude-sonnet-4-6-20260112" still resolves from "claude-sonnet-4-6".
# The accent, not a warning colour: this marks the *suggested* provider and
# model, and red here read as "something is wrong with this choice".
RECOMMENDED_COLOR = ACCENT

AGENT_RECOMMENDATIONS = {
    "creator": {
        "provider": "anthropic", "model": "claude-sonnet-5",
        "reason": "Marketing copy in a consistent voice across many short "
                  "pieces — Sonnet holds a persona without Opus pricing.",
    },
    "fiverr": {
        "provider": "openai", "model": "gpt-4o-mini",
        "reason": "Gig copy sits next to DALL·E logo generation — staying on OpenAI "
                  "keeps prompt style and image calls on one provider, cheaply.",
    },
    "author": {
        "provider": "anthropic", "model": "claude-fable-5",
        "reason": "Fable 5 is the creative-writing member of the Claude 5 family — "
                  "the closest fit for long-form fiction, character and dialogue work.",
    },
    "manuscript": {
        "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
        "reason": "Sales metrics and todo tracking are light structured tasks — "
                  "Haiku is the fastest and cheapest fit.",
    },
    "music": {
        "provider": "anthropic", "model": "claude-sonnet-5",
        "reason": "Release planning and distribution strategy — broad, practical "
                  "reasoning without needing Opus depth.",
    },
    "webdesign": {
        "provider": "anthropic", "model": "claude-sonnet-5",
        "reason": "Strongest HTML/CSS/JS generation; produces working responsive "
                  "markup in one pass more often than the cheaper models.",
    },
    "audiobook": {
        "provider": "openai", "model": "tts-1", "voice": "alloy",
        "reason": "Narrator is hard-wired to OpenAI TTS. Alloy is the most neutral, "
                  "even-paced voice — the safest default for hours of narration.",
    },
}

# agent key -> (provider box attribute, model box attribute)
AGENT_SETUP_WIDGETS = {
    "fiverr":      ("fiverr_provider_box",      "fiverr_model_box"),
    "creator":     ("creator_provider_box",     "creator_model_box"),
    "author":      ("author_provider_box",      "author_model_box"),
    "manuscript":  ("manuscript_provider_box",  "manuscript_model_box"),
    "music":       ("music_provider_box",       "music_model_box"),
    "webdesign":   ("webdesign_provider_box",   "webdesign_model_box"),
}

# agent key -> the panel's own "reload the model list" method, called after the
# provider is switched programmatically so the model box is populated before we
# try to select the recommended model in it.
AGENT_MODEL_LOADERS = {
    "fiverr":      "fiverr_load_models",
    "creator":     "creator_load_models",
    "author":      "author_load_models",
    "manuscript":  "manuscript_load_models",
    "music":       "music_load_models",
    "webdesign":   "webdesign_load_models",
}

AGENT_PRETTY_NAMES = {
    "chat": "Studio Assistant",
    "fiverr": "Client Gigs",
    "creator": "Creator",
    "author": "Draft",
    "manuscript": "Publish",
    "music": "Music",
    "webdesign": "Site Builder",
    "audiobook": "Audiobooks",
}


from ui.panels.base import AgentPanel
from services.audiobook_library import (
    format_time as format_audiobook_time,
    load_position as load_audiobook_position,
    mark_unfinished as mark_audiobook_unfinished,
    scan as scan_audiobooks,
)
from ui.audio_player import AudiobookPlayer
from ui.workers import (
    ChatWorker, SubprocessWorker, ModelPullWorker, FiverrImageWorker, ShortsWorker,
    HiggsfieldWorker,
)
from ui.forms import (
    CONTENT_MAX_WIDTH, HEADER_HEIGHT, LG, MD, RAIL_LEFT_WIDTH,
    RAIL_RIGHT_WIDTH, SM, XS, Meter, StatBlock, combo, field, form_grid,
    line_edit, micro, nav_tab, primary, quiet, rail, rule, section, stat,
)
from ui.widgets import (
    FlowLayout, CollapsibleSection, scrollable, let_combos_shrink,
)
from ui.tooltips import seed_tooltips

class GodAI(QWidget):
    def __init__(self):
        super().__init__()
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
        self._last_music_response: str = ""
        self.webdesign_worker: Optional[ChatWorker] = None
        self._last_webdesign_response: str = ""
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
        """Swallow QEvent.ToolTip when tooltips are toggled off."""
        if event.type() == QEvent.ToolTip and not self.tooltips_enabled:
            return True
        return super().eventFilter(obj, event)

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
        approx_input_tokens = max(1, int(len(prompt) / 4))
        approx_output_tokens = max(250, int(approx_input_tokens * 1.2))
        approx_total_tokens = approx_input_tokens + approx_output_tokens

        if backend == "ollama":
            return 0.0, approx_total_tokens

        estimated_cost = self.usage_tracker.calculate_cost_eur(
            backend, model, approx_input_tokens, approx_output_tokens
        )

        return round(estimated_cost, 5), approx_total_tokens

    def get_current_cost_estimate(self):
        raw_text = self.input_box.toPlainText().strip()

        if not raw_text:
            return 0.0, 0, None, None

        _, full_prompt = self.build_user_prompt(raw_text)
        backend, model = self.resolve_backend_model()

        estimated_cost, approx_tokens = self.estimate_chat_cost(
            backend,
            model,
            full_prompt
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

    def check_budget_before_request(self, estimated_cost: float, backend: str) -> bool:
        if backend == "ollama":
            return True

        today_total = self.usage_tracker.get_today_total()

        session_remaining = self.session_budget_eur - self.session_cost_total
        daily_remaining = self.daily_budget_eur - today_total

        if estimated_cost > session_remaining:
            QMessageBox.warning(
                self,
                "Session Budget Exceeded",
                f"This request is estimated at €{estimated_cost:.2f}, "
                f"but your remaining session budget is only €{session_remaining:.2f}."
            )
            return False

        if estimated_cost > daily_remaining:
            QMessageBox.warning(
                self,
                "Daily Budget Exceeded",
                f"This request is estimated at €{estimated_cost:.2f}, "
                f"but your remaining daily budget is only €{daily_remaining:.2f}."
            )
            return False

        return True

    def save_budget_limits(self):
        try:
            self.session_budget_eur = float(self.session_budget_input.text().strip())
            self.daily_budget_eur = float(self.daily_budget_input.text().strip())

            save_setting("session_budget_eur", str(self.session_budget_eur))
            save_setting("daily_budget_eur", str(self.daily_budget_eur))

            self.update_usage_labels()
            QMessageBox.information(self, "Budget Saved", "Budget limits saved.")

        except ValueError:
            QMessageBox.warning(self, "Invalid Budget", "Please enter valid numbers.")

    def reset_session_spend(self):
        self.session_cost_total = 0.0
        self.session_request_count = 0
        self.update_usage_labels()
        QMessageBox.information(self, "Session Reset", "Session spend has been reset.")

    def get_recommended_setup(self):
        agent = self.agent_box.currentText() if hasattr(self, "agent_box") else "chat"
        tool = self.tool_box.currentText() if hasattr(self, "tool_box") else "General Chat"
        command = self.command_box.currentText() if hasattr(self, "command_box") else "General Chat"
        prompt = self.input_box.toPlainText().strip() if hasattr(self, "input_box") else ""
        tool_config = self.tool_prompts.get(tool, {})
        tool_provider = tool_config.get("recommended_provider")
        tool_model = tool_config.get("recommended_model")
        
        if tool_provider:
            model = tool_model or self.model_box.currentText()

            # ===== CHECK API PERMISSION =====
            if tool_provider == "openai" and not self.allow_openai_checkbox.isChecked():
                return {
                    "mode": "Local only",
                    "provider": "ollama",
                    "model": self.model_box.currentText(),
                    "reason": f"{tool} recommends OpenAI, but API is disabled. Using local model."
                }

            if tool_provider == "deepseek" and not self.allow_deepseek_checkbox.isChecked():
                return {
                    "mode": "Local only",
                    "provider": "ollama",
                    "model": self.model_box.currentText(),
                    "reason": f"{tool} recommends DeepSeek, but API is disabled. Using local model."
                }

            if tool_provider == "kimi" and not self.allow_kimi_checkbox.isChecked():
                return {
                    "mode": "Local only",
                    "provider": "ollama",
                    "model": self.model_box.currentText(),
                    "reason": f"{tool} recommends Kimi, but API is disabled. Using local model."
                }

            if tool_provider == "gemini" and not self.allow_gemini_checkbox.isChecked():
                return {
                    "mode": "Local only",
                    "provider": "ollama",
                    "model": self.model_box.currentText(),
                    "reason": f"{tool} recommends Gemini, but API is disabled. Using local model."
                }

            if tool_provider == "anthropic" and not self.allow_anthropic_checkbox.isChecked():
                return {
                    "mode": "Local only",
                    "provider": "ollama",
                    "model": self.model_box.currentText(),
                    "reason": f"{tool} recommends Anthropic, but API is disabled. Using local model."
                }

            # ===== VALID CASE =====
            mode = "Local only" if tool_provider == "ollama" else "Hybrid allowed"

            return {
                "mode": mode,
                "provider": tool_provider,
                "model": model,
                "reason": f"{tool} tool recommends {tool_provider} for best results."
            }

        text = f"{agent} {tool} {command} {prompt}".lower()

        if agent == "audiobook":
            return {
                "mode": "Cloud only",
                "provider": "openai",
                "model": "tts",
                "reason": "Audiobook conversion uses OpenAI TTS only."
            }

        if any(k in text for k in ["debug", "error", "traceback", "python", "code", "refactor", "function", "class"]):
            if self.allow_anthropic_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "anthropic", "model": "claude-sonnet-4-6", "reason": "Coding/debugging task; Claude Sonnet is excellent for code analysis and generation."}
            if self.allow_kimi_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "kimi", "model": "kimi-k2.7-code", "reason": "Coding/debugging task; Kimi K2.7 Code is purpose-built for coding and long-context tool use."}
            if self.allow_deepseek_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "deepseek", "model": "deepseek-chat", "reason": "Coding/debugging task; DeepSeek is strong for code analysis."}
            if self.allow_openai_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "openai", "model": "gpt-4o-mini", "reason": "Coding/debugging task; OpenAI is reliable for code assistance."}
            return {"mode": "Local only", "provider": "ollama", "model": self.model_box.currentText(), "reason": "Coding task detected, but APIs are not enabled. Using local model."}

        if any(k in text for k in ["write", "rewrite", "email", "cv", "cover letter", "professional", "polish"]):
            if self.allow_anthropic_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "anthropic", "model": "claude-sonnet-4-6", "reason": "Writing task; Claude is highly recommended for polished professional text."}
            if self.allow_openai_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "openai", "model": "gpt-4o-mini", "reason": "Writing task; OpenAI is recommended for polished professional text."}
            if self.allow_gemini_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "gemini", "model": "gemini-1.5-flash", "reason": "Writing task; Gemini is a good API fallback."}
            return {"mode": "Local only", "provider": "ollama", "model": self.model_box.currentText(), "reason": "Writing task detected, but APIs are not enabled. Using local model."}

        # Keyword branch, not an agent branch: "research", "analysis" and "report"
        # are ordinary asks in a publishing app (market research, sales analysis),
        # so this still fires. Only the OSINT wording left with the security half.
        if any(k in text for k in ["investigate", "research", "summarize sources", "analysis", "report"]):
            if self.allow_kimi_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "kimi", "model": "kimi-k2.7-code", "reason": "Research/analysis task; Kimi's strong tool-use performance suits multi-step work."}
            if self.allow_deepseek_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "deepseek", "model": "deepseek-chat", "reason": "Research/analysis task; DeepSeek is recommended."}
            if self.allow_gemini_checkbox.isChecked():
                return {"mode": "Hybrid allowed", "provider": "gemini", "model": "gemini-1.5-flash", "reason": "Analysis task; Gemini is suitable for broad summarization."}
            return {"mode": "Local only", "provider": "ollama", "model": self.model_box.currentText(), "reason": "Analysis task detected, but APIs are not enabled. Using local model."}

        return {
            "mode": "Local only",
            "provider": "ollama",
            "model": self.model_box.currentText(),
            "reason": "General/simple task. Local Ollama is free and private."
        }

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

        if hasattr(self, "recommendation_label"):
            self.recommendation_label.setText(
                f"Recommendation:\n"
                f"{rec['provider']} · {rec['model']}\n"
                f"{rec['reason']}"
            )

        self.update_live_cost_estimate()

    def update_recommendation_label(self):
        if not hasattr(self, "recommendation_label"):
            return

        rec = self.get_recommended_setup()

        self.recommendation_label.setText(
            f"Recommendation:\n"
            f"{rec['provider']} · {rec['model']}\n"
            f"{rec['reason']}"
        )
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

    # ── Per-agent recommended setup ──────────────────────────────────────────
    # Every agent panel gets its recommendation from AGENT_RECOMMENDATIONS
    # pre-selected on startup, and the recommended provider/model entries are
    # painted red inside their dropdowns. The red entry survives the user
    # switching to something else, so the original recommendation stays visible
    # for the whole session.

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
        return -1

    def _paint_recommended_item(self, combo, index: int, tooltip: str) -> None:
        """Colour one dropdown entry red + bold and clear any previous marking.

        Only the item's colour and tooltip change — never its text — because the
        panels read `currentText()` straight back as the provider/model name.
        """
        if combo is None:
            return

        # The stock combo popup ignores per-item colour under some styles; an
        # explicit QStyledItemDelegate makes ForegroundRole/FontRole take effect.
        if not combo.property("_rec_delegate"):
            from PySide6.QtWidgets import QStyledItemDelegate
            combo.setItemDelegate(QStyledItemDelegate(combo))
            combo.setProperty("_rec_delegate", True)

        default_font = combo.font()
        for i in range(combo.count()):
            combo.setItemData(i, None, Qt.ForegroundRole)
            combo.setItemData(i, default_font, Qt.FontRole)
            combo.setItemData(i, "", Qt.ToolTipRole)

        if index < 0:
            return

        marked_font = QFont(default_font)
        marked_font.setBold(True)
        combo.setItemData(index, QColor(RECOMMENDED_COLOR), Qt.ForegroundRole)
        combo.setItemData(index, marked_font, Qt.FontRole)
        combo.setItemData(index, tooltip, Qt.ToolTipRole)

    def _mark_deviation(self, combo, is_recommended: bool) -> None:
        """Tint a combo's border red while it holds a non-recommended value.

        The red dropdown entry is only visible once the list is open; this makes
        the deviation legible at a glance with the panel closed. The focus rule
        is repeated here because a widget-level stylesheet outranks the global
        one and would otherwise drop the green focus ring.
        """
        if combo is None:
            return

        if is_recommended:
            combo.setStyleSheet("")
        else:
            combo.setStyleSheet(
                f"QComboBox {{ border: 1px solid {RECOMMENDED_COLOR}; }}"
                f"QComboBox:focus {{ border: 1px solid {ACCENT}; }}"
            )

    def _recommendation_for(self, agent_key: str) -> dict | None:
        """Return {provider, model, reason} for an agent.

        Chat is the one agent whose recommendation is not fixed — it already has
        a live recommender that reacts to the selected tool, command and prompt
        text — so defer to that and let the red marking follow it around.
        """
        if agent_key == "chat":
            try:
                rec = self.get_recommended_setup()
            except Exception:
                return None
            # The audiobook branch reports a pseudo-model that has no combo entry.
            return rec if rec.get("model") != "tts" else None

        return AGENT_RECOMMENDATIONS.get(agent_key)

    def refresh_recommendation_marks(self, agent_key: str) -> None:
        """Re-apply the red marking for one agent's provider and model boxes.

        Called after any model-list reload, since clearing a combo also drops the
        per-item colour data.
        """
        rec = self._recommendation_for(agent_key)
        widgets = AGENT_SETUP_WIDGETS.get(agent_key)
        if not rec or not widgets:
            return

        provider_box = getattr(self, widgets[0], None)
        model_box = getattr(self, widgets[1], None)
        pretty = AGENT_PRETTY_NAMES.get(agent_key, agent_key)
        tooltip = (
            f"Recommended for {pretty}: {rec['provider']} · {rec['model']}\n"
            f"{rec['reason']}"
        )

        if provider_box is not None:
            idx = provider_box.findText(rec["provider"])
            self._paint_recommended_item(provider_box, idx, tooltip)
            provider_box.setToolTip(tooltip)
            self._mark_deviation(
                provider_box, provider_box.currentText() == rec["provider"]
            )

        if model_box is not None:
            idx = self._find_model_index(model_box, rec["model"])
            self._paint_recommended_item(model_box, idx, tooltip)
            model_box.setToolTip(tooltip)
            self._mark_deviation(
                model_box, idx >= 0 and model_box.currentIndex() == idx
            )
            # After the red marking, since _paint_recommended_item resets every
            # item's colour and would otherwise wipe the grey.
            self.mark_oversized_models(model_box)

    def _on_recommended_provider_changed(self, agent_key: str) -> None:
        """React to the user switching provider on an agent panel.

        Whenever the provider lands back on the recommended one, snap the model
        box to the recommended model too — otherwise the panel's loader leaves
        it on whatever happens to be first in the list. A deliberate model change
        afterwards is left alone.
        """
        rec = self._recommendation_for(agent_key)
        widgets = AGENT_SETUP_WIDGETS.get(agent_key)
        if rec and widgets:
            provider_box = getattr(self, widgets[0], None)
            model_box = getattr(self, widgets[1], None)
            if (provider_box is not None and model_box is not None
                    and provider_box.currentText() == rec["provider"]):
                idx = self._find_model_index(model_box, rec["model"])
                if idx >= 0:
                    model_box.setCurrentIndex(idx)

        self.refresh_recommendation_marks(agent_key)

    def apply_agent_recommendation(self, agent_key: str) -> None:
        """Pre-select this agent's recommended provider + model, then mark them."""
        if agent_key == "chat":
            # Chat has its own apply path that also updates the recommendation
            # panel and the live cost estimate.
            self.apply_recommended_setup()
            self.refresh_recommendation_marks("chat")
            return

        rec = AGENT_RECOMMENDATIONS.get(agent_key)
        widgets = AGENT_SETUP_WIDGETS.get(agent_key)
        if not rec or not widgets:
            return

        provider_box = getattr(self, widgets[0], None)
        model_box = getattr(self, widgets[1], None)

        if provider_box is not None:
            idx = provider_box.findText(rec["provider"])
            if idx >= 0:
                provider_box.setCurrentIndex(idx)

        # Populate the model list for the provider we just selected. Setting the
        # provider fires currentTextChanged -> the panel's loader, but only when
        # the value actually changed, so call the loader directly to cover the
        # case where the recommended provider was already selected.
        loader = getattr(self, AGENT_MODEL_LOADERS.get(agent_key, ""), None)
        if callable(loader):
            try:
                loader()
            except Exception as exc:
                self._note_failure("apply recommendation: reload models", exc)

        if model_box is not None:
            idx = self._find_model_index(model_box, rec["model"])
            if idx >= 0:
                model_box.setCurrentIndex(idx)

        self.refresh_recommendation_marks(agent_key)

    def _install_audiobook_recommendation(self) -> None:
        """Narrator has no provider/model choice — OpenAI TTS is hard-wired — so
        the only thing to recommend is the narration voice."""
        rec = AGENT_RECOMMENDATIONS.get("audiobook", {})
        voice_box = getattr(self, "audiobook_voice_box", None)
        voice = rec.get("voice")
        if voice_box is None or not voice:
            return

        tooltip = f"Recommended for Narrator: voice '{voice}'\n{rec['reason']}"
        idx = voice_box.findText(voice)
        if idx >= 0:
            voice_box.setCurrentIndex(idx)
        self._paint_recommended_item(voice_box, idx, tooltip)
        voice_box.setToolTip(tooltip)
        voice_box.currentTextChanged.connect(
            lambda _t: self._mark_deviation(
                voice_box, voice_box.currentText() == voice
            )
        )

    def install_agent_recommendations(self) -> None:
        """Apply every agent's recommended setup once, at startup, and keep the
        red markings in sync as the user changes providers or models later."""
        self._install_audiobook_recommendation()

        for agent_key in AGENT_SETUP_WIDGETS:
            widgets = AGENT_SETUP_WIDGETS[agent_key]
            provider_box = getattr(self, widgets[0], None)
            model_box = getattr(self, widgets[1], None)

            try:
                self.apply_agent_recommendation(agent_key)
            except Exception as e:
                print(f"[Recommendations] {agent_key}: {e}")

            # Re-mark after the panel's own loader has repopulated the model box.
            # Connected last, so it runs after the loader already wired up above.
            if provider_box is not None:
                provider_box.currentTextChanged.connect(
                    lambda _t, k=agent_key: self._on_recommended_provider_changed(k)
                )
            if model_box is not None:
                model_box.currentTextChanged.connect(
                    lambda _t, k=agent_key: self.refresh_recommendation_marks(k)
                )

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

        # After every panel exists: a combo sized to its longest item pins the
        # control columns wider than the panes they live in, which is what cut
        # the fields off down the right-hand edge.
        let_combos_shrink(self)

        self.apply_global_style()

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
        for workspace_name in WORKSPACES:
            self.workspace_tabs.addTab(workspace_name)
        # Connected only after every tab exists: addTab on an empty bar sets the
        # current index and would fire the handler before the panels are built.
        self.workspace_tabs.currentChanged.connect(self._workspace_changed)
        row.addWidget(self.workspace_tabs, 0, Qt.AlignVCenter)

        row.addStretch()

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

        # Narrow the list to one agent. Populated from the chats that exist, so
        # it only ever offers agents you have actually used.
        self.history_agent_filter = QComboBox()
        self.history_agent_filter.addItem(ALL_AGENTS_FILTER)
        self.history_agent_filter.currentTextChanged.connect(self.load_history_list)
        left_layout.addWidget(self.history_agent_filter)

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Search projects")
        self.history_search.textChanged.connect(self.load_history_list)
        left_layout.addWidget(self.history_search)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.open_selected_chat)
        # Double-click renames: chat_title_from_data already prefers a stored
        # "title" over the truncated first prompt, it was just never written.
        self.history_list.itemDoubleClicked.connect(self.rename_selected_chat)
        # The list takes the rail's spare height rather than being capped at
        # 200px with the buttons stranded at the bottom of the window.
        self.history_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_layout.addWidget(self.history_list, 1)

        left_layout.addWidget(rule())

        self.new_chat_btn = QPushButton("New Project")
        self.new_chat_btn.clicked.connect(self.new_chat)
        left_layout.addWidget(self.new_chat_btn)

        # Destructive and rarely wanted: quiet, and below the thing it acts on.
        self.delete_chat_btn = quiet("Remove")
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
        agent_items = self.agents_config.get("agents", [])
        for extra in ("author", "manuscript", "audiobook", "music", "webdesign", "fiverr"):
            if extra not in agent_items:
                agent_items = list(agent_items) + [extra]
        self.agent_box.addItems(agent_items)
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

        self.build_audiobook_panel()
        center_layout.addWidget(self.audiobook_panel)

        self.build_author_panel()
        center_layout.addWidget(self.author_panel)

        self.build_manuscript_panel()
        center_layout.addWidget(self.manuscript_panel)

        self.build_music_panel()
        center_layout.addWidget(self.music_panel)

        self.build_webdesign_panel()
        center_layout.addWidget(self.webdesign_panel)

        self.build_fiverr_panel()
        center_layout.addWidget(self.fiverr_panel)

        self.build_creator_panel()
        center_layout.addWidget(self.creator_panel)

        self.output_label = QLabel("OUTPUT")
        self.output_label.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #707070; "
            "letter-spacing: 1.5px; padding: 6px 0 2px 0; background: transparent;"
        )
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
        """Convert a book to MP3, and listen to what came out.

        Was three group boxes side by side. The settings box held six rows in a
        space sized by the book list next to it, so it stretched them apart
        with 60px of nothing between each — the emptiest screen in the app,
        and boxed on all four sides to draw attention to it.
        """
        self.audiobook_panel = QWidget()
        outer = QVBoxLayout(self.audiobook_panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(MD)

        # Convert and Listen are two different jobs. The app could produce an
        # audiobook and then had no way to play it; the Listen tab is that.
        self.audiobook_tabs = QTabWidget()
        outer.addWidget(self.audiobook_tabs, 1)

        convert_page = QWidget()
        convert_page.setObjectName("Transparent")
        page = QVBoxLayout(convert_page)
        page.setContentsMargins(MD, MD, MD, MD)
        page.setSpacing(LG)

        # ── Source ──────────────────────────────────────────────────────
        page.addWidget(section("Book"))

        self.audiobook_book_list = QListWidget()
        self.audiobook_book_list.setMinimumHeight(150)
        self.audiobook_book_list.currentItemChanged.connect(
            lambda *_: self.estimate_audiobook_cost_from_selection())
        page.addWidget(self.audiobook_book_list, 1)

        # ── Settings ────────────────────────────────────────────────────
        page.addWidget(section("Conversion settings"))

        self.audiobook_input_path = QLineEdit()
        self.audiobook_input_path.setReadOnly(True)
        self.audiobook_open_input_btn = QPushButton("Open")
        self.audiobook_open_input_btn.setFixedWidth(96)
        self.audiobook_open_input_btn.clicked.connect(self.open_audiobook_input_folder)

        self.audiobook_output_path = QLineEdit()
        self.audiobook_output_path.setReadOnly(True)
        self.audiobook_change_output_btn = QPushButton("Change")
        self.audiobook_change_output_btn.setFixedWidth(96)
        self.audiobook_change_output_btn.clicked.connect(self.change_audiobook_output_folder)

        folders = QGridLayout()
        folders.setHorizontalSpacing(SM)
        folders.setVerticalSpacing(MD)
        folders.addWidget(field("Input folder", self.audiobook_input_path), 0, 0, Qt.AlignTop)
        folders.addWidget(self.audiobook_open_input_btn, 0, 1, Qt.AlignBottom)
        folders.addWidget(field("Output folder", self.audiobook_output_path), 1, 0, Qt.AlignTop)
        folders.addWidget(self.audiobook_change_output_btn, 1, 1, Qt.AlignBottom)
        folders.setColumnStretch(0, 1)
        page.addLayout(folders)

        self.audiobook_voice_box = combo(
            ["alloy", "verse", "aria", "coral", "sage"])
        self.audiobook_chunk_input = line_edit("1400", "1400")

        options = QGridLayout()
        options.setHorizontalSpacing(MD)
        options.setVerticalSpacing(MD)
        options.addWidget(field("Voice", self.audiobook_voice_box), 0, 0, Qt.AlignTop)
        options.addWidget(field("Chunk tokens", self.audiobook_chunk_input), 0, 1, Qt.AlignTop)
        for column in range(3):
            options.setColumnStretch(column, 1)
        page.addLayout(options)

        # ── Actions ─────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.audiobook_start_btn = primary("Start")
        self.audiobook_start_btn.setMinimumWidth(160)
        self.audiobook_start_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.audiobook_start_btn.clicked.connect(self.start_selected_audiobook_book)
        actions.addWidget(self.audiobook_start_btn)

        self.audiobook_refresh_btn = QPushButton("Refresh List")
        self.audiobook_refresh_btn.clicked.connect(self.refresh_audiobook_books)
        actions.addWidget(self.audiobook_refresh_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("DangerAction")
        self.stop_btn.clicked.connect(self.stop_current_task)
        self.stop_btn.hide()
        actions.addWidget(self.stop_btn)

        actions.addStretch()
        self.audiobook_cost_label = QLabel("Estimated cost: not calculated")
        self.audiobook_cost_label.setObjectName("EstimateLine")
        actions.addWidget(self.audiobook_cost_label)
        page.addLayout(actions)

        # ── Progress ────────────────────────────────────────────────────
        self.tool_progress = QProgressBar()
        self.tool_progress.setRange(0, 100)
        self.tool_progress.setValue(0)
        self.tool_progress.setTextVisible(True)
        page.addWidget(self.tool_progress)

        self.audiobook_status_label = QLabel("[Ready] Select a book and click Start.")
        self.audiobook_status_label.setObjectName("EstimateLine")
        self.audiobook_status_label.setWordWrap(True)
        page.addWidget(self.audiobook_status_label)

        self.audiobook_tabs.addTab(convert_page, "Convert")
        self.audiobook_tabs.addTab(self._build_audiobook_library_tab(), "Listen")
        self.audiobook_panel.hide()

    def _build_audiobook_library_tab(self) -> QWidget:
        """The finished audiobooks, and a player that resumes where you left off."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(section("Audiobooks in your output folder"))
        header.addStretch()
        self.audiobook_refresh_btn = QPushButton("Rescan")
        self.audiobook_refresh_btn.setObjectName("ChipBtn")
        self.audiobook_refresh_btn.clicked.connect(self.refresh_audiobook_library)
        header.addWidget(self.audiobook_refresh_btn)
        layout.addLayout(header)

        self.audiobook_library_table = QTableWidget(0, 4)
        self.audiobook_library_table.setHorizontalHeaderLabels(
            ["Title", "Progress", "Position", "Last played"])
        self.audiobook_library_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.audiobook_library_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.audiobook_library_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.audiobook_library_table.itemSelectionChanged.connect(
            self._audiobook_selection_changed)
        self.audiobook_library_table.doubleClicked.connect(
            lambda *_: self.play_selected_audiobook())
        layout.addWidget(self.audiobook_library_table, 1)

        row = QHBoxLayout()
        self.audiobook_play_btn = QPushButton("Listen")
        self.audiobook_play_btn.setObjectName("PrimaryAction")
        self.audiobook_play_btn.setEnabled(False)
        self.audiobook_play_btn.clicked.connect(self.play_selected_audiobook)
        row.addWidget(self.audiobook_play_btn)

        self.audiobook_restart_btn = QPushButton("Start Over")
        self.audiobook_restart_btn.setEnabled(False)
        self.audiobook_restart_btn.clicked.connect(self.restart_selected_audiobook)
        row.addWidget(self.audiobook_restart_btn)

        self.audiobook_reveal_btn = QPushButton("Show in Finder")
        self.audiobook_reveal_btn.setEnabled(False)
        self.audiobook_reveal_btn.clicked.connect(self.reveal_selected_audiobook)
        row.addWidget(self.audiobook_reveal_btn)
        row.addStretch()
        layout.addLayout(row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("CardDivider")
        layout.addWidget(divider)

        self.audiobook_player = AudiobookPlayer()
        self.audiobook_player.position_saved.connect(
            lambda *_: self._audiobook_refresh_row())
        layout.addWidget(self.audiobook_player)

        self._audiobook_library: list = []
        return page

    def refresh_audiobook_library(self):
        """Rescan the output folder. Cheap, so it runs on every panel entry."""
        defaults = self.get_audiobook_defaults()
        folder = Path(defaults["output"]).expanduser()
        try:
            self._audiobook_library = scan_audiobooks(folder)
        except Exception as exc:
            self._note_failure("audiobook: scan library", exc)
            self._audiobook_library = []

        table = self.audiobook_library_table
        table.setRowCount(0)
        for book in self._audiobook_library:
            r = table.rowCount()
            table.insertRow(r)
            if book.finished:
                progress = "finished"
            elif book.duration_ms:
                progress = f"{book.progress * 100:.0f}%"
            elif book.position_ms:
                progress = "started"
            else:
                progress = "—"
            position = (format_audiobook_time(book.position_ms)
                        if book.position_ms else "—")
            table.setItem(r, 0, QTableWidgetItem(book.title))
            table.setItem(r, 1, QTableWidgetItem(progress))
            table.setItem(r, 2, QTableWidgetItem(position))
            table.setItem(r, 3, QTableWidgetItem(book.last_played or "—"))

        if not self._audiobook_library:
            self.audiobook_status_label.setText(
                f"[Library] No audio files in {folder}. Convert a book first.")

    def _selected_audiobook(self):
        row = self.audiobook_library_table.currentRow()
        if row < 0 or row >= len(self._audiobook_library):
            return None
        return self._audiobook_library[row]

    def _audiobook_selection_changed(self):
        book = self._selected_audiobook()
        for button in (self.audiobook_play_btn, self.audiobook_restart_btn,
                       self.audiobook_reveal_btn):
            button.setEnabled(book is not None)
        if book and book.started:
            self.audiobook_play_btn.setText(
                f"Resume at {format_audiobook_time(book.position_ms)}")
        else:
            self.audiobook_play_btn.setText("Listen")

    def _audiobook_refresh_row(self):
        """Update the selected row in place while playing.

        A full rescan here would reset the selection under the user mid-listen.
        """
        book = self._selected_audiobook()
        if not book:
            return
        row = self.audiobook_library_table.currentRow()
        position = load_audiobook_position(book.path)
        book.position_ms = position
        self.audiobook_library_table.setItem(
            row, 2, QTableWidgetItem(format_audiobook_time(position)))

    def play_selected_audiobook(self):
        book = self._selected_audiobook()
        if not book:
            return
        if not book.path.exists():
            QMessageBox.warning(
                self, "File Missing",
                f"{book.path.name} is no longer in the output folder.")
            self.refresh_audiobook_library()
            return
        self.audiobook_player.load(
            book.path, title=book.title,
            resume_ms=load_audiobook_position(book.path))
        self.audiobook_player.play()
        self.audiobook_status_label.setText(f"[Playing] {book.title}")

    def restart_selected_audiobook(self):
        book = self._selected_audiobook()
        if not book:
            return
        mark_audiobook_unfinished(book.path)
        self.audiobook_player.load(book.path, title=book.title, resume_ms=0)
        self.audiobook_player.play()
        self.refresh_audiobook_library()

    def reveal_selected_audiobook(self):
        book = self._selected_audiobook()
        if book:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(book.path.parent)))

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

        pb_layout = form_grid([
            ("Title", self.author_title_input),
            ("Author", self.author_name_input),
            ("Type", self.author_content_type_box),
            ("Genre", self.author_genre_box),
            ("Tone", self.author_tone_box),
            ("Point of view", self.author_pov_box),
        ], columns=3)
        pb_layout.setContentsMargins(MD, MD, MD, MD)
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
        profile_section = CollapsibleSection("Book Profile", expanded=False)

        profile_row1 = QWidget()
        pr1 = QHBoxLayout(profile_row1)
        pr1.setContentsMargins(4, 0, 4, 0)
        pr1.setSpacing(8)
        self.author_profile_hook_input = QLineEdit()
        self.author_profile_hook_input.setPlaceholderText("One-sentence pitch — the core promise of the book…")
        pr1.addWidget(field("Hook", self.author_profile_hook_input))
        profile_section.addWidget(profile_row1)

        profile_row2 = QWidget()
        pr2 = QHBoxLayout(profile_row2)
        pr2.setContentsMargins(4, 0, 4, 0)
        pr2.setSpacing(8)
        self.author_profile_reader_input = QLineEdit()
        self.author_profile_reader_input.setPlaceholderText("e.g. Women 25-40 navigating modern dating apps")
        pr2.addWidget(field("Target reader", self.author_profile_reader_input))
        profile_section.addWidget(profile_row2)

        profile_row3 = QWidget()
        pr3 = QHBoxLayout(profile_row3)
        pr3.setContentsMargins(4, 0, 4, 0)
        pr3.setSpacing(8)
        self.author_profile_comps_input = QLineEdit()
        self.author_profile_comps_input.setPlaceholderText("e.g. For readers of [Title A] and [Title B]")
        pr3.addWidget(field("Comp titles", self.author_profile_comps_input))
        profile_section.addWidget(profile_row3)

        profile_row4 = QWidget()
        pr4 = QHBoxLayout(profile_row4)
        pr4.setContentsMargins(4, 0, 4, 0)
        pr4.setSpacing(8)
        self.author_profile_path_box = QComboBox()
        self.author_profile_path_box.addItems(["Undecided", "Self-Publishing (KDP)", "Traditional"])
        pr4.addWidget(field("Publishing path", self.author_profile_path_box))
        pr4.addStretch()
        self.author_profile_save_btn = QPushButton("Save Profile")
        self.author_profile_save_btn.clicked.connect(self.author_save_profile)
        pr4.addWidget(self.author_profile_save_btn)
        profile_section.addWidget(profile_row4)

        layout.addWidget(profile_section)

        # ── Main workspace ────────────────────────────────────────────────────
        workspace_splitter = QSplitter(Qt.Horizontal)

        # Left: editable manuscript tabs
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

        workspace_splitter.addWidget(self.author_tabs)

        # Right: control sidebar
        sidebar = QWidget()
        sidebar.setObjectName("AuthorSidebar")
        sidebar.setMinimumWidth(210)
        sidebar.setMaximumWidth(270)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(8, 4, 4, 4)
        sb.setSpacing(MD)

        # Sections and micro-labels rather than a run of "Label:" rows — see
        # ui/forms.py. The labels line up down one column instead of each
        # sitting wherever its own row started.
        sb.addWidget(section("Compose"))

        self.author_direction_input = QTextEdit()
        self.author_direction_input.setPlaceholderText(
            "What happens next? One concrete instruction beats a paragraph."
        )
        self.author_direction_input.setFixedHeight(90)
        sb.addWidget(field("Direction", self.author_direction_input))

        self.author_task_box = QComboBox()
        # Populated by _author_on_content_type_changed() once the panel finishes building —
        # the task list depends on the Type combo (Fiction/Non-Fiction) in the Project Bar.
        sb.addWidget(field("Task", self.author_task_box))

        sb.addWidget(rule())
        sb.addWidget(section("Model"))

        self.author_panel_base = AgentPanel(
            self, "author", providers=tuple(["ollama", "openai", "deepseek", "kimi", "gemini", "anthropic", "qwen"]),
            default_provider="anthropic")
        self.author_provider_box = self.author_panel_base.provider_box
        self.author_model_box = self.author_panel_base.model_box
        sb.addWidget(field("Provider", self.author_provider_box))
        sb.addWidget(field("Model", self.author_model_box))

        self.author_write_btn = QPushButton("Write")
        self.author_write_btn.setMinimumHeight(34)
        self.author_write_btn.setObjectName("PrimaryAction")
        self.author_write_btn.clicked.connect(self.author_write)
        sb.addWidget(self.author_write_btn)

        self.author_continue_btn = QPushButton("Continue")
        self.author_continue_btn.setMinimumHeight(34)
        self.author_continue_btn.setObjectName("SecondaryAction")
        self.author_continue_btn.clicked.connect(self.author_continue)
        sb.addWidget(self.author_continue_btn)

        self.author_stop_btn = QPushButton("Stop")
        self.author_stop_btn.setEnabled(False)
        self.author_stop_btn.setMinimumHeight(34)
        self.author_stop_btn.setObjectName("DangerAction")
        self.author_stop_btn.clicked.connect(self.author_stop)
        sb.addWidget(self.author_stop_btn)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setObjectName("CardDivider")
        sb.addWidget(sep1)

        word_group = QGroupBox("Words")
        word_group.setObjectName("AuthorWordGroup")
        wg_layout = QVBoxLayout(word_group)
        wg_layout.setContentsMargins(4, 4, 4, 4)
        self.author_word_count_label = QLabel("0")
        self.author_word_count_label.setAlignment(Qt.AlignCenter)
        self.author_word_count_label.setStyleSheet(
            f"font-size: 26px; font-weight: 600; color: {TEXT};"
        )
        wg_layout.addWidget(self.author_word_count_label)
        sb.addWidget(word_group)

        scene_group = QGroupBox("Scenes / Chapters")
        scene_group.setObjectName("AuthorSceneGroup")
        sg_layout = QVBoxLayout(scene_group)
        sg_layout.setContentsMargins(4, 4, 4, 4)
        self.author_scene_count_label = QLabel("0")
        self.author_scene_count_label.setAlignment(Qt.AlignCenter)
        self.author_scene_count_label.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {TEXT};"
        )
        sg_layout.addWidget(self.author_scene_count_label)
        sb.addWidget(scene_group)

        sb.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setObjectName("CardDivider")
        sb.addWidget(sep2)

        self.author_save_btn = QPushButton("Save Draft")
        self.author_save_btn.setEnabled(False)
        self.author_save_btn.clicked.connect(self.author_save)
        sb.addWidget(self.author_save_btn)

        self.author_export_author_input = QLineEdit()
        self.author_export_author_input.setPlaceholderText("e.g. Celeste Morgan")
        sb.addWidget(field("Author name (for export)", self.author_export_author_input))

        # FlowLayout: a QHBoxLayout here reports combo + button as its minimum
        # width (276px) and pinned the whole sidebar wider than its pane, which
        # is what clipped the controls down the right-hand edge. These wrap.
        export_row_container = QWidget()
        export_row = FlowLayout(export_row_container, spacing=6)
        self.author_export_format_box = QComboBox()
        self.author_export_format_box.addItems(["EPUB", "DOCX", "PDF"])
        export_row.addWidget(self.author_export_format_box)
        self.author_export_btn = QPushButton("Export Book")
        self.author_export_btn.clicked.connect(self.author_export_book)
        export_row.addWidget(self.author_export_btn)
        sb.addWidget(export_row_container)

        self.author_clear_btn = QPushButton("Clear All")
        self.author_clear_btn.clicked.connect(self.author_clear)
        sb.addWidget(self.author_clear_btn)

        workspace_splitter.addWidget(scrollable(sidebar))
        workspace_splitter.setSizes([760, 240])

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
        self.author_content_stack.addWidget(workspace_splitter)   # page 0: write

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
        pub_outer = QHBoxLayout(publish_page)
        pub_outer.setContentsMargins(0, 0, 0, 0)
        pub_outer.setSpacing(8)

        self.author_pub_output = QTextEdit()
        self.author_pub_output.setPlaceholderText(
            "Generated publishing document appears here. Fully editable."
        )
        pub_outer.addWidget(self.author_pub_output, 1)

        pub_ctrl = QWidget()
        pub_ctrl.setObjectName("AuthorPubCtrl")
        pub_ctrl.setMinimumWidth(210)
        pub_ctrl.setMaximumWidth(270)
        pc = QVBoxLayout(pub_ctrl)
        pc.setContentsMargins(6, 0, 0, 0)
        pc.setSpacing(5)

        self.author_pub_type_box = QComboBox()
        self.author_pub_type_box.addItems([
            "Synopsis — 1 Page", "Synopsis — 3 Page", "Query Letter",
            "Book Proposal", "Back-Cover Blurb", "Author Bio", "Chapter Breakdown",
        ])
        pc.addWidget(field("Output Type", self.author_pub_type_box))

        self.author_pub_wordcount_input = QLineEdit()
        self.author_pub_wordcount_input.setPlaceholderText("e.g. 80,000")
        pc.addWidget(field("Word Count Target", self.author_pub_wordcount_input))

        self.author_pub_comps_input = QLineEdit()
        self.author_pub_comps_input.setPlaceholderText("e.g. Gone Girl meets Dark Places")
        pc.addWidget(field("Comp Titles", self.author_pub_comps_input))

        self.author_pub_pitch_tone_box = QComboBox()
        self.author_pub_pitch_tone_box.addItems(["Professional", "Conversational", "High-Concept"])
        pc.addWidget(field("Pitch Tone", self.author_pub_pitch_tone_box))

        self.author_pub_notes_input = QTextEdit()
        self.author_pub_notes_input.setPlaceholderText("Target audience, themes, hook, extra context…")
        self.author_pub_notes_input.setFixedHeight(65)
        pc.addWidget(field("Extra Notes", self.author_pub_notes_input))

        pc.addStretch()

        self.author_pub_generate_btn = QPushButton("Generate")
        self.author_pub_generate_btn.setMinimumHeight(34)
        self.author_pub_generate_btn.setObjectName("PrimaryAction")
        self.author_pub_generate_btn.clicked.connect(self.author_pub_generate)
        pc.addWidget(self.author_pub_generate_btn)

        self.author_pub_stop_btn = QPushButton("Stop")
        self.author_pub_stop_btn.setEnabled(False)
        self.author_pub_stop_btn.setObjectName("DangerAction")
        self.author_pub_stop_btn.clicked.connect(self.author_pub_stop)
        pc.addWidget(self.author_pub_stop_btn)

        self.author_pub_copy_btn = QPushButton("Copy to Clipboard")
        self.author_pub_copy_btn.clicked.connect(self.author_pub_copy)
        pc.addWidget(self.author_pub_copy_btn)

        self.author_pub_save_btn = QPushButton("Save as File")
        self.author_pub_save_btn.setEnabled(False)
        self.author_pub_save_btn.clicked.connect(self.author_pub_save)
        pc.addWidget(self.author_pub_save_btn)

        pub_outer.addWidget(scrollable(pub_ctrl))
        self.author_sub_stack.addWidget(publish_page)   # sub-page 0

        # ── Market page ───────────────────────────────────────────────────────
        market_page = QWidget()
        mkt_outer = QHBoxLayout(market_page)
        mkt_outer.setContentsMargins(0, 0, 0, 0)
        mkt_outer.setSpacing(8)

        self.author_mkt_output = QTextEdit()
        self.author_mkt_output.setPlaceholderText(
            "Generated marketing copy appears here. Fully editable."
        )
        mkt_outer.addWidget(self.author_mkt_output, 1)

        mkt_ctrl = QWidget()
        mkt_ctrl.setObjectName("AuthorMktCtrl")
        mkt_ctrl.setMinimumWidth(210)
        mkt_ctrl.setMaximumWidth(270)
        mc = QVBoxLayout(mkt_ctrl)
        mc.setContentsMargins(6, 0, 0, 0)
        mc.setSpacing(5)

        self.author_mkt_platform_box = QComboBox()
        self.author_mkt_platform_box.addItems([
            "Amazon Description", "KDP Listing", "Goodreads Blurb", "Instagram Post",
            "Twitter / X Thread", "TikTok Caption", "Pinterest Pin Description",
            "YouTube Description", "Newsletter", "Press Release", "Book Club Questions",
            "ARC Outreach Email", "Launch Team Email", "Podcast Pitch", "Author Website Bio",
        ])
        mc.addWidget(field("Platform", self.author_mkt_platform_box))

        self.author_mkt_hook_input = QLineEdit()
        self.author_mkt_hook_input.setPlaceholderText("One sentence that sells the book")
        mc.addWidget(field("Hook / Logline", self.author_mkt_hook_input))

        self.author_mkt_comps_input = QLineEdit()
        self.author_mkt_comps_input.setPlaceholderText("e.g. Reaper's Creek meets Harlan Coben")
        mc.addWidget(field("Comp Titles", self.author_mkt_comps_input))

        self.author_mkt_tone_box = QComboBox()
        self.author_mkt_tone_box.addItems(["Punchy", "Literary", "Warm", "Hype", "Mysterious"])
        mc.addWidget(field("Tone", self.author_mkt_tone_box))

        self.author_mkt_notes_input = QTextEdit()
        self.author_mkt_notes_input.setPlaceholderText("Target audience, mood, key themes…")
        self.author_mkt_notes_input.setFixedHeight(65)
        mc.addWidget(field("Extra Notes", self.author_mkt_notes_input))

        mc.addStretch()

        self.author_mkt_generate_btn = QPushButton("Generate")
        self.author_mkt_generate_btn.setMinimumHeight(34)
        self.author_mkt_generate_btn.setObjectName("PrimaryAction")
        self.author_mkt_generate_btn.clicked.connect(self.author_mkt_generate)
        mc.addWidget(self.author_mkt_generate_btn)

        self.author_mkt_stop_btn = QPushButton("Stop")
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_mkt_stop_btn.setObjectName("DangerAction")
        self.author_mkt_stop_btn.clicked.connect(self.author_mkt_stop)
        mc.addWidget(self.author_mkt_stop_btn)

        self.author_mkt_copy_btn = QPushButton("Copy to Clipboard")
        self.author_mkt_copy_btn.clicked.connect(self.author_mkt_copy)
        mc.addWidget(self.author_mkt_copy_btn)

        self.author_mkt_save_btn = QPushButton("Save as File")
        self.author_mkt_save_btn.setEnabled(False)
        self.author_mkt_save_btn.clicked.connect(self.author_mkt_save)
        mc.addWidget(self.author_mkt_save_btn)

        mkt_outer.addWidget(scrollable(mkt_ctrl))
        self.author_sub_stack.addWidget(market_page)   # sub-page 1

        pm_layout.addWidget(self.author_sub_stack, 1)
        self.author_content_stack.addWidget(pubmkt_widget)   # page 1

        layout.addWidget(self.author_content_stack, 1)

        self.author_status_label = QLabel("")
        self.author_status_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTE}; padding: 2px 4px;")
        layout.addWidget(self.author_status_label)

        self.author_draft_box.textChanged.connect(self._author_update_counts)

        self.author_panel.hide()

        self.author_load_models()

        self._author_on_content_type_changed(self.author_content_type_box.currentText())
        self._author_load_profile()

    # ── Music Agent Panel ─────────────────────────────────────────────────────
    def build_music_panel(self):
        """Release planning: profile, distribution, Spotify, income.

        The sidebar of indicator cards is gone. "Release Type", "Genre" and
        "Distributor" were three bordered boxes echoing three combo boxes six
        inches above them, in three different colours, and "Procedure" listed
        the names of the tabs sitting next to it. Four boxes, no new
        information — and they were what squeezed the results pane.
        """
        self.music_panel = QWidget()
        self.music_panel.setObjectName("MusicPanel")
        outer = QVBoxLayout(self.music_panel)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        # ── Setup ───────────────────────────────────────────────────────
        layout.addWidget(section("Artist setup"))

        self.music_artist_input = line_edit("Nova Drift, DJ Phantom, The Hollow Road")
        self.music_genre_box = combo([
            "Pop", "Rock", "Hip-Hop", "Electronic", "Jazz", "Classical",
            "R&B", "Metal", "Indie", "Folk", "Country", "Latin", "Reggae",
            "Ambient", "World", "Other",
        ])
        self.music_release_type_box = combo(
            ["Single", "EP (3–6 tracks)", "Album (7+ tracks)", "Mixtape"])
        self.music_distributor_box = combo([
            "Not signed up yet", "DistroKid", "TuneCore", "CD Baby", "Amuse",
            "AWAL", "Other",
        ])
        self.music_audience_input = line_edit("18–25 lo-fi hip-hop fans, gym-goers")

        setup = QGridLayout()
        setup.setHorizontalSpacing(MD)
        setup.setVerticalSpacing(MD)
        setup.addWidget(field("Artist / project name", self.music_artist_input),
                        0, 0, 1, 2, Qt.AlignTop)
        setup.addWidget(field("Genre", self.music_genre_box), 0, 2, Qt.AlignTop)
        setup.addWidget(field("Release type", self.music_release_type_box),
                        1, 0, Qt.AlignTop)
        setup.addWidget(field("Distributor", self.music_distributor_box),
                        1, 1, Qt.AlignTop)
        setup.addWidget(field("Target audience", self.music_audience_input),
                        1, 2, Qt.AlignTop)
        for column in range(3):
            setup.setColumnStretch(column, 1)
        layout.addLayout(setup)

        self.music_query_input = QTextEdit()
        self.music_query_input.setPlaceholderText(
            "Your sound, influences, vibe, and anything specific about this "
            "release — e.g. dark trap beats with melodic hooks, a 4-track EP "
            "about late-night city life.")
        self.music_query_input.setFixedHeight(70)
        layout.addWidget(field("Describe your music", self.music_query_input))

        # ── Model ───────────────────────────────────────────────────────
        layout.addWidget(section("Model"))
        self.music_panel_base = AgentPanel(
            self, "music",
            providers=("ollama", "openai", "deepseek", "kimi", "gemini",
                       "anthropic", "qwen"),
            default_provider="anthropic")
        self.music_provider_box = self.music_panel_base.provider_box
        self.music_model_box = self.music_panel_base.model_box

        models = QGridLayout()
        models.setHorizontalSpacing(MD)
        models.setVerticalSpacing(MD)
        models.addWidget(field("Provider", self.music_provider_box), 0, 0, Qt.AlignTop)
        models.addWidget(field("Model", self.music_model_box), 0, 1, Qt.AlignTop)
        for column in range(3):
            models.setColumnStretch(column, 1)
        layout.addLayout(models)

        # ── Actions ─────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.music_analyse_btn = primary("Generate Plan")
        self.music_analyse_btn.setMinimumWidth(160)
        self.music_analyse_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.music_analyse_btn.clicked.connect(self.music_analyse)
        actions.addWidget(self.music_analyse_btn)

        self.music_save_btn = QPushButton("Save Full Plan")
        self.music_save_btn.setEnabled(False)
        self.music_save_btn.clicked.connect(self.music_save)
        actions.addWidget(self.music_save_btn)

        self.music_clear_btn = QPushButton("Clear")
        self.music_clear_btn.clicked.connect(self.music_clear)
        actions.addWidget(self.music_clear_btn)

        self.music_stop_btn = QPushButton("Stop")
        self.music_stop_btn.setObjectName("DangerAction")
        self.music_stop_btn.clicked.connect(self.music_stop)
        self.music_stop_btn.hide()
        actions.addWidget(self.music_stop_btn)

        actions.addStretch()
        self.music_status_label = QLabel("")
        self.music_status_label.setObjectName("EstimateLine")
        actions.addWidget(self.music_status_label)
        layout.addLayout(actions)

        # ── Results ─────────────────────────────────────────────────────
        # The five tabs are the procedure, in order, so the "Procedure" card
        # that listed them was the tab bar written out as prose.
        self.music_tabs = QTabWidget()
        self.music_profile_box = QTextBrowser()
        self.music_profile_box.setOpenExternalLinks(False)
        self.music_tabs.addTab(self.music_profile_box, "Artist Profile")
        self.music_release_box = QTextBrowser()
        self.music_tabs.addTab(self.music_release_box, "Release Setup")
        self.music_distribution_box = QTextBrowser()
        self.music_tabs.addTab(self.music_distribution_box, "Distribution")
        self.music_strategy_box = QTextBrowser()
        self.music_tabs.addTab(self.music_strategy_box, "Spotify Strategy")
        self.music_income_box = QTextBrowser()
        self.music_tabs.addTab(self.music_income_box, "Income Roadmap")
        layout.addWidget(self.music_tabs, 1)

        self.music_panel.hide()
        self.music_load_models()

    # ── NFL Prop Bet Panel ───────────────────────────────────────────────────
    # ── OSINT Light panel ────────────────────────────────────────────────────
    # ── OSINT Pro (Heavy) panel ──────────────────────────────────────────────
    # ── OSINT Light handlers ──────────────────────────────────────────────────
    # ── OSINT Pro (Heavy) handlers ───────────────────────────────────────────
    # ── OSINT Pro image helpers ──────────────────────────────────────────────
    # ── Web Design panel ────────────────────────────────────────────────────
    def build_webdesign_panel(self):
        """Generate a page: HTML, CSS, JS, plus what came out of it.

        The three indicator cards (Responsive / Framework Used / Lines of Code)
        are real output facts rather than echoes of the form, so they stay —
        but as a row of stats above the code, not three bordered boxes in a
        200px column squeezing the pane you actually read.
        """
        self.webdesign_panel = QWidget()
        self.webdesign_panel.setObjectName("WebdesignPanel")
        outer = QVBoxLayout(self.webdesign_panel)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("Transparent")
        outer.addWidget(scrollable(content))
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(LG)

        # ── Brief ───────────────────────────────────────────────────────
        layout.addWidget(section("Page"))

        self.webdesign_type_box = combo([
            "Landing Page", "Portfolio", "Dashboard", "Form", "Blog",
            "Component / Widget", "Other",
        ])
        self.webdesign_style_box = combo(
            ["Minimal", "Dark", "Corporate", "Playful", "Brutalist"])
        self.webdesign_palette_input = line_edit("#1a1a2e, #e94560  ·  ocean blues")
        self.webdesign_framework_box = combo(["Vanilla", "Tailwind", "Bootstrap"])

        setup = QGridLayout()
        setup.setHorizontalSpacing(MD)
        setup.setVerticalSpacing(MD)
        setup.addWidget(field("Page type", self.webdesign_type_box), 0, 0, Qt.AlignTop)
        setup.addWidget(field("Style", self.webdesign_style_box), 0, 1, Qt.AlignTop)
        setup.addWidget(field("Framework", self.webdesign_framework_box), 0, 2, Qt.AlignTop)
        setup.addWidget(field("Colour palette", self.webdesign_palette_input),
                        1, 0, 1, 3, Qt.AlignTop)
        for column in range(3):
            setup.setColumnStretch(column, 1)
        layout.addLayout(setup)

        self.webdesign_brief_input = QTextEdit()
        self.webdesign_brief_input.setPlaceholderText(
            "What to build — sections, features, content, interactions.")
        self.webdesign_brief_input.setFixedHeight(70)
        layout.addWidget(field("Brief", self.webdesign_brief_input))

        # ── Model ───────────────────────────────────────────────────────
        layout.addWidget(section("Model"))
        self.webdesign_panel_base = AgentPanel(
            self, "webdesign",
            providers=("ollama", "openai", "deepseek", "kimi", "gemini",
                       "anthropic", "qwen"),
            default_provider="anthropic")
        self.webdesign_provider_box = self.webdesign_panel_base.provider_box
        self.webdesign_model_box = self.webdesign_panel_base.model_box

        models = QGridLayout()
        models.setHorizontalSpacing(MD)
        models.setVerticalSpacing(MD)
        models.addWidget(field("Provider", self.webdesign_provider_box), 0, 0, Qt.AlignTop)
        models.addWidget(field("Model", self.webdesign_model_box), 0, 1, Qt.AlignTop)
        for column in range(3):
            models.setColumnStretch(column, 1)
        layout.addLayout(models)

        # ── Actions ─────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(SM)
        self.webdesign_generate_btn = primary("Generate")
        self.webdesign_generate_btn.setMinimumWidth(160)
        self.webdesign_generate_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.webdesign_generate_btn.clicked.connect(self.webdesign_generate)
        actions.addWidget(self.webdesign_generate_btn)

        self.webdesign_copy_btn = QPushButton("Copy All")
        self.webdesign_copy_btn.setEnabled(False)
        self.webdesign_copy_btn.clicked.connect(self.webdesign_copy_all)
        actions.addWidget(self.webdesign_copy_btn)

        self.webdesign_save_btn = QPushButton("Save .html")
        self.webdesign_save_btn.setEnabled(False)
        self.webdesign_save_btn.clicked.connect(self.webdesign_save)
        actions.addWidget(self.webdesign_save_btn)

        self.webdesign_clear_btn = QPushButton("Clear")
        self.webdesign_clear_btn.clicked.connect(self.webdesign_clear)
        actions.addWidget(self.webdesign_clear_btn)

        self.webdesign_stop_btn = QPushButton("Stop")
        self.webdesign_stop_btn.setObjectName("DangerAction")
        self.webdesign_stop_btn.clicked.connect(self.webdesign_stop)
        self.webdesign_stop_btn.hide()
        actions.addWidget(self.webdesign_stop_btn)

        actions.addStretch()
        self.webdesign_status_label = QLabel("")
        self.webdesign_status_label.setObjectName("EstimateLine")
        actions.addWidget(self.webdesign_status_label)
        layout.addLayout(actions)

        # ── Output ──────────────────────────────────────────────────────
        layout.addWidget(section("Output"))
        stats = QHBoxLayout()
        stats.setSpacing(LG)
        responsive_stat = StatBlock("responsive", "—")
        framework_stat = StatBlock("framework used", "—")
        lines_stat = StatBlock("lines of code", "—")
        # The existing handlers call setText on these, so they keep pointing at
        # the value label rather than the block.
        self.webdesign_responsive_label = responsive_stat.value_label
        self.webdesign_framework_label = framework_stat.value_label
        self.webdesign_lines_label = lines_stat.value_label
        for block in (responsive_stat, framework_stat, lines_stat):
            stats.addWidget(block)
        stats.addStretch()
        layout.addLayout(stats)

        self.webdesign_tabs = QTabWidget()
        self.webdesign_html_box = QTextEdit()
        self.webdesign_html_box.setReadOnly(True)
        self.webdesign_tabs.addTab(self.webdesign_html_box, "HTML")
        self.webdesign_css_box = QTextEdit()
        self.webdesign_css_box.setReadOnly(True)
        self.webdesign_tabs.addTab(self.webdesign_css_box, "CSS")
        self.webdesign_js_box = QTextEdit()
        self.webdesign_js_box.setReadOnly(True)
        self.webdesign_tabs.addTab(self.webdesign_js_box, "JS")
        layout.addWidget(self.webdesign_tabs, 1)

        self.webdesign_panel.hide()
        self.webdesign_load_models()

    # ── Wi-Fi Adapter panel ──────────────────────────────────────────────────
    # ── Wi-Fi handlers ───────────────────────────────────────────────────────
    # ── Web Design handlers ──────────────────────────────────────────────────
    def webdesign_load_models(self):
        """Kept as a method so existing call sites stay put."""
        self.webdesign_panel_base.load_models()

    def webdesign_generate(self):
        page_type = self.webdesign_type_box.currentText()
        style = self.webdesign_style_box.currentText()
        palette = self.webdesign_palette_input.text().strip()
        framework = self.webdesign_framework_box.currentText()
        brief = self.webdesign_brief_input.toPlainText().strip()
        provider = self.webdesign_provider_box.currentText()
        model = self.webdesign_model_box.currentText()

        if not brief:
            QMessageBox.warning(self, "Missing Input", "Please enter a brief describing what you want built.")
            return
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return

        prompt_parts = [
            f"Page Type: {page_type}",
            f"Style: {style}",
            f"Framework: {framework}",
        ]
        if palette:
            prompt_parts.append(f"Colour Palette: {palette}")
        prompt_parts.append(f"\nBrief:\n{brief}")

        prompt = "\n".join(prompt_parts)
        agent = self.agent_instances["webdesign"]
        messages = agent.build_messages(prompt)

        self._webdesign_clear_displays()
        self._last_webdesign_response = ""
        self.webdesign_status_label.setText("Generating...")
        self.webdesign_generate_btn.setEnabled(False)
        self.webdesign_stop_btn.setEnabled(True)
        self.webdesign_stop_btn.show()
        self.webdesign_save_btn.setEnabled(False)
        self.webdesign_copy_btn.setEnabled(False)

        if not self.authorize_request("webdesign", provider, model, prompt):
            return
        self.webdesign_worker = ChatWorker(self.run_backend, provider, model, messages, prompt)
        self.webdesign_worker.token_signal.connect(self._webdesign_on_token)
        self.webdesign_worker.finished_signal.connect(self._webdesign_on_finished)
        self.webdesign_worker.usage_signal.connect(lambda u: self.note_request_usage("webdesign", u))
        self.webdesign_worker.error_signal.connect(self._webdesign_on_error)
        self.webdesign_worker.start()

    def _webdesign_on_token(self, token: str):
        self._last_webdesign_response += token
        self.webdesign_html_box.setPlainText(self._last_webdesign_response)
        self.webdesign_html_box.moveCursor(QTextCursor.End)

    def _webdesign_on_finished(self, full_response: str):
        self.record_request("webdesign", full_response)
        self._last_webdesign_response = full_response
        self._populate_webdesign_tabs(full_response)
        self._update_webdesign_indicators(full_response)
        self.webdesign_status_label.setText("Generation complete.")
        self.webdesign_generate_btn.setEnabled(True)
        self.webdesign_stop_btn.setEnabled(False)
        self.webdesign_stop_btn.hide()
        self.webdesign_save_btn.setEnabled(True)
        self.webdesign_copy_btn.setEnabled(True)

    def _webdesign_on_error(self, error: str):
        self.abandon_request("webdesign")
        self.webdesign_html_box.setPlainText(f"[Error] {error}")
        self.webdesign_status_label.setText("Error.")
        self.webdesign_generate_btn.setEnabled(True)
        self.webdesign_stop_btn.setEnabled(False)
        self.webdesign_stop_btn.hide()

    def webdesign_stop(self):
        if self.webdesign_worker is not None and self.webdesign_worker.isRunning():
            self.webdesign_worker.cancel()
        self.webdesign_status_label.setText("Stopped.")
        self.webdesign_generate_btn.setEnabled(True)
        self.webdesign_stop_btn.setEnabled(False)
        self.webdesign_stop_btn.hide()

    def webdesign_save(self):
        if not self._last_webdesign_response:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"webdesign_{ts}.html"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save HTML File", str(DATA_DIR / default_name),
            "HTML files (*.html);;All files (*)"
        )
        if path:
            full_html = self._extract_full_html(self._last_webdesign_response)
            Path(path).write_text(full_html, encoding="utf-8")

    def webdesign_copy_all(self):
        if not self._last_webdesign_response:
            return
        full_html = self._extract_full_html(self._last_webdesign_response)
        QApplication.clipboard().setText(full_html)
        self.webdesign_status_label.setText("Copied to clipboard.")

    def webdesign_clear(self):
        self._webdesign_clear_displays()
        self.webdesign_brief_input.clear()
        self.webdesign_status_label.setText("")
        self._last_webdesign_response = ""

    def _webdesign_clear_displays(self):
        self.webdesign_html_box.clear()
        self.webdesign_css_box.clear()
        self.webdesign_js_box.clear()
        self.webdesign_responsive_label.setText("—")
        self.webdesign_framework_label.setText("—")
        self.webdesign_lines_label.setText("—")
        self.webdesign_save_btn.setEnabled(False)
        self.webdesign_copy_btn.setEnabled(False)

    def _extract_full_html(self, text: str) -> str:
        import re as _re
        m = _re.search("```(?:html)?\\s*\\n(.*?)```", text, _re.DOTALL | _re.IGNORECASE)
        return m.group(1).strip() if m else text.strip()

    def _populate_webdesign_tabs(self, text: str):
        import re as _re
        # Full HTML in first tab
        full = self._extract_full_html(text)
        self.webdesign_html_box.setPlainText(full)

        # Extract <style> blocks into CSS tab
        css_parts = _re.findall(r"<style[^>]*>(.*?)</style>", full, _re.DOTALL | _re.IGNORECASE)
        self.webdesign_css_box.setPlainText("\n\n".join(p.strip() for p in css_parts) if css_parts else "")

        # Extract <script> blocks into JS tab
        js_parts = _re.findall(r"<script[^>]*>(.*?)</script>", full, _re.DOTALL | _re.IGNORECASE)
        self.webdesign_js_box.setPlainText("\n\n".join(p.strip() for p in js_parts) if js_parts else "")

    def _update_webdesign_indicators(self, text: str):
        import re as _re
        full = self._extract_full_html(text)

        # Responsive detection
        if "viewport" in full.lower() or "@media" in full.lower():
            self.webdesign_responsive_label.setText("Mobile-first")
        else:
            self.webdesign_responsive_label.setText("Desktop")

        # Framework
        fw = self.webdesign_framework_box.currentText()
        self.webdesign_framework_label.setText(fw)

        # Line count
        line_count = len(full.splitlines())
        self.webdesign_lines_label.setText(str(line_count))

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
          DALL-E for the graphics work it was already doing.
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

    # ── Creator (subscription accounts) ──────────────────────────────────────
    def build_creator_panel(self):
        """Plan and draft for subscription creator accounts.

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
        layout.addWidget(section("Account"))

        self.creator_account_box = QComboBox()
        self.creator_account_box.currentIndexChanged.connect(self._creator_account_changed)
        self.creator_handle_input = line_edit("@handle")
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
        account.addWidget(field("Account", self.creator_account_box), 0, 0, Qt.AlignTop)
        account.addWidget(field("Handle", self.creator_handle_input), 0, 1, Qt.AlignTop)
        account.addWidget(field("Type", self.creator_type_box), 0, 2, Qt.AlignTop)
        account.addWidget(self.creator_consent_field, 1, 0, 1, 2, Qt.AlignTop)
        account.addWidget(self.creator_disclosure_field, 1, 2, Qt.AlignTop)
        for column in range(3):
            account.setColumnStretch(column, 1)
        layout.addLayout(account)

        account_actions = QHBoxLayout()
        account_actions.setSpacing(SM)
        self.creator_save_account_btn = QPushButton("Save Account")
        self.creator_save_account_btn.clicked.connect(self.creator_save_account)
        account_actions.addWidget(self.creator_save_account_btn)
        self.creator_delete_account_btn = quiet("Remove account")
        self.creator_delete_account_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.creator_delete_account_btn.clicked.connect(self.creator_delete_account)
        account_actions.addWidget(self.creator_delete_account_btn)
        account_actions.addStretch()
        layout.addLayout(account_actions)

        # ── Compose ─────────────────────────────────────────────────────
        layout.addWidget(section("Compose"))

        self.creator_kind_box = combo(
            ["post", "ppv", "welcome", "promo", "bio", "campaign", "hooks"])
        self.creator_kind_box.currentTextChanged.connect(self._creator_kind_changed)
        self.creator_price_input = line_edit("12.00")
        self.creator_segment_box = combo(
            ["(any)", "new", "loyal", "lapsed", "big_spender"])
        self.creator_channel_box = combo(list(PROMO_CHANNELS))

        self.creator_price_field = field("Price (USD)", self.creator_price_input)
        self.creator_segment_field = field("Audience", self.creator_segment_box)
        self.creator_channel_field = field("Promo channel", self.creator_channel_box)

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

        self.creator_earnings_output = QTextEdit()
        self.creator_earnings_output.setReadOnly(True)
        self.creator_earnings_output.setPlaceholderText(
            "No earnings imported yet. There is no OnlyFans API, so export the "
            "statement from the site and import the CSV here.")
        self.creator_revenue_btn = QPushButton("Record Revenue")
        self.creator_revenue_btn.clicked.connect(self.creator_record_revenue)
        self.creator_import_btn = QPushButton("Import Earnings CSV")
        self.creator_import_btn.clicked.connect(self.creator_import_earnings)
        self.creator_tabs.addTab(
            self._creator_tab_with_actions(
                self.creator_earnings_output,
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

    def _creator_kind_changed(self, kind: str):
        # Which fields apply, in the order they should appear. Kind is always
        # shown; the other three depend on it.
        wanted = [
            (self.creator_kind_field, True),
            (self.creator_price_field, kind == "ppv"),
            # Audience only shapes a message aimed at someone.
            (self.creator_segment_field, kind in ("welcome", "ppv", "post")),
            (self.creator_channel_field, kind == "promo"),
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
                    "SELECT id, handle, account_type FROM creator_accounts "
                    "ORDER BY handle").fetchall()
            for row in rows:
                self.creator_account_box.addItem(
                    f"{row['handle']}  ({row['account_type']})", row["id"])
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
            QMessageBox.warning(self, "No Handle", "Enter the account handle first.")
            return
        account_type = self.creator_type_box.currentText()
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
                      account_type=excluded.account_type,
                      consent_holder=excluded.consent_holder,
                      disclosure=excluded.disclosure
                """, (handle, "onlyfans", account_type, consent,
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
            self, "Remove Account",
            f"Remove {account['handle']} and its drafts and earnings from "
            "Imprint?\n\nThis only affects this app — nothing on the platform "
            "is touched.")
        if confirm != QMessageBox.Yes:
            return
        try:
            with get_connection() as conn:
                for table in ("creator_content", "creator_earnings"):
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
            QMessageBox.warning(self, "No Account",
                                "Add an account before drafting.")
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
        if not self.authorize_request("creator", provider, model,
                                      messages[-1]["content"], label=kind):
            return

        self.creator_generate_btn.setEnabled(False)
        self.creator_stop_btn.setEnabled(True)
        self.creator_stop_btn.show()
        self.creator_status_label.setText(f"Drafting {kind}…")
        self.creator_output.clear()

        self.creator_worker = ChatWorker(self.run_backend, provider, model, messages, "")
        self.creator_worker.finished_signal.connect(self._creator_on_finished)
        self.creator_worker.error_signal.connect(self._creator_on_error)
        self.creator_worker.start()

    def _creator_on_finished(self, response: str):
        self.creator_output.setPlainText(response)
        self.record_request("creator", response)
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText("Draft ready — review before posting.")

    def _creator_on_error(self, error: str):
        self.abandon_request("creator")
        self.creator_generate_btn.setEnabled(True)
        self.creator_stop_btn.setEnabled(False)
        self.creator_stop_btn.hide()
        self.creator_status_label.setText(f"[Error] {error}")

    def creator_stop(self):
        if self.creator_worker is not None and self.creator_worker.isRunning():
            self.creator_worker.terminate()
            self.creator_worker.wait(1000)
        self.abandon_request("creator", reason="stopped")
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
                       body, price_usd, status)
                    VALUES (?,?,?,?,?,?,?,'draft')
                """, (account["id"],
                      datetime.now().isoformat(timespec="seconds"),
                      when.strip(),
                      self.creator_kind_box.currentText(),
                      body.splitlines()[0][:80] if body else "",
                      body, price))
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
                "Set HIGGSFIELD_API_KEY in the .env under Application Support "
                "to generate promo video.")
            return
        try:
            check_prompt(prompt)
        except ContentPolicyError as exc:
            QMessageBox.warning(self, "Higgsfield Content Policy", str(exc))
            return

        # A Higgsfield render is real money and, until the guard learned
        # per-unit costs, went out with no budget check, no confirmation and no
        # entry in the spend counters — the same class of bug as the 19
        # unguarded ChatWorker sites, reintroduced by adding a second paid
        # provider. It is priced per render, which the token model cannot say.
        from services.per_unit_pricing import render_cost_eur
        render_cost = render_cost_eur()
        if render_cost is None:
            proceed = QMessageBox.question(
                self, "Render cost is not priced",
                "Higgsfield bills per render and no rate is set, so this "
                "render cannot be counted against your budget caps.\n\n"
                'Set "higgsfield_render" under "per_unit_usd" in '
                "config/pricing.json to have it billed.\n\nRender anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if proceed != QMessageBox.Yes:
                return
        if not self.authorize_request(
                "creator", "higgsfield", "higgsfield-video", prompt,
                label="promo teaser",
                flat_cost_eur=render_cost if render_cost is not None else 0.0):
            return

        # Personas reuse their locked seed and reference image so successive
        # renders are the same character rather than a new one each time.
        seed = persona_seed(account["id"])
        references = reference_images(account["id"])

        output_dir = Path(BASE_DIR) / "output" / "creator" / str(account["id"])
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = output_dir / f"teaser-{stamp}.mp4"

        self.creator_video_btn.setEnabled(False)
        self.creator_video_status.setText("Submitting to Higgsfield…")

        self.creator_video_worker = HiggsfieldWorker(
            client, prompt, output_path, seed=seed,
            reference_image=references[0] if references else None)
        self.creator_video_worker.status_signal.connect(
            self.creator_video_status.setText)
        self.creator_video_worker.done_signal.connect(
            lambda path, aid=account["id"]: self._creator_video_done(aid, path))
        self.creator_video_worker.error_signal.connect(
            self._creator_video_error)
        self.creator_video_worker.start()

    def _creator_video_done(self, account_id: int, path: str):
        """Store the render in the media library rather than leaving it on disk."""
        self.record_request("creator", f"teaser: {Path(path).name}")
        self._creator_store_media(account_id, path, source="higgsfield",
                                  caption="Higgsfield teaser")
        self.creator_video_btn.setEnabled(True)
        self.creator_video_status.setText(f"Saved: {Path(path).name}")
        self.creator_refresh_media()

    def _creator_video_error(self, error: str):
        self.abandon_request("creator")
        self.creator_video_btn.setEnabled(True)
        self.creator_video_status.setText(f"[Error] {error}")

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
        if not rows:
            self.creator_earnings_output.setPlainText(
                "No earnings imported yet.\n\nThere is no OnlyFans API, so "
                "export the statement from the site and import the CSV.")
            return

        summary = account_summary(account["id"])
        lines = [
            "OVERVIEW",
            f"  Statements imported : {summary['statements']}",
            f"  Gross / Net         : ${summary['gross']:,.2f} / ${summary['net']:,.2f}",
            f"  Subscribers (peak)  : {summary['subscribers']}",
            f"  Net per subscriber  : ${summary['per_subscriber']:,.2f}",
            f"  Posted items        : {summary['posted']}"
            f"  (attributed ${summary['attributed']:,.2f})",
        ]

        points = price_points(account["id"])
        if points:
            lines += ["", "PRICE POINTS  (what each PPV price actually returned)"]
            for point in points:
                thin = "" if point["sends"] >= 5 else "   ← few sends, treat as anecdote"
                lines.append(
                    f"  ${point['price_usd']:>7.2f}  ×{point['sends']:<3}  "
                    f"avg ${point['average']:>8.2f}  total ${point['total']:>9.2f}{thin}")

        best = top_content(account["id"])
        if best:
            lines += ["", "TOP CONTENT"]
            for item in best:
                lines.append(
                    f"  ${item['revenue_usd']:>9.2f}  {item['kind']:<9} "
                    f"{(item['title'] or '')[:52]}")

        hooks = hook_results(account["id"])
        if hooks:
            lines += ["", "HOOKS THAT SHIPPED"]
            for hook in hooks[:8]:
                lines.append(f"  ${hook['revenue_usd']:>9.2f}  {hook['body'][:60]}")

        lines += ["", "STATEMENTS"]
        for r in rows:
            lines.append(
                f"  {r['source_file']}  {r['period_from']}–{r['period_to']}  "
                f"gross ${r['gross_usd']:,.2f}  net ${r['net_usd']:,.2f}  "
                f"subs {r['subscribers']}")
        self.creator_earnings_output.setPlainText("\n".join(lines))

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
                      caption=excluded.caption, source=excluded.source
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

        if not self.authorize_request("fiverr", provider, model, messages[-1]["content"] if messages else ""):
            return
        self.fiverr_text_worker = ChatWorker(self.run_backend, provider, model, messages, "")
        self.fiverr_text_worker.finished_signal.connect(self._fiverr_on_prompt_ready)
        self.fiverr_text_worker.usage_signal.connect(lambda u: self.note_request_usage("fiverr", u))
        self.fiverr_text_worker.error_signal.connect(self._fiverr_on_text_error)
        self.fiverr_text_worker.start()
        self._fiverr_pending_count = count
        self._fiverr_pending_brief = brief

    def _fiverr_on_prompt_ready(self, image_prompt: str):
        from services.per_unit_pricing import image_cost_eur
        self.record_request("fiverr", image_prompt)
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
        if not self.authorize_request(
                "fiverr", "openai", image_model,
                f"{count} logo concepts: {image_prompt[:200]}",
                label="logo images",
                flat_cost_eur=image_cost if image_cost is not None else 0.0):
            self._fiverr_reset_buttons()
            return
        self._fiverr_image_token = True

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
        self.record_request("fiverr", f"{len(paths)} logo images")
        self._fiverr_reset_buttons()
        self.fiverr_save_images_btn.setEnabled(True)
        if hasattr(self, "_fiverr_order_row"):
            from PySide6.QtWidgets import QTableWidgetItem
            self.fiverr_order_table.setItem(self._fiverr_order_row, 2, QTableWidgetItem("Done"))

    def _fiverr_on_image_error(self, error: str):
        # A failed render still consumed whatever it managed before failing,
        # but the authorised amount was for the full set — release it rather
        # than bill for images that were never produced.
        self.abandon_request("fiverr")
        self.fiverr_status_label.setText(f"Error: {error}")
        self.fiverr_preview_status.setText(f"[Error] {error}")
        self._fiverr_reset_buttons()
        if hasattr(self, "_fiverr_order_row"):
            from PySide6.QtWidgets import QTableWidgetItem
            self.fiverr_order_table.setItem(self._fiverr_order_row, 2, QTableWidgetItem("Error"))

    def _fiverr_on_text_error(self, error: str):
        self.abandon_request("fiverr")
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
        if not self.authorize_request("fiverr", provider, model, messages[-1]["content"] if messages else ""):
            return
        self.fiverr_text_worker = ChatWorker(self.run_backend, provider, model, messages, "")
        self.fiverr_text_worker.token_signal.connect(self._fiverr_on_delivery_token)
        self.fiverr_text_worker.finished_signal.connect(self._fiverr_on_delivery_done)
        self.fiverr_text_worker.usage_signal.connect(lambda u: self.note_request_usage("fiverr", u))
        self.fiverr_text_worker.error_signal.connect(self._fiverr_on_text_error)
        self.fiverr_text_worker.start()

    def _fiverr_on_delivery_token(self, token: str):
        self.fiverr_delivery_box.moveCursor(QTextCursor.End)
        self.fiverr_delivery_box.insertPlainText(token)

    def _fiverr_on_delivery_done(self, _full: str):
        self.record_request("fiverr", _full)
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
        if not self.authorize_request("fiverr", provider, model, messages[-1]["content"] if messages else ""):
            return
        self.fiverr_text_worker = ChatWorker(self.run_backend, provider, model, messages, "")
        self.fiverr_text_worker.token_signal.connect(self._fiverr_on_gig_token)
        self.fiverr_text_worker.finished_signal.connect(self._fiverr_on_gig_done)
        self.fiverr_text_worker.usage_signal.connect(lambda u: self.note_request_usage("fiverr", u))
        self.fiverr_text_worker.error_signal.connect(self._fiverr_on_text_error)
        self.fiverr_text_worker.start()

    def _fiverr_on_gig_token(self, token: str):
        self.fiverr_gig_box.moveCursor(QTextCursor.End)
        self.fiverr_gig_box.insertPlainText(token)

    def _fiverr_on_gig_done(self, _full: str):
        self.record_request("fiverr", _full)
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
        self.author_status_label.setText("[Working…]")
        self.author_write_btn.setEnabled(False)
        self.author_continue_btn.setEnabled(False)
        self.author_stop_btn.setEnabled(True)
        if not self.authorize_request("author", provider, model, prompt):
            return
        self.author_worker = ChatWorker(self.run_backend, provider, model, messages, prompt)
        self.author_worker.token_signal.connect(self._author_on_token)
        self.author_worker.finished_signal.connect(self._author_on_finished)
        self.author_worker.usage_signal.connect(lambda u: self.note_request_usage("author", u))
        self.author_worker.error_signal.connect(self._author_on_error)
        self.author_worker.start()

    def author_write(self):
        direction = self.author_direction_input.toPlainText().strip()
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
        direction = self.author_direction_input.toPlainText().strip()
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
        self.record_request("author", full_response)
        self._populate_author_tabs(full_response)
        word_count = len(self.author_draft_box.toPlainText().split())
        self.author_status_label.setText(f"[Done] {word_count:,} words")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)
        self.author_save_btn.setEnabled(True)
        self._refresh_next_step_tip()

    def _author_on_error(self, error: str):
        self.abandon_request("author")
        self.author_status_label.setText(f"[Error] {error}")
        self.author_write_btn.setEnabled(True)
        self.author_continue_btn.setEnabled(True)
        self.author_stop_btn.setEnabled(False)

    def author_stop(self):
        if self.author_worker is not None and self.author_worker.isRunning():
            self.author_worker.cancel()
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
        author_name = self.author_export_author_input.text().strip() or "Unknown Author"

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

        if not self.authorize_request("author", provider, model, prompt):
            return
        self.author_pub_worker = ChatWorker(self.run_backend, provider, model, messages, prompt)
        self.author_pub_worker.token_signal.connect(self._author_pub_on_token)
        self.author_pub_worker.finished_signal.connect(self._author_pub_on_finished)
        self.author_pub_worker.usage_signal.connect(lambda u: self.note_request_usage("author", u))
        self.author_pub_worker.error_signal.connect(self._author_pub_on_error)
        self.author_pub_worker.start()

    def _author_pub_on_token(self, token: str):
        cursor = self.author_pub_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_pub_output.setTextCursor(cursor)

    def _author_pub_on_finished(self, full_response: str):
        self.record_request("author", full_response)
        self.author_status_label.setText(
            f"[Done] {self.author_pub_type_box.currentText()} generated"
        )
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)
        self.author_pub_save_btn.setEnabled(True)

    def _author_pub_on_error(self, error: str):
        self.abandon_request("author")
        self.author_status_label.setText(f"[Error] {error}")
        self.author_pub_generate_btn.setEnabled(True)
        self.author_pub_stop_btn.setEnabled(False)

    def author_pub_stop(self):
        if self.author_pub_worker is not None and self.author_pub_worker.isRunning():
            self.author_pub_worker.cancel()
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

        if not self.authorize_request("author", provider, model, prompt):
            return
        self.author_mkt_worker = ChatWorker(self.run_backend, provider, model, messages, prompt)
        self.author_mkt_worker.token_signal.connect(self._author_mkt_on_token)
        self.author_mkt_worker.finished_signal.connect(self._author_mkt_on_finished)
        self.author_mkt_worker.usage_signal.connect(lambda u: self.note_request_usage("author", u))
        self.author_mkt_worker.error_signal.connect(self._author_mkt_on_error)
        self.author_mkt_worker.start()

    def _author_mkt_on_token(self, token: str):
        cursor = self.author_mkt_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.author_mkt_output.setTextCursor(cursor)

    def _author_mkt_on_finished(self, full_response: str):
        self.record_request("author", full_response)
        self.author_status_label.setText(
            f"[Done] {self.author_mkt_platform_box.currentText()} copy generated"
        )
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)
        self.author_mkt_save_btn.setEnabled(True)

    def _author_mkt_on_error(self, error: str):
        self.abandon_request("author")
        self.author_status_label.setText(f"[Error] {error}")
        self.author_mkt_generate_btn.setEnabled(True)
        self.author_mkt_stop_btn.setEnabled(False)

    def author_mkt_stop(self):
        if self.author_mkt_worker is not None and self.author_mkt_worker.isRunning():
            self.author_mkt_worker.cancel()
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
        if not self.authorize_request("manuscript", provider, model, query):
            return
        self.manuscript_worker = ChatWorker(self.run_backend, provider, model, messages, query)
        self.manuscript_worker.token_signal.connect(self._manuscript_on_token)
        self.manuscript_worker.finished_signal.connect(self._manuscript_on_finished)
        self.manuscript_worker.usage_signal.connect(lambda u: self.note_request_usage("manuscript", u))
        self.manuscript_worker.error_signal.connect(self._manuscript_on_error)
        self.manuscript_worker.start()

    def _manuscript_on_token(self, token: str):
        cursor = self.manuscript_metrics_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.manuscript_metrics_box.setTextCursor(cursor)

    def _manuscript_on_finished(self, _full_response: str):
        self.record_request("manuscript", _full_response)
        self.manuscript_status_label.setText("[Done]")
        self.manuscript_ask_btn.setEnabled(True)

    def _manuscript_on_error(self, error: str):
        self.abandon_request("manuscript")
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
        self._last_short_path = output_path
        self.manuscript_status_label.setText(f"[Done] Saved {Path(output_path).name}")
        self.shorts_generate_btn.setEnabled(True)
        self.shorts_play_btn.setEnabled(True)

    def _shorts_on_error(self, error: str):
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
        if not self.authorize_request("manuscript", provider, model, truncated):
            return
        self.quote_finder_worker = ChatWorker(self.run_backend, provider, model, messages, truncated)
        self.quote_finder_worker.finished_signal.connect(self._quote_finder_on_finished)
        self.quote_finder_worker.usage_signal.connect(lambda u: self.note_request_usage("manuscript", u))
        self.quote_finder_worker.error_signal.connect(self._quote_finder_on_error)
        self.quote_finder_worker.start()

    def _quote_finder_on_finished(self, full_response: str):
        self.record_request("manuscript", full_response)
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
        self.abandon_request("manuscript")
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
        self._last_short_path = output_path
        self.manuscript_status_label.setText(f"[Done] Saved {Path(output_path).name}")
        button.setText("Short")
        self._quote_finder_busy = False
        for b in self._quote_finder_short_buttons:
            b.setEnabled(True)

    def _quote_finder_short_error(self, error: str, button: QPushButton):
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
        if not self.authorize_request("manuscript", provider, model, items_json):
            return
        self.calendar_worker = ChatWorker(self.run_backend, provider, model, messages, items_json)
        self.calendar_worker.finished_signal.connect(self._calendar_on_captions_done)
        self.calendar_worker.usage_signal.connect(lambda u: self.note_request_usage("manuscript", u))
        self.calendar_worker.error_signal.connect(self._calendar_on_captions_error)
        self.calendar_worker.start()

    def _calendar_on_captions_done(self, full_response: str):
        self.record_request("manuscript", full_response)
        self.calendar_generate_btn.setEnabled(True)
        captions = self._parse_quote_list(full_response)
        for i, slot in enumerate(self._calendar_slots):
            slot.caption = captions[i] if i < len(captions) else ""
        self._populate_calendar_table()
        self.manuscript_status_label.setText(f"[Done] {len(self._calendar_slots)}-post calendar generated.")

    def _calendar_on_captions_error(self, error: str):
        self.abandon_request("manuscript")
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

        self._quote_finder_busy = True
        button.setEnabled(False)
        self.manuscript_status_label.setText("[Narrating…]")
        self.shorts_worker = ShortsWorker(slot.quote, image_path, output_path, use_elevenlabs, voice_id)
        self.shorts_worker.status_signal.connect(self.manuscript_status_label.setText)
        self.shorts_worker.done_signal.connect(lambda path, b=button: self._calendar_short_done(path, b))
        self.shorts_worker.error_signal.connect(lambda err, b=button: self._calendar_short_error(err, b))
        self.shorts_worker.start()

    def _calendar_short_done(self, output_path: str, button: QPushButton):
        self._last_short_path = output_path
        self.manuscript_status_label.setText(f"[Done] Saved {Path(output_path).name}")
        button.setEnabled(True)
        self._quote_finder_busy = False

    def _calendar_short_error(self, error: str, button: QPushButton):
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

    # ── Music handlers ────────────────────────────────────────────────────────
    def music_load_models(self):
        """Kept as a method so existing call sites stay put."""
        self.music_panel_base.load_models()

    def music_analyse(self):
        description = self.music_query_input.toPlainText().strip()
        artist = self.music_artist_input.text().strip()
        genre = self.music_genre_box.currentText()
        release_type = self.music_release_type_box.currentText()
        distributor = self.music_distributor_box.currentText()
        audience = self.music_audience_input.text().strip()
        provider = self.music_provider_box.currentText()
        model = self.music_model_box.currentText()

        if not description:
            QMessageBox.warning(self, "Missing Input", "Please describe your music in the text box.")
            return
        if not model:
            QMessageBox.warning(self, "No Model", "Please select a model.")
            return

        prompt_parts = []
        if artist:
            prompt_parts.append(f"Artist / Project Name: {artist}")
        prompt_parts += [
            f"Genre: {genre}",
            f"Release Type: {release_type}",
            f"Current Distributor: {distributor}",
        ]
        if audience:
            prompt_parts.append(f"Target Audience: {audience}")
        prompt_parts.append(f"\nMusic Description:\n{description}")
        prompt = "\n".join(prompt_parts)

        agent = self.agent_instances["music"]
        messages = agent.build_messages(prompt)

        self._music_clear_displays()
        self._last_music_response = ""
        self.music_status_label.setText("Generating Spotify plan…")
        self.music_analyse_btn.setEnabled(False)
        self.music_stop_btn.setEnabled(True)
        self.music_stop_btn.show()
        self.music_save_btn.setEnabled(False)

        if not self.authorize_request("music", provider, model, prompt):
            return
        self.music_worker = ChatWorker(self.run_backend, provider, model, messages, prompt)
        self.music_worker.token_signal.connect(self._music_on_token)
        self.music_worker.finished_signal.connect(self._music_on_finished)
        self.music_worker.usage_signal.connect(lambda u: self.note_request_usage("music", u))
        self.music_worker.error_signal.connect(self._music_on_error)
        self.music_worker.start()

    def _music_on_token(self, token: str):
        self._last_music_response += token
        self.music_profile_box.setPlainText(self._last_music_response)
        self.music_profile_box.moveCursor(QTextCursor.End)

    def _music_on_finished(self, full_response: str):
        self.record_request("music", full_response)
        self._last_music_response = full_response
        self._populate_music_tabs(full_response)
        self.music_status_label.setText("Plan complete — tabs populated.")
        self.music_analyse_btn.setEnabled(True)
        self.music_stop_btn.setEnabled(False)
        self.music_stop_btn.hide()
        self.music_save_btn.setEnabled(True)

    def _music_on_error(self, error: str):
        self.abandon_request("music")
        self.music_profile_box.setPlainText(f"[Error] {error}")
        self.music_status_label.setText("Error.")
        self.music_analyse_btn.setEnabled(True)
        self.music_stop_btn.setEnabled(False)
        self.music_stop_btn.hide()

    def music_stop(self):
        if self.music_worker is not None and self.music_worker.isRunning():
            self.music_worker.cancel()
        self.music_status_label.setText("Stopped.")
        self.music_analyse_btn.setEnabled(True)
        self.music_stop_btn.setEnabled(False)
        self.music_stop_btn.hide()

    def music_save(self):
        if not self._last_music_response:
            return
        artist = self.music_artist_input.text().strip().lower().replace(" ", "_") or "artist"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"spotify_plan_{artist}_{ts}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Spotify Plan", str(DATA_DIR / default_name), "Text files (*.txt);;All files (*)"
        )
        if path:
            Path(path).write_text(self._last_music_response, encoding="utf-8")
            self.music_status_label.setText(f"Saved to {Path(path).name}")

    def music_clear(self):
        self._music_clear_displays()
        self.music_query_input.clear()
        self.music_artist_input.clear()
        self.music_audience_input.clear()
        self.music_status_label.setText("")
        self._last_music_response = ""

    def _music_clear_displays(self):
        for box in (
            self.music_profile_box,
            self.music_release_box,
            self.music_distribution_box,
            self.music_strategy_box,
            self.music_income_box,
        ):
            box.clear()
        self.music_save_btn.setEnabled(False)

    def _populate_music_tabs(self, text: str):
        sections = self._parse_music_sections(text)
        self.music_profile_box.setPlainText(sections.get("profile", text))
        self.music_release_box.setPlainText(sections.get("release", ""))
        self.music_distribution_box.setPlainText(sections.get("distribution", ""))
        self.music_strategy_box.setPlainText(sections.get("strategy", ""))
        self.music_income_box.setPlainText(sections.get("income", ""))

    def _parse_music_sections(self, text: str) -> dict:
        patterns = {
            "profile":      r"1\.\s*ARTIST PROFILE(.*?)(?=2\.\s*RELEASE SETUP|$)",
            "release":      r"2\.\s*RELEASE SETUP(.*?)(?=3\.\s*DISTRIBUTION GUIDE|$)",
            "distribution": r"3\.\s*DISTRIBUTION GUIDE(.*?)(?=4\.\s*SPOTIFY STRATEGY|$)",
            "strategy":     r"4\.\s*SPOTIFY STRATEGY(.*?)(?=5\.\s*INCOME ROADMAP|$)",
            "income":       r"5\.\s*INCOME ROADMAP(.*?)$",
        }
        result = {}
        for key, pat in patterns.items():
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            result[key] = m.group(1).strip() if m else ""
        return result

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
        rail_outer.addWidget(scrollable(rail_body))
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
        layout.addWidget(self.session_meter)
        layout.addWidget(self.daily_meter)

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

        layout.addStretch()

        # ── Utilities: open a window, change nothing. Links, not buttons. ──
        layout.addWidget(rule())
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

        system_card = CollapsibleSection("SYSTEM", expanded=False)
        system_body = QWidget()
        system_body.setObjectName("Transparent")
        system_layout = QVBoxLayout(system_body)
        system_layout.setContentsMargins(SM, XS, SM, SM)
        system_layout.setSpacing(SM)
        self.resource_label = QLabel()
        self.resource_label.setTextFormat(Qt.RichText)
        self.resource_label.setWordWrap(True)
        self.resource_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.resource_label.setObjectName("ResourceLabel")
        system_layout.addWidget(self.resource_label)
        self.realtime_monitor_btn = QPushButton("Realtime Monitor")
        self.realtime_monitor_btn.setEnabled(False)
        system_layout.addWidget(self.realtime_monitor_btn)
        system_card.addWidget(system_body)
        reference.addWidget(system_card)

        routing_card = CollapsibleSection("ROUTING", expanded=False)
        routing_body = QWidget()
        routing_body.setObjectName("Transparent")
        routing_layout = QVBoxLayout(routing_body)
        routing_layout.setContentsMargins(SM, XS, SM, SM)
        routing_layout.setSpacing(XS)
        self.route_result_label = QLabel("Router: not yet computed")
        self.route_result_label.setWordWrap(True)
        routing_layout.addWidget(self.route_result_label)
        self.recommendation_label = QLabel("Recommendation: not yet calculated")
        self.recommendation_label.setWordWrap(True)
        routing_layout.addWidget(self.recommendation_label)
        routing_card.addWidget(routing_body)
        reference.addWidget(routing_card)

        keys_card = CollapsibleSection("API KEYS", expanded=False)
        keys_body = QWidget()
        keys_body.setObjectName("Transparent")
        keys_layout = QVBoxLayout(keys_body)
        keys_layout.setContentsMargins(SM, XS, SM, SM)
        keys_layout.setSpacing(XS)
        self.openai_key_label = QLabel(f"OpenAI: {self.safe_key_status(OpenAIClientWrapper)}")
        self.deepseek_key_label = QLabel(f"DeepSeek: {self.safe_key_status(DeepSeekClientWrapper)}")
        self.kimi_key_label = QLabel(f"Kimi: {self.safe_key_status(KimiClientWrapper)}")
        self.gemini_key_label = QLabel(f"Gemini: {self.safe_key_status(GeminiClientWrapper)}")
        self.anthropic_key_label = QLabel(f"Anthropic: {self.safe_key_status(AnthropicClientWrapper)}")
        for key_label in (self.openai_key_label, self.deepseek_key_label,
                          self.kimi_key_label, self.gemini_key_label,
                          self.anthropic_key_label):
            keys_layout.addWidget(key_label)
        keys_card.addWidget(keys_body)
        reference.addWidget(keys_card)

        layout.addLayout(reference)

        return right_widget

    def load_provider_models(self):
        if not hasattr(self, "provider_box") or not hasattr(self, "model_box"):
            return

        provider = self.provider_box.currentText()
        previous_model = self.settings.get(f"default_model_{provider}", "")

        self.model_box.clear()

        try:
            if provider == "ollama":
                models = self.ollama.list_models()
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
                    models = [
                        "gemini-1.5-flash",
                        "gemini-1.5-pro",
                        "gemini-2.0-flash",
                        "gemini-2.5-flash",
                        "gemini-2.5-pro",
                    ]

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
        agent_titles = {
            "chat": "Studio Assistant", "fiverr": "Client Gigs",
            "author": "Draft", "manuscript": "Publish", "music": "Music",
            "webdesign": "Site Builder", "audiobook": "Audiobooks",
            "creator": "Creator", }
        agent_subtitles = {
            "chat":        "General-purpose conversation. Pick a tool, pick a model, talk.",
            "fiverr":      "Create client-ready logo concepts, gig listings, and polished delivery messages.",
            "author":      "Plan, draft, revise, and export long-form fiction and non-fiction.",
            "manuscript":  "Prepare a finished book for distribution, marketing, and ongoing sales tracking.",
            "music":       "Plan releases, distribution, promotion, and sustainable artist income.",
            "webdesign":   "Modern HTML, CSS, and JavaScript generation with responsive layout and design advice.",
            "audiobook":   "Turn PDF, EPUB, TXT, and MOBI books into production-ready MP3 audiobooks.",
            "creator":     "Plan, draft, and schedule subscription content across accounts you hold consent for.",
            }
        if hasattr(self, "agent_title_label"):
            self.agent_title_label.setText(
                agent_titles.get(agent_name, agent_name.title()))
        if hasattr(self, "agent_subtitle_label"):
            self.agent_subtitle_label.setText(agent_subtitles.get(agent_name, ""))
        if hasattr(self, "agent_status_pill"):
            self.agent_status_pill.setText("●  Ready")
            self.agent_status_pill.setStyleSheet("")

        is_audiobook = agent_name == "audiobook"
        is_author = agent_name == "author"
        is_manuscript = agent_name == "manuscript"
        is_music = agent_name == "music"
        is_fiverr = agent_name == "fiverr"
        is_webdesign = agent_name == "webdesign"
        is_creator = agent_name == "creator"
        is_custom = (is_audiobook or is_author or is_manuscript
                     or is_music or is_fiverr or is_webdesign or is_creator)

        self.normal_panel.setVisible(not is_custom)
        self.audiobook_panel.setVisible(is_audiobook)
        self.author_panel.setVisible(is_author)
        self.manuscript_panel.setVisible(is_manuscript)
        self.music_panel.setVisible(is_music)
        self.fiverr_panel.setVisible(is_fiverr)
        self.creator_panel.setVisible(is_creator)
        self.webdesign_panel.setVisible(is_webdesign)
        # Output area only relevant for standard (non-custom) agents like Chat.
        # Within those, auto-hide if there is no content yet — keeps the UI clean.
        standard_agent_with_output = not is_custom
        has_output_content = bool(self.output_box.toPlainText().strip())
        show_output = standard_agent_with_output and has_output_content
        self.output_label.setVisible(show_output)
        self.output_box.setVisible(show_output)

        if is_audiobook:
            self.output_label.setText("Output Log")
            self.output_box.setPlainText("[Ready] Click Start to begin.")
            self.refresh_audiobook_books()
            self.refresh_audiobook_library()
        elif is_manuscript:
            from services.kdp_csv_parser import manuscript_seed_todos
            manuscript_seed_todos()
            self._load_manuscript_todos()
            self._refresh_next_step_tip()
        elif is_author:
            self._refresh_next_step_tip()
        elif is_music or is_fiverr or is_webdesign:
            pass
        else:
            self.output_label.setText("Output")

    def get_audiobook_defaults(self):
        tool = self.tool_runner.tools["audiobook"]
        return {
            "input": tool["default_input"],
            "output": tool["default_output"],
            "voice": tool.get("default_voice", "alloy"),
            "chunk_tokens": tool.get("default_chunk_tokens", 1400),
        }

    def refresh_audiobook_books(self):
        defaults = self.get_audiobook_defaults()
        input_folder = Path(defaults["input"]).expanduser()
        output_folder = Path(defaults["output"]).expanduser()

        self.audiobook_input_path.setText(str(input_folder))
        self.audiobook_output_path.setText(str(output_folder))
        self.audiobook_voice_box.setCurrentText(defaults["voice"])
        self.audiobook_chunk_input.setText(str(defaults["chunk_tokens"]))
        self.audiobook_book_list.clear()
        self.tool_progress.setValue(0)

        if not input_folder.exists():
            self.output_box.setPlainText(f"[Error] Input folder does not exist:\n{input_folder}")
            self.audiobook_status_label.setText("Choose an input folder to add your first book.")
            return

        books = sorted(f for f in input_folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EBOOKS)

        if not books:
            self.output_box.setPlainText(f"[Info] No supported ebooks found in:\n{input_folder}")
            self.audiobook_status_label.setText("No books yet — add a PDF, EPUB, TXT, or MOBI file.")
            return

        for book in books:
            item = QListWidgetItem(book.name)
            item.setData(Qt.UserRole, str(book))
            self.audiobook_book_list.addItem(item)

        if len(books) == 1:
            self.audiobook_book_list.setCurrentRow(0)

        self.output_box.setPlainText(f"[Ready] Found {len(books)} book(s). Select one and click Start.")
        self.audiobook_status_label.setText(f"[Ready] Found {len(books)} book(s).")
        self.estimate_audiobook_cost_from_selection()

    def show_empty_audiobook_folder_popup(self, folder_path: Path):
        msg = QMessageBox(self)
        msg.setWindowTitle("Audiobook Folder Empty")
        msg.setText(f"No supported ebooks found in:\n{folder_path}")
        open_btn = msg.addButton("Open Folder", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Ok)
        msg.exec()

        if msg.clickedButton() == open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_path)))

    def open_audiobook_input_folder(self):
        folder = self.audiobook_input_path.text().strip()
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def change_audiobook_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Audiobook Output Folder")
        if folder:
            self.audiobook_output_path.setText(folder)

    def estimate_audiobook_cost_from_selection(self):
        item = self.audiobook_book_list.currentItem()
        if not item:
            self.audiobook_cost_label.setText("Estimated cost: select a book first")
            return

        path = Path(item.data(Qt.UserRole))
        try:
            mb = max(0.1, path.stat().st_size / (1024 * 1024))
            rough = min(25.0, max(0.50, mb * 0.80))
            self.audiobook_cost_label.setText(f"Estimated cost: rough €{rough:.2f}–€{rough * 1.8:.2f} (file-size estimate)")
        except Exception:
            self.audiobook_cost_label.setText("Estimated cost: unavailable")

    def start_selected_audiobook_book(self):
        item = self.audiobook_book_list.currentItem()
        if not item:
            self.output_box.setPlainText("[Error] Please select a book first.")
            return

        book_path = item.data(Qt.UserRole)
        output_path = self.audiobook_output_path.text().strip()
        voice = self.audiobook_voice_box.currentText().strip()

        # Preflight: narrator needs an OpenAI key for TTS. Catch the most common
        # failure (missing key) before launching, so the user gets a clear message
        # instead of a process that silently exits.
        if not OpenAIClientWrapper.key_available():
            self.audiobook_status_label.setText("[Error] OPENAI_API_KEY not set.")
            QMessageBox.critical(
                self,
                "OpenAI API Key Required",
                "Audiobook conversion uses OpenAI's text-to-speech API, but "
                "OPENAI_API_KEY is not set.\n\n"
                "Add your key to the .env file in the project root:\n"
                "    OPENAI_API_KEY=sk-...\n\n"
                "then restart Imprint and try again. "
                "Get a key at platform.openai.com/api-keys.",
            )
            return

        try:
            chunk_tokens = int(self.audiobook_chunk_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid Value", "Chunk tokens must be a number.")
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Confirm Audiobook Conversion")
        msg.setText(
            f"Start audiobook conversion?\n\n"
            f"Book: {Path(book_path).name}\n"
            f"Voice: {voice}\n"
            f"Chunk tokens: {chunk_tokens}\n\n"
            f"This uses OpenAI TTS API and may cost real money."
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        if msg.exec() != QMessageBox.Yes:
            return

        config = {"input": book_path, "output": output_path, "voice": voice, "chunk_tokens": chunk_tokens}

        self.output_box.setPlainText(
            f"[Starting]\nBook: {Path(book_path).name}\nOutput: {output_path}\nVoice: {voice}\nChunk tokens: {chunk_tokens}\n\n"
        )
        self.audiobook_status_label.setText(f"[Running] {Path(book_path).name}")
        self.run_audiobook_live(config)

    def run_audiobook_live(self, config):
        self.tool_progress.setValue(0)
        self.stop_btn.setEnabled(True)
        self.stop_btn.show()
        self.audiobook_start_btn.setEnabled(False)
        self.audiobook_refresh_btn.setEnabled(False)

        tool = self.tool_runner.tools["audiobook"]
        project_root = str(Path(__file__).resolve().parent)
        self.audiobook_process = QProcess(self)
        self.audiobook_process.setProcessChannelMode(QProcess.MergedChannels)
        # Run from the project root so "-m services.narrator.converter" resolves,
        # using the app's own interpreter (no separate venv -> PyInstaller-friendly).
        self.audiobook_process.setWorkingDirectory(project_root)

        program = sys.executable
        conv_args = [
            "--input", config["input"],
            "--output", config["output"],
            "--voice", config["voice"],
            "--chunk-tokens", str(config["chunk_tokens"]),
        ]
        if is_frozen():
            # Packaged app: re-invoke our own executable with the worker sentinel
            # (PyInstaller apps have no `python -m`).
            arguments = ["--narrator-worker"] + conv_args
        else:
            arguments = ["-u", "-m", tool.get("module", "services.narrator.converter")] + conv_args

        self.audiobook_process.readyReadStandardOutput.connect(self.handle_audiobook_stdout)
        self.audiobook_process.finished.connect(self.handle_audiobook_finished)
        self.audiobook_process.errorOccurred.connect(self.handle_audiobook_error)
        self.audiobook_process.start(program, arguments)

    def handle_audiobook_error(self, error):
        """Fired when the process fails to start/crashes at the QProcess level
        (e.g. interpreter not found) — distinct from a non-zero exit code."""
        # FailedToStart still emits finished() on some platforms; on others it
        # does not, so report here to guarantee the user sees something.
        reason = {
            QProcess.FailedToStart: "The converter process failed to start "
                                    "(interpreter or module not found).",
            QProcess.Crashed: "The converter process crashed.",
            QProcess.Timedout: "The converter process timed out.",
        }.get(error, "The converter process encountered an unknown error.")

        self.stop_btn.setEnabled(False)
        self.stop_btn.hide()
        self.audiobook_start_btn.setEnabled(True)
        self.audiobook_refresh_btn.setEnabled(True)
        self.tool_progress.setValue(0)
        self.audiobook_status_label.setText("[Error] Converter could not run.")
        self.output_box.append(f"\n[Error] {reason}")
        QMessageBox.critical(self, "Audiobook Conversion Failed", reason)

    def handle_audiobook_stdout(self):
        data = self.audiobook_process.readAll().data().decode("utf-8", errors="replace")
        if not data:
            return

        self.output_box.moveCursor(QTextCursor.End)
        self.output_box.insertPlainText(data)
        self.output_box.ensureCursorVisible()

        matches = re.findall(r"(\d+(?:\.\d+)?)%\s+\((\d+)/(\d+)\)", data)
        if matches:
            percent = float(matches[-1][0])
            done = matches[-1][1]
            total = matches[-1][2]
            self.tool_progress.setValue(int(percent))
            self.audiobook_status_label.setText(f"[Running] {percent:.1f}% ({done}/{total})")

    def handle_audiobook_finished(self):
        self.stop_btn.setEnabled(False)
        self.stop_btn.hide()
        self.audiobook_start_btn.setEnabled(True)
        self.audiobook_refresh_btn.setEnabled(True)

        exit_code = self.audiobook_process.exitCode() if self.audiobook_process else 0
        exit_status = self.audiobook_process.exitStatus() if self.audiobook_process else QProcess.NormalExit
        output_text = self.output_box.toPlainText()
        crashed = exit_status == QProcess.CrashExit

        success = "ALL BOOKS COMPLETED" in output_text or "🎉" in output_text
        quota_hit = any(k in output_text for k in (
            "insufficient_quota", "exceeded your current quota", "Billing hard limit"))
        paused = "Conversion paused" in output_text or "⏸️" in output_text

        if quota_hit:
            self.tool_progress.setValue(0)
            self.audiobook_status_label.setText("[Blocked] OpenAI quota exceeded — top up your account.")
            self.output_box.append(
                "\n[Blocked] Your OpenAI account has run out of quota.\n"
                "Top up your account at platform.openai.com/settings/billing,\n"
                "then click Start on the same book to resume automatically."
            )
            QMessageBox.warning(
                self, "OpenAI Quota Exceeded",
                "Your OpenAI account has run out of quota. Top up at "
                "platform.openai.com/settings/billing, then click Start to resume.",
            )

        elif paused and exit_code != 0:
            self.tool_progress.setValue(0)
            self.audiobook_status_label.setText("[Paused] Incomplete — click Start to resume.")
            self.output_box.append(
                "\n[Paused] Some chunks were not completed.\n"
                "Click Start on the same book to resume automatically."
            )

        elif crashed or exit_code != 0:
            reason = self._extract_audiobook_error(output_text)
            self.tool_progress.setValue(0)
            self.audiobook_status_label.setText("[Error] Conversion failed.")
            self.output_box.append(
                f"\n[Error] Conversion failed (exit code {exit_code}).\n{reason}"
            )
            QMessageBox.critical(
                self, "Audiobook Conversion Failed",
                f"The conversion did not complete.\n\n{reason}",
            )

        elif success:
            self.tool_progress.setValue(100)
            self.audiobook_status_label.setText("[Done] Audiobook created successfully.")
            self.output_box.append("\n[Done] Audiobook created successfully.")

        else:
            # Exit 0 but no success marker — don't fake success.
            reason = self._extract_audiobook_error(output_text)
            self.tool_progress.setValue(0)
            self.audiobook_status_label.setText("[Warning] Ended without confirming success.")
            self.output_box.append(
                "\n[Warning] The converter exited without reporting completion. "
                f"Nothing may have been produced.\n{reason}"
            )
            QMessageBox.warning(
                self, "Audiobook Conversion Incomplete",
                "The converter exited without confirming the audiobook was "
                f"created.\n\n{reason}",
            )

        self.refresh_audiobook_books()

    @staticmethod
    def _extract_audiobook_error(output_text: str) -> str:
        """Pull the most informative error line out of the converter's output so
        the user sees *why* it failed, not just that it did."""
        lines = [ln.strip() for ln in output_text.splitlines() if ln.strip()]
        # Prefer lines that name a concrete cause over generic failure notices.
        specific = ("not found", "not set", "Fatal error", "Traceback", "Exception",
                    "quota", "Authentication", "401", "Failed to read")
        for ln in reversed(lines):
            if any(m in ln for m in specific):
                return ln
        for ln in reversed(lines):
            if "❌" in ln or "Error" in ln:
                return ln
        return lines[-1] if lines else "No output was produced by the converter."

    def load_models(self):
        self.model_box.clear()
        try:
            models = self.ollama.list_models()
        except Exception:
            models = []
        if not models:
            models = list(OllamaClient.KNOWN_MODELS)
        self.model_box.addItems(models)
        self.update_live_cost_estimate()

    def build_tool_messages(self, selected_tool, full_prompt):
        tool_config = self.tool_prompts.get(selected_tool, {})
        system_prompt = tool_config.get("system", "You are a helpful assistant.")

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt},
        ]

    def auto_route_agent(self):
        raw_text = self.input_box.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Warning", "Please enter text first.")
            return

        selected_agent = self.agent_box.currentText()
        selected_tool = self.tool_box.currentText() if hasattr(self, "tool_box") else "General Chat"
        backend, model = self.resolve_backend_model()
        self.route_result_label.setText(f"Router: {selected_agent} · {backend} · {model}")

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

        estimated_cost, approx_tokens = self.estimate_chat_cost(final_backend, final_model, full_prompt)

        api_permissions = {
            "allow_openai": self.allow_openai_checkbox.isChecked(),
            "allow_deepseek": self.allow_deepseek_checkbox.isChecked(),
            "allow_kimi": self.allow_kimi_checkbox.isChecked(),
            "allow_gemini": self.allow_gemini_checkbox.isChecked(),
            "allow_anthropic": self.allow_anthropic_checkbox.isChecked(),
            "allow_qwen": self.allow_qwen_checkbox.isChecked(),
        }

        validation = self.validator.validate(
            agent_name=selected_agent,
            tool_name=selected_tool,
            provider=final_backend,
            api_permissions=api_permissions,
            session_cost=self.session_cost_total,
            session_budget=self.session_budget_eur,
            daily_cost=self.usage_tracker.get_today_total(),
            daily_budget=self.daily_budget_eur,
            estimated_cost=estimated_cost,
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
            if selected_tool in self.tool_prompts:
                messages = self.build_tool_messages(selected_tool, full_prompt)
            elif selected_agent in self.agent_instances:
                agent = self.agent_instances[selected_agent]
                messages = agent.build_messages(full_prompt)
            else:
                messages = [{"role": "user", "content": full_prompt}]

            self.pending_agent = selected_agent
            self.pending_tool = selected_tool
            self.pending_backend = final_backend
            self.pending_model = final_model
            self.pending_command = command_name
            self.pending_messages = messages
            self.pending_prompt = full_prompt
            self.pending_usage = None

            self.show_output_area()
            self.output_box.clear()
            self.output_box.append("[Working]")
            self.output_box.append(f"Agent: {selected_agent}")
            self.output_box.append(f"Backend: {final_backend}")
            self.output_box.append(f"Model: {final_model}")
            self.output_box.append(f"Command: {command_name}")
            self.output_box.append("")
            self.output_box.append("Starting background worker...\n")

            self.route_result_label.setText(f"Router: {selected_agent} · {final_backend} · {final_model}")

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

            self.chat_worker = ChatWorker(self.run_backend, final_backend, final_model, messages, full_prompt)
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
        request token, which is returned. A caller may hand that token back to
        record_request()/abandon_request(); passing the agent name still works
        and resolves to that agent's oldest outstanding request.
        """
        # `flat_cost_eur` is for work billed per unit rather than per token —
        # an image, a video render, a minute of speech. Without it the guard
        # prices those at zero and they slip past the caps entirely.
        if flat_cost_eur is not None:
            estimated_cost, approx_tokens = float(flat_cost_eur), 0
        else:
            estimated_cost, approx_tokens = self.estimate_chat_cost(provider, model, prompt)

        validation = self.validator.validate(
            agent_name=agent,
            tool_name=tool,
            provider=provider,
            api_permissions=self.current_api_permissions(),
            session_cost=self.session_cost_total,
            session_budget=self.session_budget_eur,
            daily_cost=self.usage_tracker.get_today_total(),
            daily_budget=self.daily_budget_eur,
            estimated_cost=estimated_cost,
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
            prompt_text=context["prompt"],
            response_text=response,
            usage=context["usage"],
            flat_cost_eur=context.get("flat_cost_eur"),
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
        self.output_box.append("\n\n[Finished]")

        usage_entry = self.usage_tracker.log_request(
            agent=self.pending_agent,
            backend=self.pending_backend,
            model=self.pending_model,
            prompt_text=self.pending_prompt,
            response_text=response,
            usage=self.pending_usage,
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
        )

        self.load_history_list()
        self.route_result_label.setText(f"Router: {self.pending_agent} · {self.pending_backend} · {self.pending_model}")

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
        if self.chat_worker is not None and self.chat_worker.isRunning():
            self.chat_worker.cancel()
            self.chat_worker.terminate()
            self.chat_worker.wait(2000)
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
            self.music_stop()
            return

        if self.webdesign_worker is not None and self.webdesign_worker.isRunning():
            self.webdesign_stop()
            return

        if self.fiverr_image_worker is not None and self.fiverr_image_worker.isRunning():
            self.fiverr_stop()
            return

        if self.fiverr_text_worker is not None and self.fiverr_text_worker.isRunning():
            self.fiverr_stop()
            return

        stopped = False
        if self.audiobook_process is not None:
            if self.audiobook_process.state() != QProcess.NotRunning:
                self.audiobook_process.kill()
                stopped = True

        self.stop_btn.setEnabled(False)
        self.stop_btn.hide()
        self.audiobook_start_btn.setEnabled(True)
        self.audiobook_refresh_btn.setEnabled(True)

        if stopped:
            self.output_box.append("\n[Stopped] Current task stopped by user.")
            self.audiobook_status_label.setText("[Stopped]")
        else:
            self.output_box.append("\n[Info] No running task to stop.")

    def update_resource_label(self):
        stats = self.monitor.snapshot()

        def colorize(text: str, level: str):
            color_map = {"green": "#1a7f37", "yellow": "#b07d00", "red": "#b42318"}
            return f"<span style='color:{color_map.get(level, '#ffffff')}; font-weight:600;'>{text}</span>"

        cpu_text = colorize(f"{stats['cpu_percent']:5.1f}%", stats["cpu_level"])
        ram_text = colorize(f"{stats['ram_percent']:5.1f}%", stats["ram_level"])
        swap_text = colorize(f"{stats['swap_percent']:5.1f}%", stats["swap_level"])

        if stats["battery_percent"] is None:
            battery_text = "<span style='color:#666;'>n/a</span>"
        else:
            battery_text = colorize(f"{stats['battery_percent']:5.1f}% {stats['battery_note']}", stats["battery_level"])

        html = f"""
        <b>RAM</b> {ram_text}<br>
        <small>Used: {stats['ram_used_gb']:.1f} GB · Free: {stats['ram_available_gb']:.1f} GB</small><br>
        <b>CPU</b> {cpu_text}<br>
        <b>SWAP</b> {swap_text}<br>
        <small>Used: {stats['swap_used_gb']:.1f} / {stats['swap_total_gb']:.1f} GB</small><br>
        <b>BATTERY</b> {battery_text}
        """.strip()

        self.resource_label.setText(html)

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

            self._refresh_history_agent_filter(loaded)
            wanted = (self.history_agent_filter.currentText()
                      if hasattr(self, "history_agent_filter") else ALL_AGENTS_FILTER)

            for file, data in loaded:
                if wanted != ALL_AGENTS_FILTER and data.get("agent", "chat") != wanted:
                    continue
                title = self.chat_title_from_data(file, data)
                if query and query not in title.lower():
                    continue
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, str(file))
                self.history_list.addItem(item)
        except Exception as exc:
            self._note_failure("saved chats: load list", exc)

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
            self.show_output_area()
            self.output_box.setPlainText(data.get("response", ""))

            first_user_message = ""
            for msg in data.get("messages", []):
                if msg.get("role") == "user":
                    first_user_message = msg.get("content", "")
                    break

            self.input_box.setPlainText(first_user_message)
            self.route_result_label.setText(
                f"Router: {data.get('agent')} · {data.get('backend')} · {data.get('model')}"
            )

            agent_name = data.get("agent", "chat")
            if self.agent_box.findText(agent_name) >= 0:
                self.select_agent(agent_name)

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
        self.input_box.clear()
        self.output_box.clear()
        self.hide_output_area()
        self.route_result_label.setText("Router: not yet computed")

    def export_report(self):
        content = self.output_box.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Warning", "No output to export.")
            return
        title = self.agent_box.currentText() + "_report"
        filepath = self.report_exporter.export_text_report(title, content)
        QMessageBox.information(self, "Export Complete", f"Report saved to:\n{filepath}")

    def show_agent_docs(self):
        """Open the documentation dialog for the currently active agent."""
        agent_name = getattr(self, "_current_agent", "chat")

        # Map agent key → doc filename (same as the key for most)
        doc_file_map = {
            "chat": "chat", "fiverr": "fiverr", "creator": "creator",
            "author": "author", "music": "music",
            "webdesign": "webdesign", "audiobook": "audiobook",
            "manuscript": "manuscript",
        }
        doc_key = doc_file_map.get(agent_name, agent_name)

        # Read-only bundled resource (works in dev and in the frozen .app)
        docs_dir = RESOURCE_DIR / "docs" / "agents"
        doc_path = docs_dir / f"{doc_key}.md"

        # Read the markdown source
        if doc_path.exists():
            raw_md = doc_path.read_text(encoding="utf-8")
        else:
            raw_md = f"# No documentation found\n\nNo documentation file was found for **{agent_name}**.\n\nExpected path: `{doc_path}`"

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

    def show_model_guide(self):
        from ui.dialogs import show_model_guide as _show_model_guide
        return _show_model_guide(self)
    def show_learning_center(self):
        """Guides, workflows and the money chapter, rendered from docs/learn/."""
        from ui.learning_center import show_learning_center as _show
        return _show(self, RESOURCE_DIR)

    def show_docs(self, anchor: str = ""):
        dialog = QDialog(self)
        dialog.setWindowTitle("Documentation")
        dialog.resize(950, 700)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setOpenLinks(False)

        if README_FILE.exists():
            text = README_FILE.read_text(encoding="utf-8")
            html = markdown.markdown(text, extensions=["toc", "tables"])
        else:
            html = "<h2>No README.md found</h2><p>Create README.md in the project root.</p>"

        browser.setHtml(html)

        def on_anchor_clicked(url):
            fragment = url.fragment()
            if fragment:
                browser.scrollToAnchor(fragment)

        browser.anchorClicked.connect(on_anchor_clicked)

        if anchor:
            QTimer.singleShot(50, lambda: browser.scrollToAnchor(anchor))

        layout.addWidget(browser)
        dialog.exec()

    def closeEvent(self, event):
        try:
            if self.audiobook_process is not None and self.audiobook_process.state() != QProcess.NotRunning:
                self.audiobook_process.kill()
            if self.chat_worker is not None and self.chat_worker.isRunning():
                self.chat_worker.cancel()
                self.chat_worker.terminate()
                self.chat_worker.wait(1000)
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


if __name__ == "__main__":
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
