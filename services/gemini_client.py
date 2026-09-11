import base64
import os
import time
from dataclasses import dataclass, field

from google import genai
from google.genai import types as genai_types

from services.api_limits import REQUEST_TIMEOUT_MS
from services.media_catalog import GEMINI_VIDEO_MODELS

VIDEO_REQUEST_TIMEOUT_MS = 900_000


def _gemini_api_key():
    """Read the Gemini key, accepting either name. Google's own SDK uses
    GOOGLE_API_KEY; this app historically referenced GEMINI_API_KEY. Support
    both so whichever is set in .env works."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


@dataclass
class GeminiVideoJob:
    job_id: str
    status: str
    model: str
    seconds: int
    aspect_ratio: str
    progress: int = 0
    error: str = ""
    operation: object | None = field(default=None, repr=False, compare=False)
    video: object | None = field(default=None, repr=False, compare=False)
    video_bytes: bytes | None = field(default=None, repr=False, compare=False)

    @property
    def done(self) -> bool:
        return self.status in {"completed", "failed"}


class GeminiClientWrapper:
    KNOWN_MODELS = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]

    def __init__(self):
        self.api_key = _gemini_api_key()
        self.client = (
            genai.Client(
                api_key=self.api_key,
                # google-genai takes milliseconds here, unlike the other SDKs
                http_options=genai_types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
            )
            if self.api_key
            else None
        )
        # A timed-out paid create must never be replayed automatically. Reads
        # can still use the normal client above; video generation uses this
        # one-attempt client for both Omni interactions and Veo operations.
        self.media_client = (
            genai.Client(
                api_key=self.api_key,
                http_options=genai_types.HttpOptions(
                    timeout=VIDEO_REQUEST_TIMEOUT_MS,
                    retry_options=genai_types.HttpRetryOptions(attempts=1),
                ),
            )
            if self.api_key
            else None
        )

    @staticmethod
    def key_available():
        return bool(_gemini_api_key())

    def list_models(self) -> list[str]:
        """Model ids that support generateContent, from the API when reachable.

        Falls back to KNOWN_MODELS with no key or on any API error so the model
        dropdowns are never left empty.
        """
        if not self.client:
            return self.KNOWN_MODELS
        try:
            def supports_generate(m) -> bool:
                # The SDK has used both attribute names across versions, and
                # either can come back as None.
                actions = (getattr(m, "supported_actions", None)
                           or getattr(m, "supported_generation_methods", None)
                           or [])
                return "generateContent" in actions

            models = sorted(
                m.name.replace("models/", "")
                for m in self.client.models.list()
                if supports_generate(m)
            )
            return models if models else self.KNOWN_MODELS
        except Exception:
            return self.KNOWN_MODELS

    def chat(self, messages, model="gemini-1.5-flash"):
        if not self.client:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        prompt = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in messages
        )

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
        )

        text = response.text or ""

        usage_metadata = getattr(response, "usage_metadata", None)

        usage = {
            "input_tokens": getattr(usage_metadata, "prompt_token_count", 0) if usage_metadata else 0,
            "output_tokens": getattr(usage_metadata, "candidates_token_count", 0) if usage_metadata else 0,
            "total_tokens": getattr(usage_metadata, "total_token_count", 0) if usage_metadata else 0,
        }

        return text, usage

    def generate(self, prompt, model="gemini-1.5-flash"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)

    # ── Gemini video (Omni synchronous interaction + Veo operation) ──
    def _media(self):
        client = getattr(self, "media_client", None) or self.client
        if not client:
            raise RuntimeError("GOOGLE_API_KEY is not set.")
        return client

    @staticmethod
    def _validate_video(model: str, seconds: int, aspect_ratio: str) -> None:
        if model not in GEMINI_VIDEO_MODELS:
            raise ValueError(f"Unsupported Gemini video model: {model}")
        allowed = (range(3, 11) if model == "gemini-omni-1.1-flash"
                   else (4, 6, 8))
        if int(seconds) not in allowed:
            raise ValueError(f"{model} does not support a {seconds}-second clip.")
        if aspect_ratio not in ("16:9", "9:16"):
            raise ValueError("Gemini video supports 16:9 or 9:16 output.")

    @staticmethod
    def _operation_error(operation) -> str:
        error = getattr(operation, "error", None)
        if not error:
            return ""
        return str(getattr(error, "message", "") or error)

    @classmethod
    def _veo_job(cls, operation, *, model: str, seconds: int,
                 aspect_ratio: str) -> GeminiVideoJob:
        if not getattr(operation, "done", False):
            status, progress, video = "running", 35, None
        elif getattr(operation, "error", None):
            status, progress, video = "failed", 100, None
        else:
            generated = getattr(getattr(operation, "response", None),
                                "generated_videos", None) or []
            video = generated[0] if generated else None
            status = "completed" if video is not None else "failed"
            progress = 100
        error = cls._operation_error(operation)
        if status == "failed" and not error:
            error = "Gemini returned no generated video."
        return GeminiVideoJob(
            str(getattr(operation, "name", "") or "veo-operation"),
            status, model, int(seconds), aspect_ratio, progress,
            error,
            operation=operation, video=video,
        )

    def create_video(self, prompt: str, *, model: str, seconds: int,
                     aspect_ratio: str = "9:16") -> GeminiVideoJob:
        """Create a Gemini video without retrying its paid generation call."""
        self._validate_video(model, seconds, aspect_ratio)
        client = self._media()
        if model == "gemini-omni-1.1-flash":
            timed_prompt = (
                f"{prompt}\n\nGenerate an exactly {int(seconds)}-second video "
                "with a complete beginning, middle and end."
            )
            interaction = client.interactions.create(
                model=model,
                input=timed_prompt,
                response_format={
                    "type": "video", "aspect_ratio": aspect_ratio,
                    "resolution": "720p",
                },
            )
            output = getattr(interaction, "output_video", None)
            encoded = getattr(output, "data", None)
            if not encoded:
                raise RuntimeError("Gemini Omni returned no video data.")
            return GeminiVideoJob(
                str(getattr(interaction, "id", "") or "omni-interaction"),
                "completed", model, int(seconds), aspect_ratio, 100,
                video_bytes=base64.b64decode(encoded),
            )

        operation = client.models.generate_videos(
            model=model,
            prompt=prompt,
            config=genai_types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                duration_seconds=int(seconds),
                resolution="720p",
            ),
        )
        return self._veo_job(
            operation, model=model, seconds=seconds,
            aspect_ratio=aspect_ratio)

    def poll_video(self, job: GeminiVideoJob) -> GeminiVideoJob:
        if job.model == "gemini-omni-1.1-flash" or job.done:
            return job
        operation = self._media().operations.get(job.operation)
        return self._veo_job(
            operation, model=job.model, seconds=job.seconds,
            aspect_ratio=job.aspect_ratio)

    def wait_video(self, job: GeminiVideoJob, *, timeout: int = 900,
                   interval: float = 5.0, on_progress=None) -> GeminiVideoJob:
        deadline = time.time() + timeout
        delay = max(0.1, float(interval))
        while time.time() < deadline:
            if job.done:
                return job
            job = self.poll_video(job)
            if on_progress:
                on_progress(job)
            if job.done:
                return job
            time.sleep(delay)
            delay = min(delay * 1.4, 15.0)
        job.status = "failed"
        job.error = f"Timed out after {timeout}s"
        return job

    def download_video(self, job: GeminiVideoJob) -> bytes:
        if job.video_bytes is not None:
            return job.video_bytes
        if job.video is None:
            raise RuntimeError("Gemini video is not ready to download.")
        data = self._media().files.download(file=job.video)
        if not data:
            raise RuntimeError("Gemini returned an empty video file.")
        return data
    
    def stream_chat(self, messages, model="gemini-1.5-flash"):
        if not self.client:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        prompt = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in messages
        )

        try:
            stream = self.client.models.generate_content_stream(
                model=model,
                contents=prompt,
            )

            for chunk in stream:
                text = getattr(chunk, "text", "")
                if text:
                    yield text

        except Exception as e:
            raise RuntimeError(f"Gemini streaming request failed: {e}")
