"""General assistant implementation owned by the Chat agent package."""


class ChatAgent:
    def build_messages(self, prompt: str) -> list[dict]:
        return [{"role": "user", "content": prompt}]  # simple one-message chat payload
