"""Recommendation policy tests: constraints first, preferences second."""

from agents.recommendation_profiles import profile_for
from services.recommendations import (
    AgentProfile, Candidate, RecommendationContext, RecommendationEngine,
)


def candidate(provider, model, **overrides):
    values = dict(
        provider=provider, model_id=model, label=model,
        task_fit={"general": .8, "code": .8},
        quality=.75, reliability=.75, cost_efficiency=.75,
        speed=.75, context=.75,
    )
    values.update(overrides)
    return Candidate(**values)


def test_best_model_is_scoped_to_selected_provider():
    engine = RecommendationEngine()
    profile = AgentProfile("test", "Test", ("general",))
    choices = [
        candidate("alpha", "alpha-good", quality=.95),
        candidate("beta", "beta-fast", quality=.65, speed=.90),
        candidate("beta", "beta-best", quality=.90),
    ]
    result = engine.recommend(
        profile, choices,
        RecommendationContext(agent="test", selected_provider="beta"),
    )
    assert result.candidate.model_id == "beta-best"


def test_configured_availability_is_a_hard_filter():
    engine = RecommendationEngine()
    profile = AgentProfile("test", "Test", ("general",))
    result = engine.recommend(profile, [
        candidate("offline", "spectacular", quality=1.0, available=False),
        candidate("ready", "solid", quality=.70, available=True),
    ], RecommendationContext(agent="test"))
    assert result.candidate.provider == "ready"
    assert result.fallback is False


def test_no_configured_provider_still_returns_explained_setup_target():
    engine = RecommendationEngine()
    profile = AgentProfile("test", "Test", ("general",))
    result = engine.recommend(profile, [
        candidate("a", "one", quality=.90, available=False),
        candidate("b", "two", quality=.60, available=False),
    ], RecommendationContext(agent="test"))
    assert result.candidate.model_id == "one"
    assert result.fallback is True
    assert "setup target" in result.reason


def test_incompatible_retired_over_budget_media_are_never_ranked():
    engine = RecommendationEngine()
    profile = AgentProfile("video", "Video", ("video",))
    choices = [
        candidate("A", "retired", modality="visual", kind="direct_video",
                  retired=True, aspects=("Vertical",), durations=(8,)),
        candidate("A", "wrong-aspect", modality="visual", kind="direct_video",
                  aspects=("Landscape",), durations=(8,)),
        candidate("A", "too-long", modality="visual", kind="direct_video",
                  aspects=("Vertical",), durations=(4,)),
        candidate("A", "too-expensive", modality="visual", kind="direct_video",
                  aspects=("Vertical",), durations=(8,), estimated_cost=2.0),
        candidate("B", "eligible", modality="visual", kind="direct_video",
                  aspects=("Vertical",), durations=(8,), estimated_cost=.50),
    ]
    result = engine.recommend(
        profile, choices,
        RecommendationContext(agent="video", modality="visual",
                              required_kind="direct_video", aspect="Vertical",
                              duration=8, budget_remaining=1.0),
    )
    assert result.candidate.model_id == "eligible"


def test_each_selectable_agent_owns_a_requirement_profile():
    for key in ("chat", "author", "manuscript", "music", "webdesign",
                "fiverr", "creator", "social", "video", "audiobook",
                "onlyfans"):
        profile = profile_for(key)
        assert profile.key == key
        assert profile.task_tags
