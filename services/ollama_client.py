import json
import requests


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> list[str]:
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            return [model["name"] for model in data.get("models", [])]

        except requests.RequestException as e:
            raise RuntimeError(f"Ollama model list request failed: {e}")

    def generate(self, model: str, prompt: str, keep_alive: str = "3m") -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=300,
            )
            response.raise_for_status()

            data = response.json()
            return data.get("response", "")

        except requests.RequestException as e:
            raise RuntimeError(f"Ollama generate request failed: {e}")

    def chat(self, model: str, messages: list[dict], keep_alive: str = "3m") -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=300,
            )
            response.raise_for_status()

            data = response.json()
            return data.get("message", {}).get("content", "")

        except requests.RequestException as e:
            raise RuntimeError(f"Ollama chat request failed: {e}")

    def stream_chat(self, model: str, messages: list[dict], keep_alive: str = "3m"):
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
        }

        try:
            with requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=300,
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue

                    data = json.loads(line.decode("utf-8"))

                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]

                    if data.get("done"):
                        break

        except requests.RequestException as e:
            raise RuntimeError(f"Ollama streaming request failed: {e}")

        except json.JSONDecodeError as e:
            raise RuntimeError(f"Ollama streaming JSON parse failed: {e}")