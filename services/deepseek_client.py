import os
from openai import OpenAI


class DeepSeekClientWrapper:
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

    def chat(self, messages, model="deepseek-chat"):
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

    def generate(self, prompt, model="deepseek-chat"):
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages=messages, model=model)
    
    def stream_chat(self, messages, model="deepseek-chat"):
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