from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "webdesign", "Site Builder", ("code", "structured", "analysis"),
    quality_weight=.45, reliability_weight=.25,
    provider_affinity={"openai": .98, "anthropic": .96, "kimi": .94,
                       "deepseek": .92, "qwen": .88, "gemini": .86, "ollama": .70},
)
