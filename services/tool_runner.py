import subprocess
import json
from pathlib import Path


class ToolRunner:
    def __init__(self):
        config_path = Path("config/tools.json")
        with open(config_path, "r") as f:
            self.tools = json.load(f)

    def run_audiobook(self, input_path, output_path, voice, chunk_tokens):
        tool = self.tools["audiobook"]

        cmd = [
            tool["venv_python"],
            tool["script_path"],
            "--input", input_path,
            "--output", output_path,
            "--voice", voice,
            "--chunk-tokens", str(chunk_tokens)
        ]

        result = subprocess.run(
            cmd,
            cwd=tool["working_dir"],
            capture_output=True,
            text=True
        )

        return result.stdout, result.stderr
