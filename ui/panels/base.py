"""What every agent panel repeats: a provider box, a model box, and the code
that fills the second from the first.

Five panels carried their own `*_load_models` — webdesign, fiverr and author
byte-identical, manuscript and music differing in ways that turned out to
matter (see `ALL_PROVIDERS` and `load_models` below). This is the composition
half of phase 3: `GodAI` owns one `AgentPanel` per agent and delegates to it,
rather than a mixin reaching back into the window.

Phase 4 turns each panel into its own module built on this class. Nothing here
constructs a layout for that reason — a panel's arrangement is its own; only the
provider/model pair and its wiring are shared.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from ui.host import AgentHost

# Every provider the app can talk to, in the order the panels list them.
ALL_PROVIDERS = ("ollama", "openai", "deepseek", "kimi", "gemini", "anthropic", "qwen")


class AgentPanel:
    """The provider/model pair for one agent.

    `providers` is the subset that agent may use. It is not cosmetic: the
    manuscript panel deliberately omits `ollama` and `qwen`, matching the
    allowed_providers on its registry row, and a panel that offered them would
    let the user pick a provider the validator then refuses.
    """

    def __init__(self, host: AgentHost, agent: str,
                 providers: tuple[str, ...] = ALL_PROVIDERS,
                 default_provider: str | None = None):
        self.host = host
        self.agent = agent
        self.providers = tuple(providers)

        self.provider_box = QComboBox()
        self.provider_box.addItems(self.providers)
        if default_provider and default_provider in self.providers:
            self.provider_box.setCurrentText(default_provider)

        self.model_box = QComboBox()

        # Reloading on change is why every panel had this method at all.
        self.provider_box.currentTextChanged.connect(self.load_models)

    # ── the part that was copied five times ─────────────────────────────
    def load_models(self) -> None:
        """Fill the model box from the selected provider.

        Failures go through the host's `_note_failure` rather than being
        swallowed. The music panel used to do `except Exception: models = []`,
        which left an empty dropdown and no clue why — exactly the silent-except
        pattern the v1 work replaced everywhere else, missed here because this
        method had been copied before that change.
        """
        provider = self.provider_box.currentText()
        self.model_box.clear()
        try:
            client = getattr(self.host, provider, None)
            models = client.list_models() if client is not None else []
            for model in models:
                self.model_box.addItem(model)
        except Exception as exc:
            self.host._note_failure(f"{self.agent}: load models", exc, self.model_box)

    # ── convenience for the call sites that read the pair ───────────────
    @property
    def provider(self) -> str:
        return self.provider_box.currentText()

    @property
    def model(self) -> str:
        return self.model_box.currentText()
