from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class VoiceConfig:
    voice_id: str = "default"
    stability: float = 0.5
    similarity_boost: float = 0.75
    speaking_rate: float = 1.0
    pitch: float = 0.0


class VoiceProvider(ABC):
    """Convert text to speech audio."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def list_voices(self) -> list[dict]:
        """Return available voices with id, name, preview_url."""
        ...

    @abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: str,
        config: Optional[VoiceConfig] = None,
    ) -> str:
        """
        Synthesize text to speech.
        Returns local path to the generated audio file (MP3 or WAV).
        """
        ...
