"""Background workers owned by the Video & Ad Generator workspace.

The submit-and-wait workers live in ui/workers.py; this module holds the
resume side: finishing a provider job that outlived the process.
"""

from pathlib import Path

from PySide6.QtCore import QThread, Signal


class VideoResumeWorker(QThread):
    """Re-polls a persisted provider job and saves the paid result.

    The create POST happened in a previous run — this worker only ever
    reads status and downloads, so it can never double-spend.  The
    provider-specific job object is rebuilt inside run() because Gemini's
    reconstruction is itself a network poll and must stay off the UI
    thread.
    """

    status_signal = Signal(str)
    job_signal = Signal(object)
    done_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, client, provider: str, *, job_id: str, model: str,
                 seconds: int, aspect_ratio: str, status_url: str,
                 output_path, timeout: int = 900):
        super().__init__()
        self.client = client
        self.provider = provider
        self.job_id = job_id
        self.model = model
        self.seconds = seconds
        self.aspect_ratio = aspect_ratio
        self.status_url = status_url
        self.output_path = Path(output_path)
        self.timeout = timeout
        # Read by the completion handlers: a local poll deadline is not a
        # provider verdict, so a timed-out row stays pending for the next
        # launch instead of being marked failed.
        self.timed_out = False
        self.provider_completed = False

    def _rebuild_job(self):
        if self.provider == "higgsfield":
            from services.higgsfield_client import VideoJob
            return VideoJob(job_id=self.job_id, status_url=self.status_url)
        if self.provider == "qwen":
            from services.qwen_client import WanVideoJob
            return WanVideoJob(
                job_id=self.job_id, status="queued", model=self.model,
                seconds=self.seconds, aspect_ratio=self.aspect_ratio)
        # Gemini: reconstructing the operation is itself the first poll.
        return self.client.resume_video(
            self.job_id, model=self.model, seconds=self.seconds,
            aspect_ratio=self.aspect_ratio)

    def run(self):
        try:
            self.status_signal.emit(
                f"[Resume] Checking {self.provider} job {self.job_id}…")
            job = self._rebuild_job()
            self.job_signal.emit(job)

            def progress(current):
                self.job_signal.emit(current)
                self.status_signal.emit(
                    f"[Resume] {self.provider} rendering… ({current.status})")

            if self.provider == "higgsfield":
                job = self.client.wait(
                    job, timeout=self.timeout, on_progress=progress)
            else:
                job = self.client.wait_video(
                    job, timeout=self.timeout, on_progress=progress)
            if job.status != "completed":
                self.timed_out = (job.error or "").startswith("Timed out after")
                if not self.timed_out:
                    # A provider verdict is worth persisting; a local
                    # deadline is not — the render may still finish.
                    self.job_signal.emit(job)
                self.error_signal.emit(
                    job.error or f"{self.provider} render {job.status}")
                return
            self.job_signal.emit(job)
            self.provider_completed = True

            self.status_signal.emit(
                f"[Resume] Downloading {self.provider} video…")
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            if self.provider == "higgsfield":
                if not job.video_url:
                    self.error_signal.emit(
                        "Render completed but the provider returned no "
                        "video URL.")
                    return
                import requests
                with requests.get(job.video_url, stream=True,
                                  timeout=120) as response:
                    response.raise_for_status()
                    with open(self.output_path, "wb") as handle:
                        for chunk in response.iter_content(chunk_size=1 << 16):
                            if chunk:
                                handle.write(chunk)
            else:
                self.output_path.write_bytes(self.client.download_video(job))
            self.done_signal.emit(str(self.output_path))
        except Exception as exc:
            self.error_signal.emit(str(exc))
