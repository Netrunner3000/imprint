"""Media-generation capabilities shown by Imprint's Video workspace.

This is deliberately separate from chat-model discovery. A model appearing in
``GET /models`` does not mean it can generate an image or a video, and offering
every GPT/Claude model in a visual dropdown creates controls that fail only
after the user presses Render. Every entry returned here has an implemented
execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


OPENAI_IMAGE_MODELS = (
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-2",
)
OPENAI_VIDEO_MODELS = ("sora-2", "sora-2-pro")
RETIRED_DALLE_MODELS = ("dall-e-2", "dall-e-3")
SORA_SHUTDOWN_DATE = date(2026, 9, 24)

# Official rates for 720p portrait/landscape Sora output, per generated second.
SORA_USD_PER_SECOND = {"sora-2": 0.10, "sora-2-pro": 0.30}

@dataclass(frozen=True)
class MediaModel:
    provider: str
    model_id: str
    label: str
    kind: str  # scene_images | direct_video | stock | local
    note: str = ""


MODELS = (
    MediaModel("OpenAI", "gpt-image-2.5-sunburst",
               "GPT Image 2.5 Sunburst", "scene_images",
               "Highest-fidelity scene images."),
    MediaModel("OpenAI", "gpt-image-2.5-flare",
               "GPT Image 2.5 Flare", "scene_images",
               "Faster scene-image generation."),
    MediaModel("OpenAI", "gpt-image-2", "GPT Image 2", "scene_images",
               "Current general image model."),
    MediaModel("OpenAI", "sora-2", "Sora 2 · retiring 24 Sep",
               "direct_video", "Direct 4, 8 or 12 second clip with audio."),
    MediaModel("OpenAI", "sora-2-pro", "Sora 2 Pro · retiring 24 Sep",
               "direct_video", "Higher-quality direct clip with audio."),
    MediaModel("Higgsfield", "seedance-1.0-lite", "Seedance 1.0 Lite",
               "direct_video", "Direct clip priced by Higgsfield before approval."),
    MediaModel("Pexels", "pexels-stock", "Pexels stock photography", "stock",
               "Stock visuals; requires PEXELS_API_KEY. Script and narration "
               "still use the configured pipeline providers."),
    MediaModel("Local", "gradient-cards", "Local gradient cards", "local",
               "Local visuals with no image-generation charge. Script and "
               "narration still use the configured pipeline providers."),
)

MEDIA_PROVIDERS = tuple(dict.fromkeys(model.provider for model in MODELS))


def models_for(provider: str) -> tuple[MediaModel, ...]:
    """Only return models for which Imprint has a real execution path."""
    return tuple(model for model in MODELS if model.provider == provider)


def find_model(provider: str, model_id: str) -> MediaModel | None:
    return next((model for model in MODELS
                 if model.provider == provider and model.model_id == model_id), None)


def sora_cost_usd(model: str, seconds: int) -> float:
    if model not in SORA_USD_PER_SECOND:
        raise ValueError(f"Unsupported Sora model: {model}")
    if int(seconds) not in (4, 8, 12):
        raise ValueError("Sora clips must be 4, 8 or 12 seconds.")
    return round(SORA_USD_PER_SECOND[model] * int(seconds), 2)


def sora_is_retired(today: date | None = None) -> bool:
    return (today or date.today()) >= SORA_SHUTDOWN_DATE


def openai_image_reserve_usd(model: str) -> float:
    from services.per_unit_pricing import rate_usd

    value = rate_usd("openai_image", model)
    if value is None:
        raise ValueError(f"No budget reserve is configured for {model}")
    return value
