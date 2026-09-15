from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "music", "Music", ("creative", "planning", "marketing"),
    provider_affinity={"anthropic": .98, "openai": .91, "gemini": .88,
                       "qwen": .83, "kimi": .82, "deepseek": .78, "ollama": .68},
)
