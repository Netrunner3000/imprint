import os
from openai import OpenAI


class DeepSeekClientWrapper:
    # Offline fallback only. Ordered to match what the API currently serves —
    # the older deepseek-chat / deepseek-reasoner ids are no longer offered.
    KNOWN_MODELS = [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.client = (
            OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com",
            )
            if self.api_key
            else None
        )

    @staticmethod
    def key_available():
        return bool(os.getenv("DEEPSEEK_API_KEY"))

    def list_models(self) -> list[str]:
        """Available model ids, from the API when reachable.

        Falls back to KNOWN_MODELS with no key or on any API error so the model
        dropdowns are never left empty.
        """
        if not self.client:
            return self.KNOWN_MODELS
        try:
            result = self.client.models.list()
            models = sorted(m.id for m in result.data)
            return models if models else self.KNOWN_MODELS
        except Exception:
            return self.KNOWN_MODELS

    def chat(self, messages, model="deepseek-v4-flash"):
        if not self.client:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
        )

        text = response.choices[0].message.content or ""

        usage = {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        return text, usage

    def generate(self, prompt, model="deepseek-v4-flash"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)
    
    def stream_chat(self, messages, model="deepseek-v4-flash"):
        if not self.client:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")

        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
            )

            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        except Exception as e:
            raise RuntimeError(f"DeepSeek streaming request failed: {e}")