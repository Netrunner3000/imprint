"""Background worker threads.

Moved verbatim out of main.py (see docs/refactor_plan.md, phase 1). These are
standalone QThread subclasses: they take everything they need as constructor
arguments and touch no application state, which is why they move first.
"""
import re
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from services.openai_client import DEFAULT_IMAGE_MODEL


class ChatWorker(QThread):
    token_signal = Signal(str)
    status_signal = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)
    usage_signal = Signal(dict)

    def __init__(self, run_backend_func, backend: str, model: str, messages: list, prompt: str):
        super().__init__()
        self.run_backend_func = run_backend_func
        self.backend = backend
        self.model = model
        self.messages = messages
        self.prompt = prompt
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _emit_as_tokens(self, text: str):
        for part in re.split(r"(\s+)", text):
            if self._cancel_requested:
                return
            self.token_signal.emit(part)
            time.sleep(0.006)

    def run(self):
        try:
            self.status_signal.emit("Model processing started...")
            result = self.run_backend_func(
                self.backend,
                self.model,
                self.messages,
                self.prompt,
            )

            usage = None
            response_parts = []

            # ===== STREAMING CASE =====
            if hasattr(result, "__iter__") and not isinstance(result, (str, tuple, dict)):
                self.status_signal.emit("Streaming response...")

                for token in result:
                    if self._cancel_requested:
                        self.error_signal.emit("Request cancelled by user.")
                        return

                    response_parts.append(token)
                    self.token_signal.emit(token)

                response = "".join(response_parts)
                
                usage = {
                    "cost_type_override": "stream-estimated"
        }

            # ===== TUPLE (response, usage) =====
            elif isinstance(result, tuple):
                response, usage = result
                self._emit_as_tokens(response)

            # ===== NORMAL STRING RESPONSE =====
            else:
                response = result
                self._emit_as_tokens(response)

            if usage:
                self.usage_signal.emit(usage)

            self.finished_signal.emit(response)

        except Exception as e:
            self.error_signal.emit(str(e))


class SubprocessWorker(QThread):
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, cmd: list):
        super().__init__()
        self._cmd = cmd
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result = subprocess.run(self._cmd, capture_output=True, text=True, timeout=30)
            if self._cancelled:
                return
            output = result.stdout.strip()
            if result.stderr.strip():
                output += f"\n\n[stderr]\n{result.stderr.strip()}"
            self.finished_signal.emit(output or "[No output returned]")
        except subprocess.TimeoutExpired:
            self.error_signal.emit("Command timed out after 30 seconds.")
        except FileNotFoundError as e:
            self.error_signal.emit(f"Command not found: {e}")
        except Exception as e:
            self.error_signal.emit(str(e))


class ModelPullWorker(QThread):
    """Downloads an Ollama model off the UI thread.

    progress_signal carries (status, completed_bytes, total_bytes); total is 0
    until Ollama has resolved the manifest.
    """
    progress_signal = Signal(str, int, int)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, client, model: str):
        super().__init__()
        self._client = client
        self._model = model

    def run(self):
        try:
            self._client.pull_model(
                self._model,
                on_progress=lambda status, done, total: self.progress_signal.emit(
                    status, int(done or 0), int(total or 0)
                ),
            )
            self.finished_signal.emit(self._model)
        except Exception as e:
            self.error_signal.emit(str(e))


class FiverrImageWorker(QThread):
    """Generates and saves logo images, one concept at a time."""
    image_ready_signal = Signal(str, int)   # local_path, index
    all_done_signal = Signal(list)           # all local paths
    error_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, openai_client, image_prompt: str, count: int,
                 save_dir: Path, image_model: str = DEFAULT_IMAGE_MODEL):
        super().__init__()
        self.openai_client = openai_client
        self.image_prompt = image_prompt
        self.count = count
        self.save_dir = save_dir
        self.image_model = image_model
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        self.save_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(self.count):
            if self._cancel_requested:
                self.error_signal.emit("Cancelled.")
                return
            try:
                self.status_signal.emit(f"Generating concept {i + 1} of {self.count}...")
                # The adapter normalises every supported GPT Image response to
                # bytes before the worker writes it to the local order folder.
                data = self.openai_client.generate_image(
                    self.image_prompt, model=self.image_model)
                local_path = self.save_dir / f"logo_{i + 1}.png"
                local_path.write_bytes(data)
                paths.append(str(local_path))
                self.image_ready_signal.emit(str(local_path), i)
            except Exception as e:
                self.error_signal.emit(f"Concept {i + 1} failed: {e}")
                return
        self.all_done_signal.emit(paths)


class ShortsWorker(QThread):
    """Narrates a quote and renders it into a short vertical MP4."""
    status_signal = Signal(str)
    done_signal = Signal(str)   # output video path
    error_signal = Signal(str)

    def __init__(self, quote: str, image_path: Path, output_path: Path,
                 use_elevenlabs: bool, voice_id: str):
        super().__init__()
        self.quote = quote
        self.image_path = image_path
        self.output_path = output_path
        self.use_elevenlabs = use_elevenlabs
        self.voice_id = voice_id

    def run(self):
        from services.shorts_generator import render_short
        try:
            self.status_signal.emit("[Narrating…]")
            render_short(
                self.quote, self.image_path, self.output_path,
                use_elevenlabs=self.use_elevenlabs, voice_id=self.voice_id,
            )
            self.done_signal.emit(str(self.output_path))
        except Exception as e:
            self.error_signal.emit(str(e))


class HiggsfieldEstimateWorker(QThread):
    """Upload any reference image and price the exact request off the UI thread."""

    status_signal = Signal(str)
    done_signal = Signal(object, object)  # PreparedVideoRequest, VideoEstimate
    error_signal = Signal(str)

    def __init__(self, client, prompt: str, *, duration: int = 5,
                 reference_image: str | None = None,
                 aspect_ratio: str | None = None,
                 resolution: str | None = None):
        super().__init__()
        self.client = client
        self.prompt = prompt
        self.duration = duration
        self.reference_image = reference_image
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution
        self._cancel_requested = False

    def cancel(self):
        # Preparation contains short network operations rather than a remote
        # render, so cancellation is observed between upload and estimate.
        self._cancel_requested = True

    def run(self):
        try:
            self.status_signal.emit(
                "Uploading reference image…" if self.reference_image
                else "Preparing render estimate…")
            request = self.client.prepare_video(
                self.prompt, duration=self.duration,
                reference_image=self.reference_image,
                aspect_ratio=self.aspect_ratio, resolution=self.resolution)
            if self._cancel_requested:
                self.error_signal.emit("Cancelled.")
                return
            self.status_signal.emit("Checking Higgsfield price…")
            estimate = self.client.estimate(request)
            if self._cancel_requested:
                self.error_signal.emit("Cancelled.")
                return
            self.done_signal.emit(request, estimate)
        except Exception as exc:
            self.error_signal.emit(str(exc))


class OpenAIVideoWorker(QThread):
    """Run a short Sora job and preserve its paid output locally.

    The legacy Sora endpoint has no cancel operation. A stop request therefore
    cannot safely abandon the result: the provider keeps rendering and billing,
    so this worker continues polling and downloads the asset.
    """

    status_signal = Signal(str)
    progress_signal = Signal(int, str)
    job_signal = Signal(object)
    done_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, client, prompt: str, output_path, *, model: str,
                 seconds: int, size: str, timeout: int = 900):
        super().__init__()
        self.client = client
        self.prompt = prompt
        self.output_path = Path(output_path)
        self.model = model
        self.seconds = seconds
        self.size = size
        self.timeout = timeout

    def run(self):
        try:
            self.status_signal.emit("Submitting to OpenAI Sora…")
            job = self.client.create_video(
                self.prompt, model=self.model, seconds=self.seconds,
                size=self.size)
            self.job_signal.emit(job)

            def progress(current):
                self.job_signal.emit(current)
                self.progress_signal.emit(
                    current.progress,
                    f"Sora rendering… {current.progress}% ({current.status})")

            job = self.client.wait_video(
                job, timeout=self.timeout, on_progress=progress)
            self.job_signal.emit(job)
            if job.status != "completed":
                self.error_signal.emit(job.error or f"Sora render {job.status}")
                return

            self.status_signal.emit("Downloading Sora video…")
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_bytes(self.client.download_video(job.job_id))
            self.done_signal.emit(str(self.output_path))
        except Exception as exc:
            self.error_signal.emit(str(exc))


class HiggsfieldWorker(QThread):
    """Submits a Higgsfield render, waits for it, and downloads the result.

    On a thread because a render takes minutes. The panel used to submit and
    then tell the user to go and look on Higgsfield's site, which is not a
    feature so much as a note apologising for the absence of one.

    Emits `status_signal` on every poll so the wait is legible rather than a
    frozen button.
    """
    status_signal = Signal(str)
    job_signal = Signal(object)   # latest VideoJob, for durable tracking
    done_signal = Signal(str)     # local path of the downloaded video
    error_signal = Signal(str)

    def __init__(self, client, prompt: str, output_path,
                 *, duration: int = 5, reference_image: str | None = None,
                 seed: int | None = None, timeout: int = 900,
                 prepared_request=None):
        super().__init__()
        self.client = client
        self.prompt = prompt
        self.output_path = Path(output_path)
        self.duration = duration
        self.reference_image = reference_image
        self.seed = seed
        self.timeout = timeout
        self.prepared_request = prepared_request
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            self.status_signal.emit("Submitting to Higgsfield…")
            if self.prepared_request is not None:
                job = self.client.generate_prepared(self.prepared_request)
            else:
                job = self.client.generate_video(
                    self.prompt, duration=self.duration,
                    reference_image=self.reference_image, seed=self.seed)
            self.job_signal.emit(job)

            def progress(current):
                self.job_signal.emit(current)
                self.status_signal.emit(f"Rendering… ({current.status})")

            job = self.client.wait(job, timeout=self.timeout,
                                   on_progress=progress,
                                   should_cancel=lambda: self._cancel_requested)
            self.job_signal.emit(job)
            if job.status != "completed" or not job.video_url:
                self.error_signal.emit(job.error or f"Render {job.status}")
                return

            self.status_signal.emit("Downloading…")
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            import requests
            with requests.get(job.video_url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with open(self.output_path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        if chunk:
                            handle.write(chunk)
            self.done_signal.emit(str(self.output_path))
        except Exception as exc:
            self.error_signal.emit(str(exc))


class VideoWorker(QThread):
    """Runs one vidforge render on a thread, reporting progress to Qt.

    vidforge's pipeline talks to a `Reporter` rather than printing, which is
    the seam that lets the same code drive the CLI and a progress bar. The
    reporter is created inside `run()` because it is the thread's own object:
    building it on the GUI thread and emitting from the worker is the usual way
    this goes wrong.

    Cancellation is cooperative and goes through the reporter — the pipeline
    calls `raise_if_cancelled()` between stages and inside the per-scene loops,
    so a cancelled render stops at the next checkpoint rather than being
    killed mid-ffmpeg with a half-written file.
    """

    stage_signal = Signal(str, str)        # stage key, human label
    progress_signal = Signal(int, str)     # 0-100 overall, detail
    log_signal = Signal(str)
    done_signal = Signal(str, str)         # slug, video path
    error_signal = Signal(str)

    def __init__(self, topic: str = "", overrides: dict | None = None,
                 resume_slug: str = ""):
        super().__init__()
        self.topic = topic.strip()
        self.overrides = overrides or {}
        self.resume_slug = resume_slug.strip()
        self._reporter = None
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True
        if self._reporter is not None:
            self._reporter.cancel()

    def run(self):
        from services import video_studio

        try:
            base = video_studio.reporter_base()

            worker = self

            class QtReporter(base):
                def on_stage(self, stage_key, detail):
                    from services.video_studio import overall_fraction
                    label = dict((k, l) for k, l, _ in video_studio.stages()).get(
                        stage_key, stage_key)
                    worker.stage_signal.emit(stage_key, label)
                    worker.progress_signal.emit(
                        int(overall_fraction(stage_key) * 100), detail)

                def on_progress(self, stage_key, fraction, detail):
                    from services.video_studio import overall_fraction
                    worker.progress_signal.emit(
                        int(overall_fraction(stage_key, fraction) * 100), detail)

                def on_log(self, message):
                    worker.log_signal.emit(message)

            self._reporter = QtReporter()
            if self._cancel_requested:      # cancelled before the thread started
                self._reporter.cancel()

            cfg = video_studio.load_config(self.overrides)
            build = video_studio.produce(
                cfg,
                topic=self.topic or None,
                resume_slug=self.resume_slug or None,
                reporter=self._reporter,
            )
            self.progress_signal.emit(100, "")
            self.done_signal.emit(build.slug, str(build.video_path))

        except Exception as exc:
            if type(exc).__name__ == "Cancelled":
                self.error_signal.emit("Cancelled.")
            else:
                self.error_signal.emit(f"{type(exc).__name__}: {exc}")
