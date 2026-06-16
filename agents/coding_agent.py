class CodingAgent:
    def build_messages(self, prompt: str) -> list[dict]:
        system = (
            "You are a coding assistant. Explain clearly, debug carefully, "
            "and provide practical code when useful."
        )  # instruction for code-related behavior

        return [
            {"role": "system", "content": system},  # coding-specific guidance
            {"role": "user", "content": prompt},    # user request
        ]
