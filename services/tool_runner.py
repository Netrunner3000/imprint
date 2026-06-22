import io
import json
import contextlib
from pathlib import Path


class ToolRunner:
    def __init__(self):
        # tools.json lives at <project_root>/config/tools.json, regardless of cwd.
        config_path = Path(__file__).resolve().parent.parent / "config" / "tools.json"
        with open(config_path, "r") as f:
            self.tools = json.load(f)

    def run_audiobook(self, input_path, output_path, voice, chunk_tokens):
        """Run the audiobook conversion in-process (no subprocess, no separate venv).

        Returns (stdout_text, stderr_text) to preserve the previous interface.
        """
        # Imported lazily so importing ToolRunner doesn't pull in heavy TTS deps
        # unless the audiobook tool is actually used.
        from services.narrator.converter import convert

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                convert(
                    input=input_path,
                    output=output_path,
                    voice=voice,
                    chunk_tokens=chunk_tokens,
                )
            return buf.getvalue(), ""
        except Exception as e:
            return buf.getvalue(), str(e)
