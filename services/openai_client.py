import base64
import os
import urllib.request

from openai import OpenAI

from services.api_limits import REQUEST_TIMEOUT_SECONDS, MAX_RETRIES

# Image models offered by the Gigs panel. dall-e-3 stays the default because it
# is what every existing saved order was generated with; gpt-image-1 is the
# newer model and is markedly better at text inside an image, which is most of
# what a logo is.
IMAGE_MODELS = ("dall-e-3", "gpt-image-1")
DEFAULT_IMAGE_MODEL = "dall-e-3"

# Approximate US$ per 1024x1024 image at the quality this app requests. Used
# for the estimate shown next to the button, NOT by the budget guard — that is
# denominated in tokens and cannot express "one image". See SUGGESTIONS.md.
IMAGE_COST_USD = {"dall-e-3": 0.04, "gpt-image-1": 0.04}


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
            models = sorted(
                m.id for m in result.data
                if any(x in m.id.lower() for x in ("gpt", "o1", "o3", "o4"))
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

        Bytes rather than a URL because the two models do not agree on how they
        hand an image back: dall-e-3 returns a short-lived URL, gpt-image-1
        always returns base64 and has no URL at all. Returning bytes makes the
        caller identical for both, and takes the download out of the worker.

        The models also do not share a `quality` vocabulary — dall-e-3 takes
        "standard"/"hd", gpt-image-1 takes "low"/"medium"/"high"/"auto" — so
        only dall-e-3 is sent an explicit value and gpt-image-1 is left on its
        own default. Sending the wrong word is a 400.
        """
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        kwargs = {"model": model, "prompt": prompt, "size": size, "n": 1}
        if model == "dall-e-3":
            kwargs["quality"] = "standard"
        response = self.client.images.generate(**kwargs)
        item = response.data[0]

        encoded = getattr(item, "b64_json", None)
        if encoded:
            return base64.b64decode(encoded)
        url = getattr(item, "url", None)
        if not url:
            raise RuntimeError(
                f"{model} returned neither image data nor a URL.")
        with urllib.request.urlopen(url) as handle:
            return handle.read()

    def stream_chat(self, messages, model="gpt-4o-mini"):
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")

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
            raise RuntimeError(f"OpenAI streaming request failed: {e}")