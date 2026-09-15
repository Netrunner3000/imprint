from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "video", "Video", ("video", "creative", "social"),
    quality_weight=.44, reliability_weight=.23, cost_weight=.16,
    provider_affinity={"gemini": .98, "openai": .96, "qwen": .92,
                       "higgsfield": .86, "pexels": .76, "local": .62},
)
