"""
Short-form video generator for the Manuscript agent.
Combines a quote graphic (static image, from quote_graphics.py) with narrated
audio into a vertical MP4 sized for TikTok / Reels / Shorts. Uses free
on-device TTS (macOS `say`) by default; ElevenLabs if ELEVENLABS_API_KEY is set.
"""

from __future__ import annotations
import os
import subprocess
from pathlib import Path

from providers.voice.base import VoiceConfig

SHORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "shorts"
SHORTS_DIR.mkdir(parents=True, exist_ok=True)


def _ffmpeg(*args: str) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[-1000:]}")
    return result


def get_voice_provider(use_elevenlabs: bool = False):
    if use_elevenlabs and os.environ.get("ELEVENLABS_API_KEY"):
        from providers.voice.elevenlabs import ElevenLabsProvider
        return ElevenLabsProvider()
    from providers.voice.mock import MockVoiceProvider
    return MockVoiceProvider()


def render_short(
    quote: str,
    image_path: Path,
    output_path: Path,
    use_elevenlabs: bool = False,
    voice_id: str = "default",
) -> Path:
    """Narrate `quote` and combine with the static `image_path` into a vertical MP4."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path = output_path.with_suffix(".mp3")

    provider = get_voice_provider(use_elevenlabs)
    provider.synthesize(quote, str(audio_path), VoiceConfig(voice_id=voice_id))

    _ffmpeg(
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-shortest",
        str(output_path),
    )

    if audio_path.exists():
        audio_path.unlink()

    return output_path
