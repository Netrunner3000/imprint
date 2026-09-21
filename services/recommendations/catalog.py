"""Turn Imprint's selectable model ids into comparable candidates.

This catalog describes stable product characteristics (fast/small/pro/local),
not marketing claims or a frozen universal leaderboard. Unknown live model ids
receive conservative provider-family defaults and are still rankable.
"""

from __future__ import annotations

import os
from datetime import date

from .models import Candidate


_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "KIMI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "higgsfield": "HIGGSFIELD_API_KEY",
    "pexels": "PEXELS_API_KEY",
}

_PROVIDER_DEFAULTS = {
    "openai":       (0.84, 0.86, 0.55, 0.72, 0.78),
    "anthropic":    (0.88, 0.87, 0.48, 0.67, 0.90),
    "deepseek":     (0.82, 0.76, 0.88, 0.72, 0.78),
    "kimi":         (0.82, 0.76, 0.61, 0.76, 0.88),
    "gemini":       (0.82, 0.80, 0.78, 0.82, 0.86),
    "qwen":         (0.82, 0.76, 0.67, 0.72, 0.94),
    "ollama":       (0.66, 0.70, 1.00, 0.48, 0.62),
}

_PROVIDER_TASKS = {
    "openai": {"general": .86, "code": .92, "analysis": .87,
               "marketing": .88, "social": .90, "structured": .88},
    "anthropic": {"general": .90, "creative": .96, "longform": .96,
                  "editing": .94, "analysis": .91, "code": .89,
                  "planning": .92, "marketing": .90, "social": .87},
    "deepseek": {"general": .79, "analysis": .94, "code": .95,
                 "structured": .88, "planning": .82},
    "kimi": {"general": .83, "analysis": .88, "code": .95,
             "longform": .87, "planning": .86},
    "gemini": {"general": .84, "analysis": .89, "marketing": .86,
               "social": .88, "longform": .85, "planning": .86},
    "qwen": {"general": .84, "analysis": .88, "code": .90,
             "longform": .87, "structured": .88},
    "ollama": {"general": .68, "creative": .70, "analysis": .72,
               "code": .72, "privacy": 1.0},
}


def provider_configured(provider: str) -> bool | None:
    provider = provider.casefold()
    if provider == "local":
        return True
    if provider == "ollama":
        # Unknown local tags must not beat a usable cloud fallback merely
        # because they need no API key.  The GUI can promote Ollama candidates
        # to available when its live list contains them.
        return False
    env = _KEY_ENV.get(provider)
    return bool(os.getenv(env, "")) if env else None


def text_candidate(provider: str, model_id: str,
                   *, available: bool | None = None) -> Candidate:
    key = provider.casefold()
    name = model_id.casefold()
    quality, reliability, cost, speed, context = _PROVIDER_DEFAULTS.get(
        key, (0.65, 0.65, 0.55, 0.60, 0.65))
    tasks = dict(_PROVIDER_TASKS.get(key, {"general": .65}))

    if any(token in name for token in ("opus", "pro", "max", "reasoner", "k3")):
        quality, speed, cost = min(1.0, quality + .10), speed - .14, cost - .15
        tasks["analysis"] = max(tasks.get("analysis", 0), .94)
    if any(token in name for token in ("mini", "flash", "haiku", "lite", "1.5b")):
        quality, speed, cost = quality - .10, min(1.0, speed + .17), min(1.0, cost + .18)
    if any(token in name for token in ("sonnet", "4o", "plus", "chat")):
        quality, speed = min(1.0, quality + .035), min(1.0, speed + .04)
    if "fable" in name:
        tasks["creative"], tasks["longform"] = 1.0, .98
    if "coder" in name or "code" in name:
        tasks["code"] = .98
    if "reasoner" in name or "r1" in name:
        tasks["analysis"] = .97
    if key == "ollama":
        privacy = 1.0
    else:
        privacy = 0.10

    return Candidate(
        provider=provider,
        model_id=model_id,
        label=model_id,
        task_fit=tasks,
        quality=max(0.0, min(1.0, quality)),
        reliability=max(0.0, min(1.0, reliability)),
        cost_efficiency=max(0.0, min(1.0, cost)),
        speed=max(0.0, min(1.0, speed)),
        context=max(0.0, min(1.0, context)),
        privacy=privacy,
        available=provider_configured(provider) if available is None else available,
    )


def known_text_models(provider: str) -> tuple[str, ...]:
    """Read each provider client's canonical offline list without an API call."""
    key = provider.casefold()
    classes = {
        "openai": ("services.openai_client", "OpenAIClientWrapper"),
        "anthropic": ("services.anthropic_client", "AnthropicClientWrapper"),
        "deepseek": ("services.deepseek_client", "DeepSeekClientWrapper"),
        "kimi": ("services.kimi_client", "KimiClientWrapper"),
        "gemini": ("services.gemini_client", "GeminiClientWrapper"),
        "qwen": ("services.qwen_client", "QwenClientWrapper"),
        "ollama": ("services.ollama_client", "OllamaClient"),
    }
    target = classes.get(key)
    if target is None:
        return ()
    module_name, class_name = target
    module = __import__(module_name, fromlist=[class_name])
    return tuple(getattr(getattr(module, class_name), "KNOWN_MODELS", ()))


def text_candidates(providers: list[str] | tuple[str, ...],
                    live_models: dict[str, list[str]] | None = None
                    ) -> list[Candidate]:
    live_models = live_models or {}
    result: list[Candidate] = []
    for provider in providers:
        models = live_models.get(provider, []) or list(known_text_models(provider))
        result.extend(text_candidate(provider, model) for model in models)
    return result


def media_candidate(model, duration: int | None = None) -> Candidate:
    """Adapt a services.media_catalog.MediaModel without coupling the engine."""
    from services.media_catalog import direct_video_rate_usd

    name = model.model_id.casefold()
    if model.kind == "local":
        quality, reliability, cost, speed, privacy = .42, .99, 1.0, .95, 1.0
        available = True
    elif model.kind == "stock":
        quality, reliability, cost, speed, privacy = .68, .92, .96, .92, .10
        available = provider_configured(model.provider)
    elif model.kind == "scene_images":
        quality = .94 if "sunburst" in name else .84 if "flare" in name else .80
        reliability, cost, speed, privacy = .88, .62, .62, .10
        if "flare" in name:
            speed = .88
        available = provider_configured(model.provider)
    else:
        quality = (.96 if "veo-3.1-generate" in name
                   else .91 if "wan3.0" in name else .86)
        reliability = .78
        speed = .88 if any(x in name for x in ("fast", "prime", "lite")) else .58
        rate = direct_video_rate_usd(model.model_id)
        cost = max(.10, 1.0 - (rate or .20) / .45)
        privacy = .08
        available = provider_configured(model.provider)
    estimated = None
    if duration and model.kind == "direct_video":
        rate = direct_video_rate_usd(model.model_id)
        estimated = rate * duration if rate is not None else None
    # No retirement gate is needed: Sora's rows left the media catalog ahead
    # of the scheduled 2026-09-24 shutdown.
    retired = False
    return Candidate(
        provider=model.provider,
        model_id=model.model_id,
        label=model.label,
        modality="visual",
        kind=model.kind,
        task_fit={"general": .80, "video": quality,
                  "social": min(1.0, speed + .05), "longform": quality},
        quality=quality,
        reliability=reliability,
        cost_efficiency=cost,
        speed=speed,
        context=.60,
        privacy=privacy,
        available=available,
        retired=retired,
        aspects=tuple(model.aspects),
        durations=tuple(model.durations),
        estimated_cost=estimated,
    )
