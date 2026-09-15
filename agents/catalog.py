"""Canonical roster for the Imprint umbrella.

This is the only cross-agent index.  An agent owns its implementation and
project documents inside ``agents/<key>/``; the umbrella owns navigation,
shared providers, budgets, persistence and composition between agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class AgentSpec:
    """Stable metadata the umbrella needs without importing agent internals."""

    key: str
    label: str
    workspace: str | None
    description: str
    package: str
    panel: bool = True
    recommendation_profile: str | None = None


AGENT_SPECS = (
    AgentSpec(
        "author", "Draft", "Write",
        "Plan, draft and revise long-form fiction and non-fiction.",
        "agents.author",
        recommendation_profile="agents.author.recommendations",
    ),
    AgentSpec(
        "manuscript", "Publish", "Write",
        "Prepare, export, distribute and measure finished books.",
        "agents.manuscript",
        recommendation_profile="agents.manuscript.recommendations",
    ),
    AgentSpec(
        "audiobook", "Audiobooks", "Audio",
        "Convert books into resumable, production-ready audiobooks.",
        "agents.audiobook",
        recommendation_profile="agents.audiobook.recommendations",
    ),
    AgentSpec(
        "music", "Music", "Audio",
        "Plan releases, distribution, promotion and artist income.",
        "agents.music",
        recommendation_profile="agents.music.recommendations",
    ),
    AgentSpec(
        "video", "Video", "Video",
        "Script, generate, narrate and assemble long-form or vertical video.",
        "agents.video",
        recommendation_profile="agents.video.recommendations",
    ),
    AgentSpec(
        "social", "Social", "Social",
        "Draft, schedule and publish platform-native campaign content.",
        "agents.social",
        recommendation_profile="agents.social.recommendations",
    ),
    AgentSpec(
        "webdesign", "Site Builder", "Web",
        "Create responsive HTML, CSS and JavaScript experiences.",
        "agents.webdesign",
        recommendation_profile="agents.webdesign.recommendations",
    ),
    AgentSpec(
        "fiverr", "Client Gigs", "Gigs",
        "Create client-ready concepts, listings and delivery messages.",
        "agents.fiverr",
        recommendation_profile="agents.fiverr.recommendations",
    ),
    AgentSpec(
        "creator", "Creator", "Creator",
        "Create reusable campaigns, captions and promotional assets.",
        "agents.creator",
        recommendation_profile="agents.creator.recommendations",
    ),
    AgentSpec(
        "onlyfans", "OnlyFans", "OnlyFans",
        "Operate the consent-aware OnlyFans venture and analytics workflow.",
        "agents.onlyfans",
        recommendation_profile="agents.onlyfans.recommendations",
    ),
    AgentSpec(
        "course", "Course Generator", None,
        "Produce packaged courses from the command line.",
        "agents.course", panel=False,
    ),
    AgentSpec(
        "chat", "Studio Assistant", None,
        "General assistant retained as an internal compatibility capability.",
        "agents.chat", panel=False,
        recommendation_profile="agents.chat.recommendations",
    ),
    AgentSpec(
        "router", "Router", None,
        "Internal intent classification for the umbrella runtime.",
        "agents.router", panel=False,
    ),
)

AGENTS_BY_KEY = MappingProxyType({spec.key: spec for spec in AGENT_SPECS})


def workspace_map() -> dict[str, tuple[str, ...]]:
    """Return visible workspaces in catalog order."""
    result: dict[str, list[str]] = {}
    for spec in AGENT_SPECS:
        if spec.workspace is not None:
            result.setdefault(spec.workspace, []).append(spec.key)
    return {workspace: tuple(keys) for workspace, keys in result.items()}


def package_for(key: str) -> str:
    return AGENTS_BY_KEY[key].package
