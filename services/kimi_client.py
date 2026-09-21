import os
from openai import OpenAI

from services.api_limits import REQUEST_TIMEOUT_SECONDS, MAX_RETRIES
from services.stream_usage import UsageStream, cached_input_tokens


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
            "cached_input_tokens": cached_input_tokens(response.usage),
        }

        return text, usage

    def generate(self, prompt, model="kimi-k2.7-code"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)

    def stream_chat(self, messages, model="kimi-k2.7-code"):
        if not self.client:
            raise RuntimeError("KIMI_API_KEY is not set.")

        def _gen(out):
            try:
                stream = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                    # The provider's real token counts arrive in a final
                    # usage-only frame; without this every stream was billed
                    # on the chars/4 estimate (and cached-input billing could
                    # never fire).
                    stream_options={"include_usage": True},
                )
                for chunk in stream:
                    usage = getattr(chunk, "usage", None)
                    if usage:
                        out.usage = {
                            "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                            "cached_input_tokens": cached_input_tokens(usage),
                        }
                    # OpenAI-compatible endpoints legitimately emit chunks with an
                    # empty choices array (content filters, usage-only frames);
                    # indexing [0] blindly crashed the stream mid-response.
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
            except Exception as e:
                raise RuntimeError(f"Kimi streaming request failed: {e}")

        return UsageStream(_gen)


# _cached_tokens moved to services/stream_usage.py (cached_input_tokens) so
# every OpenAI-compatible stream can report cache hits, not just Kimi.
