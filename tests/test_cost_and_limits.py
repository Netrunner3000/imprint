"""
Sentinel AI — Cost & Permission Tests
=====================================
Type: Unit tests of the logic that decides whether a request may run and what
it costs.

Why this file exists: the agent scenario tests cover prompt construction, but
nothing covered the money path — the budget gate and the token/cost maths. That
is the part where a bug spends real money, so it is the part most worth pinning
down. See TODO.md #6.

`Validator` takes its registry by injection, so these tests use a stub and never
touch the database. `UsageTracker.calculate_cost_eur` does read the pricing
table, so it is asserted on invariants that hold for any pricing data rather
than on hardcoded prices.

Run with:  pytest tests/test_cost_and_limits.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.validator import Validator
from services.usage_tracker import UsageTracker


# ─────────────────────────────────────────────────────────────────────────────
# Stub registry — mirrors the methods Validator calls, nothing more.
# ─────────────────────────────────────────────────────────────────────────────
class StubRegistry:
    def __init__(self, **overrides):
        self.agent_enabled = overrides.get("agent_enabled", True)
        self.tool_enabled = overrides.get("tool_enabled", True)
        self.agent_providers = overrides.get("agent_providers", [])   # [] == all
        self.tool_providers = overrides.get("tool_providers", [])
        self.agent_tools = overrides.get("agent_tools", None)         # None == all
        self.agent_budget = overrides.get("agent_budget", None)
        self.requires_approval = overrides.get("requires_approval", False)

    def is_agent_enabled(self, name):
        return self.agent_enabled

    def is_tool_enabled(self, name):
        return self.tool_enabled

    def agent_allows_provider(self, agent, provider):
        return not self.agent_providers or provider in self.agent_providers

    def tool_allows_provider(self, tool, provider):
        return not self.tool_providers or provider in self.tool_providers

    def agent_allows_tool(self, agent, tool):
        return self.agent_tools is None or tool in self.agent_tools

    def get_agent_budget(self, agent):
        return self.agent_budget

    def agent_requires_approval(self, agent):
        return self.requires_approval


ALL_PERMS = {
    "allow_openai": True, "allow_deepseek": True, "allow_kimi": True,
    "allow_gemini": True, "allow_anthropic": True, "allow_qwen": True,
}
NO_PERMS = {k: False for k in ALL_PERMS}


def check(registry=None, **kwargs):
    """Run validate() with sensible defaults, overridden per test."""
    args = dict(
        agent_name="chat",
        tool_name="General Chat",
        provider="openai",
        api_permissions=ALL_PERMS,
        session_cost=0.0,
        session_budget=1.0,
        daily_cost=0.0,
        daily_budget=5.0,
        estimated_cost=0.01,
    )
    args.update(kwargs)
    return Validator(registry or StubRegistry()).validate(**args)


# ─────────────────────────────────────────────────────────────────────────────
# The happy path
# ─────────────────────────────────────────────────────────────────────────────
def test_allows_a_normal_request():
    result = check()
    assert result.allowed
    assert result.reason == "OK"


# ─────────────────────────────────────────────────────────────────────────────
# Registry gates
# ─────────────────────────────────────────────────────────────────────────────
def test_disabled_agent_is_refused():
    assert not check(StubRegistry(agent_enabled=False)).allowed


def test_disabled_tool_is_refused():
    assert not check(StubRegistry(tool_enabled=False)).allowed


def test_provider_not_permitted_for_agent_is_refused():
    registry = StubRegistry(agent_providers=["ollama"])
    assert not check(registry, provider="openai").allowed
    assert check(registry, provider="ollama").allowed


def test_provider_not_permitted_for_tool_is_refused():
    assert not check(StubRegistry(tool_providers=["ollama"]), provider="openai").allowed


def test_tool_not_permitted_for_agent_is_refused():
    assert not check(StubRegistry(agent_tools=["Summarize"]), tool_name="Coding").allowed


def test_agent_requiring_approval_is_refused():
    assert not check(StubRegistry(requires_approval=True)).allowed


def test_empty_tool_name_skips_the_tool_checks():
    """Agent panels pass no tool — their mode names are not registry entries.

    Regression guard: passing the panel's mode ("Person", "Deep Scan", …) as
    tool_name made every such request fail as a disabled tool.
    """
    registry = StubRegistry(tool_enabled=False, tool_providers=["nothing"])
    assert check(registry, tool_name=None).allowed


# ─────────────────────────────────────────────────────────────────────────────
# API permission checkboxes
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "provider", ["openai", "deepseek", "kimi", "gemini", "anthropic", "qwen"]
)
def test_paid_provider_requires_its_checkbox(provider):
    assert not check(provider=provider, api_permissions=NO_PERMS).allowed
    assert check(provider=provider, api_permissions=ALL_PERMS).allowed


def test_ollama_needs_no_permission():
    """Local execution is free, so it bypasses the permission checkboxes."""
    assert check(provider="ollama", api_permissions=NO_PERMS).allowed


# ─────────────────────────────────────────────────────────────────────────────
# Budgets — the checks that actually stop money being spent
# ─────────────────────────────────────────────────────────────────────────────
def test_request_over_session_budget_is_refused():
    result = check(session_cost=0.99, session_budget=1.0, estimated_cost=0.50)
    assert not result.allowed
    assert "Session budget" in result.reason


def test_request_over_daily_budget_is_refused():
    result = check(daily_cost=4.99, daily_budget=5.0, estimated_cost=0.50)
    assert not result.allowed
    assert "Daily budget" in result.reason


def test_request_over_the_per_agent_cap_is_refused():
    result = check(StubRegistry(agent_budget=0.10), estimated_cost=0.25)
    assert not result.allowed
    assert "budget cap" in result.reason


def test_request_exactly_at_the_remaining_budget_is_allowed():
    """The rule is `estimated > remaining`, so spending the last cent is fine."""
    assert check(session_cost=0.5, session_budget=1.0, estimated_cost=0.5).allowed


def test_ollama_ignores_every_budget():
    """A local request costs nothing, so an exhausted budget must not block it."""
    result = check(
        provider="ollama",
        session_cost=99.0, session_budget=1.0,
        daily_cost=99.0, daily_budget=5.0,
        estimated_cost=0.0,
    )
    assert result.allowed


# ─────────────────────────────────────────────────────────────────────────────
# Token accounting — decides what the user is billed for
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def tracker():
    """A tracker whose writes land in a throwaway database.

    `UsageTracker.log_request` INSERTs into the app's real `usage` table, so a
    test that calls it bills the user: the first version of the per-unit tests
    below put nine fabricated requests and €0.47 of imaginary spend into the
    live spend counters. Read-only helpers never needed the isolation, which is
    why it was missing until a test wrote something.
    """
    import sqlite3
    import tempfile
    from pathlib import Path

    from services import database

    original = database.DB_PATH
    with tempfile.TemporaryDirectory() as tmp:
        database.DB_PATH = Path(tmp) / "test.db"
        conn = sqlite3.connect(str(database.DB_PATH))
        conn.executescript(database.SCHEMA)
        # Seeded the same way a real launch seeds it. Without the pricing rows
        # calculate_cost_eur returns 0.0 for every provider, which would make
        # the billing tests pass against an empty table for the wrong reason.
        database._seed_pricing_from_json(conn)
        conn.commit()
        conn.close()
        try:
            yield UsageTracker()
        finally:
            database.DB_PATH = original


def test_missing_usage_falls_back_to_an_estimate(tracker):
    i, o, kind = tracker.normalize_usage(None, "x" * 400, "y" * 800)
    assert kind == "estimated"
    assert (i, o) == (100, 200)          # ~4 chars per token


def test_real_usage_is_reported_as_exact(tracker):
    usage = {"input_tokens": 123, "output_tokens": 456}
    assert tracker.normalize_usage(usage, "prompt", "response") == (123, 456, "exact")


@pytest.mark.parametrize("keys", [
    ("input_tokens", "output_tokens"),           # anthropic / generic
    ("prompt_tokens", "completion_tokens"),      # openai-compatible
    ("prompt_token_count", "candidates_token_count"),  # gemini
])
def test_each_sdk_token_naming_is_understood(tracker, keys):
    """Every provider names these differently; all must be read correctly."""
    usage = {keys[0]: 10, keys[1]: 20}
    assert tracker.normalize_usage(usage, "p", "r") == (10, 20, "exact")


def test_partial_usage_is_marked_mixed(tracker):
    """A provider reporting only one side must not bill the other as zero."""
    i, o, kind = tracker.normalize_usage({"input_tokens": 50}, "p" * 40, "r" * 80)
    assert (i, kind) == (50, "mixed")
    assert o > 0


def test_token_estimate_never_returns_zero(tracker):
    """Zero tokens would silently make a request look free."""
    assert tracker.estimate_tokens("", "") == (1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Cost — asserted as invariants, so local pricing data cannot break these
# ─────────────────────────────────────────────────────────────────────────────
def test_local_execution_is_always_free(tracker):
    assert tracker.calculate_cost_eur("ollama", "deepseek-r1:8b", 10**6, 10**6) == 0.0


def test_unknown_backend_costs_nothing(tracker):
    assert tracker.calculate_cost_eur("no-such-backend", "no-such-model", 1000, 1000) == 0.0


def test_cost_scales_with_token_count(tracker):
    small = tracker.calculate_cost_eur("openai", "gpt-4o", 1_000, 1_000)
    large = tracker.calculate_cost_eur("openai", "gpt-4o", 100_000, 100_000)
    if small == 0.0 and large == 0.0:
        pytest.skip("no pricing row for openai/gpt-4o in this database")
    assert large > small


def test_cost_is_never_negative(tracker):
    assert tracker.calculate_cost_eur("openai", "gpt-4o", 0, 0) >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Prompt caching — cached input tokens bill at a discounted rate
# ─────────────────────────────────────────────────────────────────────────────
def test_cached_input_is_cheaper_than_uncached(tracker):
    """The whole point of the cached rate: repeated context costs less."""
    full = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 10**6, 0)
    cached = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 10**6, 0,
                                        cached_input_tokens=10**6)
    assert 0 < cached < full


def test_cached_tokens_default_to_the_full_rate(tracker):
    """Omitting the argument must not change what an existing caller is billed."""
    a = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 10**6, 10**6)
    b = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 10**6, 10**6,
                                   cached_input_tokens=0)
    assert a == b


def test_partly_cached_input_lands_between_the_two_rates(tracker):
    full = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 10**6, 0)
    all_cached = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 10**6, 0,
                                            cached_input_tokens=10**6)
    half = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 10**6, 0,
                                      cached_input_tokens=5 * 10**5)
    assert all_cached < half < full


def test_more_cached_than_input_tokens_cannot_go_negative(tracker):
    """A provider over-reporting cache hits must not produce a credit."""
    cost = tracker.calculate_cost_eur("kimi", "kimi-k2.7-code", 1000, 0,
                                      cached_input_tokens=99999)
    assert cost >= 0


def test_a_backend_without_a_cached_rate_bills_at_full_input(tracker):
    """No cached rate known means no discount — never a free request."""
    full = tracker.calculate_cost_eur("anthropic", "claude-sonnet-5", 10**6, 0)
    claimed = tracker.calculate_cost_eur("anthropic", "claude-sonnet-5", 10**6, 0,
                                         cached_input_tokens=10**6)
    assert claimed == full


@pytest.mark.parametrize("backend,model", [
    ("kimi", "kimi-k2.7-code"),
    ("openai", "gpt-4o-mini"),
    ("deepseek", "deepseek-chat"),
])
def test_every_priced_provider_actually_bills(tracker, backend, model):
    """Regression: these four had no pricing rows at all, so every request
    through them cost EUR 0.00 — invisible to the budget caps and the spend
    counters. Gemini is excluded: its rates are genuinely 0.0 in
    config/pricing.json and still need filling in."""
    assert tracker.calculate_cost_eur(backend, model, 10**6, 10**6) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Rename migration — the app was "Create & Publish" before it was Imprint
# ─────────────────────────────────────────────────────────────────────────────
def test_a_previous_database_is_adopted(tmp_path, monkeypatch):
    """Renaming the app renamed its database file. Without adoption the app
    starts empty: no usage history, no KDP ingests, no todos."""
    import sqlite3
    from services import database as db

    data = tmp_path / "data"
    data.mkdir()
    old = data / "create_and_publish.db"
    conn = sqlite3.connect(old)
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO settings VALUES ('marker', 'carried-over')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_PATH", data / "imprint.db")
    db._adopt_previous_db()

    assert not old.exists(), "old database left behind"
    moved = sqlite3.connect(data / "imprint.db")
    value = moved.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0]
    moved.close()
    assert value == "carried-over"


def test_an_empty_placeholder_does_not_block_adoption(tmp_path, monkeypatch):
    """Connecting to a sqlite path creates the file, so anything touching the
    new path before init_db leaves a 0-table placeholder. Treating that as a
    real database is what would silently strand the user's data."""
    import sqlite3
    from services import database as db

    data = tmp_path / "data"
    data.mkdir()
    old = data / "create_and_publish.db"
    conn = sqlite3.connect(old)
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO settings VALUES ('marker', 'real-data')")
    conn.commit()
    conn.close()
    sqlite3.connect(data / "imprint.db").close()          # the placeholder

    monkeypatch.setattr(db, "DB_PATH", data / "imprint.db")
    db._adopt_previous_db()

    moved = sqlite3.connect(data / "imprint.db")
    value = moved.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0]
    moved.close()
    assert value == "real-data"


def test_a_populated_database_is_never_clobbered(tmp_path, monkeypatch):
    """Adoption must be one-way and safe: real current data wins."""
    import sqlite3
    from services import database as db

    data = tmp_path / "data"
    data.mkdir()
    for name, marker in (("create_and_publish.db", "old"), ("imprint.db", "current")):
        conn = sqlite3.connect(data / name)
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO settings VALUES ('marker', ?)", (marker,))
        conn.commit()
        conn.close()

    monkeypatch.setattr(db, "DB_PATH", data / "imprint.db")
    db._adopt_previous_db()

    kept = sqlite3.connect(data / "imprint.db")
    value = kept.execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0]
    kept.close()
    assert value == "current"
    assert (data / "create_and_publish.db").exists(), "old database should be left alone"


# ── Per-unit billing ─────────────────────────────────────────────────────────
class TestPerUnitPricing:
    """Work that is not billed per token.

    An image, a video render and a minute of speech are all priced per unit,
    and the token cost model returns 0.00 for every one of them. That is how
    DALL-E generation, Higgsfield renders and TTS all ran outside the session
    and daily caps regardless of what they actually cost.
    """

    def test_a_flat_cost_wins_over_the_token_arithmetic(self, tracker):
        entry = tracker.log_request(
            agent="fiverr", backend="openai", model="dall-e-3",
            prompt_text="two logo concepts", response_text="",
            flat_cost_eur=0.0736)
        assert entry["cost_eur"] == 0.0736
        assert entry["cost_type"] == "per_unit"

    def test_without_it_an_image_request_bills_effectively_nothing(self, tracker):
        """The bug this exists to prevent, pinned so it cannot come back.

        dall-e-3 has no row of its own, so the token path falls through to
        OpenAI's default text rates and prices a $0.04 image as the handful of
        tokens in its prompt — €0.000001 here. Not literally zero, which is
        worse: it looks like a real number.
        """
        entry = tracker.log_request(
            agent="fiverr", backend="openai", model="dall-e-3",
            prompt_text="two logo concepts", response_text="")
        real_cost = 0.04 * per_unit_eur_per_usd()
        assert entry["cost_eur"] < real_cost / 1000, (
            "the token path should badly under-price an image; if this now "
            "prices it correctly the per-unit path may be redundant")


def per_unit_eur_per_usd() -> float:
    from services import per_unit_pricing
    return per_unit_pricing.eur_per_usd()

    def test_a_flat_cost_counts_toward_the_daily_total(self, tracker):
        before = tracker.get_today_total()
        tracker.log_request(
            agent="creator", backend="higgsfield", model="higgsfield-video",
            prompt_text="teaser", response_text="", flat_cost_eur=0.25)
        assert tracker.get_today_total() == pytest.approx(before + 0.25)

    def test_zero_in_the_price_table_reads_as_unknown_not_free(self):
        """An unfilled placeholder and a genuinely free service look identical
        in JSON. Of the two readings, silently billing nothing is the one that
        costs money, so 0 means unknown."""
        from services import per_unit_pricing
        assert per_unit_pricing.rate_usd("higgsfield_render") is None
        assert per_unit_pricing.render_cost_eur() is None
        assert "not priced" in per_unit_pricing.describe(None, "1 render")

    def test_a_known_rate_converts_to_euros(self):
        from services import per_unit_pricing
        cost = per_unit_pricing.image_cost_eur("dall-e-3", 2)
        assert cost == pytest.approx(0.04 * 2 * per_unit_pricing.eur_per_usd())

    def test_an_unpriced_model_is_unknown_rather_than_zero(self):
        from services import per_unit_pricing
        assert per_unit_pricing.image_cost_eur("some-unlisted-model", 1) is None
