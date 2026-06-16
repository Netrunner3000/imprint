import os
from openai import OpenAI


class OpenAIClientWrapper:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    @staticmethod
    def key_available():
        return bool(os.getenv("OPENAI_API_KEY"))

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
    
    def generate_image(self, prompt: str, size: str = "1024x1024") -> str:
        """Generate an image with DALL-E 3. Returns the image URL."""
        if not self.client:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        response = self.client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        return response.data[0].url

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