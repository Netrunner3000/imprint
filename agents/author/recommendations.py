from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "author", "Draft", ("creative", "longform", "editing"),
    quality_weight=.48, context_weight=.16, cost_weight=.08,
    provider_affinity={"anthropic": 1.0, "openai": .86, "gemini": .82,
                       "qwen": .82, "kimi": .80, "deepseek": .74, "ollama": .66},
)
