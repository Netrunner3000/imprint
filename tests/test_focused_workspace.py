"""Regression tests for the focused Create & Publish product shell."""

import json
from pathlib import Path

import services.resource_monitor as resource_monitor


def test_workspace_map_contains_only_creative_tools():
    import main

    assert main.WORKSPACES == {
        "Write": ("author", "manuscript"),
        "Audio": ("audiobook", "music"),
        "Web": ("webdesign",),
        "Gigs": ("fiverr",),
    }


def test_registry_exposes_only_focused_agents():
    registry_path = Path(__file__).parents[1] / "config" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    assert {agent["name"] for agent in registry["agents"]} == {
        "author", "manuscript", "audiobook", "music", "webdesign", "fiverr"
    }


def test_resource_monitor_degrades_when_os_metrics_are_unavailable(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise OSError("telemetry blocked")

    monkeypatch.setattr(resource_monitor.psutil, "virtual_memory", unavailable)
    monkeypatch.setattr(resource_monitor.psutil, "swap_memory", unavailable)
    monkeypatch.setattr(resource_monitor.psutil, "cpu_percent", unavailable)
    monkeypatch.setattr(resource_monitor.psutil, "sensors_battery", unavailable)

    snapshot = resource_monitor.ResourceMonitor().snapshot()

    assert snapshot["ram_percent"] == 0.0
    assert snapshot["swap_percent"] == 0.0
    assert snapshot["cpu_percent"] == 0.0
    assert snapshot["battery_percent"] is None
