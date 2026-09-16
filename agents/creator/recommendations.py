from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "creator", "Brand Creator", ("creative", "marketing", "social"),
    reliability_weight=.23, speed_weight=.14,
    provider_affinity={"anthropic": .98, "openai": .96, "gemini": .91,
                       "qwen": .85, "kimi": .83, "deepseek": .78},
)
