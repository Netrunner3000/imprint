"""Contracts for the media-model catalog and OpenAI media adapters.

These tests never call a paid API. They prove that every option shown in the
Video workspace has a real route, and that retired DALL-E ids (and the removed
Sora adapters) cannot leak back into the new-job controls.
"""

import base64
from types import SimpleNamespace

import pytest

from services.media_catalog import (
    DIRECT_VIDEO_USD_PER_SECOND,
    GEMINI_VIDEO_MODELS,
    MEDIA_PROVIDERS,
    MODELS,
    OPENAI_IMAGE_MODELS,
    RETIRED_DALLE_MODELS,
    WAN_VIDEO_MODELS,
    direct_video_cost_usd,
    models_for,
)
from services.openai_client import OpenAIClientWrapper
from services.gemini_client import GeminiClientWrapper, GeminiVideoJob
from services.qwen_client import QwenClientWrapper, WanVideoJob
from ui.workers import VideoGenerationWorker


def wrapper_with(client):
    wrapper = OpenAIClientWrapper.__new__(OpenAIClientWrapper)
    wrapper.api_key = "test"
    wrapper.client = client
    return wrapper


def test_every_selectable_media_provider_has_an_implemented_model():
    assert MEDIA_PROVIDERS == (
        "OpenAI", "Gemini", "Qwen", "Higgsfield", "Pexels", "Local")
    assert all(models_for(provider) for provider in MEDIA_PROVIDERS)
    assert {model.kind for model in MODELS} == {
        "scene_images", "direct_video", "stock", "local"}


def test_retired_dalle_models_are_not_selectable():
    selectable = {model.model_id for model in MODELS}
    assert selectable.isdisjoint(RETIRED_DALLE_MODELS)
    assert set(OPENAI_IMAGE_MODELS) <= selectable


def test_openai_offers_no_direct_video_model():
    # Sora's rows, rates and adapters were removed ahead of the 2026-09-24
    # Videos API shutdown; OpenAI direct video must never quietly return.
    assert all(model.kind != "direct_video" for model in models_for("OpenAI"))
    assert all(not m.startswith("sora") for m in DIRECT_VIDEO_USD_PER_SECOND)


def test_all_gemini_and_wan_video_models_are_selectable_and_costed():
    selectable = {model.model_id for model in MODELS}
    assert set(GEMINI_VIDEO_MODELS) <= selectable
    assert set(WAN_VIDEO_MODELS) <= selectable
    assert set(GEMINI_VIDEO_MODELS + WAN_VIDEO_MODELS) <= set(
        DIRECT_VIDEO_USD_PER_SECOND)
    assert direct_video_cost_usd("veo-3.1-lite-generate-preview", 8) == 0.40
    assert direct_video_cost_usd("wan3.0-video-prime", 10) == 1.40
    with pytest.raises(ValueError, match="does not support"):
        direct_video_cost_usd("veo-3.1-generate-preview", 12)


def test_image_generation_accepts_current_model_and_rejects_dalle():
    calls = []

    class Images:
        @staticmethod
        def generate(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(
                b64_json=base64.b64encode(b"png").decode(), url=None)])

    wrapper = wrapper_with(SimpleNamespace(images=Images()))
    assert wrapper.generate_image(
        "minimal mark", model="gpt-image-2.5-flare") == b"png"
    assert calls[0]["quality"] == "medium"
    with pytest.raises(ValueError, match="Unsupported image model"):
        wrapper.generate_image("minimal mark", model="dall-e-3")


def test_chat_model_discovery_excludes_media_models():
    data = [SimpleNamespace(id=model) for model in (
        "gpt-4.1", "gpt-image-2", "gpt-realtime", "sora-2", "o3-mini")]
    client = SimpleNamespace(models=SimpleNamespace(
        list=lambda: SimpleNamespace(data=data)))
    assert wrapper_with(client).list_models() == ["gpt-4.1", "o3-mini"]


def gemini_wrapper_with(client):
    wrapper = GeminiClientWrapper.__new__(GeminiClientWrapper)
    wrapper.api_key = "test"
    wrapper.client = client
    wrapper.media_client = client
    return wrapper


def test_veo_create_uses_supported_720p_parameters():
    calls = []
    operation = SimpleNamespace(
        name="operations/veo-1", done=False, error=None, response=None)

    class Models:
        @staticmethod
        def generate_videos(**kwargs):
            calls.append(kwargs)
            return operation

    wrapper = gemini_wrapper_with(SimpleNamespace(models=Models()))
    job = wrapper.create_video(
        "ink becoming a book", model="veo-3.1-fast-generate-preview",
        seconds=6, aspect_ratio="9:16")

    assert job.job_id == "operations/veo-1"
    assert job.status == "running"
    assert calls[0]["model"] == "veo-3.1-fast-generate-preview"
    assert calls[0]["config"].duration_seconds == 6
    assert calls[0]["config"].aspect_ratio == "9:16"
    assert calls[0]["config"].resolution == "720p"


def test_gemini_omni_decodes_inline_video_and_requests_length():
    calls = []

    class Interactions:
        @staticmethod
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                id="v1_omni", output_video=SimpleNamespace(
                    data=base64.b64encode(b"omni-mp4").decode()))

    wrapper = gemini_wrapper_with(SimpleNamespace(interactions=Interactions()))
    job = wrapper.create_video(
        "ink becoming a book", model="gemini-omni-1.1-flash",
        seconds=7, aspect_ratio="16:9")

    assert job.status == "completed"
    assert job.video_bytes == b"omni-mp4"
    assert "exactly 7-second" in calls[0]["input"]
    assert calls[0]["response_format"] == {
        "type": "video", "aspect_ratio": "16:9", "resolution": "720p"}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_wan_create_uses_async_task_endpoint_and_no_watermark():
    calls = []

    class Session:
        @staticmethod
        def post(url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse({
                "output": {"task_id": "wan-123", "task_status": "PENDING"}})

    wrapper = QwenClientWrapper.__new__(QwenClientWrapper)
    wrapper.api_key = "test"
    wrapper.video_base_url = "https://dashscope.example/api/v1"
    wrapper.video_session = Session()
    job = wrapper.create_video(
        "paper folds into a crane", model="wan3.0-video", seconds=12,
        aspect_ratio="1:1")

    assert job == WanVideoJob(
        "wan-123", "queued", "wan3.0-video", 12, "1:1", 5, "", "")
    url, kwargs = calls[0]
    assert url.endswith("/services/aigc/video-generation/video-synthesis")
    assert kwargs["headers"]["X-DashScope-Async"] == "enable"
    assert kwargs["json"]["parameters"] == {
        "resolution": "720P", "ratio": "1:1", "duration": 12,
        "prompt_extend": True, "watermark": False}


def test_generic_video_worker_preserves_completed_provider_output(tmp_path):
    output = tmp_path / "gemini.mp4"
    complete = GeminiVideoJob(
        "veo-2", "completed", "veo-3.1-lite-generate-preview", 4,
        "9:16", 100, video_bytes=b"video")

    class Client:
        @staticmethod
        def create_video(*_args, **_kwargs):
            return complete

        @staticmethod
        def wait_video(job, **_kwargs):
            return job

        @staticmethod
        def download_video(job):
            assert job is complete
            return b"video"

    done, errors, jobs = [], [], []
    worker = VideoGenerationWorker(
        Client(), "a prompt", output, provider="Gemini",
        model=complete.model, seconds=4, aspect_ratio="9:16")
    worker.done_signal.connect(done.append)
    worker.error_signal.connect(errors.append)
    worker.job_signal.connect(jobs.append)
    worker.run()

    assert output.read_bytes() == b"video"
    assert done == [str(output)]
    assert errors == []
    assert jobs[-1].status == "completed"
