import os
from google import genai


def _gemini_api_key():
    """Read the Gemini key, accepting either name. Google's own SDK uses
    GOOGLE_API_KEY; Sentinel historically referenced GEMINI_API_KEY. Support
    both so whichever is set in .env works."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


class GeminiClientWrapper:
    def __init__(self):
        self.api_key = _gemini_api_key()
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    @staticmethod
    def key_available():
        return bool(_gemini_api_key())

    def chat(self, messages, model="gemini-1.5-flash"):
        if not self.client:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        prompt = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in messages
        )

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
        )

        text = response.text or ""

        usage_metadata = getattr(response, "usage_metadata", None)

        usage = {
            "input_tokens": getattr(usage_metadata, "prompt_token_count", 0) if usage_metadata else 0,
            "output_tokens": getattr(usage_metadata, "candidates_token_count", 0) if usage_metadata else 0,
            "total_tokens": getattr(usage_metadata, "total_token_count", 0) if usage_metadata else 0,
        }

        return text, usage

    def generate(self, prompt, model="gemini-1.5-flash"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)
    
    def stream_chat(self, messages, model="gemini-1.5-flash"):
        if not self.client:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        prompt = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}"
            for m in messages
        )

        try:
            stream = self.client.models.generate_content_stream(
                model=model,
                contents=prompt,
            )

            for chunk in stream:
                text = getattr(chunk, "text", "")
                if text:
                    yield text

        except Exception as e:
            raise RuntimeError(f"Gemini streaming request failed: {e}")