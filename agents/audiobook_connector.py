class AudiobookConnector:
    def parse_input(self, text):
        config = {
            "input": None,
            "output": None,
            "voice": "alloy",
            "chunk_tokens": 1500
        }

        for line in text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()

        if not config["input"]:
            raise ValueError("Missing required field: input=/path/to/book-or-folder")

        if not config["output"]:
            raise ValueError("Missing required field: output=/path/to/output-folder")

        return config
