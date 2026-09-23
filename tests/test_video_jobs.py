"""Provider video jobs survive a restart: the durable row, the resume
worker, and the startup reconciliation that downloads and bills the result.

Money-safety contract under test:
  * a job row is written before the create POST and follows every provider
    transition (submitted -> running -> terminal);
  * a submission the provider never acknowledged is marked lost, never
    billed;
  * a resumed job re-reserves its budget, is billed exactly once through
    the normal guard close-out, and lands in the library;
  * a local poll timeout is not a provider verdict — the row stays pending
    for the next launch.
"""

import os
import types
from pathlib import Path

import pytest

from agents.video import jobs


@pytest.fixture()
def clean_jobs_table():
    from services.database import get_connection
    with get_connection() as conn:
        conn.execute("DELETE FROM video_jobs")
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM video_jobs")


def _submit(**overrides):
    fields = dict(
        provider="qwen", model="wan3.0-video", topic="a calm ocean",
        slug="calm-ocean", output_path="/tmp/calm-ocean.mp4", seconds=8,
        aspect_ratio="9:16", flat_cost_eur=0.75, project=None,
        run_id="run-1")
    fields.update(overrides)
    return jobs.record_submission(**fields)


# ── the durable row ──────────────────────────────────────────────────────────

def test_video_jobs_schema_preserves_money_and_resume_fields():
    from services.database import get_connection
    with get_connection() as conn:
        columns = {row["name"] for row in
                   conn.execute("PRAGMA table_info(video_jobs)")}
    assert {"provider", "job_id", "model", "slug", "topic", "output_path",
            "seconds", "aspect_ratio", "status", "error", "agent",
            "flat_cost_eur", "spend_state", "project", "run_id",
            "status_url", "created_at", "updated_at"} <= columns


def test_submission_lifecycle_round_trip(clean_jobs_table):
    row_id = _submit()
    # Unacknowledged submissions are not pollable and must not be pending.
    assert jobs.pending_rows() == []

    jobs.update_job(row_id, job_id="task-123", status="queued")
    (row,) = jobs.pending_rows()
    assert row["job_id"] == "task-123"
    assert row["spend_state"] == "reserved"
    assert row["flat_cost_eur"] == 0.75

    jobs.update_job(row_id, status="running")
    jobs.mark_terminal(row_id, spend_state="billed",
                       fallback_status="completed")
    assert jobs.pending_rows() == []
    from services.database import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM video_jobs WHERE id = ?",
                           (row_id,)).fetchone()
    assert (row["status"], row["spend_state"]) == ("completed", "billed")


def test_mark_terminal_keeps_a_provider_verdict(clean_jobs_table):
    row_id = _submit(provider="higgsfield")
    jobs.update_job(row_id, job_id="req-1", status="nsfw",
                    error="moderation")
    jobs.mark_terminal(row_id, spend_state="released",
                       fallback_status="failed")
    from services.database import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT status, spend_state FROM video_jobs "
                           "WHERE id = ?", (row_id,)).fetchone()
    # The provider's own terminal word survives; only the spend settles.
    assert (row["status"], row["spend_state"]) == ("nsfw", "released")


def test_pending_rows_exclude_every_terminal_spelling(clean_jobs_table):
    for status in sorted(jobs.TERMINAL_STATUSES):
        row_id = _submit(slug=f"s-{status}")
        jobs.update_job(row_id, job_id=f"j-{status}", status=status)
    for status in ("queued", "running", "unknown"):
        row_id = _submit(slug=f"s-{status}")
        jobs.update_job(row_id, job_id=f"j-{status}", status=status)
    slugs = {row["slug"] for row in jobs.pending_rows()}
    assert slugs == {"s-queued", "s-running", "s-unknown"}


def test_sweep_lost_marks_unacknowledged_submissions(clean_jobs_table):
    lost_id = _submit(slug="never-acked")
    live_id = _submit(slug="acked")
    jobs.update_job(live_id, job_id="task-9", status="running")

    (lost,) = jobs.sweep_lost()
    assert lost["id"] == lost_id
    from services.database import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT status, spend_state FROM video_jobs "
                           "WHERE id = ?", (lost_id,)).fetchone()
    assert (row["status"], row["spend_state"]) == ("lost", "released")
    # The acknowledged job is untouched and still pending.
    assert [r["id"] for r in jobs.pending_rows()] == [live_id]
    # A second sweep finds nothing: lost is terminal.
    assert jobs.sweep_lost() == []


# ── the resume worker (run() called synchronously, house idiom) ─────────────

@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _resume_worker(client, provider, tmp_path, **overrides):
    from agents.video.workers import VideoResumeWorker
    fields = dict(job_id="task-1", model="wan3.0-video", seconds=8,
                  aspect_ratio="9:16", status_url="",
                  output_path=tmp_path / "out.mp4")
    fields.update(overrides)
    return VideoResumeWorker(client, provider, **fields)


def test_resume_worker_downloads_a_completed_qwen_job(app, tmp_path):
    done_job = types.SimpleNamespace(
        status="completed", error="", video_url="https://x/1.mp4")
    client = types.SimpleNamespace(
        wait_video=lambda job, timeout, on_progress: done_job,
        download_video=lambda job: b"mp4-bytes")
    worker = _resume_worker(client, "qwen", tmp_path)
    done, errors = [], []
    worker.done_signal.connect(done.append)
    worker.error_signal.connect(errors.append)
    worker.run()
    assert errors == []
    assert done == [str(tmp_path / "out.mp4")]
    assert (tmp_path / "out.mp4").read_bytes() == b"mp4-bytes"
    assert worker.provider_completed is True


def test_resume_worker_treats_local_timeout_as_retryable(app, tmp_path):
    stalled = types.SimpleNamespace(
        status="failed", error="Timed out after 900s", video_url="")
    client = types.SimpleNamespace(
        wait_video=lambda job, timeout, on_progress: stalled)
    worker = _resume_worker(client, "qwen", tmp_path)
    errors, transitions = [], []
    worker.error_signal.connect(errors.append)
    worker.job_signal.connect(transitions.append)
    worker.run()
    assert worker.timed_out is True
    assert worker.provider_completed is False
    assert errors == ["Timed out after 900s"]
    # The local deadline was NOT persisted as a provider verdict: the only
    # emitted transition is the rebuilt job, still non-terminal.
    assert all(t.status != "failed" for t in transitions)


def test_resume_worker_reports_a_provider_failure(app, tmp_path):
    failed = types.SimpleNamespace(
        status="failed", error="Renderer exploded", video_url="")
    client = types.SimpleNamespace(
        wait_video=lambda job, timeout, on_progress: failed)
    worker = _resume_worker(client, "qwen", tmp_path)
    errors, transitions = [], []
    worker.error_signal.connect(errors.append)
    worker.job_signal.connect(transitions.append)
    worker.run()
    assert worker.timed_out is False
    assert errors == ["Renderer exploded"]
    assert transitions[-1].status == "failed"


def test_resume_worker_streams_a_higgsfield_url(app, tmp_path, monkeypatch):
    completed = types.SimpleNamespace(
        status="completed", error="", video_url="https://api.higgsfield.ai/v.mp4")
    client = types.SimpleNamespace(
        wait=lambda job, timeout, on_progress: completed)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        @staticmethod
        def iter_content(chunk_size):
            yield b"chunk-a"
            yield b"chunk-b"

    import requests
    monkeypatch.setattr(requests, "get",
                        lambda url, stream, timeout: FakeResponse())
    worker = _resume_worker(client, "higgsfield", tmp_path,
                            job_id="req-7", model="/bytedance/x")
    done = []
    worker.done_signal.connect(done.append)
    worker.run()
    assert done and (tmp_path / "out.mp4").read_bytes() == b"chunk-achunk-b"


# ── startup reconciliation through the real window ──────────────────────────

@pytest.fixture(scope="module")
def window(app):
    from PySide6.QtWidgets import QMessageBox
    import main
    saved = (QMessageBox.warning, QMessageBox.question,
             QMessageBox.information)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        yield main.GodAI()
    finally:
        (QMessageBox.warning, QMessageBox.question,
         QMessageBox.information) = saved


def test_startup_reconciliation_bills_and_lands_a_finished_job(
        window, clean_jobs_table, tmp_path, monkeypatch):
    if not window.video_panel._available:
        pytest.skip("vidforge is not importable in this checkout")

    output_path = tmp_path / "sunset" / "sunset.mp4"
    window.registry.upsert_project("video-sunset", "Sunset campaign")
    row_id = _submit(slug="sunset", topic="a sunset",
                     output_path=str(output_path), flat_cost_eur=0.62,
                     project="video-sunset")
    jobs.update_job(row_id, job_id="task-77", status="running")

    done_job = types.SimpleNamespace(
        status="completed", error="", video_url="https://x/s.mp4")
    monkeypatch.setattr(
        window, "qwen", types.SimpleNamespace(
            key_available=lambda: True,
            wait_video=lambda job, timeout, on_progress: done_job,
            download_video=lambda job: b"sunset-bytes"))
    recorded = []
    from agents.video import video_studio, workers
    from services.history_store import HistoryStore
    monkeypatch.setattr(window, "history", HistoryStore(tmp_path / "chats"))
    monkeypatch.setattr(video_studio, "record_external",
                        lambda **kw: recorded.append(kw))
    monkeypatch.setattr(window.video_panel, "refresh_library", lambda: None)
    # House idiom: run the QThread synchronously on the test thread.
    monkeypatch.setattr(workers.VideoResumeWorker, "start",
                        workers.VideoResumeWorker.run)

    before_spend = window.usage_tracker.get_agent_today_total("video")
    window.video_panel.resume_pending_jobs()

    # The paid result exists locally and joined the library.
    assert output_path.read_bytes() == b"sunset-bytes"
    assert recorded and recorded[0]["slug"] == "sunset"
    assert recorded[0]["job_id"] == "task-77"
    from services.project_artifacts import list_for_project
    assert list_for_project("video-sunset", kinds=("video_direct",))[0]["path"] == \
        str(output_path)
    # Billed exactly once through the guard: the usage table gained the
    # flat cost and no synthetic reservation is left open.
    after_spend = window.usage_tracker.get_agent_today_total("video")
    assert after_spend == pytest.approx(before_spend + 0.62)
    assert not window._pending_requests
    # The row is terminal and settled.
    from services.database import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT status, spend_state FROM video_jobs "
                           "WHERE id = ?", (row_id,)).fetchone()
    assert (row["status"], row["spend_state"]) == ("completed", "billed")


def test_pipeline_output_stays_with_project_captured_at_authorization(
        window, tmp_path, monkeypatch):
    if not window.video_panel._available:
        pytest.skip("vidforge is not importable in this checkout")
    from services.project_artifacts import list_for_project

    window.registry.upsert_project("video-first", "First campaign")
    window.registry.upsert_project("video-second", "Second campaign")
    panel = window.video_panel
    clip = tmp_path / "first-campaign.mp4"
    clip.write_bytes(b"video")
    panel._render_project_id = "video-first"
    panel._active_kind = "pipeline"
    panel._request_token = None
    monkeypatch.setattr(panel, "refresh_library", lambda: None)
    # The selected Project can change while a local pipeline worker runs.
    monkeypatch.setattr(window, "_active_project",
                        lambda: window.registry.get_project("video-second"))
    panel._on_done("first-campaign", str(clip))

    assert list_for_project("video-first", kinds=("video_pipeline",))[0]["path"] == \
        str(clip)
    assert list_for_project("video-second") == []
    assert panel._render_project_id is None


def test_startup_reconciliation_surfaces_lost_submissions(
        window, clean_jobs_table):
    if not window.video_panel._available:
        pytest.skip("vidforge is not importable in this checkout")
    _submit(slug="ghost")   # never acknowledged: no job id
    window.video_panel.resume_pending_jobs()
    log_text = window.video_panel.video_log.toPlainText()
    assert "no job id" in log_text
    from services.database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status, spend_state FROM video_jobs WHERE slug = ?",
            ("ghost",)).fetchone()
    assert (row["status"], row["spend_state"]) == ("lost", "released")
    # Nothing was billed and nothing is reserved.
    assert not window._pending_requests


def test_missing_key_keeps_the_row_pending(window, clean_jobs_table,
                                           monkeypatch):
    if not window.video_panel._available:
        pytest.skip("vidforge is not importable in this checkout")
    row_id = _submit(slug="keyless")
    jobs.update_job(row_id, job_id="task-88", status="running")
    monkeypatch.setattr(
        window, "qwen",
        types.SimpleNamespace(key_available=lambda: False))
    window.video_panel.resume_pending_jobs()
    # Still pending for a launch where the key exists; nothing reserved.
    assert [r["id"] for r in jobs.pending_rows()] == [row_id]
    assert not window._pending_requests
