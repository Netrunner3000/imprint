from __future__ import annotations
import os
import time
import requests
from typing import Optional
from .base import AvatarProvider, AvatarConfig

_BASE_URL = "https://api.heygen.com/v2"


class HeyGenProvider(AvatarProvider):
    """
    HeyGen avatar video generation.
    Requires HEYGEN_API_KEY environment variable.
    Docs: https://docs.heygen.com/reference/video-generation
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("HEYGEN_API_KEY", "")
        if not self._api_key:
            raise ValueError("HEYGEN_API_KEY not set")

    @property
    def name(self) -> str:
        return "heygen"

    def _headers(self) -> dict:
        return {"X-Api-Key": self._api_key, "Content-Type": "application/json"}

    def list_avatars(self) -> list[dict]:
        r = requests.get(f"{_BASE_URL}/avatars", headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json().get("data", {}).get("avatars", [])

    def generate_video(
        self,
        script: str,
        output_path: str,
        config: Optional[AvatarConfig] = None,
    ) -> str:
        cfg = config or AvatarConfig()

        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": cfg.avatar_id,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script,
                        "voice_id": cfg.voice_id,
                    },
                }
            ],
            "dimension": {"width": 1920, "height": 1080},
        }

        r = requests.post(f"{_BASE_URL}/video/generate", json=payload, headers=self._headers(), timeout=60)
        r.raise_for_status()
        video_id = r.json()["data"]["video_id"]

        # Poll until complete (HeyGen is async)
        for _ in range(120):
            status = self.check_status(video_id)
            if status["status"] == "completed":
                video_url = status["video_url"]
                return self._download(video_url, output_path)
            if status["status"] == "failed":
                raise RuntimeError(f"HeyGen video generation failed for id {video_id}")
            time.sleep(10)

        raise TimeoutError(f"HeyGen video {video_id} did not complete within 20 minutes")

    def check_status(self, job_id: str) -> dict:
        r = requests.get(f"{_BASE_URL}/video/{job_id}", headers=self._headers(), timeout=30)
        r.raise_for_status()
        data = r.json()["data"]
        return {
            "status": data.get("status", "processing"),
            "video_url": data.get("video_url"),
        }

    def _download(self, url: str, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        r = requests.get(url, stream=True, timeout=300)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return output_path
