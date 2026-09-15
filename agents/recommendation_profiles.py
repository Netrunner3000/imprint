"""Discover the requirement profile owned by each independent agent package."""

from __future__ import annotations

from importlib import import_module

from services.recommendations.models import AgentProfile


def profile_for(agent_key: str) -> AgentProfile:
    module = import_module(f"agents.{agent_key}.recommendations")
    profile = module.RECOMMENDATION_PROFILE
    if not isinstance(profile, AgentProfile):
        raise TypeError(f"agents.{agent_key}.recommendations must export AgentProfile")
    return profile
