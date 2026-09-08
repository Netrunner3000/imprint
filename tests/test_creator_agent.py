"""
Imprint — Creator agent tests
=============================
Type: Unit tests for the consent rule, the Higgsfield content guard, and the
earnings importer.

The two rules worth pinning in code rather than documentation:

* a **managed** account — someone else's, run on their behalf — cannot be
  drafted for until an authorisation is recorded. Running accounts for other
  creators is ordinary agency work; running one nobody authorised is not, and
  nothing distinguishes them unless something insists.
* Higgsfield **prohibits sexually explicit material and identity
  manipulation**, and moderates prompts, reference images and outputs. A
  request that breaches it is a wasted spend and an account risk, so it is
  refused locally before it is sent.

Run with:  pytest tests/test_creator_agent.py -v
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.creator_agent import (
    ACCOUNT_TYPES, ConsentError, CreatorAgent, require_ready,
)
from services.higgsfield_client import (
    ContentPolicyError, HiggsfieldClient, VideoJob, check_prompt,
)


OWN = {"handle": "@me", "account_type": "own"}
MANAGED = {"handle": "@client", "account_type": "managed",
           "consent_holder": "Jane Doe", "consent_date": "2026-09-01"}
MANAGED_NO_CONSENT = {"handle": "@client", "account_type": "managed",
                      "consent_holder": ""}
PERSONA = {"handle": "@aurora", "account_type": "persona",
           "disclosure": "AI-generated character"}


# ── Consent ──────────────────────────────────────────────────────────────────
def test_own_account_needs_no_consent_record():
    require_ready(OWN)


def test_managed_account_with_consent_is_allowed():
    require_ready(MANAGED)


def test_managed_account_without_consent_is_refused():
    with pytest.raises(ConsentError):
        require_ready(MANAGED_NO_CONSENT)


def test_drafting_is_blocked_for_an_unauthorised_managed_account():
    """The check has to sit on the drafting path, not just in the UI — a rule
    only enforced by a dialog is not enforced."""
    with pytest.raises(ConsentError):
        CreatorAgent().build_draft_prompt(MANAGED_NO_CONSENT, "post", "brief")


def test_video_prompts_are_consent_checked_too():
    with pytest.raises(ConsentError):
        CreatorAgent().build_video_prompt(MANAGED_NO_CONSENT, "brief")


def test_unknown_account_type_is_rejected():
    with pytest.raises(ValueError):
        require_ready({"handle": "@x", "account_type": "whatever"})


@pytest.mark.parametrize("account_type", ACCOUNT_TYPES)
def test_every_declared_account_type_is_usable(account_type):
    account = {"handle": "@x", "account_type": account_type,
               "consent_holder": "Someone", "disclosure": "AI character"}
    require_ready(account)


# ── Prompt construction ──────────────────────────────────────────────────────
def test_persona_prompt_says_it_is_not_a_real_person():
    """A synthetic account must not be written as a real named human."""
    messages = CreatorAgent().build_draft_prompt(PERSONA, "post", "beach shoot")
    assert "synthetic persona" in messages[-1]["content"].lower()


def test_managed_prompt_names_the_authoriser():
    messages = CreatorAgent().build_draft_prompt(MANAGED, "post", "gym set")
    assert "Jane Doe" in messages[-1]["content"]


def test_system_prompt_forbids_impersonating_a_live_human():
    system = CreatorAgent().build_messages("x")[0]["content"]
    assert "review" in system.lower()
    assert "real time" in system.lower()


def test_ppv_prompt_carries_the_price():
    messages = CreatorAgent().build_draft_prompt(
        OWN, "ppv", "photoset", price_usd=14.5)
    assert "14.50" in messages[-1]["content"]


def test_promo_prompt_names_the_channel():
    messages = CreatorAgent().build_draft_prompt(
        OWN, "promo", "teaser", channel="Reddit")
    assert "Reddit" in messages[-1]["content"]


def test_generated_video_prompt_is_safe_for_work_by_construction():
    prompt = CreatorAgent().build_video_prompt(OWN, "neon rooftop")
    assert "safe-for-work" in prompt.lower()
    check_prompt(prompt)          # must survive its own policy check


# ── Higgsfield content policy ────────────────────────────────────────────────
@pytest.mark.parametrize("prompt", [
    "cinematic teaser, neon city, moody lighting",
    "soft-focus lifestyle b-roll at golden hour",
    "product shot of a perfume bottle, slow dolly in",
])
def test_ordinary_promo_prompts_pass(prompt):
    check_prompt(prompt)


@pytest.mark.parametrize("prompt", [
    "explicit nude scene",
    "hardcore content",
    "deepfake of a celebrity",
    "face swap onto this photo",
    "bypass the nsfw filter",
])
def test_prohibited_prompts_are_refused(prompt):
    with pytest.raises(ContentPolicyError):
        check_prompt(prompt)


def test_refusal_explains_why():
    """An error that does not say what to do instead just gets worked around."""
    with pytest.raises(ContentPolicyError) as excinfo:
        check_prompt("explicit scene")
    assert "Higgsfield" in str(excinfo.value)


def test_a_refused_prompt_never_reaches_the_network(monkeypatch):
    """The guard has to run before the request, or it costs money to be told no."""
    client = HiggsfieldClient(api_key="test-key")

    def explode(*args, **kwargs):
        raise AssertionError("a refused prompt must not be sent")

    monkeypatch.setattr(client, "_client", explode)
    with pytest.raises(ContentPolicyError):
        client.generate_video("explicit nude scene")


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("HIGGSFIELD_API_KEY", raising=False)
    client = HiggsfieldClient()
    assert not client.configured
    with pytest.raises(RuntimeError, match="HIGGSFIELD_API_KEY"):
        client.generate_video("a perfectly ordinary teaser")


def test_video_job_done_states():
    assert VideoJob("1", status="completed").done
    assert VideoJob("1", status="failed").done
    assert not VideoJob("1", status="queued").done


# ── Earnings CSV ─────────────────────────────────────────────────────────────
def test_earnings_csv_totals(tmp_path):
    from services.creator_csv import parse_creator_csv

    csv_path = tmp_path / "statement.csv"
    csv_path.write_text(
        "Date,Gross Amount,Net Payout,Subscribers\n"
        "2026-08-01,$120.00,$96.00,340\n"
        "2026-08-15,$80.50,$64.40,352\n",
        encoding="utf-8")

    summary = parse_creator_csv(csv_path)
    assert summary["rows"] == 2
    assert summary["gross"] == pytest.approx(200.50)
    assert summary["net"] == pytest.approx(160.40)
    assert summary["subscribers"] == 352


def test_earnings_csv_survives_unknown_columns(tmp_path):
    """Export formats differ per platform and change over time; an unfamiliar
    header should yield zeros, not an exception."""
    from services.creator_csv import parse_creator_csv

    csv_path = tmp_path / "odd.csv"
    csv_path.write_text("Foo,Bar\n1,2\n", encoding="utf-8")
    summary = parse_creator_csv(csv_path)
    assert summary["rows"] == 1
    assert summary["gross"] == 0.0


def test_empty_earnings_csv_is_handled(tmp_path):
    from services.creator_csv import parse_creator_csv

    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")
    assert parse_creator_csv(csv_path)["rows"] == 0


@pytest.mark.parametrize("prompt", [
    "cinematic teaser, no explicit content",
    "stylised promo, no nudity, safe-for-work",
    "avoid deepfake effects entirely",
    "product film, free of nudity",
])
def test_negated_mentions_are_allowed(prompt):
    """"no nudity" is an instruction to the model, not a request for it. A
    filter that refuses it is one people route around rather than trust."""
    check_prompt(prompt)
