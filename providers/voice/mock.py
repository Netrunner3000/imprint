from __future__ import annotations
import os
import subprocess
import platform
from typing import Optional
from .base import VoiceProvider, VoiceConfig


class MockVoiceProvider(VoiceProvider):
    """
    Local TTS using the OS speech engine (no API key needed).
    macOS: uses `say` command → AIFF → MP3.
    Linux: uses espeak if available, otherwise silent audio.
    Falls back to a silent audio file if no TTS is available.
    """

    @property
    def name(self) -> str:
        return "mock"

    def list_voices(self) -> list[dict]:
        if platform.system() == "Darwin":
            result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
            voices = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if parts:
                    voices.append({"id": parts[0], "name": parts[0], "preview_url": None})
            return voices[:10]
        return [{"id": "default", "name": "System TTS", "preview_url": None}]

    def synthesize(
        self,
        text: str,
        output_path: str,
        config: Optional[VoiceConfig] = None,
    ) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        system = platform.system()
        if system == "Darwin":
            return self._synthesize_macos(text, output_path, config)
        elif system == "Linux":
            return self._synthesize_linux(text, output_path)
        else:
            return self._silent_audio(text, output_path)

    def _synthesize_macos(self, text: str, output_path: str, config: Optional[VoiceConfig]) -> str:
        voice = config.voice_id if config and config.voice_id != "default" else "Samantha"
        rate = int(180 * (config.speaking_rate if config else 1.0))

        aiff_path = output_path.replace(".mp3", ".aiff").replace(".wav", ".aiff")
        if not aiff_path.endswith(".aiff"):
            aiff_path += ".aiff"

        say_cmd = ["say", "-v", voice, "-r", str(rate), "-o", aiff_path, text]
        r = subprocess.run(say_cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return self._silent_audio(text, output_path)

        # Convert AIFF → MP3
        ffmpeg_cmd = ["ffmpeg", "-y", "-i", aiff_path, "-codec:a", "libmp3lame", "-qscale:a", "2", output_path]
        subprocess.run(ffmpeg_cmd, capture_output=True)
        if os.path.exists(aiff_path):
            os.remove(aiff_path)

        return output_path

    def _synthesize_linux(self, text: str, output_path: str) -> str:
        wav_path = output_path.replace(".mp3", ".wav")
        if not wav_path.endswith(".wav"):
            wav_path += ".wav"

        r = subprocess.run(["espeak", "-w", wav_path, text], capture_output=True)
        if r.returncode != 0:
            return self._silent_audio(text, output_path)

        subprocess.run(["ffmpeg", "-y", "-i", wav_path, output_path], capture_output=True)
        if os.path.exists(wav_path):
            os.remove(wav_path)
        return output_path

    def _silent_audio(self, text: str, output_path: str) -> str:
        words = len(text.split())
        duration = max(5, int(words / 130 * 60))
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:a", "libmp3lame", "-q:a", "9",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True)
        return output_path
