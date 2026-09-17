"""Projects group saved chats without changing legacy chat files."""

from pathlib import Path
import json

import pytest

from services import database
from services.history_store import HistoryStore
from services.registry import Registry
from services.chat_projects import (
    continue_chat_messages, conversation_turns, with_project_instructions,
)
from services.usage_tracker import UsageTracker
from services.validator import Validator


def test_project_registry_round_trip_and_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "imprint.db")
    database.init_db()
    registry = Registry()

    registry.upsert_project(
        "novel-1", "Moonlight Novel", instructions="Use a restrained voice.",
        default_agent="author", default_provider="anthropic",
        default_model="claude-sonnet-4-6", budget_eur=2.5,
    )
    project = registry.get_project("novel-1")
    assert project["name"] == "Moonlight Novel"
    assert project["instructions"] == "Use a restrained voice."
    assert project["default_agent"] == "author"
    assert project["budget_eur"] == 2.5
    assert [p["id"] for p in registry.list_projects()] == ["novel-1"]

    registry.archive_project("novel-1")
    assert registry.list_projects() == []
    assert registry.get_project("novel-1")["archived"] == 1
    registry.archive_project("novel-1", False)
    assert len(registry.list_projects()) == 1
    registry.delete_project("novel-1")
    assert registry.get_project("novel-1") is None


def test_project_chat_field_is_optional_and_legacy_chats_load(tmp_path):
    store = HistoryStore(str(tmp_path / "chats"))
    store.save_chat("chat", "ollama", "local", "General Chat",
                    [{"role": "user", "content": "old"}], "answer")
    old = store.load_chat(str(store.list_chats()[0]))
    assert "project" not in old

    # Existing JSON files without a project association still load.
    legacy_path = Path(tmp_path / "chats" / "legacy.json")
    legacy_path.write_text('{"agent":"chat","messages":[],"response":"old"}')
    assert store.load_chat(str(legacy_path)).get("project") is None


def test_two_chats_saved_in_one_second_do_not_overwrite(tmp_path):
    store = HistoryStore(str(tmp_path / "chats"))
    for text in ("first", "second"):
        store.save_chat("chat", "ollama", "local", "General Chat",
                        [{"role": "user", "content": text}], text)
    assert len(store.list_chats()) == 2
    assert {store.load_chat(str(path))["response"] for path in store.list_chats()} == {
        "first", "second",
    }


def test_project_chat_is_tagged(tmp_path):
    store = HistoryStore(str(tmp_path / "chats"))
    store.save_chat("author", "ollama", "local", "Draft",
                    [{"role": "user", "content": "chapter"}], "result",
                    project="novel-1")
    saved = store.load_chat(str(store.list_chats()[0]))
    assert saved["project"] == "novel-1"
    assert store.unfile_project("novel-1") == 1
    assert "project" not in store.load_chat(str(store.list_chats()[0]))


def test_instructions_appear_once_in_system_and_not_in_other_project():
    original = [
        {"role": "system", "content": "You are a writing assistant."},
        {"role": "user", "content": "Draft a scene."},
    ]
    a = with_project_instructions(original, "Use a restrained voice.")
    repeated = with_project_instructions(a, "Use a restrained voice.")
    b = with_project_instructions(original, "Use a vivid voice.")
    assert len(repeated) == 2
    assert repeated[0]["content"].count("Use a restrained voice.") == 1
    assert "Use a restrained voice." not in b[0]["content"]
    assert original[0]["content"] == "You are a writing assistant."


def test_followup_keeps_turns_but_replaces_saved_system_context():
    old = [
        {"role": "system", "content": "Project instructions:\nOld client secret"},
        {"role": "user", "content": "First question"},
    ]
    turns = conversation_turns(old, "First answer")
    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    fresh = [
        {"role": "system", "content": "Project instructions:\nNew brief"},
        {"role": "user", "content": "Second question"},
    ]
    continued = continue_chat_messages(fresh, turns)
    assert [turn["role"] for turn in continued] == [
        "system", "user", "assistant", "user",
    ]
    assert "Old client secret" not in str(continued)
    assert continued[-2]["content"] == "First answer"
    assert conversation_turns(continued, "Second answer")[-1]["content"] == "Second answer"


def test_project_spend_is_separate_and_budget_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "imprint.db")
    database.init_db()
    tracker = UsageTracker()
    for project, cost in (("novel-1", 0.20), ("album-1", 0.70)):
        tracker.log_request(
            "chat", "openai", "gpt-4o", "prompt", "response",
            flat_cost_eur=cost, project=project,
        )
    assert tracker.get_project_today_total("novel-1") == 0.20
    assert tracker.get_project_today_total("album-1") == 0.70
    result = Validator(Registry()).validate(
        agent_name="chat", tool_name=None, provider="openai",
        api_permissions={"allow_openai": True}, session_cost=0,
        session_budget=10, daily_cost=0.9, daily_budget=10,
        estimated_cost=0.31, project_name="Moonlight Novel",
        project_cost=0.20, project_budget=0.50,
    )
    assert not result.allowed
    assert "Moonlight Novel" in result.reason


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_project_filter_intersects_search_and_agent_without_reapplying_defaults(
        app, tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "imprint.db")
    chat_dir = tmp_path / "chats"
    chat_dir.mkdir()
    monkeypatch.setattr(main, "CHATS_DIR", chat_dir)
    window = main.GodAI()
    try:
        window.history = HistoryStore(str(chat_dir))
        window.registry.upsert_project(
            "novel-1", "Moonlight Novel", default_agent="chat",
            instructions="Use the project brief. " * 20,
            budget_eur=0.0,
        )
        for name, project, agent in (
            ("project.json", "novel-1", "chat"),
            ("unfiled.json", "", "author"),
        ):
            payload = {
                "agent": agent, "title": name,
                "messages": [{"role": "user", "content": "hello"}],
                "response": "answer",
            }
            if project:
                payload["project"] = project
            (chat_dir / name).write_text(json.dumps(payload), encoding="utf-8")

        no_project_tokens = window.estimate_chat_cost("ollama", "local", "a")[1]
        window.load_history_list()
        window.history_project_filter.setCurrentIndex(
            window.history_project_filter.findData("novel-1")
        )
        assert window.history_list.count() == 1
        assert window.agent_box.currentText() == "chat"
        assert window.estimate_chat_cost("ollama", "local", "a")[1] > no_project_tokens
        worker = window._new_chat_worker(
            "ollama", "local", [{"role": "user", "content": "hello"}], "hello"
        )
        assert worker.messages[0]["role"] == "system"
        assert worker.messages[0]["content"].count("Use the project brief.") == 20
        from PySide6.QtWidgets import QMessageBox
        warnings = []
        monkeypatch.setattr(
            QMessageBox, "warning",
            staticmethod(lambda _parent, _title, message: warnings.append(message)),
        )
        window.allow_openai_checkbox.setChecked(True)
        window.session_budget_eur = 1000.0
        window.daily_budget_eur = 1000.0
        assert not window.authorize_request(
            "chat", "openai", "gpt-4o", "hello", tool=None
        )
        assert "Moonlight Novel" in warnings[-1]
        window.history_search.setText("unfiled")
        assert window.history_list.count() == 0
        window.history_search.clear()
        window.history_agent_filter.setCurrentText("author")
        assert window.history_list.count() == 0
        window.history_agent_filter.setCurrentText("All agents")

        item = window.history_list.item(0)
        window.open_selected_chat(item)
        assert window.input_box.toPlainText() == ""
        assert "answer" in window.output_box.toPlainText()
        assert window.current_chat_project == "novel-1"
        assert window._conversation_context_text("chat", window.tool_box.currentText()) == \
            "hello\nanswer"
        followup = window._build_chat_request_messages(
            "chat", window.tool_box.currentText(), "next question", True,
        )
        assert [message["role"] for message in followup] == [
            "system", "user", "assistant", "user",
        ]
        assert followup[-1]["content"] == "next question"
        assert followup[0]["content"].count("Use the project brief.") == 20
        assert window._conversation_context_text("author", window.tool_box.currentText()) == ""
        window.history_project_filter.setCurrentIndex(
            window.history_project_filter.findData(main.UNFILED_PROJECTS_FILTER)
        )
        assert window._conversation_context_text("chat", window.tool_box.currentText()) == ""
        window.history_project_filter.setCurrentIndex(
            window.history_project_filter.findData("novel-1")
        )

        window.select_agent("author")
        window.load_history_list()
        assert window.agent_box.currentText() == "author"

        item = window.history_list.item(0)
        window.assign_chat_to_project(item, "")
        assert "project" not in json.loads(
            (chat_dir / "project.json").read_text(encoding="utf-8")
        )
        assert window.history_list.count() == 0
        window.history_project_filter.setCurrentIndex(
            window.history_project_filter.findData(main.UNFILED_PROJECTS_FILTER)
        )
        assert window.history_list.count() == 2
    finally:
        window.resource_timer.stop()
        app.removeEventFilter(window)
        window.close()
        window.deleteLater()


def test_project_manager_edits_instructions_and_budget(app, tmp_path, monkeypatch):
    from ui.project_manager import ProjectManagerDialog

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "imprint.db")
    database.init_db()
    registry = Registry()
    registry.upsert_project("p1", "First")
    manager = ProjectManagerDialog(None, registry)
    try:
        manager.name.setText("Renamed")
        manager.instructions.setPlainText("Keep source citations.")
        manager.budget.setText("1.75")
        manager._save()
        stored = registry.get_project("p1")
        assert stored["name"] == "Renamed"
        assert stored["instructions"] == "Keep source citations."
        assert stored["budget_eur"] == 1.75
        manager._archive()
        assert registry.list_projects() == []
        assert registry.get_project("p1")["archived"] == 1
    finally:
        manager.close()


def test_deleting_project_unfiles_but_keeps_chat(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from ui.project_manager import ProjectManagerDialog

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "imprint.db")
    database.init_db()
    registry = Registry()
    registry.upsert_project("p1", "First")
    history = HistoryStore(str(tmp_path / "chats"))
    history.save_chat("chat", "ollama", "local", "General Chat", [],
                      "saved answer", project="p1")
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *args, **kwargs: QMessageBox.Yes))
    manager = ProjectManagerDialog(None, registry, history=history)
    try:
        manager._delete()
        assert registry.get_project("p1") is None
        assert len(history.list_chats()) == 1
        assert "project" not in history.load_chat(str(history.list_chats()[0]))
    finally:
        manager.close()
