from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "onlyfans", "OnlyFans", ("social", "marketing", "creative"),
    reliability_weight=.25, speed_weight=.15,
    provider_affinity={"anthropic": .98, "openai": .96, "gemini": .90,
                       "qwen": .84, "kimi": .82, "deepseek": .78},
)
