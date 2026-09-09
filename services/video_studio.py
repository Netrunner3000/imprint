"""The bridge to vidforge — Imprint's video pipeline.

`vidforge` is a **separate git repository** nested at `imprint/vidforge/`, and
this module imports it rather than vendoring a copy. That is deliberate. The
workspace already has one vendored-copy pair (`lab_hub/tools/convert` against
`toolbox/convert_epub`) and they have silently drifted apart in four files; a
second copy of a 20-module video pipeline would drift faster and matter more.
So: one checkout, one pipeline, two front doors — `vidforge.app` standalone and
Imprint's Video mode.

## What that costs, and how it is handled

*A clone of `imprint` alone has no `vidforge`.* Every entry point here answers
`available()` first, and the Video panel renders an explanation instead of a
dead form when it is missing. Nothing raises at import time.

*Frozen builds share a data directory.* vidforge decides its own paths from
`sys.frozen`: inside Imprint.app that resolves `BUNDLE_ROOT` to Imprint's
bundle (so `Imprint.spec` ships vidforge's `config.yaml`, `topics.txt` and
`assets/`) and `PROJECT_ROOT` to `~/Library/Application Support/vidforge` —
the same directory the standalone app uses. That is the intended outcome: one
config, one output library, one history, whichever front door you came in by.

## Long-form and clips are the same pipeline

`produce()` renders at `video.width` x `video.height` from the config, so a
vertical social clip is the same call with an override rather than a second
code path. `clip_overrides()` builds that override set. The Social mode asks
for clips through here, so there is one video pipeline in the app and not one
per caller.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Where the nested repo lives when running from a checkout. In a frozen build
# the package is bundled, so it is already importable and this is unused.
VIDFORGE_ROOT = PROJECT_ROOT / "vidforge"

# Aspect presets. Long-form is whatever config.yaml says; the rest are the
# platform-native shapes the Social mode schedules against.
ASPECTS: dict[str, tuple[int, int]] = {
    "Landscape 16:9": (1920, 1080),
    "Vertical 9:16": (1080, 1920),
    "Square 1:1": (1080, 1080),
}
DEFAULT_ASPECT = "Landscape 16:9"

# Clip lengths offered for social. vidforge sizes a script by target seconds.
CLIP_SECONDS = (15, 30, 45, 60, 90)

_import_error: str | None = None
_pipeline: Any = None
_config_mod: Any = None
_progress_mod: Any = None


def _load() -> bool:
    """Import vidforge once. Returns True when it is usable.

    Import failures are recorded rather than raised: a missing sibling repo is
    a state the UI explains, not a crash on startup.
    """
    global _pipeline, _config_mod, _progress_mod, _import_error
    if _pipeline is not None:
        return True
    if _import_error is not None:
        return False

    try:
        if VIDFORGE_ROOT.is_dir() and str(VIDFORGE_ROOT) not in sys.path:
            sys.path.insert(0, str(VIDFORGE_ROOT))
        from vidforge import config as config_mod      # type: ignore
        from vidforge import pipeline as pipeline_mod  # type: ignore
        from vidforge import progress as progress_mod  # type: ignore
    except Exception as exc:                       # ImportError, and anything
        _import_error = f"{type(exc).__name__}: {exc}"   # its own imports raise
        return False

    _config_mod, _pipeline, _progress_mod = config_mod, pipeline_mod, progress_mod
    return True


def available() -> bool:
    return _load()


def unavailable_reason() -> str:
    """Why Video is unavailable, phrased for the panel rather than a log."""
    if _load():
        return ""
    if not VIDFORGE_ROOT.is_dir():
        return (
            "The vidforge repository is not present.\n\n"
            "Video mode runs the vidforge pipeline directly rather than "
            "keeping a second copy of it, so it needs that checkout at:\n"
            f"    {VIDFORGE_ROOT}\n\n"
            "Clone it there and restart Imprint."
        )
    return (
        "vidforge is present but could not be imported:\n\n"
        f"    {_import_error}\n\n"
        "This is usually a missing dependency — vidforge needs PyYAML, and "
        "the YouTube upload step additionally needs google-api-python-client "
        "and google-auth-oauthlib."
    )


def stages() -> tuple[tuple[str, str, float], ...]:
    """(key, label, share of the bar) for each pipeline stage."""
    return _progress_mod.STAGES if _load() else ()


def reporter_base():
    """vidforge's Reporter class, for the Qt subclass in ui/workers.py."""
    return _progress_mod.Reporter if _load() else object


def cancelled_error():
    """The exception `produce()` raises when a reporter is cancelled."""
    return _progress_mod.Cancelled if _load() else RuntimeError


def overall_fraction(stage_key: str, within: float = 0.0) -> float:
    return _progress_mod.overall_fraction(stage_key, within) if _load() else 0.0


def load_config(overrides: dict[str, Any] | None = None):
    """vidforge's Config, with any overrides applied.

    `ensure_user_root()` seeds config.yaml and topics.txt into the writable
    directory on a frozen build's first run; on a checkout it is a no-op.
    """
    if not _load():
        raise RuntimeError(unavailable_reason())
    _config_mod.ensure_user_root()
    cfg = _config_mod.Config.load()
    for dotted, value in (overrides or {}).items():
        cfg.set(dotted, value)
    return cfg


def clip_overrides(aspect: str = DEFAULT_ASPECT,
                   seconds: int | None = None) -> dict[str, Any]:
    """Config overrides that turn the long-form pipeline into a social clip.

    Nothing here is a separate rendering path: the pipeline already sizes every
    stage from `video.width`/`video.height` and the script from a target
    length, so a vertical 30-second clip is the same `produce()` call with
    different numbers.
    """
    width, height = ASPECTS.get(aspect, ASPECTS[DEFAULT_ASPECT])
    overrides: dict[str, Any] = {"video.width": width, "video.height": height}

    # The image model has to be asked for the right shape too, or a portrait
    # clip is a landscape image cropped to a strip of its middle.
    if height > width:
        overrides["visuals.image_size"] = "1024x1536"
        overrides["visuals.pexels_orientation"] = "portrait"
    elif height == width:
        overrides["visuals.image_size"] = "1024x1024"
        overrides["visuals.pexels_orientation"] = "square"

    if seconds:
        overrides["script.target_seconds"] = int(seconds)
        # A clip inherits the long-form cadence of one visual per 14s
        # otherwise, so a 30-second clip would be two shots. Short-form is cut
        # much faster than that. 6 is the pipeline's own floor.
        overrides["script.scene_seconds"] = 6
    return overrides


def produce(cfg, *, topic: str | None = None, resume_slug: str | None = None,
            reporter=None):
    """Render one video. Returns vidforge's Build."""
    if not _load():
        raise RuntimeError(unavailable_reason())
    return _pipeline.produce(cfg, topic=topic, resume_slug=resume_slug,
                             reporter=reporter)


def output_root() -> Path:
    """Where finished videos land — shared with the standalone app."""
    if not _load():
        return PROJECT_ROOT / "data" / "video"
    return _config_mod.output_root()


def library() -> list[dict]:
    """Every build vidforge has recorded, newest first.

    Reads vidforge's own history rather than keeping a second index, so a
    render started in the standalone app shows up here and vice versa.
    """
    if not _load():
        return []
    try:
        from vidforge import history  # type: ignore
        entries = list(history.load())
    except Exception:
        return []
    entries.sort(key=lambda e: e.get("created", ""), reverse=True)
    return entries


def pre_estimate(cfg) -> dict[str, float]:
    """Per-stage cost estimate **before** the script exists.

    vidforge's own `script.estimate_cost_usd()` needs a finished plan, which
    only exists after the first paid call has already been made. The panel has
    to show a number before you press the button, so this reproduces the same
    arithmetic from config alone: target length gives a word budget, the word
    budget and scene length give a scene count, and the rest follows.

    Deliberately the same shape and the same rates as vidforge's version, so
    the estimate shown before a run and the actual recorded on the build are
    comparable. Both are rough — a video is billed per image, per character and
    per audio minute, none of which the token-denominated budget guard can
    express (see SUGGESTIONS.md).
    """
    if not _load():
        return {"script": 0.0, "narration": 0.0, "images": 0.0,
                "captions": 0.0, "total": 0.0}

    seconds = int(cfg.get("script.target_seconds", 480))
    wpm = int(cfg.get("script.words_per_minute", 155))
    scene_seconds = max(6, int(cfg.get("script.scene_seconds", 14)))

    words = seconds / 60 * wpm
    scenes = max(1, round(seconds / scene_seconds))
    chars = words * 6

    tts = chars / 4 / 1_000_000 * 0.60
    images = (scenes + 1) * 0.04 if cfg.get("visuals.source") == "ai" else 0.0
    whisper = ((words / wpm) * 0.006
               if cfg.get("captions.enabled")
               and cfg.get("captions.align") == "whisper" else 0.0)
    script_cost = 0.05 if cfg.get("script.provider") == "anthropic" else 0.03

    return {
        "script": round(script_cost, 3),
        "narration": round(tts, 3),
        "images": round(images, 3),
        "captions": round(whisper, 3),
        "scenes": scenes,
        "words": int(words),
        "total": round(script_cost + tts + images + whisper, 2),
    }
