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

    import services.creator_profile as profile
    import services.creator_insights as insights
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
    from services.creator_profile import voice_block
    _, account_id = db
    assert voice_block(account_id) == ""


def test_voice_block_carries_the_samples(db):
    """Samples are what the model imitates — the rules only stop it drifting."""
    from services.creator_profile import save_voice, voice_block
    _, account_id = db
    save_voice(account_id, samples="first post\nsecond post", tone="dry")
    block = voice_block(account_id)
    assert "first post" in block and "second post" in block
    assert "dry" in block


def test_voice_samples_are_capped(db):
    """Beyond a handful the marginal value drops and the prompt just costs more."""
    from services.creator_profile import MAX_SAMPLES, save_voice, voice_block
    _, account_id = db
    save_voice(account_id, samples="\n".join(f"post {i}" for i in range(30)))
    assert voice_block(account_id).count("  — ") == MAX_SAMPLES


def test_saving_voice_twice_updates_rather_than_duplicates(db):
    from services.creator_profile import load_voice, save_voice
    database, account_id = db
    save_voice(account_id, tone="first")
    save_voice(account_id, tone="second")
    assert load_voice(account_id)["tone"] == "second"
    count = database.get_connection().execute(
        "SELECT COUNT(*) FROM creator_voice").fetchone()[0]
    assert count == 1


def test_voice_reaches_the_draft_prompt(db):
    """The point of the whole feature: it has to be in the prompt."""
    from agents.creator_agent import CreatorAgent
    from services.creator_profile import save_voice
    _, account_id = db
    save_voice(account_id, samples="a line only this creator would write")
    messages = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"},
        "post", "brief")
    assert "a line only this creator would write" in messages[-1]["content"]


# ── Persona ──────────────────────────────────────────────────────────────────
def test_persona_block_reaches_persona_accounts_only(db):
    from agents.creator_agent import CreatorAgent
    from services.creator_profile import save_persona
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
    from services.creator_profile import persona_seed, save_persona
    _, account_id = db
    save_persona(account_id, appearance="x", seed=4821)
    assert persona_seed(account_id) == 4821


def test_persona_appearance_is_reused_in_video_prompts(db):
    """Without it every render is a different character."""
    from agents.creator_agent import CreatorAgent
    from services.creator_profile import save_persona
    _, account_id = db
    save_persona(account_id, appearance="silver hair, green coat")
    prompt = CreatorAgent().build_video_prompt(
        {"id": account_id, "handle": "@a", "account_type": "persona"}, "rooftop")
    assert "silver hair" in prompt


# ── Segments ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("segment", ["new", "loyal", "lapsed", "big_spender"])
def test_each_segment_changes_the_prompt(db, segment):
    from agents.creator_agent import CreatorAgent
    _, account_id = db
    messages = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"},
        "welcome", "x", segment=segment)
    assert "Audience:" in messages[-1]["content"]


def test_no_segment_adds_nothing(db):
    from agents.creator_agent import CreatorAgent
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
    from services.creator_insights import price_history
    _, account_id = db
    assert price_history(account_id) == ""


def test_price_history_reports_the_average_per_price(db):
    from services.creator_insights import price_history
    database, account_id = db
    _post(database, account_id, 10.0, 40.0)
    _post(database, account_id, 10.0, 60.0)
    history = price_history(account_id)
    assert "$10.00" in history and "50.00" in history


def test_thin_evidence_is_labelled(db):
    """Three sales at $15 is an anecdote, and presenting it as a finding is
    worse than not presenting it."""
    from services.creator_insights import price_history
    database, account_id = db
    _post(database, account_id, 15.0, 20.0)
    assert "few sends" in price_history(account_id)


def test_price_history_reaches_the_ppv_prompt(db):
    from agents.creator_agent import CreatorAgent
    from services.creator_insights import price_history
    database, account_id = db
    _post(database, account_id, 12.0, 90.0)
    messages = CreatorAgent().build_draft_prompt(
        {"id": account_id, "handle": "@a", "account_type": "own"},
        "ppv", "x", price_usd=12.0, price_history=price_history(account_id))
    assert "actually earned" in messages[-1]["content"]


def test_recording_revenue_marks_it_posted(db):
    from services.creator_insights import record_revenue
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
    from services.creator_insights import account_summary
    _, account_id = db
    assert account_summary(account_id)["per_subscriber"] == 0.0


def test_agency_overview_lists_every_account(db):
    from services.creator_insights import agency_overview
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
    from services.creator_insights import commission
    split = commission(1000.0, rate)
    assert split["manager"] == pytest.approx(expected_manager)
    assert split["manager"] + split["creator"] == pytest.approx(1000.0)


def test_commission_rate_is_clamped():
    """A typo in a percentage field should not invent money."""
    from services.creator_insights import commission
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
    titles = [window.creator_tabs.tabText(i)
              for i in range(window.creator_tabs.count())]
    for expected in ("Draft", "Calendar", "Earnings", "Voice", "Media",
                     "Agency", "Records"):
        assert any(expected in t for t in titles), f"missing {expected} tab"


def test_consent_fields_appear_only_for_managed_accounts(window):
    window._creator_type_changed("own")
    assert not window.creator_consent_input.isVisible()
    window._creator_type_changed("managed")
    assert window.creator_consent_input.isVisibleTo(window.creator_panel)


def test_persona_fields_appear_only_for_personas(window):
    window._creator_type_changed("persona")
    assert window.creator_disclosure_input.isVisibleTo(window.creator_panel)
    window._creator_type_changed("own")
    assert not window.creator_disclosure_input.isVisible()


def test_price_shows_only_for_ppv(window):
    window._creator_kind_changed("post")
    assert not window.creator_price_input.isVisible()
    window._creator_kind_changed("ppv")
    assert window.creator_price_input.isVisibleTo(window.creator_panel)


def test_segment_shows_only_where_it_means_something(window):
    window._creator_kind_changed("welcome")
    assert window.creator_segment_box.isVisibleTo(window.creator_panel)
    window._creator_kind_changed("bio")
    assert not window.creator_segment_box.isVisible()


def test_drafting_without_an_account_does_not_crash(window):
    window.creator_account_box.clear()
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
