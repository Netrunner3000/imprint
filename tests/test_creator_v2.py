"""
Imprint — Creator agent, second arc
===================================
Type: Unit + panel tests for voice, persona, insights, media and records.

Covers the three things v1 left thin — an unused media column, a Higgsfield
submit with no polling behind it, and untested panel handlers — plus the
feedback loop from posted content back into the next draft.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A real schema in a throwaway file — these are SQL-shaped behaviours."""
    import services.database as database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "t.db")
    database.init_db()

    import agents.creator.profile as profile
    import agents.creator.insights as insights
    monkeypatch.setattr(profile, "get_connection", database.get_connection)
    monkeypatch.setattr(insights, "get_connection", database.get_connection)

    conn = database.get_connection()
    conn.execute(
        "INSERT INTO creator_accounts (handle, account_type, created_at) "
        "VALUES ('@a', 'own', ?)", (datetime.now().isoformat(),))
    conn.commit()
    account_id = conn.execute(
        "SELECT id FROM creator_accounts WHERE handle='@a'").fetchone()[0]
    return database, account_id


# ── Voice ────────────────────────────────────────────────────────────────────
def test_voice_block_is_empty_when_nothing_is_recorded(db):
    from agents.creator.profile import voice_block
    _, account_id = db
    assert voice_block(account_id) == ""


def test_voice_block_carries_the_samples(db):
    """Samples are what the model imitates — the rules only stop it drifting."""
    from agents.creator.profile import save_voice, voice_block
    _, account_id = db
    save_voice(account_id, samples="first post\nsecond post", tone="dry")
    block = voice_block(account_id)
    assert "first post" in block and "second post" in block
    assert "dry" in block


def test_voice_samples_are_capped(db):
    """Beyond a handful the marginal value drops and the prompt just costs more."""
    from agents.creator.profile import MAX_SAMPLES, save_voice, voice_block
    _, account_id = db
    save_voice(account_id, samples="\n".join(f"post {i}" for i in range(30)))
    assert voice_block(account_id).count("  — ") == MAX_SAMPLES


def test_saving_voice_twice_updates_rather_than_duplicates(db):
    from agents.creator.profile import load_voice, save_voice
    database, account_id = db
    save_voice(account_id, tone="first")
    save_voice(account_id, tone="second")
    assert load_voice(account_id)["tone"] == "second"
    count = database.get_connection().execute(
        "SELECT COUNT(*) FROM creator_voice").fetchone()[0]
    assert count == 1


def test_voice_reaches_the_draft_prompt(db):
    """The point of the whole feature: it has to be in the prompt."""
    from agents.creator import CreatorAgent
    from agents.creator.profile import save_voice
    _, account_id = db
    save_voice(account_id, samples="a line only this creator would write")
    messages = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"},
        "post", "brief")
    assert "a line only this creator would write" in messages[-1]["content"]


# ── Persona ──────────────────────────────────────────────────────────────────
def test_persona_block_reaches_persona_accounts_only(db):
    from agents.creator import CreatorAgent
    from agents.creator.profile import save_persona
    _, account_id = db
    save_persona(account_id, appearance="silver hair", backstory="from Lisbon")

    persona = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "persona"},
        "post", "x")
    assert "silver hair" in persona[-1]["content"]

    own = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"}, "post", "x")
    assert "silver hair" not in own[-1]["content"]


def test_persona_seed_is_kept_for_consistent_renders(db):
    from agents.creator.profile import persona_seed, save_persona
    _, account_id = db
    save_persona(account_id, appearance="x", seed=4821)
    assert persona_seed(account_id) == 4821


def test_persona_appearance_is_reused_in_video_prompts(db):
    """Without it every render is a different character."""
    from agents.creator import CreatorAgent
    from agents.creator.profile import save_persona
    _, account_id = db
    save_persona(account_id, appearance="silver hair, green coat")
    prompt = CreatorAgent().build_video_prompt(
        {"id": account_id, "handle": "@a", "account_type": "persona"}, "rooftop")
    assert "silver hair" in prompt


# ── Segments ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("segment", ["new", "loyal", "lapsed", "big_spender"])
def test_each_segment_changes_the_prompt(db, segment):
    from agents.creator import CreatorAgent
    _, account_id = db
    messages = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"},
        "welcome", "x", segment=segment)
    assert "Audience:" in messages[-1]["content"]


def test_no_segment_adds_nothing(db):
    from agents.creator import CreatorAgent
    _, account_id = db
    messages = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"},
        "welcome", "x", segment="")
    assert "Audience:" not in messages[-1]["content"]


# ── Insights ─────────────────────────────────────────────────────────────────
def _post(database, account_id, price, revenue, kind="ppv"):
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO creator_content (account_id, created_at, kind, price_usd,"
        " status, revenue_usd) VALUES (?,?,?,?,'posted',?)",
        (account_id, datetime.now().isoformat(), kind, price, revenue))
    conn.commit()


def test_price_history_is_empty_without_data(db):
    from agents.creator.insights import price_history
    _, account_id = db
    assert price_history(account_id) == ""


def test_price_history_reports_the_average_per_price(db):
    from agents.creator.insights import price_history
    database, account_id = db
    _post(database, account_id, 10.0, 40.0)
    _post(database, account_id, 10.0, 60.0)
    history = price_history(account_id)
    assert "$10.00" in history and "50.00" in history


def test_thin_evidence_is_labelled(db):
    """Three sales at $15 is an anecdote, and presenting it as a finding is
    worse than not presenting it."""
    from agents.creator.insights import price_history
    database, account_id = db
    _post(database, account_id, 15.0, 20.0)
    assert "few sends" in price_history(account_id)


def test_asset_outcome_keeps_currency_and_evidence_separate(db):
    from agents.creator.insights import asset_outcomes, record_outcome
    database, account_id = db
    conn = database.get_connection()
    cur = conn.execute(
        "INSERT INTO creator_content (account_id, created_at, title, status, "
        "generation_cost_eur) VALUES (?,?,?,'draft',?)",
        (account_id, datetime.now().isoformat(), "Test post", 0.12))
    conn.commit()
    content_id = cur.lastrowid
    values = dict(campaign="Launch", channel="Instagram", permalink="https://example.test/p",
                  reach=500, clicks=25, subscriptions=3, ppv_purchases=1,
                  revenue_usd=30.0, attributable_cost_usd=10.0,
                  source="platform export", window="2026-09-01 to 2026-09-07")
    record_outcome(content_id, **values)
    row = asset_outcomes(account_id)[0]
    assert row["status"] == "posted"
    assert (row["campaign"], row["channel"], row["clicks"]) == (
        "Launch", "Instagram", 25)
    assert row["generation_cost_eur"] == 0.12
    assert row["attributable_cost_usd"] == 10.0
    assert row["metric_source"] == "platform export"
    with pytest.raises(ValueError, match="source"):
        record_outcome(content_id, **{**values, "source": ""})


def test_price_history_reaches_the_ppv_prompt(db):
    from agents.creator import CreatorAgent
    from agents.creator.insights import price_history
    database, account_id = db
    _post(database, account_id, 12.0, 90.0)
    messages = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"},
        "ppv", "x", price_usd=12.0, price_history=price_history(account_id))
    assert "actually earned" in messages[-1]["content"]


def test_recording_revenue_marks_it_posted(db):
    from agents.creator.insights import record_revenue
    database, account_id = db
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO creator_content (account_id, created_at, kind, status) "
        "VALUES (?,?,'post','draft')", (account_id, datetime.now().isoformat()))
    conn.commit()
    content_id = conn.execute("SELECT id FROM creator_content").fetchone()[0]

    record_revenue(content_id, 42.5)
    row = database.get_connection().execute(
        "SELECT status, revenue_usd FROM creator_content WHERE id = ?",
        (content_id,)).fetchone()
    assert row["status"] == "posted"
    assert row["revenue_usd"] == pytest.approx(42.5)


def test_account_summary_handles_no_subscribers(db):
    """Division by zero is the obvious way this breaks on a new account."""
    from agents.creator.insights import account_summary
    _, account_id = db
    assert account_summary(account_id)["per_subscriber"] == 0.0


def test_agency_overview_lists_every_account(db):
    from agents.creator.insights import agency_overview
    database, _ = db
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO creator_accounts (handle, account_type, consent_holder, "
        "created_at) VALUES ('@b','managed','Jane', ?)",
        (datetime.now().isoformat(),))
    conn.commit()
    handles = {row["handle"] for row in agency_overview()}
    assert handles == {"@a", "@b"}


@pytest.mark.parametrize("rate,expected_manager", [(0, 0.0), (20, 200.0), (100, 1000.0)])
def test_commission_split(rate, expected_manager):
    from agents.creator.insights import commission
    split = commission(1000.0, rate)
    assert split["manager"] == pytest.approx(expected_manager)
    assert split["manager"] + split["creator"] == pytest.approx(1000.0)


def test_commission_rate_is_clamped():
    """A typo in a percentage field should not invent money."""
    from agents.creator.insights import commission
    assert commission(1000.0, 500)["manager"] == pytest.approx(1000.0)
    assert commission(1000.0, -50)["manager"] == pytest.approx(0.0)


# ── Panel handlers (the gap v1 left) ─────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app):
    from PySide6.QtWidgets import QMessageBox
    import main
    saved = (QMessageBox.warning, QMessageBox.question, QMessageBox.information)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        w = main.GodAI()
        yield w
    finally:
        QMessageBox.warning, QMessageBox.question, QMessageBox.information = saved


def test_creator_panel_has_every_tab(window):
    titles = [window.creator_panel.creator_tabs.tabText(i)
              for i in range(window.creator_panel.creator_tabs.count())]
    for expected in ("Draft", "Calendar", "Earnings", "Voice", "Media",
                     "Agency", "Records"):
        assert any(expected in t for t in titles), f"missing {expected} tab"
    assert "Trends" not in titles


def test_higgsfield_has_an_explicit_api_permission(window):
    window.allow_higgsfield_checkbox.setChecked(False)
    assert not window.current_api_permissions()["allow_higgsfield"]
    window.allow_higgsfield_checkbox.setChecked(True)
    assert window.current_api_permissions()["allow_higgsfield"]
    window.allow_higgsfield_checkbox.setChecked(False)


def test_video_job_schema_preserves_cost_and_lifecycle(db):
    database, _ = db
    columns = {
        row["name"] for row in database.get_connection().execute(
            "PRAGMA table_info(creator_video_jobs)")
    }
    assert {
        "request_id", "endpoint", "prompt_version", "estimated_credits",
        "estimated_usd", "actual_usd", "status", "policy_result",
        "local_path", "correlation_id",
    } <= columns


def test_onlyfans_handoff_loads_a_structured_creator_campaign(window):
    context = {
        "venture": "OnlyFans", "platform": "OnlyFans",
        "signal": "POV mini-series", "category": "Story-led",
        "geography": "Global", "window": "30 days",
        "opportunity_index": 77, "momentum_index": 82,
        "demand_index": 76, "saturation_index": 54,
        "monetization_index": 84, "suggested_format": "3-part vertical video",
        "pricing_experiment": "$12–18 bundle", "risk": "Low",
        "source": "Demonstration dataset", "observed_at": "2026-09-09",
        "confidence": "sample",
        "deliverables": ("three concepts", "captions", "posting plan", "assets"),
    }
    window._onlyfans_create_campaign(context)
    assert window._current_agent == "creator"
    assert window.creator_panel.creator_platform_box.currentText() == "OnlyFans"
    assert window.creator_panel.creator_kind_box.currentText() == "campaign"
    brief = window.creator_panel.creator_brief_input.toPlainText()
    assert "POV mini-series" in brief
    assert "Demonstration dataset" in brief
    assert "posting plan" in brief


def test_onlyfans_teaser_uses_creator_higgsfield_pipeline(window, monkeypatch):
    context = {
        "venture": "OnlyFans", "platform": "OnlyFans",
        "signal": "POV mini-series", "category": "Story-led",
        "geography": "Global", "window": "30 days",
        "opportunity_index": 77, "momentum_index": 82,
        "demand_index": 76, "saturation_index": 54,
        "monetization_index": 84, "suggested_format": "3-part vertical video",
        "pricing_experiment": "$12–18 bundle", "risk": "Low",
        "source": "Demonstration dataset", "observed_at": "2026-09-09",
        "confidence": "sample",
        "deliverables": ("three concepts", "captions", "posting plan", "assets"),
    }
    calls = []
    monkeypatch.setattr(window, "creator_generate_video", lambda: calls.append(True))

    window._onlyfans_generate_teaser(context)

    assert window._current_agent == "creator"
    assert window.creator_panel.creator_platform_box.currentText() == "OnlyFans"
    assert "POV mini-series" in window.creator_panel.creator_brief_input.toPlainText()
    assert calls == [True]


def test_consent_fields_appear_only_for_managed_accounts(window):
    window._creator_type_changed("own")
    assert not window.creator_panel.creator_consent_input.isVisible()
    window._creator_type_changed("managed")
    assert window.creator_panel.creator_consent_input.isVisibleTo(window.creator_panel)


def test_persona_fields_appear_only_for_personas(window):
    window._creator_type_changed("persona")
    assert window.creator_panel.creator_disclosure_input.isVisibleTo(window.creator_panel)
    window._creator_type_changed("own")
    assert not window.creator_panel.creator_disclosure_input.isVisible()


def test_price_shows_only_for_ppv(window):
    window._creator_kind_changed("post")
    assert not window.creator_panel.creator_price_input.isVisible()
    window._creator_kind_changed("ppv")
    assert window.creator_panel.creator_price_input.isVisibleTo(window.creator_panel)


def test_segment_shows_only_where_it_means_something(window):
    window._creator_kind_changed("welcome")
    assert window.creator_panel.creator_segment_box.isVisibleTo(window.creator_panel)
    window._creator_kind_changed("bio")
    assert not window.creator_panel.creator_segment_box.isVisible()


def test_drafting_without_an_account_does_not_crash(window):
    window.creator_panel.creator_account_box.clear()
    window.creator_generate()          # warns and returns


def test_media_kind_is_inferred_from_the_extension(window, tmp_path):
    import services.database as database
    conn = database.get_connection()
    conn.execute("INSERT OR IGNORE INTO creator_accounts (handle, account_type,"
                 " created_at) VALUES ('@paneltest','own',?)",
                 (datetime.now().isoformat(),))
    conn.commit()
    account_id = conn.execute(
        "SELECT id FROM creator_accounts WHERE handle='@paneltest'").fetchone()[0]

    window._creator_store_media(account_id, str(tmp_path / "clip.mp4"))
    window._creator_store_media(account_id, str(tmp_path / "shot.jpg"))
    rows = dict(database.get_connection().execute(
        "SELECT path, kind FROM creator_media WHERE account_id = ?",
        (account_id,)).fetchall())
    assert rows[str(tmp_path / "clip.mp4")] == "video"
    assert rows[str(tmp_path / "shot.jpg")] == "image"

    conn = database.get_connection()
    conn.execute("DELETE FROM creator_media WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM creator_accounts WHERE id = ?", (account_id,))
    conn.commit()


# ── Higgsfield worker ────────────────────────────────────────────────────────
def test_worker_reports_a_failed_render_rather_than_hanging(app, tmp_path):
    """v1 submitted and told the user to go look elsewhere. The worker has to
    finish, one way or the other."""
    from ui.workers import HiggsfieldWorker
    from services.higgsfield_client import VideoJob

    class FailingClient:
        def generate_video(self, prompt, **kwargs):
            return VideoJob("job-1", status="queued")

        def wait(self, job, **kwargs):
            return VideoJob("job-1", status="failed", error="render failed")

    worker = HiggsfieldWorker(FailingClient(), "a teaser", tmp_path / "out.mp4")
    errors = []
    worker.error_signal.connect(errors.append)
    worker.run()                      # synchronous: exercise the body directly
    assert errors and "render failed" in errors[0]


def test_estimate_worker_prepares_before_pricing(app):
    from services.higgsfield_client import PreparedVideoRequest, VideoEstimate
    from ui.workers import HiggsfieldEstimateWorker

    events = []

    class Client:
        def prepare_video(self, prompt, **kwargs):
            events.append(("prepare", prompt, kwargs))
            return PreparedVideoRequest("/model/video", {"prompt": prompt})

        def estimate(self, request):
            events.append(("estimate", request))
            return VideoEstimate(credits=2, usd=1)

    worker = HiggsfieldEstimateWorker(Client(), "safe teaser", duration=6)
    results = []
    worker.done_signal.connect(lambda request, estimate: results.append(
        (request, estimate)))
    worker.run()

    assert [event[0] for event in events] == ["prepare", "estimate"]
    assert results[0][1].usd == pytest.approx(1)


def test_worker_cancels_a_queued_remote_render(app, tmp_path):
    from services.higgsfield_client import VideoJob
    from ui.workers import HiggsfieldWorker

    cancelled = []

    class Client:
        def generate_video(self, prompt, **kwargs):
            return VideoJob("job-cancel", status="queued")

        def wait(self, job, *, should_cancel, **kwargs):
            assert should_cancel()
            cancelled.append(job.job_id)
            return VideoJob(job.job_id, status="canceled")

    worker = HiggsfieldWorker(Client(), "teaser", tmp_path / "out.mp4")
    errors = []
    worker.error_signal.connect(errors.append)
    worker.cancel()
    worker.run()

    assert cancelled == ["job-cancel"]
    assert errors == ["Render canceled"]


def test_worker_passes_the_seed_through(app, tmp_path):
    """A persona's locked seed has to reach the API or renders drift."""
    from ui.workers import HiggsfieldWorker
    from services.higgsfield_client import VideoJob

    seen = {}

    class RecordingClient:
        def generate_video(self, prompt, **kwargs):
            seen.update(kwargs)
            return VideoJob("job-1")

        def wait(self, job, **kwargs):
            return VideoJob("job-1", status="failed", error="stop here")

    worker = HiggsfieldWorker(RecordingClient(), "teaser",
                              tmp_path / "out.mp4", seed=4821)
    worker.error_signal.connect(lambda _: None)
    worker.run()
    assert seen.get("seed") == 4821


def test_deleting_project_unfiles_creator_work_but_keeps_account_and_consent(db):
    from services.registry import Registry

    database, account_id = db
    registry = Registry()
    registry.upsert_project("creator-work", "Creator campaign")
    with database.get_connection() as conn:
        conn.execute(
            "UPDATE creator_accounts SET account_type='managed', "
            "consent_holder='Authorised client' WHERE id=?", (account_id,))
        conn.execute(
            "INSERT INTO creator_content "
            "(account_id, project_id, created_at, body) VALUES (?,?,?,?)",
            (account_id, "creator-work", datetime.now().isoformat(), "A draft"))
        conn.execute(
            "INSERT INTO creator_video_jobs "
            "(request_id, account_id, project_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            ("creator-job", account_id, "creator-work", "now", "now"))
    registry.delete_project("creator-work")
    with database.get_connection() as conn:
        content = conn.execute(
            "SELECT project_id, body FROM creator_content").fetchone()
        job = conn.execute(
            "SELECT project_id FROM creator_video_jobs WHERE request_id=?",
            ("creator-job",)).fetchone()
        account = conn.execute(
            "SELECT consent_holder FROM creator_accounts WHERE id=?",
            (account_id,)).fetchone()
    assert (content["project_id"], content["body"]) == (None, "A draft")
    assert job["project_id"] is None
    assert account["consent_holder"] == "Authorised client"


def test_existing_creator_tables_gain_optional_project_columns(tmp_path, monkeypatch):
    import sqlite3
    from services import database

    path = tmp_path / "legacy.db"
    legacy_schema = database.SCHEMA.replace(
        "    project_id   TEXT REFERENCES projects(id) ON DELETE SET NULL,\n",
        "", 1).replace(
        "    project_id       TEXT REFERENCES projects(id) ON DELETE SET NULL,\n",
        "", 1)
    with sqlite3.connect(path) as conn:
        conn.executescript(legacy_schema)
        conn.execute(
            "INSERT INTO creator_accounts (handle, created_at) "
            "VALUES ('@legacy', 'yesterday')")
        conn.execute(
            "INSERT INTO creator_content (account_id, created_at, body) "
            "VALUES (1, 'yesterday', 'Keep this draft')")
    monkeypatch.setattr(database, "DB_PATH", path)
    database.init_db()
    with database.get_connection() as conn:
        content_columns = {row["name"] for row in conn.execute(
            "PRAGMA table_info(creator_content)")}
        job_columns = {row["name"] for row in conn.execute(
            "PRAGMA table_info(creator_video_jobs)")}
        draft = conn.execute(
            "SELECT project_id, body FROM creator_content").fetchone()
    assert "project_id" in content_columns & job_columns
    assert (draft["project_id"], draft["body"]) == (None, "Keep this draft")


def test_creator_schedule_and_teaser_keep_origin_project_and_account(
        window, db, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QInputDialog
    from services.registry import Registry
    from services.project_artifacts import list_for_project

    database, account_id = db
    registry = Registry()
    registry.upsert_project("creator-first", "First campaign")
    registry.upsert_project("creator-second", "Second campaign")
    panel = window.creator_panel
    panel.refresh_accounts()
    panel.creator_output.setPlainText("A campaign draft")
    panel._draft_origin = ("creator-first", account_id)
    monkeypatch.setattr(
        window, "_active_project",
        lambda: registry.get_project("creator-second"))
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Friday", True)))
    panel.schedule()
    with database.get_connection() as conn:
        content = conn.execute(
            "SELECT id, account_id, project_id FROM creator_content "
            "ORDER BY id DESC LIMIT 1").fetchone()
    assert (content["account_id"], content["project_id"]) == (
        account_id, "creator-first")

    with database.get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO creator_accounts (handle, account_type, created_at) "
            "VALUES ('@other', 'own', ?)", (datetime.now().isoformat(),))
        other_account_id = cursor.lastrowid
    panel.refresh_accounts()
    panel.creator_account_box.setCurrentIndex(
        panel.creator_account_box.findData(other_account_id))
    panel.schedule()  # Must refuse to put the first account's draft in @other.
    with database.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM creator_content").fetchone()[0] == 1

    panel.creator_account_box.setCurrentIndex(0)
    panel._video_context = {
        "account_id": account_id, "content_id": content["id"],
        "project_id": "creator-first", "prompt": "A safe teaser",
        "request_token": None, "job_id": "", "estimated_usd": 1.0,
    }
    panel._video_job_update(SimpleNamespace(
        job_id="job-project", status="completed", endpoint="/video",
        error="", correlation_id=""))
    clip = tmp_path / "teaser.mp4"
    clip.write_bytes(b"clip")
    panel._video_done(account_id, str(clip))
    with database.get_connection() as conn:
        job = conn.execute(
            "SELECT project_id, local_path FROM creator_video_jobs "
            "WHERE request_id='job-project'").fetchone()
        media = conn.execute(
            "SELECT account_id FROM creator_media WHERE path=?",
            (str(clip),)).fetchone()
    assert (job["project_id"], job["local_path"]) == (
        "creator-first", str(clip))
    assert media["account_id"] == account_id
    assert list_for_project("creator-first", kinds=("creator_video",))[0]["path"] == \
        str(clip)
    assert list_for_project("creator-second") == []


def test_creator_calendar_and_media_keep_all_and_project_views(
        window, db, tmp_path, monkeypatch):
    from services.project_artifacts import record
    from services.registry import Registry

    database, account_id = db
    Registry().upsert_project("creator-campaign", "Campaign")
    with database.get_connection() as conn:
        for title, project_id in (("Linked post", "creator-campaign"),
                                  ("Unfiled post", None)):
            conn.execute(
                "INSERT INTO creator_content "
                "(account_id, project_id, created_at, scheduled_for, kind, "
                "title, body, price_usd, status) "
                "VALUES (?, ?, ?, ?, 'post', ?, 'body', 0, 'draft')",
                (account_id, project_id, datetime.now().isoformat(),
                 datetime.now().isoformat(), title))
    panel = window.creator_panel
    linked = tmp_path / "linked.jpg"
    other = tmp_path / "unfiled.jpg"
    linked.write_bytes(b"linked")
    other.write_bytes(b"other")
    panel._store_media(account_id, str(linked))
    panel._store_media(account_id, str(other))
    record("creator-campaign", "creator", "creator_image", linked)
    monkeypatch.setattr(window, "_active_project", lambda: {
        "id": "creator-campaign", "name": "Campaign"})
    try:
        panel.refresh_accounts()
        panel.creator_calendar_scope.setCurrentIndex(0)
        panel.creator_media_scope.setCurrentIndex(0)
        panel.refresh_calendar()
        panel.refresh_media()
        assert panel.creator_calendar_table.rowCount() == 2
        assert panel.creator_media_table.rowCount() == 2
        panel.creator_calendar_scope.setCurrentIndex(1)
        panel.creator_media_scope.setCurrentIndex(1)
        assert panel.creator_calendar_table.rowCount() == 1
        assert panel._calendar_ids and len(panel._calendar_ids) == 1
        assert panel.creator_calendar_table.item(0, 2).text() == "Linked post"
        assert panel.creator_media_table.rowCount() == 1
        assert panel.creator_media_table.item(0, 0).text() == "linked.jpg"
    finally:
        panel.creator_calendar_scope.setCurrentIndex(0)
        panel.creator_media_scope.setCurrentIndex(0)


# ── The ampersand trap ───────────────────────────────────────────────────────
def test_no_button_text_has_a_bare_ampersand():
    """Qt reads a lone '&' in button text as a mnemonic and swallows it, so
    "Publish & Market" renders as "Publish_Market". This has now happened
    twice — once on the author panel, once on "Save Voice & Character" — so it
    gets a test rather than a third fix."""
    import re
    source = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    offenders = []
    for match in re.finditer(r'QPushButton\("([^"]*)"\)', source):
        text = match.group(1)
        # A single & that is not part of an escaped && pair.
        if re.search(r'(?<!&)&(?!&)', text):
            offenders.append(text)
    assert not offenders, (
        "button labels with an unescaped '&' (use '&&'): " + repr(offenders))
