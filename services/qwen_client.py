import os
import time
from dataclasses import dataclass

import requests
from openai import OpenAI

from services.api_limits import REQUEST_TIMEOUT_SECONDS
from services.media_catalog import WAN_VIDEO_MODELS

# Alibaba's Qwen, served through Model Studio / DashScope. The API is
# OpenAI-compatible, so this wrapper is the same shape as the DeepSeek and Kimi
# ones — only the base URL and key differ.
#
# Endpoints are regional. The international ("intl", Singapore-routed) host is
# the right default outside mainland China; DASHSCOPE_BASE_URL overrides it for
# a China account or a workspace-scoped regional host, so switching regions
# never needs a code change.
INTL_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
CHINA_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
INTL_VIDEO_BASE_URL = "https://dashscope-intl.aliyuncs.com/api/v1"


def _base_url() -> str:
    return os.getenv("DASHSCOPE_BASE_URL", INTL_BASE_URL)


def _video_base_url() -> str:
    return os.getenv("DASHSCOPE_VIDEO_BASE_URL", INTL_VIDEO_BASE_URL).rstrip("/")


@dataclass
class WanVideoJob:
    job_id: str
    status: str
    model: str
    seconds: int
    aspect_ratio: str
    progress: int = 0
    error: str = ""
    video_url: str = ""

    @property
    def done(self) -> bool:
        return self.status in {"completed", "failed", "cancelled"}


class QwenClientWrapper:
    # Qwen3.8-Max — 2.4T-parameter MoE (95B active per token), released
    # 2026-08-03. 1M-token context, up to 131,072 output tokens, multimodal in
    # (text/image/video), text out, with function calling and structured output.
    KNOWN_MODELS = [
        "qwen3.8-max",
        "qwen3-max",
        "qwen-plus",
        "qwen-flash",
    ]

    DEFAULT_MODEL = "qwen3.8-max"

    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.base_url = _base_url()
        self.client = (
            OpenAI(api_key=self.api_key, base_url=self.base_url)
            if self.api_key
            else None
        )
        self.video_base_url = _video_base_url()
        # requests.Session does not retry POSTs unless an adapter explicitly
        # enables it, so an ambiguous timeout cannot duplicate a paid task.
        self.video_session = requests.Session() if self.api_key else None

    @staticmethod
    def key_available():
        return bool(os.getenv("DASHSCOPE_API_KEY"))

    def list_models(self) -> list[str]:
        """Model ids from the API when reachable, else KNOWN_MODELS.

        Mirrors the other clients: never returns empty, so the model dropdowns
        always have something selectable.
        """
        if not self.client:
            return self.KNOWN_MODELS
        try:
            result = self.client.models.list()
            models = sorted(m.id for m in result.data)
            return models if models else self.KNOWN_MODELS
        except Exception:
            return self.KNOWN_MODELS

    def chat(self, messages, model=DEFAULT_MODEL):
        if not self.client:
            raise RuntimeError("DASHSCOPE_API_KEY is not set.")

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

    def generate(self, prompt, model=DEFAULT_MODEL):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)

    def stream_chat(self, messages, model=DEFAULT_MODEL):
        if not self.client:
            raise RuntimeError("DASHSCOPE_API_KEY is not set.")

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
            raise RuntimeError(f"Qwen streaming request failed: {e}")

    # ── Alibaba Model Studio / Wan video ────────────────────────
    def _video_headers(self, *, create: bool = False) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if create:
            headers.update({
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            })
        return headers

    @staticmethod
    def _validate_video(model: str, seconds: int, aspect_ratio: str) -> None:
        if model not in WAN_VIDEO_MODELS:
            raise ValueError(f"Unsupported Wan video model: {model}")
        maximum = 15 if model == "wan2.7-t2v" else 30
        if not 2 <= int(seconds) <= maximum:
            raise ValueError(
                f"{model} clips must be between 2 and {maximum} seconds.")
        if aspect_ratio not in ("16:9", "9:16", "1:1", "4:3", "3:4"):
            raise ValueError(f"Unsupported Wan aspect ratio: {aspect_ratio}")

    @staticmethod
    def _video_job(data: dict, *, model: str, seconds: int,
                   aspect_ratio: str) -> WanVideoJob:
        output = data.get("output") or {}
        raw = str(output.get("task_status") or "UNKNOWN").upper()
        status = {
            "PENDING": "queued", "RUNNING": "running",
            "SUCCEEDED": "completed", "FAILED": "failed",
            "CANCELED": "cancelled", "UNKNOWN": "failed",
        }.get(raw, raw.lower())
        progress = 100 if status in {"completed", "failed", "cancelled"} else (
            45 if status == "running" else 5)
        return WanVideoJob(
            str(output.get("task_id") or ""), status, model, int(seconds),
            aspect_ratio, progress,
            str(output.get("message") or data.get("message") or ""),
            str(output.get("video_url") or ""),
        )

    def create_video(self, prompt: str, *, model: str, seconds: int,
                     aspect_ratio: str = "9:16") -> WanVideoJob:
        if not self.video_session or not self.api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not set.")
        self._validate_video(model, seconds, aspect_ratio)
        response = self.video_session.post(
            f"{self.video_base_url}/services/aigc/video-generation/video-synthesis",
            headers=self._video_headers(create=True),
            json={
                "model": model,
                "input": {"prompt": prompt},
                "parameters": {
                    "resolution": "720P", "ratio": aspect_ratio,
                    "duration": int(seconds), "prompt_extend": True,
                    "watermark": False,
                },
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        job = self._video_job(
            response.json(), model=model, seconds=seconds,
            aspect_ratio=aspect_ratio)
        if not job.job_id:
            raise RuntimeError(job.error or "Wan returned no task ID.")
        return job

    def poll_video(self, job: WanVideoJob) -> WanVideoJob:
        if not self.video_session or not self.api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not set.")
        response = self.video_session.get(
            f"{self.video_base_url}/tasks/{job.job_id}",
            headers=self._video_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return self._video_job(
            response.json(), model=job.model, seconds=job.seconds,
            aspect_ratio=job.aspect_ratio)

    def wait_video(self, job: WanVideoJob, *, timeout: int = 900,
                   interval: float = 15.0, on_progress=None) -> WanVideoJob:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if job.done:
                return job
            job = self.poll_video(job)
            if on_progress:
                on_progress(job)
            if job.done:
                return job
            time.sleep(max(0.1, float(interval)))
        job.status = "failed"
        job.error = f"Timed out after {timeout}s"
        return job

    def download_video(self, job: WanVideoJob) -> bytes:
        if not job.video_url:
            raise RuntimeError("Wan video is not ready to download.")
        response = requests.get(
            job.video_url, timeout=120,
            headers={"Accept": "video/mp4"})
        response.raise_for_status()
        return response.content

    def test_connection(self) -> tuple[bool, str]:
        """Send a minimal request and return (success, message)."""
        if not self.client:
            return False, "DASHSCOPE_API_KEY is not set. Add it to your .env file."
        try:
            self.client.chat.completions.create(
                model=self.DEFAULT_MODEL,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return True, f"Connected to Qwen ({self.base_url})."
        except Exception as e:
            return False, f"Qwen connection failed: {e}"
