"""Discover the requirement profile owned by each independent agent package."""

from __future__ import annotations

from importlib import import_module

from services.recommendations.models import AgentProfile


def profile_for(agent_key: str) -> AgentProfile:
    # The catalog's AgentSpec.recommendation_profile names the module; it
    # used to be metadata nothing read while this function hardcoded the
    # same convention. The catalog wins now, with the convention as the
    # fallback for a spec that leaves it unset.
    from agents.catalog import AGENT_SPECS
    path = next(
        (spec.recommendation_profile for spec in AGENT_SPECS
         if spec.key == agent_key and spec.recommendation_profile),
        None,
    )
    module = import_module(path or f"agents.{agent_key}.recommendations")
    profile = module.RECOMMENDATION_PROFILE
    if not isinstance(profile, AgentProfile):
        raise TypeError(f"agents.{agent_key}.recommendations must export AgentProfile")
    return profile
