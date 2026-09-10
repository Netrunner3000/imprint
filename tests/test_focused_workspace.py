"""Regression tests for the focused Imprint product shell."""

import json
from pathlib import Path

import services.resource_monitor as resource_monitor


# The seven agents the fork removed. None of them may come back through a
# workspace, which is the property this file is named for.
STRIPPED_AGENTS = {"chat", "osint", "osint_heavy", "wifi", "bug_bounty",
                   "manager", "nfl_bet"}


def test_workspace_map_contains_only_creative_tools():
    """No stripped agent is reachable from a workspace.

    This asserted an exact literal of the whole map, so it failed on any
    legitimate addition — adding the Video workspace broke it, which says
    nothing about whether a security vertical crept back in. The property is
    what matters, not the inventory.
    """
    import main

    listed = {agent for agents in main.WORKSPACES.values() for agent in agents}
    assert not (listed & STRIPPED_AGENTS), (
        f"a stripped agent is reachable again: {sorted(listed & STRIPPED_AGENTS)}")


def test_every_workspace_agent_has_a_panel():
    """A tab that opens nothing is worse than a missing tab.

    `CUSTOM_PANELS` drives both construction and visibility switching, so an
    agent listed in a workspace but missing from it would build no panel and
    show a blank centre column.
    """
    import main

    listed = {agent for agents in main.WORKSPACES.values() for agent in agents}
    missing = sorted(a for a in listed if a not in main.CUSTOM_PANELS)
    assert not missing, f"workspace agents with no panel: {missing}"

    labelled = sorted(a for a in listed if a not in main.WORKSPACE_LABELS)
    assert not labelled, f"workspace agents with no stage label: {labelled}"


def test_onlyfans_is_a_venture_and_creator_stays_shared():
    import main

    assert main.WORKSPACES["OnlyFans"] == ("onlyfans",)
    assert main.WORKSPACES["Creator"] == ("creator",)
    assert "onlyfans" not in main.WORKSPACES["Creator"]


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


def test_every_workspace_agent_is_registered_and_enabled():
    """A panel the validator refuses is a button that never works.

    `authorize_request` runs every paid call past `Validator.validate`, which
    refuses an agent with no registry row — so an agent can be fully built,
    visible and wired, and still fail on the first click with "Agent 'video' is
    disabled in the registry". Nothing else catches that: the panel builds
    fine, the tests pass, and it only shows up when money is about to be spent.
    """
    import main
    from services.registry import Registry

    registry = Registry()
    listed = {agent for agents in main.WORKSPACES.values() for agent in agents}
    unregistered = sorted(a for a in listed if not registry.is_agent_enabled(a))
    assert not unregistered, (
        f"workspace agents the validator would refuse: {unregistered}")


def test_paid_backends_are_permitted_for_the_agents_that_use_them():
    """Each (agent, backend) pair that reaches authorize_request must pass.

    Higgsfield is a video renderer rather than a chat provider, so it was
    absent from Creator's `allowed_providers` — meaning the guard added to
    meter its renders would have refused all of them instead.
    """
    from services.registry import Registry

    registry = Registry()
    pairs = [
        ("video", "openai"),          # the vidforge pipeline
        ("creator", "higgsfield"),    # promo teasers
        ("fiverr", "openai"),         # logo images
    ]
    refused = [f"{a} + {p}" for a, p in pairs
               if not registry.agent_allows_provider(a, p)]
    assert not refused, f"the validator would refuse: {refused}"


def test_a_new_provider_reaches_an_agent_that_already_exists(tmp_path, monkeypatch):
    """Adding a provider must apply to databases that already have the agent.

    `_seed_default_agents` uses INSERT OR IGNORE, which only ever helps a
    *missing* agent. Without reconciliation an existing row keeps its original
    provider list forever, so adding a backend silently does nothing on every
    machine that has run the app before — which is every machine that matters.
    """
    import json
    import sqlite3

    from services import database

    original = database.DB_PATH
    database.DB_PATH = tmp_path / "reconcile.db"
    try:
        conn = sqlite3.connect(str(database.DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.executescript(database.SCHEMA)
        # An agent as an older build would have written it.
        conn.execute(
            "INSERT INTO agents (name, label, enabled, version, allowed_providers) "
            "VALUES ('creator', 'Creator', 1, '1.0', ?)",
            (json.dumps(["anthropic", "openai"]),))
        conn.commit()

        database._seed_default_agents(conn)

        row = conn.execute(
            "SELECT allowed_providers FROM agents WHERE name='creator'").fetchone()
        providers = json.loads(row["allowed_providers"])
        conn.close()
    finally:
        database.DB_PATH = original

    assert "higgsfield" in providers, "a newly added provider never reached the row"
    # Additive only — the reconciler must not drop what was already there.
    assert {"anthropic", "openai"} <= set(providers)
