from __future__ import annotations
import subprocess
import os
from typing import Optional
from .base import AvatarProvider, AvatarConfig


class MockAvatarProvider(AvatarProvider):
    """
    Generates a placeholder avatar video using ffmpeg.
    Produces a dark frame with animated text — no API required.
    Used for local development and pipeline testing.
    """

    @property
    def name(self) -> str:
        return "mock"

    def list_avatars(self) -> list[dict]:
        return [{"id": "default", "name": "Mock Avatar (placeholder)", "preview_url": None}]

    def generate_video(
        self,
        script: str,
        output_path: str,
        config: Optional[AvatarConfig] = None,
    ) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Estimate duration from word count (average 130 wpm)
        words = len(script.split())
        duration = max(5, int(words / 130 * 60))

        # Plain indigo rectangle — no drawtext needed (avoids libfreetype dependency)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x4F46E5:size=480x270:duration={duration}:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Mock avatar ffmpeg failed: {result.stderr}")

        return output_path

    def check_status(self, job_id: str) -> dict:
        return {"status": "completed"}
