import base64
import os
import time
import urllib.request
from dataclasses import dataclass

from openai import OpenAI

from services.api_limits import REQUEST_TIMEOUT_SECONDS, MAX_RETRIES
from services.stream_usage import UsageStream, cached_input_tokens
from services.media_catalog import OPENAI_IMAGE_MODELS

# Image models offered by the Gigs and Video panels. DALL-E 2/3 were removed
# from the API; these are the current replacements listed in the provider's
# model catalog.
IMAGE_MODELS = OPENAI_IMAGE_MODELS
DEFAULT_IMAGE_MODEL = "gpt-image-2.5-flare"


class OpenAIClientWrapper:
    KNOWN_MODELS = [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
    ]

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = (
            OpenAI(
                api_key=self.api_key,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=MAX_RETRIES,
            )
            if self.api_key
            else None
        )

    @staticmethod
    def key_available():
        return bool(os.getenv("OPENAI_API_KEY"))

    def list_models(self) -> list[str]:
        """Chat-capable model ids, newest listing from the API when reachable.

        Falls back to KNOWN_MODELS with no key or on any API error so the model
        dropdowns are never left empty.
        """
        if not self.client:
            return self.KNOWN_MODELS
        try:
            result = self.client.models.list()
            excluded = (
                "image", "realtime", "audio", "transcribe", "tts", "sora",
                "video", "embedding", "moderation",
            )
            models = sorted(
                m.id for m in result.data
                if any(x in m.id.lower() for x in ("gpt", "o1", "o3", "o4"))
                and not any(x in m.id.lower() for x in excluded)
            )
            return models if models else self.KNOWN_MODELS
        except Exception:
            return self.KNOWN_MODELS

    def chat(self, messages, model="gpt-4o-mini"):
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")

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

    def generate(self, prompt, model="gpt-4o-mini"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)
    
    def generate_image(self, prompt: str, size: str = "1024x1024",
                       model: str = DEFAULT_IMAGE_MODEL) -> bytes:
        """Generate one image and return its PNG bytes.

        Current GPT Image models normally return base64. URL handling remains
        for compatibility with provider responses that use temporary assets.
        """
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        if model not in IMAGE_MODELS:
            raise ValueError(
                f"Unsupported image model {model!r}. Select one of: "
                + ", ".join(IMAGE_MODELS))
        kwargs = {
            "model": model, "prompt": prompt, "size": size,
            "quality": "medium", "n": 1,
        }
        response = self.client.images.generate(**kwargs)
        item = response.data[0]

        encoded = getattr(item, "b64_json", None)
        if encoded:
            return base64.b64decode(encoded)
        url = getattr(item, "url", None)
        if not url:
            raise RuntimeError(
                f"{model} returned neither image data nor a URL.")
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as handle:
            return handle.read()

    # The Sora job methods (create/poll/wait/download and OpenAIVideoJob) were
    # removed ahead of OpenAI's scheduled 2026-09-24 Videos API shutdown.

    def stream_chat(self, messages, model="gpt-4o-mini"):
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")

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
                raise RuntimeError(f"OpenAI streaming request failed: {e}")

        return UsageStream(_gen)
