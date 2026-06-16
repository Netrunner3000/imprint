import json
import re
from pathlib import Path
from services.database import get_connection


REQUIRED_SPEC_KEYS = {
    "name", "label", "description",
    "allowed_providers", "allowed_tools",
    "budget_limit_eur", "requires_approval",
    "system_prompt",
}

AGENT_TEMPLATE = '''\
class {class_name}Agent:
    """{description}"""

    def __init__(self):
        self.name = {name!r}

    def build_messages(self, prompt: str) -> list:
        return [
            {{"role": "system", "content": {system_prompt!r}}},
            {{"role": "user", "content": prompt}},
        ]
'''


class AgentFactory:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.agents_dir = base_dir / "agents"
        self.config_dir = base_dir / "config"
        self.registry_path = self.config_dir / "registry.json"
        self.tool_prompts_path = self.config_dir / "tool_prompts.json"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_spec(self, spec: dict) -> tuple[bool, str]:
        missing = REQUIRED_SPEC_KEYS - set(spec.keys())
        if missing:
            return False, f"Spec is missing required fields: {', '.join(sorted(missing))}"

        name = spec.get("name", "")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            return False, f"Agent name must be lowercase snake_case, got: {name!r}"

        agent_file = self.agents_dir / f"{name}_agent.py"
        if agent_file.exists():
            return False, f"Agent file already exists: {agent_file.name}"

        with get_connection() as conn:
            row = conn.execute("SELECT name FROM agents WHERE name = ?", (name,)).fetchone()
        if row:
            return False, f"Agent '{name}' already exists in registry."

        return True, "OK"

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def create_agent(self, spec: dict) -> dict:
        """
        Creates all files for the approved spec.
        Returns a report dict with keys: success, files_created, errors.
        """
        report = {"success": False, "files_created": [], "errors": []}

        valid, msg = self.validate_spec(spec)
        if not valid:
            report["errors"].append(msg)
            return report

        name = spec["name"]
        class_name = "".join(part.capitalize() for part in name.split("_"))

        try:
            # 1. Write agent Python file
            agent_file = self._write_agent_file(name, class_name, spec)
            report["files_created"].append(str(agent_file.relative_to(self.base_dir)))
        except Exception as e:
            report["errors"].append(f"Failed to write agent file: {e}")
            return report

        try:
            # 2. Add to registry.json
            self._update_registry(spec)
            report["files_created"].append("config/registry.json (updated)")
        except Exception as e:
            report["errors"].append(f"Failed to update registry: {e}")

        try:
            # 3. Add system prompt to tool_prompts.json
            self._update_tool_prompts(spec)
            report["files_created"].append("config/tool_prompts.json (updated)")
        except Exception as e:
            report["errors"].append(f"Failed to update tool_prompts: {e}")

        report["success"] = len(report["errors"]) == 0
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write_agent_file(self, name: str, class_name: str, spec: dict) -> Path:
        code = AGENT_TEMPLATE.format(
            class_name=class_name,
            description=spec.get("description", ""),
            name=name,
            system_prompt=spec.get("system_prompt", "You are a helpful assistant."),
        )
        path = self.agents_dir / f"{name}_agent.py"
        path.write_text(code, encoding="utf-8")
        return path

    def _update_registry(self, spec: dict) -> None:
        allowed_tools = spec.get("allowed_tools", ["General Chat"])
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO agents
                  (name, label, enabled, version, allowed_providers, allowed_tools,
                   budget_limit_eur, requires_approval, description, log_path, auto_generated)
                VALUES (?,?,1,'1.0',?,?,?,?,?,'data/logs/runs.jsonl',1)
            """, (
                spec["name"],
                spec.get("label", spec["name"].capitalize()),
                json.dumps(spec.get("allowed_providers", ["ollama"])),
                json.dumps(allowed_tools) if allowed_tools is not None else None,
                spec.get("budget_limit_eur"),
                1 if spec.get("requires_approval", False) else 0,
                spec.get("description", ""),
            ))
            conn.commit()

    def _update_tool_prompts(self, spec: dict) -> None:
        label = spec.get("label", spec["name"].capitalize())
        providers = spec.get("allowed_providers", [])
        recommended_provider = providers[0] if providers else "ollama"

        with get_connection() as conn:
            conn.execute("""
                INSERT INTO tools (name, label, system_prompt, recommended_provider, recommended_model)
                VALUES (?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET
                  system_prompt        = excluded.system_prompt,
                  recommended_provider = excluded.recommended_provider,
                  recommended_model    = excluded.recommended_model
            """, (label, label, spec.get("system_prompt", ""), recommended_provider, ""))
            conn.commit()
