"""
Modal dialogs lifted out of `GodAI` (TODO.md #2, Phase 2).

Each function takes the application window as `app` — used both as the dialog's
parent and to read the handful of members it needs — and shows the dialog. The
bodies are moved verbatim; only the receiver was renamed from `self` to `app`.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QGridLayout, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

from services.anthropic_client import AnthropicClientWrapper
from services.database import get_connection, get_setting, save_setting
from services.deepseek_client import DeepSeekClientWrapper
from services.gemini_client import GeminiClientWrapper
from services.kimi_client import KimiClientWrapper
from services.media_catalog import DIRECT_VIDEO_USD_PER_SECOND, MODELS as MEDIA_MODELS
from services.openai_client import OpenAIClientWrapper
from services.per_unit_pricing import rate_usd
from services.pricing_catalog import (
    PROVIDER_LABELS, build_token_price_catalog,
)
from services.registry import Registry
from services.validator import Validator
from ui.style import (
    ACCENT, ACCENT_WASH, BG, BORDER, ELEVATED, SUNKEN, SURFACE, TEXT,
    TEXT_DIM, TEXT_MUTE,
)
from ui.project_manager import ProjectManagerDialog


def show_cost_history(app):
    entries = app.usage_tracker.load_log()

    dialog = QDialog(app)
    dialog.setWindowTitle("Cost History")
    dialog.resize(1050, 650)

    layout = QVBoxLayout(dialog)

    filter_row = QHBoxLayout()

    provider_filter = QComboBox()
    provider_filter.addItems(["all", "ollama", "openai", "deepseek", "kimi", "gemini"])
    filter_row.addWidget(QLabel("Provider:"))
    filter_row.addWidget(provider_filter)

    export_btn = QPushButton("Export CSV")
    filter_row.addWidget(export_btn)

    filter_row.addStretch()
    layout.addLayout(filter_row)

    summary_label = QLabel("")
    layout.addWidget(summary_label)

    browser = QTextBrowser()
    layout.addWidget(browser)

    def render():
        provider = provider_filter.currentText()

        filtered = entries
        if provider != "all":
            filtered = [e for e in entries if e.get("backend") == provider]

        total_cost = sum(
            float(e.get("cost_eur", e.get("estimated_cost", 0.0)))
            for e in filtered
        )
        total_tokens = sum(int(e.get("total_tokens", 0)) for e in filtered)
        total_requests = len(filtered)

        summary_label.setText(
            f"Requests: {total_requests} | "
            f"Tokens: {total_tokens:,} | "
            f"Total Cost: €{total_cost:.2f}"
        )

        if not filtered:
            browser.setHtml("<h2>No cost history for this filter.</h2>")
            return

        rows = ""
        for e in reversed(filtered[-200:]):
            rows += f"""
            <tr>
                <td>{e.get('timestamp', '')}</td>
                <td>{e.get('agent', '')}</td>
                <td>{e.get('backend', '')}</td>
                <td>{e.get('model', '')}</td>
                <td>{e.get('input_tokens', 0)}</td>
                <td>{e.get('output_tokens', 0)}</td>
                <td>{e.get('total_tokens', 0)}</td>
                <td>€{float(e.get('cost_eur', e.get('estimated_cost', 0.0))):.2f}</td>
                <td>{e.get('cost_type', '')}</td>
            </tr>
            """

        browser.setHtml(f"""
        <h2>Cost History</h2>
        <table border="1" cellspacing="0" cellpadding="6">
            <tr>
                <th>Time</th>
                <th>Agent</th>
                <th>Provider</th>
                <th>Model</th>
                <th>Input</th>
                <th>Output</th>
                <th>Total</th>
                <th>Cost</th>
                <th>Type</th>
            </tr>
            {rows}
        </table>
        """)

    def export_csv():
        provider = provider_filter.currentText()

        filtered = entries
        if provider != "all":
            filtered = [e for e in entries if e.get("backend") == provider]

        if not filtered:
            QMessageBox.information(dialog, "No Data", "No entries to export.")
            return

        export_path, _ = QFileDialog.getSaveFileName(
            dialog,
            "Export Cost History",
            "cost_history.csv",
            "CSV Files (*.csv)"
        )

        if not export_path:
            return

        import csv

        with open(export_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "agent",
                "backend",
                "model",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cost_eur",
                "cost_type",
            ])

            for e in filtered:
                writer.writerow([
                    e.get("timestamp", ""),
                    e.get("agent", ""),
                    e.get("backend", ""),
                    e.get("model", ""),
                    e.get("input_tokens", 0),
                    e.get("output_tokens", 0),
                    e.get("total_tokens", 0),
                    float(e.get("cost_eur", e.get("estimated_cost", 0.0))),
                    e.get("cost_type", ""),
                ])

        QMessageBox.information(dialog, "Export Complete", f"Saved to:\n{export_path}")

    provider_filter.currentTextChanged.connect(render)
    export_btn.clicked.connect(export_csv)

    render()
    dialog.exec()


def show_run_log(app):
    entries = app.run_logger.load_recent(500)

    dialog = QDialog(app)
    dialog.setWindowTitle("Run Log")
    dialog.resize(1050, 650)

    layout = QVBoxLayout(dialog)

    filter_row = QHBoxLayout()

    status_filter = QComboBox()
    status_filter.addItems(["all", "success", "error", "cancelled"])
    filter_row.addWidget(QLabel("Status:"))
    filter_row.addWidget(status_filter)

    agent_filter = QComboBox()
    agent_filter.addItems(["all"] + sorted({e.get("agent", "") for e in entries if e.get("agent")}))
    filter_row.addWidget(QLabel("Agent:"))
    filter_row.addWidget(agent_filter)

    filter_row.addStretch()
    layout.addLayout(filter_row)

    summary_label = QLabel("")
    layout.addWidget(summary_label)

    browser = QTextBrowser()
    layout.addWidget(browser)

    def render():
        status = status_filter.currentText()
        agent = agent_filter.currentText()

        filtered = entries
        if status != "all":
            filtered = [e for e in filtered if e.get("status") == status]
        if agent != "all":
            filtered = [e for e in filtered if e.get("agent") == agent]

        total_runs = len(filtered)
        total_cost = sum(float(e.get("cost_eur", 0.0)) for e in filtered)
        errors = sum(1 for e in filtered if e.get("status") == "error")

        summary_label.setText(
            f"Runs: {total_runs} | Errors: {errors} | Total Cost: €{total_cost:.4f}"
        )

        if not filtered:
            browser.setHtml("<h2>No runs match this filter.</h2>")
            return

        rows = ""
        for e in reversed(filtered[-300:]):
            status_val = e.get("status", "")
            color = {"success": "#3cff88", "error": "#ff5555", "cancelled": "#ffaa00"}.get(status_val, "#ffffff")
            error_cell = f'<span style="color:#ff5555">{e.get("error", "")}</span>' if e.get("error") else ""
            rows += f"""
            <tr>
                <td>{e.get("timestamp", "")}</td>
                <td>{e.get("run_id", "")}</td>
                <td>{e.get("agent", "")}</td>
                <td>{e.get("tool", "")}</td>
                <td>{e.get("provider", "")}</td>
                <td>{e.get("model", "")}</td>
                <td><span style="color:{color}">{status_val}</span></td>
                <td>{e.get("input_tokens", 0)}</td>
                <td>{e.get("output_tokens", 0)}</td>
                <td>€{float(e.get("cost_eur", 0.0)):.4f}</td>
                <td>{e.get("duration_sec", 0.0)}s</td>
                <td>{error_cell}</td>
            </tr>
            """

        browser.setHtml(f"""
        <h2>Run Log</h2>
        <table border="1" cellspacing="0" cellpadding="5" style="font-size:11px">
            <tr>
                <th>Time</th><th>Run ID</th><th>Agent</th><th>Tool</th>
                <th>Provider</th><th>Model</th><th>Status</th>
                <th>In</th><th>Out</th><th>Cost</th><th>Duration</th><th>Error</th>
            </tr>
            {rows}
        </table>
        """)

    status_filter.currentTextChanged.connect(render)
    agent_filter.currentTextChanged.connect(render)

    render()
    dialog.exec()


def show_settings(app):
    dialog = QDialog(app)
    dialog.setWindowTitle("Settings")
    dialog.setObjectName("SettingsDialog")
    dialog.resize(1040, 720)
    dialog.setMinimumSize(820, 600)

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(24, 22, 24, 20)
    outer.setSpacing(16)

    title = QLabel("Settings")
    title.setObjectName("SettingsTitle")
    title.setFixedHeight(34)
    outer.addWidget(title)
    subtitle = QLabel(
        "Control budgets, agents, tools, and the cost estimates Imprint uses before paid work runs."
    )
    subtitle.setObjectName("SettingsSubtitle")
    subtitle.setWordWrap(True)
    subtitle.setMinimumHeight(20)
    outer.addWidget(subtitle)

    tabs = QTabWidget()
    tabs.setObjectName("SettingsTabs")
    outer.addWidget(tabs, 1)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)
    save_all_btn = QPushButton("Save All")
    save_all_btn.setObjectName("SettingsSave")
    save_all_btn.setFixedHeight(38)
    cancel_btn = QPushButton("Cancel")
    cancel_btn.setFixedHeight(38)
    cancel_btn.clicked.connect(dialog.reject)
    btn_row.addStretch()
    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(save_all_btn)
    outer.addLayout(btn_row)

    def page_intro(layout, heading, copy):
        heading_label = QLabel(heading)
        heading_label.setObjectName("SettingsSectionTitle")
        layout.addWidget(heading_label)
        copy_label = QLabel(copy)
        copy_label.setObjectName("SettingsHelp")
        copy_label.setWordWrap(True)
        layout.addWidget(copy_label)

    def readonly_item(text, tooltip=""):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if tooltip:
            item.setToolTip(tooltip)
        return item

    def prepare_table(table):
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        table.horizontalHeader().setMinimumSectionSize(80)

    # ── Tab 1: General ────────────────────────────────────────────
    general_tab = QWidget()
    general_tab.setObjectName("SettingsPage")
    general_page = QVBoxLayout(general_tab)
    general_page.setContentsMargins(18, 20, 18, 18)
    general_page.setSpacing(14)
    page_intro(
        general_page,
        "Budget defaults",
        "These safeguards apply across agents. Prices are stored in USD and converted before Imprint checks your euro limits.",
    )
    general_card = QFrame()
    general_card.setObjectName("SettingsCard")
    gl = QGridLayout(general_card)
    gl.setSpacing(14)
    gl.setContentsMargins(18, 18, 18, 18)

    gl.addWidget(QLabel("EUR per USD"), 0, 0)
    eur_input = QLineEdit(get_setting("eur_per_usd", "0.92"))
    eur_input.setObjectName("EurUsdRate")
    eur_input.setPlaceholderText("0.92")
    gl.addWidget(eur_input, 0, 1)

    gl.addWidget(QLabel("Session budget (€)"), 1, 0)
    sess_input = QLineEdit(get_setting("session_budget_eur", str(app.session_budget_eur)))
    sess_input.setObjectName("SessionBudget")
    gl.addWidget(sess_input, 1, 1)

    gl.addWidget(QLabel("Daily budget (€)"), 2, 0)
    daily_input = QLineEdit(get_setting("daily_budget_eur", str(app.daily_budget_eur)))
    daily_input.setObjectName("DailyBudget")
    gl.addWidget(daily_input, 2, 1)
    gl.setColumnStretch(1, 1)
    general_page.addWidget(general_card)
    general_page.addStretch()
    tabs.addTab(general_tab, "General")

    # ── Tab 2: Agents ─────────────────────────────────────────────
    agents_tab = QWidget()
    agents_tab.setObjectName("SettingsPage")
    al = QVBoxLayout(agents_tab)
    al.setContentsMargins(18, 20, 18, 18)
    al.setSpacing(14)
    page_intro(
        al,
        "Agent access and limits",
        "Disable an agent without removing its work. A blank cap means it uses only the global session and daily budgets.",
    )

    agent_rows = app.registry.list_agents()
    agents_table = QTableWidget(len(agent_rows), 3)
    agents_table.setObjectName("SettingsAgentsTable")
    agents_table.setHorizontalHeaderLabels(["Agent", "Enabled", "Agent budget (€)"])
    prepare_table(agents_table)
    agents_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    agents_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    agents_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    agents_table.setColumnWidth(2, 190)

    agent_widgets = {}
    for i, agent in enumerate(agent_rows):
        label = agent["label"] or agent["name"]
        agents_table.setItem(i, 0, readonly_item(label, agent.get("description", "")))
        chk = QCheckBox()
        chk.setChecked(agent.get("enabled", True))
        chk.setAccessibleName(f"Enable {label}")
        budget_val = agent.get("budget_limit_eur")
        budget_edit = QLineEdit("" if budget_val is None else str(budget_val))
        budget_edit.setPlaceholderText("No agent-specific limit")
        agents_table.setCellWidget(i, 1, chk)
        agents_table.setCellWidget(i, 2, budget_edit)
        agent_widgets[agent["name"]] = (chk, budget_edit)

    al.addWidget(agents_table)
    tabs.addTab(agents_tab, "Agents")

    # ── Tab 3: Tools ──────────────────────────────────────────────
    tools_tab = QWidget()
    tools_tab.setObjectName("SettingsPage")
    tl = QVBoxLayout(tools_tab)
    tl.setContentsMargins(18, 20, 18, 18)
    tl.setSpacing(14)
    page_intro(
        tl,
        "Tool availability",
        "Tools are shared capabilities used by agents. Hover a prompt preview to read the full instruction.",
    )

    tool_rows = app.registry.list_tools()
    tools_table = QTableWidget(len(tool_rows), 3)
    tools_table.setObjectName("SettingsToolsTable")
    tools_table.setHorizontalHeaderLabels(["Tool", "Enabled", "Instruction preview"])
    prepare_table(tools_table)
    tools_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    tools_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    tools_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    tool_widgets = {}
    for i, tool in enumerate(tool_rows):
        tools_table.setItem(i, 0, readonly_item(tool.get("label") or tool["name"]))
        chk = QCheckBox()
        chk.setChecked(tool.get("enabled", True))
        prompt = tool.get("system_prompt") or "No system instruction"
        preview = prompt.replace("\n", " ")
        if len(preview) > 110:
            preview = preview[:107].rstrip() + "…"
        tools_table.setCellWidget(i, 1, chk)
        tools_table.setItem(i, 2, readonly_item(preview, prompt))
        tool_widgets[tool["name"]] = chk

    tl.addWidget(tools_table)
    tabs.addTab(tools_tab, "Tools")

    # ── Tab 4: Pricing ────────────────────────────────────────────
    pricing_tab = QWidget()
    pricing_tab.setObjectName("SettingsPage")
    pl = QVBoxLayout(pricing_tab)
    pl.setContentsMargins(18, 20, 18, 18)
    pl.setSpacing(12)
    page_intro(
        pl,
        "Pricing catalog",
        "Imprint uses these estimates for budget checks. Provider defaults cover newly discovered models; “Unknown” never means free.",
    )

    pricing_modes = QTabWidget()
    pricing_modes.setObjectName("PricingModes")
    token_page = QWidget()
    token_layout = QVBoxLayout(token_page)
    token_layout.setContentsMargins(0, 12, 0, 0)
    token_layout.setSpacing(10)

    filter_row = QHBoxLayout()
    pricing_search = QLineEdit()
    pricing_search.setObjectName("PricingSearch")
    pricing_search.setPlaceholderText("Search models")
    provider_filter = QComboBox()
    provider_filter.setObjectName("PricingProviderFilter")
    provider_filter.addItem("All providers", "")
    filter_row.addWidget(pricing_search, 1)
    filter_row.addWidget(provider_filter)
    token_layout.addLayout(filter_row)

    with get_connection() as conn:
        pricing_entries = build_token_price_catalog(conn)

    present_providers = []
    for entry in pricing_entries:
        if entry.provider not in present_providers:
            present_providers.append(entry.provider)
    for provider in present_providers:
        provider_filter.addItem(PROVIDER_LABELS.get(provider, provider.title()), provider)

    pricing_table = QTableWidget(len(pricing_entries), 6)
    pricing_table.setObjectName("SettingsPricingTable")
    pricing_table.setHorizontalHeaderLabels([
        "Provider", "Model", "Input / 1M", "Cached input / 1M", "Output / 1M", "Coverage"
    ])
    prepare_table(pricing_table)
    pricing_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    pricing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    pricing_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    pricing_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    pricing_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    pricing_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
    pricing_table.setColumnWidth(0, 110)
    pricing_table.setColumnWidth(2, 115)
    pricing_table.setColumnWidth(3, 145)
    pricing_table.setColumnWidth(4, 115)
    pricing_table.setColumnWidth(5, 165)

    pricing_widgets = {}
    pricing_row_meta = []
    for i, entry in enumerate(pricing_entries):
        pricing_table.setItem(i, 0, readonly_item(entry.provider_label))
        pricing_table.setItem(i, 1, readonly_item(entry.model))

        edits = []
        for value in (entry.input_usd, entry.cached_input_usd, entry.output_usd):
            edit = QLineEdit("" if value is None else f"{value:g}")
            edit.setPlaceholderText("Unknown")
            if entry.source == "local":
                edit.setEnabled(False)
            edits.append(edit)
        pricing_table.setCellWidget(i, 2, edits[0])
        pricing_table.setCellWidget(i, 3, edits[1])
        pricing_table.setCellWidget(i, 4, edits[2])

        status_item = readonly_item(entry.status)
        status_item.setData(Qt.ItemDataRole.UserRole, entry.source)
        pricing_table.setItem(i, 5, status_item)
        key = (entry.provider, entry.model)
        original = tuple(0.0 if value is None else value for value in (
            entry.input_usd, entry.cached_input_usd, entry.output_usd
        ))
        pricing_widgets[key] = (edits, entry.source, original)
        pricing_row_meta.append((i, entry.provider, entry.model))

    pricing_summary = QLabel()
    pricing_summary.setObjectName("PricingSummary")
    token_layout.addWidget(pricing_summary)
    token_layout.addWidget(pricing_table)

    def filter_pricing():
        wanted_provider = provider_filter.currentData() or ""
        needle = pricing_search.text().strip().casefold()
        visible = 0
        visible_providers = set()
        for row, provider, model in pricing_row_meta:
            show = (not wanted_provider or provider == wanted_provider) and (
                not needle or needle in model.casefold() or needle in provider.casefold()
            )
            pricing_table.setRowHidden(row, not show)
            if show:
                visible += 1
                visible_providers.add(provider)
        pricing_summary.setText(
            f"{visible} model{'s' if visible != 1 else ''} · "
            f"{len(visible_providers)} provider{'s' if len(visible_providers) != 1 else ''} · USD"
        )

    provider_filter.currentIndexChanged.connect(filter_pricing)
    pricing_search.textChanged.connect(filter_pricing)
    filter_pricing()
    pricing_modes.addTab(token_page, "Token models")

    unit_page = QWidget()
    unit_layout = QVBoxLayout(unit_page)
    unit_layout.setContentsMargins(0, 12, 0, 0)
    unit_layout.setSpacing(10)
    unit_help = QLabel(
        "Per-unit work is billed differently from chat tokens. Leave a value blank when the rate is unknown; Imprint will warn before spending."
    )
    unit_help.setObjectName("SettingsHelp")
    unit_help.setWordWrap(True)
    unit_layout.addWidget(unit_help)

    unit_specs = [
        (("openai_image", "gpt-image-2.5-sunburst"), "OpenAI", "GPT Image 2.5 Sunburst", "per image", None),
        (("openai_image", "gpt-image-2.5-flare"), "OpenAI", "GPT Image 2.5 Flare", "per image", None),
        (("openai_image", "gpt-image-2"), "OpenAI", "GPT Image 2", "per image", None),
        (("openai_tts_per_1k_chars",), "OpenAI", "Text to speech", "per 1,000 characters", None),
        (("openai_whisper_per_minute",), "OpenAI", "Whisper transcription", "per audio minute", None),
    ]
    unit_specs.extend(
        (("direct_video", model.model_id), model.provider, model.label,
         "per generated second", DIRECT_VIDEO_USD_PER_SECOND[model.model_id])
        for model in MEDIA_MODELS
        if model.kind == "direct_video" and model.model_id in DIRECT_VIDEO_USD_PER_SECOND
    )
    unit_specs.append(
        (("higgsfield_render",), "Higgsfield", "Video render", "per render", None)
    )
    unit_table = QTableWidget(len(unit_specs), 5)
    unit_table.setObjectName("SettingsPerUnitTable")
    unit_table.setHorizontalHeaderLabels(["Provider", "Service", "Unit", "USD", "Coverage"])
    prepare_table(unit_table)
    unit_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    unit_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    unit_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    unit_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    unit_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    unit_table.setColumnWidth(3, 130)
    unit_table.setColumnWidth(4, 130)
    per_unit_widgets = {}
    for row, (path, provider, service, unit, fallback) in enumerate(unit_specs):
        value = rate_usd(*path)
        if value is None:
            value = fallback
        unit_table.setItem(row, 0, readonly_item(provider))
        unit_table.setItem(row, 1, readonly_item(service))
        unit_table.setItem(row, 2, readonly_item(unit))
        edit = QLineEdit("" if value is None else f"{value:g}")
        edit.setPlaceholderText("Unknown")
        unit_table.setCellWidget(row, 3, edit)
        unit_table.setItem(row, 4, readonly_item("Configured" if value is not None else "Unknown"))
        per_unit_widgets[path] = (edit, value)
    unit_layout.addWidget(unit_table)
    pricing_modes.addTab(unit_page, "Images, audio + video")
    pl.addWidget(pricing_modes)
    tabs.addTab(pricing_tab, "Pricing")

    projects_tab = QWidget()
    projects_layout = QVBoxLayout(projects_tab)
    projects_layout.setContentsMargins(20, 24, 20, 24)
    projects_layout.setSpacing(14)
    page_intro(
        projects_layout, "Projects",
        "Group saved chats, reuse instructions and setup, and optionally cap "
        "daily project spend. Archiving hides a project without deleting chats.",
    )
    manage_projects = QPushButton("Manage Projects")
    manage_projects.setFixedWidth(190)
    manage_projects.clicked.connect(
        lambda: ProjectManagerDialog(
            dialog, app.registry, on_change=app._switch_project,
            history=app.history,
        ).exec()
    )
    projects_layout.addWidget(manage_projects)
    projects_layout.addStretch()
    tabs.addTab(projects_tab, "Projects")

    dialog.setStyleSheet(f"""
        QDialog#SettingsDialog {{ background: {BG}; }}
        QLabel#SettingsTitle {{ color: {TEXT}; font-size: 24px; font-weight: 700; }}
        QLabel#SettingsSubtitle, QLabel#SettingsHelp, QLabel#PricingSummary {{
            color: {TEXT_DIM}; font-size: 12px;
        }}
        QLabel#SettingsSectionTitle {{ color: {TEXT}; font-size: 16px; font-weight: 650; }}
        QFrame#SettingsCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
        QTabWidget#SettingsTabs::pane, QTabWidget#PricingModes::pane {{
            border: 1px solid {BORDER}; border-radius: 10px; background: {SURFACE};
        }}
        QTableWidget#SettingsAgentsTable, QTableWidget#SettingsToolsTable,
        QTableWidget#SettingsPricingTable, QTableWidget#SettingsPerUnitTable {{
            background: {SUNKEN}; alternate-background-color: {SURFACE};
            border: 1px solid {BORDER}; border-radius: 8px; gridline-color: transparent;
        }}
        QHeaderView::section {{
            background: {SURFACE}; color: {TEXT_MUTE}; border: none;
            border-bottom: 1px solid {BORDER}; padding: 9px 8px;
            font-size: 11px; font-weight: 700;
        }}
        QTableWidget::item {{ padding: 7px; }}
        QTableWidget::item:selected {{ background: {ACCENT_WASH}; color: {TEXT}; }}
        QPushButton#SettingsSave {{ background: {ACCENT}; color: {BG}; font-weight: 700; }}
    """)

    # ── Save handler ──────────────────────────────────────────────
    def save_all():
        errors = []

        # General
        try:
            eur = float(eur_input.text().strip())
            sess = float(sess_input.text().strip())
            daily = float(daily_input.text().strip())
            save_setting("eur_per_usd", str(eur))
            save_setting("session_budget_eur", str(sess))
            save_setting("daily_budget_eur", str(daily))
            app.session_budget_eur = sess
            app.daily_budget_eur = daily
            if hasattr(app, "session_budget_input"):
                app.session_budget_input.setText(str(sess))
            if hasattr(app, "daily_budget_input"):
                app.daily_budget_input.setText(str(daily))
        except ValueError:
            errors.append("General: invalid number in EUR rate or budget fields.")

        # Agents
        with get_connection() as conn:
            for name, (chk, budget_edit) in agent_widgets.items():
                raw = budget_edit.text().strip()
                try:
                    budget = float(raw) if raw else None
                except ValueError:
                    errors.append(f"Agent '{name}': invalid budget value '{raw}'.")
                    continue
                conn.execute(
                    "UPDATE agents SET enabled = ?, budget_limit_eur = ? WHERE name = ?",
                    (1 if chk.isChecked() else 0, budget, name)
                )
            conn.commit()

        # Tools
        with get_connection() as conn:
            for name, chk in tool_widgets.items():
                conn.execute(
                    "UPDATE tools SET enabled = ? WHERE name = ?",
                    (1 if chk.isChecked() else 0, name)
                )
            conn.commit()

        # Pricing
        with get_connection() as conn:
            for (backend, model), (edits, source, original) in pricing_widgets.items():
                if source == "local":
                    continue
                values = []
                valid = True
                for edit in edits:
                    raw = edit.text().strip()
                    try:
                        value = float(raw) if raw else 0.0
                        if value < 0:
                            raise ValueError
                    except ValueError:
                        errors.append(f"Pricing {backend}/{model}: use a positive number or leave it blank.")
                        valid = False
                        break
                    values.append(value)
                if not valid:
                    continue
                # Inherited catalog rows stay inherited until the user changes
                # one of their fields. This preserves future provider-default
                # updates instead of materialising dozens of stale copies.
                changed = any(abs(a - b) > 1e-12 for a, b in zip(values, original))
                if source in {"default", "unknown"} and not changed:
                    continue
                conn.execute("""
                    INSERT INTO pricing
                      (backend, model, input_per_1m_usd, cached_input_per_1m_usd,
                       output_per_1m_usd)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(backend, model) DO UPDATE SET
                      input_per_1m_usd = excluded.input_per_1m_usd,
                      cached_input_per_1m_usd = excluded.cached_input_per_1m_usd,
                      output_per_1m_usd = excluded.output_per_1m_usd
                """, (backend, model, values[0], values[1], values[2]))
            conn.commit()

        with get_connection() as conn:
            for path, (edit, original) in per_unit_widgets.items():
                key = "pricing.per_unit." + ".".join(path)
                raw = edit.text().strip()
                if not raw:
                    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                    continue
                try:
                    value = float(raw)
                    if value <= 0:
                        raise ValueError
                except ValueError:
                    errors.append(f"Per-unit pricing {' / '.join(path)}: use a number above zero or leave it blank.")
                    continue
                if original is not None and abs(value - original) <= 1e-12:
                    continue
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )
            conn.commit()

        app.update_usage_labels()
        app.registry = Registry()
        app.validator = Validator(app.registry)

        if errors:
            QMessageBox.warning(dialog, "Saved with errors", "\n".join(errors))
        else:
            QMessageBox.information(dialog, "Saved", "All settings saved successfully.")
            dialog.accept()

    save_all_btn.clicked.connect(save_all)
    dialog.exec()
    return dialog


def show_model_guide(app):
    dialog = QDialog(app)
    dialog.setWindowTitle("Model & Agent Control Panel")
    dialog.resize(1050, 750)

    layout = QVBoxLayout(dialog)

    # =========================
    # SEARCH BAR
    # =========================
    search_box = QLineEdit()
    search_box.setPlaceholderText("Search guide: ollama, openai, coding, osint, cost, routing...")
    layout.addWidget(search_box)

    tabs = QTabWidget()
    layout.addWidget(tabs)

    # =========================
    # DYNAMIC SYSTEM INFO
    # =========================
    try:
        ollama_models = app.ollama.list_models()
    except Exception:
        ollama_models = []

    openai_status = "✅ Available" if OpenAIClientWrapper.key_available() else "❌ Not set"
    deepseek_status = "✅ Available" if DeepSeekClientWrapper.key_available() else "❌ Not set"
    kimi_status = "✅ Available" if KimiClientWrapper.key_available() else "❌ Not set"
    gemini_status = "✅ Available" if GeminiClientWrapper.key_available() else "❌ Not set"
    anthropic_status = "✅ Available" if AnthropicClientWrapper.key_available() else "❌ Not set"

    current_mode = app.execution_mode_box.currentText() if hasattr(app, "execution_mode_box") else "Unknown"
    current_provider = app.provider_box.currentText() if hasattr(app, "provider_box") else "Unknown"
    current_model = app.model_box.currentText() if hasattr(app, "model_box") else "Unknown"

    ollama_html = "<br>".join(ollama_models) if ollama_models else "No local Ollama models detected."

    # =========================
    # SIMPLE RECOMMENDATION ENGINE
    # =========================
    def get_recommendation():
        agent = app.agent_box.currentText() if hasattr(app, "agent_box") else "chat"
        command = app.command_box.currentText() if hasattr(app, "command_box") else "General Chat"

        text = f"{agent} {command}".lower()

        if "audiobook" in text:
            return "Use Audiobook Agent. Provider/model selection is ignored because audiobook conversion uses OpenAI TTS."
        if "coding" in text or "code" in text or "debug" in text:
            return "Recommended: Claude Sonnet or DeepSeek for complex coding. Use Ollama for small/private fixes."
        if "writing" in text or "rewrite" in text or "email" in text:
            return "Recommended: Claude Sonnet or OpenAI for polished writing. Gemini is a good fallback. Ollama is fine for drafts."
        if "osint" in text:
            return "Recommended: DeepSeek or Gemini for analysis. Claude or OpenAI for polished final reports."
        if current_mode == "Local only":
            return "Current setup is privacy-safe and free: Local only with Ollama."
        return "Recommended default: use Ollama for simple tasks, enable APIs only when quality or context length matters."

    recommendation = get_recommendation()

    # =========================
    # TAB 1: MODELS
    # =========================
    model_tab = QTextBrowser()
    model_tab.setHtml("""
    <h2>Model Guide</h2>

    <h3>Ollama / Local Models</h3>
    <p><b>Best for:</b> private tasks, simple chat, drafts, quick analysis, offline usage.</p>
    <p><b>Cost:</b> FREE — local execution. Uses your CPU/RAM instead of API credits.</p>
    <p><b>Use when:</b> the task is not critical, not too complex, or you want privacy.</p>
    <p><b>Popular models:</b> deepseek-r1:8b, deepseek-r1:1.5b, llama3, mistral, phi3</p>

    <h3>Anthropic (Claude) API</h3>
    <p><b>Best for:</b> coding, writing, reasoning, document analysis, nuanced instruction-following.</p>
    <p><b>Key:</b> ANTHROPIC_API_KEY — get it at console.anthropic.com</p>
    <p><b>Models:</b></p>
    <ul>
        <li><b>claude-opus-4-6</b> — Most capable. Best for complex reasoning, long documents, difficult coding. ~$15/$75 per 1M tokens.</li>
        <li><b>claude-sonnet-4-6</b> — Best balance of quality and cost. Recommended for most tasks. ~$3/$15 per 1M tokens.</li>
        <li><b>claude-haiku-4-5-20251001</b> — Fastest and cheapest. Good for simple tasks and high-volume use. ~$0.80/$4 per 1M tokens.</li>
        <li><b>claude-3-5-sonnet-20241022</b> — Previous generation Sonnet. Still highly capable. ~$3/$15 per 1M tokens.</li>
        <li><b>claude-3-5-haiku-20241022</b> — Previous generation Haiku. Fast and affordable. ~$0.80/$4 per 1M tokens.</li>
        <li><b>claude-3-opus-20240229</b> — Previous generation Opus. ~$15/$75 per 1M tokens.</li>
    </ul>
    <p><b>Use when:</b> you need high-quality, nuanced responses — especially for coding, writing, and analysis.</p>

    <h3>OpenAI API</h3>
    <p><b>Best for:</b> coding, difficult reasoning, polished writing, professional documents, complex planning.</p>
    <p><b>Key:</b> OPENAI_API_KEY — get it at platform.openai.com</p>
    <p><b>Models:</b></p>
    <ul>
        <li><b>gpt-4o-mini</b> — Fast and affordable. Good for most everyday tasks.</li>
        <li><b>gpt-4.1-mini</b> — Improved mini model. Better reasoning than gpt-4o-mini.</li>
        <li><b>gpt-4.1</b> — Full model. Best for demanding tasks where quality is critical.</li>
        <li><b>o1 / o3 / o4-mini</b> — Reasoning models. Slow but excellent for hard logic problems.</li>
    </ul>
    <p><b>Use when:</b> quality matters more than cost, or you need access to the OpenAI TTS API for Audiobook.</p>

    <h3>DeepSeek API</h3>
    <p><b>Best for:</b> structured analysis, coding support, OSINT-style reasoning, long analytical tasks.</p>
    <p><b>Key:</b> DEEPSEEK_API_KEY — get it at platform.deepseek.com</p>
    <p><b>Models:</b></p>
    <ul>
        <li><b>deepseek-chat</b> — General-purpose. Strong for coding and analysis.</li>
        <li><b>deepseek-reasoner</b> — Extended reasoning model. Good for multi-step logic.</li>
        <li><b>deepseek-coder</b> — Specialised for code generation and debugging.</li>
    </ul>
    <p><b>Use when:</b> you want strong analysis and coding at potentially lower cost than OpenAI.</p>

    <h3>Kimi API (Moonshot AI)</h3>
    <p><b>Best for:</b> coding and long-context agentic/tool-use tasks (OSINT-style multi-step work).</p>
    <p><b>Key:</b> KIMI_API_KEY — get it at platform.kimi.ai</p>
    <p><b>Models:</b></p>
    <ul>
        <li><b>kimi-k2.7-code</b> — Dedicated coding model, 256k context. Default Kimi model here.</li>
        <li><b>kimi-k2.7-code-highspeed</b> — Same model, faster output.</li>
        <li><b>kimi-k2.6</b> — General dialogue/agent model, visual + text input, 256k context.</li>
        <li><b>kimi-k3</b> — Flagship model, 1M token context, strongest reasoning.</li>
    </ul>
    <p><b>Use when:</b> the task is coding-heavy or involves many chained tool calls / long context.</p>

    <h3>Gemini API</h3>
    <p><b>Best for:</b> general fallback, broad summaries, mixed tasks, long-context tasks.</p>
    <p><b>Key:</b> GOOGLE_API_KEY — get it at console.cloud.google.com</p>
    <p><b>Models:</b></p>
    <ul>
        <li><b>gemini-2.5-pro</b> — Most capable Gemini. Excellent long-context handling.</li>
        <li><b>gemini-2.5-flash</b> — Fast and cost-effective. Good for summaries and drafts.</li>
        <li><b>gemini-2.0-flash</b> — Previous generation Flash. Still solid for general use.</li>
        <li><b>gemini-1.5-pro</b> — 1M token context window. Best for very long documents.</li>
        <li><b>gemini-1.5-flash</b> — Affordable. Good fallback for most tasks.</li>
    </ul>
    <p><b>Use when:</b> you need very long context or a cost-effective alternative to OpenAI/Claude.</p>

    <h3>Audiobook Mode</h3>
    <p>Uses OpenAI TTS only. Provider/model selection in the main panel is ignored for audiobook conversion.</p>
    """)
    tabs.addTab(model_tab, "Models")

    # =========================
    # TAB 2: AGENTS
    # =========================
    agent_tab = QTextBrowser()
    agent_tab.setHtml("""
    <h2>Agent Guide</h2>

    <h3>Chat Agent</h3>
    <p><b>Use for:</b> general questions, explanations, planning, brainstorming.</p>
    <p><b>Recommended:</b> Ollama for simple/private tasks. Claude Sonnet, OpenAI, or Gemini for higher-quality answers.</p>

    <h3>Writing Agent</h3>
    <p><b>Use for:</b> emails, documentation, CVs, professional writing, rewriting.</p>
    <p><b>Recommended:</b> Claude Sonnet (best for nuanced writing). OpenAI as alternative. Ollama for drafts.</p>

    <h3>Coding Agent</h3>
    <p><b>Use for:</b> debugging, code generation, refactoring, explaining errors.</p>
    <p><b>Recommended:</b> Claude Sonnet or DeepSeek for complex code. Ollama for small fixes and private testing.</p>

    <h3>OSINT Agent</h3>
    <p><b>Use for:</b> legal/defensive OSINT summaries, public-source analysis, report structuring.</p>
    <p><b>Recommended:</b> DeepSeek or Gemini for broad analysis. Claude or OpenAI for polished final reports.</p>

    <h3>Audiobook Agent</h3>
    <p><b>Use for:</b> converting ebooks in your audiobook input folder into MP3 audiobooks.</p>
    <p><b>Recommended:</b> OpenAI TTS only. This can cost real API money, so check the estimate first.</p>

    <h3>Manager Agent</h3>
    <p><b>Use for:</b> designing and creating new agents from a plain-language description.</p>
    <p><b>Recommended:</b> Claude Sonnet or DeepSeek for spec generation. The Manager Agent writes the code and DB entry automatically.</p>
    """)
    tabs.addTab(agent_tab, "Agents")

    # =========================
    # TAB 3: ROUTING
    # =========================
    routing_tab = QTextBrowser()
    routing_tab.setHtml("""
    <h2>Routing & API Permissions</h2>

    <h3>Execution Mode</h3>
    <p><b>Local only:</b> always use Ollama/local model. No API cost.</p>
    <p><b>Hybrid allowed:</b> use selected provider, but APIs must be explicitly enabled via checkbox.</p>
    <p><b>Cloud only:</b> force a cloud provider (OpenAI, DeepSeek, Gemini, or Anthropic). API checkbox must be enabled.</p>

    <h3>API Checkboxes</h3>
    <p>Each cloud provider has a checkbox: <b>OpenAI · DeepSeek · Gemini · Anthropic</b>.</p>
    <p>If a checkbox is not ticked, that API will be blocked even if selected as provider.</p>
    <p>This prevents accidental API usage and unexpected costs.</p>

    <h3>Recommended Setup by Task</h3>
    <ul>
        <li><b>Private / simple tasks:</b> Local only + Ollama</li>
        <li><b>Coding / debugging:</b> Hybrid + Anthropic (Claude Sonnet) or DeepSeek</li>
        <li><b>Writing / documents:</b> Hybrid + Anthropic (Claude Sonnet) or OpenAI</li>
        <li><b>OSINT / analysis:</b> Hybrid + DeepSeek or Gemini</li>
        <li><b>Audiobook conversion:</b> OpenAI TTS (automatic, no mode selection needed)</li>
    </ul>
    """)
    tabs.addTab(routing_tab, "Routing")

    # =========================
    # TAB 4: SYSTEM / DYNAMIC INFO
    # =========================
    system_tab = QTextBrowser()
    system_tab.setHtml(f"""
    <h2>Current System & Model Status</h2>

    <h3>Current Selection</h3>
    <p><b>Execution Mode:</b> {current_mode}</p>
    <p><b>Provider:</b> {current_provider}</p>
    <p><b>Model:</b> {current_model}</p>

    <h3>API Key Status</h3>
    <p><b>OpenAI:</b> {openai_status}</p>
    <p><b>DeepSeek:</b> {deepseek_status}</p>
    <p><b>Kimi:</b> {kimi_status}</p>
    <p><b>Gemini:</b> {gemini_status}</p>
    <p><b>Anthropic:</b> {anthropic_status}</p>

    <h3>Installed Ollama Models</h3>
    <p>{ollama_html}</p>

    <h3>Recommendation</h3>
    <p><b>{recommendation}</b></p>
    """)
    tabs.addTab(system_tab, "System")

    # =========================
    # SEARCH FUNCTION
    # =========================
    all_tabs = {
        "Models": model_tab,
        "Agents": agent_tab,
        "Routing": routing_tab,
        "System": system_tab,
    }

    original_html = {
        "Models": model_tab.toHtml(),
        "Agents": agent_tab.toHtml(),
        "Routing": routing_tab.toHtml(),
        "System": system_tab.toHtml(),
    }

    def apply_search():
        query = search_box.text().strip().lower()

        if not query:
            for name, widget in all_tabs.items():
                widget.setHtml(original_html[name])
            return

        for name, widget in all_tabs.items():
            html = original_html[name]
            plain = widget.toPlainText().lower()

            if query in plain:
                widget.setHtml(html)
            else:
                widget.setHtml(
                    f"<h2>{name}</h2>"
                    f"<p>No matches for: <b>{query}</b></p>"
                )

    search_box.textChanged.connect(apply_search)

    dialog.exec()
