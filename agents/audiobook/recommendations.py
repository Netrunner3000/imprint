from services.recommendations import AgentProfile

RECOMMENDATION_PROFILE = AgentProfile(
    "audiobook", "Audiobooks", ("narration", "longform", "reliability"),
    reliability_weight=.32, quality_weight=.38,
    provider_affinity={"openai": .95},
)
