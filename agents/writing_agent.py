class WritingAgent:
    def build_messages(self, prompt: str) -> list[dict]:
        system = (
            "You are a writing assistant. Improve clarity, structure, tone, and readability "
            "while preserving the user's intent."
        )  # instruction that shapes the writing behavior

        return [
            {"role": "system", "content": system},  # background instruction
            {"role": "user", "content": prompt},    # actual task
        ]
