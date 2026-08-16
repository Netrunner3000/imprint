"""
Voice-source resolution shared by every panel that offers TTS.

Pure logic, no Qt — so it can be tested without a running application.
"""

from __future__ import annotations

SYSTEM_SOURCE = "System (Free)"
ELEVENLABS_SOURCE = "ElevenLabs"
VOICE_SOURCES = [SYSTEM_SOURCE, ELEVENLABS_SOURCE]

# Shown when ElevenLabs is selected but no API key is configured.
UNAVAILABLE_LABEL = "(ElevenLabs key not set)"
UNAVAILABLE_ID = "default"


def list_voices_for_source(source: str) -> list[tuple[str, str]]:
    """Return [(display_name, voice_id), …] for the given voice source.

    Falls back to a single placeholder entry if the source is unavailable
    (e.g. ElevenLabs selected with no API key) so callers always have
    something to show and a usable default id.
    """
    try:
        if source == ELEVENLABS_SOURCE:
            from providers.voice.elevenlabs import ElevenLabsProvider
            voices = ElevenLabsProvider().list_voices()
        else:
            from providers.voice.mock import MockVoiceProvider
            voices = MockVoiceProvider().list_voices()
        resolved = [(v["name"], v["id"]) for v in voices]
        return resolved or [(UNAVAILABLE_LABEL, UNAVAILABLE_ID)]
    except Exception:
        return [(UNAVAILABLE_LABEL, UNAVAILABLE_ID)]


def uses_elevenlabs(source: str) -> bool:
    """Whether the given voice source means 'call the ElevenLabs API'."""
    return source == ELEVENLABS_SOURCE
