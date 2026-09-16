"""Unknown platform rules must not silently authorise synthetic personas."""

from __future__ import annotations

import pytest


@pytest.fixture
def policy_db(tmp_path, monkeypatch):
    from services import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "policy.db")
    database.init_db()
    return database


def test_unknown_policy_blocks_platform_persona(policy_db):
    from agents.creator.agent import ConsentError, require_ready
    with pytest.raises(ConsentError, match="not confirmed"):
        require_ready({"platform": "OnlyFans", "account_type": "persona",
                       "disclosure": "fictional character"})


def test_policy_requires_source_date_and_explicit_owner_rule(policy_db):
    from agents.creator.agent import ConsentError, require_ready
    from services.creator_platform_policy import get_policy, save_policy
    values = dict(synthetic_persona="allowed", verified_owner_required="unknown",
                  ai_disclosure="#ai", publishing_method="manual_only",
                  source_url="", reviewed_on="")
    with pytest.raises(ValueError, match="source"):
        save_policy("Example", **values)
    values.update(source_url="https://example.test/rules", reviewed_on="2026-09-16")
    save_policy("Example", **values)
    assert get_policy("EXAMPLE")["ai_disclosure"] == "#ai"
    account = {"platform": "Example", "account_type": "persona",
               "disclosure": "fictional character"}
    with pytest.raises(ConsentError, match="depicted account creator"):
        require_ready(account)
    save_policy("Example", **{**values, "verified_owner_required": "no"})
    require_ready(account)


def test_reviewed_disclosure_reaches_prompt(policy_db):
    from agents.creator.agent import CreatorAgent
    from services.creator_platform_policy import save_policy
    save_policy("Example", synthetic_persona="allowed",
                verified_owner_required="no", ai_disclosure="#ai",
                publishing_method="manual_only",
                source_url="https://example.test/rules", reviewed_on="2026-09-16")
    messages = CreatorAgent().build_draft_prompt(
        {"platform": "Example", "account_type": "persona",
         "disclosure": "fictional character"}, "post", "brief")
    assert "requires this AI disclosure: #ai" in messages[-1]["content"]
