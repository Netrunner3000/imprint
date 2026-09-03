import os
from openai import OpenAI

from services.api_limits import REQUEST_TIMEOUT_SECONDS, MAX_RETRIES


class KimiClientWrapper:
    """Wrapper for Moonshot AI's Kimi models via the OpenAI-compatible Kimi API.

    Docs: https://platform.kimi.ai/docs/api/overview
    """

    KNOWN_MODELS = [
        "kimi-k3",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
        "kimi-k2.6",
    ]

    def __init__(self):
        self.api_key = os.getenv("KIMI_API_KEY")
        self.client = (
            OpenAI(
                api_key=self.api_key,
                base_url="https://api.moonshot.ai/v1",
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=MAX_RETRIES,
            )
            if self.api_key
            else None
        )

    @staticmethod
    def key_available():
        return bool(os.getenv("KIMI_API_KEY"))

    def list_models(self) -> list[str]:
        if not self.client:
            return self.KNOWN_MODELS
        try:
            result = self.client.models.list()
            models = sorted(m.id for m in result.data)
            return models if models else self.KNOWN_MODELS
        except Exception:
            return self.KNOWN_MODELS

    def chat(self, messages, model="kimi-k2.7-code"):
        if not self.client:
            raise RuntimeError("KIMI_API_KEY is not set.")

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
        )

        text = response.choices[0].message.content or ""

        usage = {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
            "cached_input_tokens": _cached_tokens(response.usage),
        }

        return text, usage

    def generate(self, prompt, model="kimi-k2.7-code"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)

    def stream_chat(self, messages, model="kimi-k2.7-code"):
        if not self.client:
            raise RuntimeError("KIMI_API_KEY is not set.")

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
            raise RuntimeError(f"Kimi streaming request failed: {e}")


def _cached_tokens(usage) -> int:
    """Input tokens the provider served from its prompt cache, or 0.

    Two shapes are in the wild on OpenAI-compatible endpoints, so both are
    read rather than assuming one: OpenAI nests it under
    `prompt_tokens_details.cached_tokens`, while the DeepSeek-style APIs report
    a flat `prompt_cache_hit_tokens`. Anything unrecognised counts as no cache
    hit, which bills at the full input rate — the conservative direction.
    """
    if not usage:
        return 0
    details = getattr(usage, "prompt_tokens_details", None)
    nested = getattr(details, "cached_tokens", None) if details else None
    if nested is None and isinstance(details, dict):
        nested = details.get("cached_tokens")
    flat = getattr(usage, "prompt_cache_hit_tokens", None)
    for value in (nested, flat):
        try:
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0
