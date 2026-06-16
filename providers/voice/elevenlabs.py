from __future__ import annotations
import os
import requests
from typing import Optional
from .base import VoiceProvider, VoiceConfig

_BASE_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsProvider(VoiceProvider):
    """
    ElevenLabs text-to-speech.
    Requires ELEVENLABS_API_KEY environment variable.
    Docs: https://docs.elevenlabs.io/api-reference
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not self._api_key:
            raise ValueError("ELEVENLABS_API_KEY not set")

    @property
    def name(self) -> str:
        return "elevenlabs"

    def _headers(self) -> dict:
        return {"xi-api-key": self._api_key, "Content-Type": "application/json"}

    def list_voices(self) -> list[dict]:
        r = requests.get(f"{_BASE_URL}/voices", headers=self._headers(), timeout=30)
        r.raise_for_status()
        return [
            {"id": v["voice_id"], "name": v["name"], "preview_url": v.get("preview_url")}
            for v in r.json().get("voices", [])
        ]

    def synthesize(
        self,
        text: str,
        output_path: str,
        config: Optional[VoiceConfig] = None,
    ) -> str:
        cfg = config or VoiceConfig()
        voice_id = cfg.voice_id if cfg.voice_id != "default" else "21m00Tcm4TlvDq8ikWAM"  # Rachel

        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": cfg.stability,
                "similarity_boost": cfg.similarity_boost,
                "speaking_rate": cfg.speaking_rate,
            },
        }

        r = requests.post(
            f"{_BASE_URL}/text-to-speech/{voice_id}",
            json=payload,
            headers={**self._headers(), "Accept": "audio/mpeg"},
            timeout=120,
        )
        r.raise_for_status()

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(r.content)

        return output_path
