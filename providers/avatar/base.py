from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AvatarConfig:
    avatar_id: str = "default"
    voice_id: str = "default"
    background: str = "transparent"   # transparent | blurred | color hex
    position: str = "bottom-right"    # where the avatar appears on screen
    scale: float = 0.35               # fraction of frame width


class AvatarProvider(ABC):
    """Generate a talking-head video from a script."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def list_avatars(self) -> list[dict]:
        """Return available avatars with id, name, preview_url."""
        ...

    @abstractmethod
    def generate_video(
        self,
        script: str,
        output_path: str,
        config: Optional[AvatarConfig] = None,
    ) -> str:
        """
        Generate an avatar video speaking the script.
        Returns local path to the downloaded MP4 file.
        Raises RuntimeError on failure.
        """
        ...

    @abstractmethod
    def check_status(self, job_id: str) -> dict:
        """Poll async job status. Returns dict with 'status' and optionally 'video_url'."""
        ...
