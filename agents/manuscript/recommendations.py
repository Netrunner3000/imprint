from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "manuscript", "Publishing Manager", ("analysis", "structured", "planning"),
    reliability_weight=.27, cost_weight=.20,
    provider_affinity={"openai": .94, "anthropic": .92, "deepseek": .90,
                       "gemini": .88, "qwen": .84, "kimi": .83},
)
