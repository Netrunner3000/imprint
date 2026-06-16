from __future__ import annotations
import os
import time
import requests
from typing import Optional
from .base import AvatarProvider, AvatarConfig

_BASE_URL = "https://api.synthesia.io/v2"


class SynthesiaProvider(AvatarProvider):
    """
    Synthesia avatar video generation.
    Requires SYNTHESIA_API_KEY environment variable.
    Docs: https://docs.synthesia.io/reference
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("SYNTHESIA_API_KEY", "")
        if not self._api_key:
            raise ValueError("SYNTHESIA_API_KEY not set")

    @property
    def name(self) -> str:
        return "synthesia"

    def _headers(self) -> dict:
        return {"Authorization": self._api_key, "Content-Type": "application/json"}

    def list_avatars(self) -> list[dict]:
        r = requests.get(f"{_BASE_URL}/avatars", headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json().get("avatars", [])

    def generate_video(
        self,
        script: str,
        output_path: str,
        config: Optional[AvatarConfig] = None,
    ) -> str:
        cfg = config or AvatarConfig()

        payload = {
            "test": False,
            "input": [
                {
                    "scriptText": script,
                    "avatar": cfg.avatar_id,
                    "avatarSettings": {
                        "horizontalAlign": "right",
                        "scale": cfg.scale,
                        "style": "rectangular",
                    },
                    "background": cfg.background if cfg.background.startswith("#") else "off_white",
                }
            ],
        }

        r = requests.post(f"{_BASE_URL}/videos", json=payload, headers=self._headers(), timeout=60)
        r.raise_for_status()
        video_id = r.json()["id"]

        for _ in range(120):
            status = self.check_status(video_id)
            if status["status"] == "complete":
                video_url = status["video_url"]
                return self._download(video_url, output_path)
            if status["status"] == "failed":
                raise RuntimeError(f"Synthesia video generation failed for id {video_id}")
            time.sleep(10)

        raise TimeoutError(f"Synthesia video {video_id} did not complete within 20 minutes")

    def check_status(self, job_id: str) -> dict:
        r = requests.get(f"{_BASE_URL}/videos/{job_id}", headers=self._headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        return {
            "status": data.get("status", "in_progress"),
            "video_url": data.get("download"),
        }

    def _download(self, url: str, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        r = requests.get(url, stream=True, timeout=300)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return output_path
