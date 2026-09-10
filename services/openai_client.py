import base64
import os
import time
import urllib.request
from dataclasses import dataclass

from openai import OpenAI

from services.api_limits import REQUEST_TIMEOUT_SECONDS, MAX_RETRIES
from services.media_catalog import OPENAI_IMAGE_MODELS, OPENAI_VIDEO_MODELS

# Image models offered by the Gigs and Video panels. DALL-E 2/3 were removed
# from the API; these are the current replacements listed in the provider's
# model catalog.
IMAGE_MODELS = OPENAI_IMAGE_MODELS
DEFAULT_IMAGE_MODEL = "gpt-image-2.5-flare"


@dataclass
class OpenAIVideoJob:
    job_id: str
    status: str
    model: str
    seconds: int
    size: str
    progress: int = 0
    error: str = ""

    @property
    def done(self) -> bool:
        return self.status in {"completed", "failed"}


class OpenAIClientWrapper:
    KNOWN_MODELS = [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
    ]

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = (
            OpenAI(
                api_key=self.api_key,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=MAX_RETRIES,
            )
            if self.api_key
            else None
        )

    @staticmethod
    def key_available():
        return bool(os.getenv("OPENAI_API_KEY"))

    def list_models(self) -> list[str]:
        """Chat-capable model ids, newest listing from the API when reachable.

        Falls back to KNOWN_MODELS with no key or on any API error so the model
        dropdowns are never left empty.
        """
        if not self.client:
            return self.KNOWN_MODELS
        try:
            result = self.client.models.list()
            excluded = (
                "image", "realtime", "audio", "transcribe", "tts", "sora",
                "video", "embedding", "moderation",
            )
            models = sorted(
                m.id for m in result.data
                if any(x in m.id.lower() for x in ("gpt", "o1", "o3", "o4"))
                and not any(x in m.id.lower() for x in excluded)
            )
            return models if models else self.KNOWN_MODELS
        except Exception:
            return self.KNOWN_MODELS

    def chat(self, messages, model="gpt-4o-mini"):
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
        )

        text = response.choices[0].message.content or ""

        usage = {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        return text, usage

    def generate(self, prompt, model="gpt-4o-mini"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)
    
    def generate_image(self, prompt: str, size: str = "1024x1024",
                       model: str = DEFAULT_IMAGE_MODEL) -> bytes:
        """Generate one image and return its PNG bytes.

        Current GPT Image models normally return base64. URL handling remains
        for compatibility with provider responses that use temporary assets.
        """
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        if model not in IMAGE_MODELS:
            raise ValueError(
                f"Unsupported image model {model!r}. Select one of: "
                + ", ".join(IMAGE_MODELS))
        kwargs = {
            "model": model, "prompt": prompt, "size": size,
            "quality": "medium", "n": 1,
        }
        response = self.client.images.generate(**kwargs)
        item = response.data[0]

        encoded = getattr(item, "b64_json", None)
        if encoded:
            return base64.b64decode(encoded)
        url = getattr(item, "url", None)
        if not url:
            raise RuntimeError(
                f"{model} returned neither image data nor a URL.")
        with urllib.request.urlopen(url) as handle:
            return handle.read()

    # ── Sora video (legacy API scheduled to close 24 Sep 2026) ──────────
    @staticmethod
    def _video_error(video) -> str:
        error = getattr(video, "error", None)
        return str(getattr(error, "message", "") or error or "")

    @classmethod
    def _video_job(cls, video) -> OpenAIVideoJob:
        return OpenAIVideoJob(
            job_id=str(video.id),
            status=str(video.status),
            model=str(video.model),
            seconds=int(video.seconds),
            size=str(video.size),
            progress=int(getattr(video, "progress", 0) or 0),
            error=cls._video_error(video),
        )

    def create_video(self, prompt: str, *, model: str = "sora-2",
                     seconds: int = 4, size: str = "720x1280") -> OpenAIVideoJob:
        """Start one Sora job without automatically replaying the paid POST."""
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        if model not in OPENAI_VIDEO_MODELS:
            raise ValueError(f"Unsupported Sora model: {model}")
        if int(seconds) not in (4, 8, 12):
            raise ValueError("Sora clips must be 4, 8 or 12 seconds.")
        if size not in ("720x1280", "1280x720", "1024x1792", "1792x1024"):
            raise ValueError(f"Unsupported Sora output size: {size}")
        # The normal client retries transient requests. That is safe for reads,
        # but an ambiguous create timeout could otherwise create two paid jobs.
        video = self.client.with_options(max_retries=0).videos.create(
            prompt=prompt, model=model, seconds=str(int(seconds)), size=size)
        return self._video_job(video)

    def poll_video(self, job_id: str) -> OpenAIVideoJob:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        return self._video_job(self.client.videos.retrieve(job_id))

    def wait_video(self, job: OpenAIVideoJob, *, timeout: int = 900,
                   interval: float = 2.0, on_progress=None) -> OpenAIVideoJob:
        deadline = time.time() + timeout
        delay = max(0.1, float(interval))
        while time.time() < deadline:
            if job.done:
                return job
            job = self.poll_video(job.job_id)
            if on_progress:
                on_progress(job)
            if job.done:
                return job
            time.sleep(delay)
            delay = min(delay * 1.5, 10.0)
        job.status = "failed"
        job.error = f"Timed out after {timeout}s"
        return job

    def download_video(self, job_id: str) -> bytes:
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        return self.client.videos.download_content(job_id).read()

    def stream_chat(self, messages, model="gpt-4o-mini"):
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")

        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        except Exception as e:
            raise RuntimeError(f"OpenAI streaming request failed: {e}")
