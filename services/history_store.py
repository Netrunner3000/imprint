import json  # used for saving history as JSON
from pathlib import Path  # makes folder paths easier
from datetime import datetime  # used to generate timestamped filenames
from uuid import uuid4

from services.runtime_paths import user_data_base


class HistoryStore:
    def __init__(self, folder: str | Path | None = None):
        # Anchored default: the old relative "data/chats" only resolved
        # correctly because main.py os.chdir()s to the writable base at
        # import time — any other entry point wrote chats wherever the
        # process happened to start.
        self.folder = Path(folder) if folder else user_data_base() / "data" / "chats"
        self.folder.mkdir(parents=True, exist_ok=True)  # create the folder if needed

    def save_chat(self, agent: str, backend: str, model: str, command: str, messages: list,
                  response: str, project: str | None = None,
                  tool: str | None = None):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # make a timestamp
        # A second can contain several completed requests. The old filename
        # silently overwrote the first one; a suffix keeps every conversation.
        filepath = self.folder / f"{timestamp}_{uuid4().hex[:8]}.json"

        payload = {
            "timestamp": timestamp,
            "agent": agent,
            "backend": backend,
            "model": model,
            "command": command,
            "messages": messages,
            "response": response
        }
        if project:
            payload["project"] = project
        if tool:
            payload["tool"] = tool

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)  # save nicely formatted JSON

    def list_chats(self):
        return sorted(self.folder.glob("*.json"), reverse=True)  # newest first

    def load_chat(self, filepath: str):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)  # read a saved chat back into Python

    def unfile_project(self, project_id: str) -> int:
        """Keep every chat but remove a deleted project's association."""
        count = 0
        for path in self.list_chats():
            payload = self.load_chat(str(path))
            if payload.get("project") != project_id:
                continue
            payload.pop("project", None)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(path)
            count += 1
        return count
