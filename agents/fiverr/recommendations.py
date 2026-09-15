from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "fiverr", "Client Gigs", ("marketing", "creative", "structured"),
    cost_weight=.22, speed_weight=.16,
    provider_affinity={"openai": .98, "anthropic": .94, "gemini": .90,
                       "qwen": .84, "kimi": .82, "deepseek": .80, "ollama": .68},
)
