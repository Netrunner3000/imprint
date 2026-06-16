import json  # lets Python read JSON config files
from pathlib import Path  # safe file path handling


class ModelRouter:
    def __init__(self, settings_path: str = "config/settings.json"):
        self.settings_path = Path(settings_path)  # store path to settings file

    def load_settings(self) -> dict:
        with open(self.settings_path, "r", encoding="utf-8") as f:  # open settings file
            return json.load(f)  # return parsed settings

    def save_hybrid_mode(self, enabled: bool) -> None:
        settings = self.load_settings()  # load current settings
        settings["hybrid_mode"] = enabled  # update hybrid flag

        with open(self.settings_path, "w", encoding="utf-8") as f:  # open for writing
            json.dump(settings, f, indent=2)  # save updated settings

    def classify_complexity(self, agent_name: str, user_text: str) -> str:
        lowered = user_text.lower()  # lowercase text for easier keyword matching
        text_length = len(user_text)  # prompt size

        if agent_name == "coding":
            if any(word in lowered for word in ["architecture", "refactor", "debug", "bug", "traceback", "design"]):
                return "very_heavy"  # advanced coding work
            if text_length > 300:
                return "heavy"  # longer coding requests
            return "medium"  # moderate coding requests

        if agent_name == "osint":
            if any(word in lowered for word in ["report", "briefing", "risk", "timeline", "assessment", "correlate"]):
                return "heavy"  # analytical OSINT requests
            if text_length > 250:
                return "heavy"  # larger OSINT prompts
            return "medium"  # smaller OSINT prompts

        if agent_name == "writing":
            if any(word in lowered for word in ["professional", "polished", "executive", "formal", "cover letter"]):
                return "heavy"  # high-quality writing
            if text_length > 400:
                return "heavy"  # large writing tasks
            return "light"  # standard writing tasks

        # default chat
        if any(word in lowered for word in ["analyze", "compare", "strategy", "reason", "evaluate"]):
            return "heavy"  # reasoning-heavy general chat
        if text_length > 500:
            return "heavy"  # large prompt
        if text_length > 180:
            return "medium"  # moderate prompt
        return "light"  # simple prompt

    def choose_cloud_backend(self, agent_name: str, complexity: str, settings: dict) -> tuple[str, str]:
        openai_allowed = settings.get("hybrid_openai", True)  # whether OpenAI is allowed in hybrid mode
        deepseek_allowed = settings.get("hybrid_deepseek", False)  # whether DeepSeek is allowed in hybrid mode

        if openai_allowed and not deepseek_allowed:
            return ("openai", settings["cloud_model"])  # OpenAI-only hybrid mode

        if deepseek_allowed and not openai_allowed:
            return ("deepseek", settings["deepseek_model"])  # DeepSeek-only hybrid mode

        # if both are enabled, choose intelligently
        if agent_name == "coding":
            return ("openai", settings["cloud_model"])  # strongest coding backend

        if agent_name == "osint":
            if complexity == "very_heavy":
                return ("openai", settings["cloud_model"])  # strongest synthesis
            return ("deepseek", settings["deepseek_model"])  # cheaper OSINT cloud option

        if agent_name == "writing":
            return ("openai", settings["cloud_model"])  # strongest writing/polish

        if complexity == "very_heavy":
            return ("openai", settings["cloud_model"])  # strongest general reasoning

        return ("gemini", settings["gemini_model"])  # balanced cloud default for general heavy chat

    def choose_backend_and_model(
        self,
        agent_name: str,
        user_text: str,
        backend_override: str = "auto",
        model_override: str | None = None
    ) -> tuple[str, str]:
        settings = self.load_settings()  # load settings
        hybrid_mode = settings.get("hybrid_mode", False)  # read hybrid flag
        complexity = self.classify_complexity(agent_name, user_text)  # classify prompt difficulty

        # manual backend overrides
        if backend_override == "openai":
            return ("openai", settings["cloud_model"])  # force OpenAI

        if backend_override == "deepseek":
            return ("deepseek", settings["deepseek_model"])  # force DeepSeek

        if backend_override == "gemini":
            return ("gemini", settings["gemini_model"])  # force Gemini

        if backend_override == "ollama":
            if model_override and not model_override.startswith("("):
                return ("ollama", model_override)  # force manually selected local model
            if complexity == "light":
                return ("ollama", settings["local_model_fallback"])  # smaller local model
            return ("ollama", settings["local_model_primary"])  # stronger local model

        # auto mode with optional local manual model
        if model_override and not model_override.startswith("("):
            if complexity in {"light", "medium", "heavy"}:
                return ("ollama", model_override)  # respect local model selection in auto mode

        # auto mode without hybrid
        if not hybrid_mode:
            if complexity == "light":
                return ("ollama", settings["local_model_fallback"])  # local fast model
            return ("ollama", settings["local_model_primary"])  # local strong model

        # hybrid mode
        if complexity == "light":
            return ("ollama", settings["local_model_fallback"])  # local and fast

        if complexity == "medium":
            return ("ollama", settings["local_model_primary"])  # local but stronger

        return self.choose_cloud_backend(agent_name, complexity, settings)  # heavy tasks go to cloud intelligently

    def get_cost_hint(self, backend: str, agent_name: str, complexity: str) -> tuple[str, str]:
        if backend == "ollama":
            if complexity == "light":
                return ("Local / free", "green")  # local and cheap
            return ("Local / free, but heavier on your machine", "yellow")  # local but resource-intensive

        if backend == "gemini":
            if complexity in {"light", "medium"}:
                return ("Cloud / low-cost or free-tier possible", "yellow")  # likely low-cost cloud
            return ("Cloud / may use free-tier quota or paid usage", "yellow")  # heavier Gemini use

        if backend == "deepseek":
            return ("Cloud / paid, usually lower cost than OpenAI", "yellow")  # DeepSeek cost hint

        if backend == "openai":
            if agent_name in {"coding", "writing"} or complexity in {"heavy", "very_heavy"}:
                return ("Cloud / paid, potentially higher cost", "red")  # higher-value premium backend
            return ("Cloud / paid", "yellow")  # general OpenAI use

        return ("Unknown cost profile", "yellow")  # fallback
