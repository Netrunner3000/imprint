from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "social", "Social Media Campaign Manager", ("social", "marketing", "creative"),
    cost_weight=.21, speed_weight=.19,
    provider_affinity={"openai": .98, "anthropic": .95, "gemini": .94,
                       "qwen": .87, "kimi": .84, "deepseek": .79, "ollama": .68},
)
